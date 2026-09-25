"""Forum-topic lifecycle handler — auto-registers new topics in topic_config.json.

Telegram fires `forum_topic_created` and `forum_topic_edited` updates whenever
a topic appears or is renamed (regardless of who did it — bot via API, user
via Telegram UI, or another admin). We catch both and keep topic_config.json
in sync, so a freshly created topic immediately works with the bot's default
mode/cwd instead of being an empty room until someone manually edits config.

The reverse direction lives here too: sync_project_topics() creates a topic for
every folder of Settings.project_topics_dir that no topic points at (by cwd) and
deletes the topic of a folder that is gone.

Topic deletion in Telegram is intentionally NOT auto-removed from config — losing the
config entry on accidental deletion would silently strip cwd/mcp settings
the user spent time configuring. Manual cleanup is safer.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
from pathlib import Path
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter
from aiogram.types import Message

from telegram_bot.core.config import Settings
from telegram_bot.core.keyboards import topic_keyboard
from telegram_bot.core.messages import t
from telegram_bot.core.services.claude import DEFAULT_MODE

logger = logging.getLogger(__name__)

router = Router(name="forum_topic")

# aiogram dispatches updates concurrently. Without this lock, two near-simultaneous
# topic events could each read the same on-disk snapshot and overwrite the other's
# write — silently dropping one of the two new topics from the config.
_config_lock = asyncio.Lock()


def _resolve_config_path(settings: Settings) -> Path:
    """Return absolute path to topic_config.json, resolving relative paths against project_root."""
    p = Path(settings.topic_config_path)
    return p if p.is_absolute() else Path(settings.project_root) / p


def _new_entry(name: str) -> dict[str, Any]:
    """Default topic entry — for fresh registration and edited-but-unknown race recovery."""
    return {
        "name": name,
        "type": "project",
        "mode": DEFAULT_MODE,
        "cwd": None,
        "mcp_config": None,
    }


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"topics": {}}
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("topic_config.json is malformed; auto-register skipped")
        raise
    if not isinstance(data, dict):
        logger.warning("topic_config.json top-level is not an object; auto-register skipped")
        raise json.JSONDecodeError("top-level not an object", "", 0)
    data.setdefault("topics", {})
    return data


def _save_config(path: Path, data: dict[str, Any]) -> None:
    """Atomic write via temp file + os.replace — readers see either the old or new file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


@router.message(F.forum_topic_created)
async def on_topic_created(message: Message, settings: Settings, bot: Bot) -> None:
    """Add a new topic to topic_config.json with default mode/cwd, then post a welcome."""
    if message.forum_topic_created is None or message.message_thread_id is None:
        return
    name = message.forum_topic_created.name
    thread_id = message.message_thread_id
    chat_id = message.chat.id
    config_path = _resolve_config_path(settings)

    newly_registered = False
    async with _config_lock:
        try:
            config = _load_config(config_path)
        except json.JSONDecodeError:
            return
        key = str(thread_id)
        if key in config["topics"]:
            # Already registered (e.g. CC pre-registered or restart re-fired event).
            return
        config["topics"][key] = _new_entry(name)
        _save_config(config_path, config)
        newly_registered = True

    logger.info("Auto-registered topic thread_id=%d name=%r", thread_id, name)

    if newly_registered:
        await _send_welcome(bot, chat_id, thread_id)


async def _send_welcome(bot: Bot, chat_id: int, thread_id: int, text: str = "") -> None:
    try:
        await bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id,
            text=text or t("ui.topic_welcome"),
            parse_mode=ParseMode.HTML,
            disable_notification=True,
            reply_markup=topic_keyboard(),
        )
    except TelegramBadRequest:
        logger.warning(
            "Failed to send welcome to thread_id=%d (deleted or perms missing)",
            thread_id,
            exc_info=True,
        )


@router.message(F.forum_topic_edited)
async def on_topic_edited(message: Message, settings: Settings) -> None:
    """Sync the renamed name into topic_config.json (other fields untouched)."""
    if message.forum_topic_edited is None or message.message_thread_id is None:
        return
    new_name = message.forum_topic_edited.name
    if new_name is None:
        # icon-only edit — name didn't change
        return
    thread_id = message.message_thread_id
    config_path = _resolve_config_path(settings)

    async with _config_lock:
        try:
            config = _load_config(config_path)
        except json.JSONDecodeError:
            return
        key = str(thread_id)
        entry = config["topics"].get(key)
        if entry is None:
            # Rename event arrived before our 'created' handler ran — register on the fly.
            config["topics"][key] = _new_entry(new_name)
        else:
            entry["name"] = new_name
        _save_config(config_path, config)

    logger.info("Topic thread_id=%d renamed to %r", thread_id, new_name)


PROJECT_TOPICS_POLL_SEC = 60
# More folders vanishing in one pass looks like an unmounted/half-synced share,
# not a cleanup — deleting a topic wipes its whole history, so skip and warn.
MAX_TOPIC_DELETES_PER_PASS = 3


def _is_project_dir(entry: os.DirEntry[str], ignore: set[str]) -> bool:
    # "#recycle" (Synology bin), "@eaDir" (SMB sidecars), dotfolders are not projects.
    return entry.is_dir() and entry.name[0] not in ".#@" and entry.name not in ignore


async def sync_project_topics(bot: Bot, settings: Settings) -> int:
    """Mirror project folders to forum topics. Returns number of topics created.

    Matching is by cwd, so a topic deleted in Telegram keeps its config entry and
    is NOT recreated; top-level "project_topics_ignore": [names] skips folders.
    A topic whose cwd was a folder of the root that no longer exists is deleted.
    """
    assert settings.notification_chat_id is not None
    root = Path(settings.project_topics_dir)
    config_path = _resolve_config_path(settings)
    try:
        config = _load_config(config_path)
    except json.JSONDecodeError:
        return 0
    known = {e.get("cwd") for e in config["topics"].values() if isinstance(e, dict)}
    ignore = set(config.get("project_topics_ignore", []))
    with os.scandir(root) as it:
        entries = [e for e in it if e.is_dir()]
    existing = {str(root / e.name) for e in entries}
    dirs = [str(root / e.name) for e in entries if _is_project_dir(e, ignore)]
    missing = sorted(d for d in dirs if d not in known)
    if dirs:  # empty root = share not mounted, never a reason to delete
        await _delete_gone_topics(bot, settings, config_path, root, existing)

    created = 0
    for cwd in missing:
        name = Path(cwd).name[:128]  # Telegram limit for topic names
        try:
            topic = await bot.create_forum_topic(settings.notification_chat_id, name)
        except TelegramRetryAfter as e:
            logger.info("Flood control on topic create, next try in %ds", e.retry_after)
            await asyncio.sleep(e.retry_after)
            break  # the rest goes in the next pass
        except TelegramAPIError:
            logger.warning("Failed to create topic for %s", cwd, exc_info=True)
            break  # usually rights/chat problems — same for every folder
        key = str(topic.message_thread_id)
        async with _config_lock:
            try:
                config = _load_config(config_path)
            except json.JSONDecodeError:
                return created
            # on_topic_created may have registered it already, without cwd.
            config["topics"].setdefault(key, _new_entry(name))["cwd"] = cwd
            _save_config(config_path, config)
        created += 1
        logger.info("Created topic thread_id=%s for project %s", key, cwd)
        await _send_welcome(
            bot,
            settings.notification_chat_id,
            topic.message_thread_id,
            t("ui.project_topic_welcome", cwd=html.escape(cwd)),
        )
    return created


async def _delete_gone_topics(
    bot: Bot, settings: Settings, config_path: Path, root: Path, existing: set[str]
) -> None:
    assert settings.notification_chat_id is not None
    async with _config_lock:
        try:
            config = _load_config(config_path)
        except json.JSONDecodeError:
            return
        gone = {
            key: e["cwd"]
            for key, e in config["topics"].items()
            if isinstance(e, dict)
            and isinstance(e.get("cwd"), str)
            and Path(e["cwd"]).parent == root
            and e["cwd"] not in existing
        }
    if len(gone) > MAX_TOPIC_DELETES_PER_PASS:
        logger.warning(
            "%d project folders vanished at once, not deleting their topics: %s",
            len(gone),
            sorted(gone.values()),
        )
        return
    for key, cwd in gone.items():
        try:
            await bot.delete_forum_topic(settings.notification_chat_id, int(key))
        except TelegramBadRequest:
            logger.info("Topic thread_id=%s for %s already gone in Telegram", key, cwd)
        except TelegramAPIError:
            logger.warning("Failed to delete topic for %s", cwd, exc_info=True)
            return
        async with _config_lock:
            try:
                config = _load_config(config_path)
            except json.JSONDecodeError:
                return
            config["topics"].pop(key, None)
            _save_config(config_path, config)
        logger.info("Deleted topic thread_id=%s: project %s is gone", key, cwd)


async def run_project_topics_sync(bot: Bot, settings: Settings) -> None:
    """Startup sync, then poll. ponytail: 60s scandir poll, inotify if a minute is too slow."""
    while True:
        try:
            await sync_project_topics(bot, settings)
        except Exception:
            logger.warning("Project topics sync failed", exc_info=True)
        await asyncio.sleep(PROJECT_TOPICS_POLL_SEC)
