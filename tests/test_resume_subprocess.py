"""/resume in a subprocess topic switches the session without tmux."""

from pathlib import Path

from telegram_bot.core.config import Settings
from telegram_bot.core.services.claude import SessionManager


async def test_resume_session_persists_and_beats_clear(tmp_path: Path) -> None:
    """/resume in a subprocess topic: next message and a bot restart both use the picked session."""
    settings = Settings(_env_file=None, telegram_bot_token="t", project_root=str(tmp_path))
    (tmp_path / "session_mapping.json").write_text("{}")  # load_mapping bails out without it
    key = (-100, 7)
    manager = SessionManager(settings)
    manager._fresh_channels.add(manager._ch_key(key))  # as right after /clear

    await manager.resume_session(key, "11111111-2222-3333-4444-555555555555", "codex")

    assert manager.get_current_session_id(key) == "11111111-2222-3333-4444-555555555555"
    assert manager._get_session(key).engine == "codex"
    assert not manager.consume_fresh_start(key)
    restarted = SessionManager(settings)
    restarted.load_mapping()
    assert restarted._get_session(key).session_id == "11111111-2222-3333-4444-555555555555"
    assert restarted._get_session(key).engine == "codex"
