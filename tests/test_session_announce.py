"""First prompt of a user-started session goes silently to its project topic."""

import datetime
import json
from pathlib import Path
from types import SimpleNamespace

from telegram_bot.core.config import Settings
from telegram_bot.core.handlers.session_announce import announce_new_sessions

TODAY = datetime.date(2026, 9, 25)


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> SimpleNamespace:
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=500 + len(self.sent))


class FakeSessions:
    def __init__(self) -> None:
        self.recorded: list[tuple[object, ...]] = []

    def record_message(self, message_id: int, sid: str, key: object, **kw: object) -> None:
        self.recorded.append((message_id, sid, key, kw.get("provider")))


def _claude(home: Path, cwd: str, sid: str, prompt: str, entrypoint: str = "claude-vscode") -> None:
    d = home / ".claude" / "projects" / cwd.replace("/", "-")
    d.mkdir(parents=True, exist_ok=True)
    row = {
        "type": "user",
        "entrypoint": entrypoint,
        "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
    }
    (d / f"{sid}.jsonl").write_text(json.dumps(row) + "\n")


def _codex(home: Path, cwd: str, sid: str, prompt: str, originator: str = "codex_vscode") -> None:
    d = home / ".codex" / "sessions" / TODAY.strftime("%Y/%m/%d")
    d.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "session_meta", "payload": {"id": sid, "cwd": cwd, "originator": originator}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": prompt}},
    ]
    (d / f"rollout-2026-09-25T10-00-00-{sid}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows)
    )


async def test_announces_only_new_user_sessions(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config = tmp_path / "topic_config.json"
    config.write_text(
        json.dumps(
            {
                "topics": {
                    "10": {"name": "a", "cwd": "/DEV/a"},
                    "20": {"name": "work", "cwd": "/DEV/work", "announce": False},
                    "30": {"name": "manual", "cwd": None},
                }
            }
        )
    )
    settings = Settings(
        _env_file=None,
        telegram_bot_token="t",
        topic_config_path=str(config),
        notification_chat_id=-100,
    )
    state = tmp_path / "announced.json"
    bot, sessions = FakeBot(), FakeSessions()

    async def run() -> int:
        return await announce_new_sessions(
            bot,  # type: ignore[arg-type]
            settings,
            sessions,  # type: ignore[arg-type]
            state,
            home=home,
            today=TODAY,
        )

    old = "00000000-0000-0000-0000-000000000001"
    _claude(home, "/DEV/a", old, "old session")
    assert await run() == 0  # first pass = baseline, history is not replayed

    new_claude = "00000000-0000-0000-0000-000000000002"
    new_codex = "00000000-0000-0000-0000-000000000003"
    _claude(home, "/DEV/a", new_claude, "<b>fix</b> the bug")
    _claude(home, "/DEV/a", "00000000-0000-0000-0000-000000000004", "bot", entrypoint="sdk-cli")
    _claude(home, "/DEV/work", "00000000-0000-0000-0000-000000000005", "secret work")
    _codex(home, "/DEV/a", new_codex, "codex task")
    _codex(home, "/DEV/a", "00000000-0000-0000-0000-000000000006", "bot", originator="codex_exec")
    _codex(home, "/elsewhere", "00000000-0000-0000-0000-000000000007", "no topic")

    assert await run() == 2
    assert await run() == 0  # each session is announced once

    assert all(m["message_thread_id"] == 10 and m["disable_notification"] for m in bot.sent)
    texts = "\n".join(str(m["text"]) for m in bot.sent)
    assert "&lt;b&gt;fix&lt;/b&gt; the bug" in texts
    assert "codex task" in texts
    assert "secret work" not in texts and "bot" not in texts.replace("🆕", "")
    assert {(sid, p) for _, sid, _, p in sessions.recorded} == {
        (new_claude, "claude"),
        (new_codex, "codex"),
    }


async def test_topic_added_later_does_not_replay_its_history(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config = tmp_path / "topic_config.json"
    topics: dict[str, dict[str, object]] = {"10": {"name": "a", "cwd": "/DEV/a"}}
    config.write_text(json.dumps({"topics": topics}))
    settings = Settings(
        _env_file=None,
        telegram_bot_token="t",
        topic_config_path=str(config),
        notification_chat_id=-100,
    )
    state = tmp_path / "announced.json"
    bot, sessions = FakeBot(), FakeSessions()

    async def run() -> int:
        return await announce_new_sessions(
            bot,  # type: ignore[arg-type]
            settings,
            sessions,  # type: ignore[arg-type]
            state,
            home=home,
            today=TODAY,
        )

    _claude(home, "/DEV/b", "00000000-0000-0000-0000-000000000011", "old b")
    _codex(home, "/DEV/b", "00000000-0000-0000-0000-000000000012", "old b codex")
    assert await run() == 0
    topics["20"] = {"name": "b", "cwd": "/DEV/b"}
    config.write_text(json.dumps({"topics": topics}))
    assert await run() == 0  # b is new to the announcer: its history is baselined
    _claude(home, "/DEV/b", "00000000-0000-0000-0000-000000000013", "new b")
    assert await run() == 1
    assert [m["message_thread_id"] for m in bot.sent] == [20]
    assert "new b" in str(bot.sent[0]["text"])
