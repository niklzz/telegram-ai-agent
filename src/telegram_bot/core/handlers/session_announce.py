"""Announce new Claude/Codex sessions of a project in its forum topic.

When a session is started outside the bot (Mac, VS Code, terminal in the box),
its first prompt is posted silently to the topic whose cwd matches. The post
bumps the topic to the top of the list; /continue (or a reply to the post)
then continues that session from the phone.

Only the first prompt goes out — the rest of the conversation stays local.
The bot's own sessions (`claude -p` = entrypoint "sdk-cli", `codex exec`) are
skipped. A topic opts out with `"announce": false` in topic_config.json.
"""

from __future__ import annotations

import asyncio
import datetime
import html
import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from telegram_bot.core.config import Settings
from telegram_bot.core.handlers.forum_topic import _load_config, _resolve_config_path
from telegram_bot.core.services.claude import SessionManager
from telegram_bot.core.services.providers import engine_display_name
from telegram_bot.core.services.resume_listing import (
    _CODEX_ORIGINATORS,
    _exchange_row,
    _iter_jsonl_soft,
)
from telegram_bot.core.tui.paths import cwd_to_slug

logger = logging.getLogger(__name__)

ANNOUNCE_POLL_SEC = 20
_PROMPT_LIMIT = 300


def _first_prompt(provider: str, path: Path) -> str:
    for data in _iter_jsonl_soft(path):
        role, text = _exchange_row(provider, data)  # type: ignore[arg-type]
        if role == "user":
            return text
    return ""


def _claude_is_bot(path: Path) -> bool:
    for data in _iter_jsonl_soft(path):
        if isinstance(data, dict) and "entrypoint" in data:
            return bool(data["entrypoint"] == "sdk-cli")
    return False


def _codex_meta(path: Path) -> tuple[str, str] | None:
    """(session id, cwd) of a user-started Codex rollout, None for the bot's own."""
    for data in _iter_jsonl_soft(path):
        if not isinstance(data, dict) or data.get("type") != "session_meta":
            continue
        payload = data.get("payload")
        if not isinstance(payload, dict) or payload.get("originator") not in _CODEX_ORIGINATORS:
            return None
        sid, cwd = payload.get("id"), payload.get("cwd")
        return (sid, cwd) if isinstance(sid, str) and isinstance(cwd, str) else None
    return None


def _candidates(
    home: Path, topics: dict[str, int], today: datetime.date
) -> Iterator[tuple[str, str, Path, int]]:
    """(provider, session id, transcript, thread id) of every session of a topic's cwd."""
    by_slug = {cwd_to_slug(cwd): thread for cwd, thread in topics.items()}
    projects = home / ".claude" / "projects"
    for slug, thread in by_slug.items():
        try:
            files = [e for e in os.scandir(projects / slug) if e.name.endswith(".jsonl")]
        except OSError:
            continue
        for e in files:
            yield "claude", e.name[: -len(".jsonl")], Path(e.path), thread
    # Rollouts live in YYYY/MM/DD of their start: today + yesterday cover midnight.
    for day in (today - datetime.timedelta(days=1), today):
        day_dir = home / ".codex" / "sessions" / day.strftime("%Y/%m/%d")
        for path in sorted(day_dir.glob("*.jsonl")):
            # Codex ids are the UUID tail of "rollout-<timestamp>-<uuid>.jsonl".
            yield "codex", path.stem[-36:], path, -1


def _load_state(path: Path, cwds: set[str]) -> tuple[set[str], set[str]]:
    """(announced session ids, topic cwds already watched). Missing file = nothing known."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set(), set()
    except (OSError, ValueError):
        logger.warning("Bad %s, starting a new baseline", path, exc_info=True)
        return set(), set()
    if isinstance(raw, list):  # first format: ids only, every current topic was watched
        return set(raw), set(cwds)
    return set(raw.get("sessions", [])), set(raw.get("cwds", []))


def _save_state(path: Path, seen: set[str], cwds: set[str]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = {"sessions": sorted(seen), "cwds": sorted(cwds)}
    tmp.write_text(json.dumps(data) + "\n", encoding="utf-8")
    os.replace(tmp, path)


async def announce_new_sessions(
    bot: Bot,
    settings: Settings,
    session_manager: SessionManager,
    state_path: Path,
    *,
    home: Path | None = None,
    today: datetime.date | None = None,
) -> int:
    """One pass. Returns posts sent.

    A topic seen for the first time (incl. every topic on the very first run) only
    records its existing sessions — history is never replayed into Telegram.
    """
    assert settings.notification_chat_id is not None
    home = home or Path.home()
    today = today or datetime.date.today()
    try:
        config = _load_config(_resolve_config_path(settings))
    except json.JSONDecodeError:
        return 0
    topics: dict[str, int] = {}
    for key, entry in config["topics"].items():
        cwd = entry.get("cwd") if isinstance(entry, dict) else None
        if isinstance(cwd, str) and entry.get("announce", True) and key.isdigit():
            topics[os.path.normpath(cwd)] = int(key)

    seen, watched = _load_state(state_path, set(topics))
    fresh = {thread for cwd, thread in topics.items() if cwd not in watched}
    posts: list[tuple[str, str, int, str]] = []
    for provider, sid, path, thread in _candidates(home, topics, today):
        if sid in seen:
            continue
        if provider == "claude":
            if _claude_is_bot(path):
                seen.add(sid)
                continue
        else:
            meta = _codex_meta(path)
            if meta is None:
                seen.add(sid)
                continue
            sid, cwd = meta
            if sid in seen:
                continue
            found = topics.get(os.path.normpath(cwd))
            if found is None:
                continue  # no topic (yet) — a later one baselines it
            thread = found
        if thread in fresh:
            seen.add(sid)
            continue
        prompt = _first_prompt(provider, path)
        if prompt:  # no prompt yet = session just opened, look again next pass
            posts.append((provider, sid, thread, prompt))

    sent = 0
    for provider, sid, thread, prompt in posts:
        clipped = prompt if len(prompt) <= _PROMPT_LIMIT else prompt[: _PROMPT_LIMIT - 1] + "…"
        text = (
            f"🆕 {engine_display_name(provider)} · <code>{sid[:8]}</code>\n"
            f"<i>{html.escape(clipped)}</i>"
        )
        try:
            msg = await bot.send_message(
                chat_id=settings.notification_chat_id,
                message_thread_id=thread,
                text=text,
                parse_mode="HTML",
                disable_notification=True,
            )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            break  # the rest goes in the next pass
        except TelegramAPIError:
            logger.warning("Failed to announce session %s in thread %d", sid, thread, exc_info=True)
            seen.add(sid)  # deleted topic etc. — do not retry forever
            continue
        seen.add(sid)
        sent += 1
        # Replying to the post continues exactly this session.
        session_manager.record_message(
            msg.message_id, sid, (settings.notification_chat_id, thread), provider=provider
        )
    _save_state(state_path, seen, set(topics))
    return sent


async def run_session_announcer(
    bot: Bot, settings: Settings, session_manager: SessionManager, state_path: Path
) -> None:
    """ponytail: 20s poll over topic cwds; the seen-set grows forever (~KB/month)."""
    while True:
        try:
            await announce_new_sessions(bot, settings, session_manager, state_path)
        except Exception:
            logger.warning("Session announce pass failed", exc_info=True)
        await asyncio.sleep(ANNOUNCE_POLL_SEC)
