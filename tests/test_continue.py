"""/continue: recent exchanges of a transcript; VS Code Codex sessions are listed."""

import json
from pathlib import Path

from telegram_bot.core.services.resume_listing import get_recent_exchanges, list_sessions


def _jsonl(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def _claude(role: str, *content: dict[str, object], **extra: object) -> dict[str, object]:
    return {"type": role, "message": {"role": role, "content": list(content)}, **extra}


def _text(text: str) -> dict[str, object]:
    return {"type": "text", "text": text}


def test_claude_exchanges_skip_tools_context_and_sidechains(tmp_path: Path) -> None:
    path = _jsonl(
        tmp_path / "s.jsonl",
        [
            _claude("user", _text("first")),
            _claude("assistant", _text("answer 1")),
            _claude("user", _text("<ide_selection>code</ide_selection>"), _text("second")),
            _claude("assistant", _text("let me look")),
            _claude("assistant", {"type": "tool_use", "name": "Bash", "input": {}}),
            _claude("user", {"type": "tool_result", "content": "out"}),
            _claude("user", _text("sub prompt"), isSidechain=True),
            _claude("assistant", {"type": "thinking", "thinking": "hm"}),
            _claude("assistant", _text("answer 2")),
            _claude("user", _text("<command-name>/clear</command-name>")),
            _claude("user", _text("third, still running")),
        ],
    )

    assert get_recent_exchanges("claude", path) == [
        ("first", "answer 1"),
        ("second", "answer 2"),
        ("third, still running", ""),
    ]
    assert get_recent_exchanges("claude", path, limit=1) == [("third, still running", "")]


def test_codex_vscode_session_is_listed_with_exchanges(tmp_path: Path) -> None:
    sid = "01a0d3ea-a56f-7b22-b4d8-ab3f2ce92b96"
    path = _jsonl(
        tmp_path / ".codex" / "sessions" / "2026" / "09" / "25" / f"rollout-x-{sid}.jsonl",
        [
            {
                "type": "session_meta",
                "payload": {"id": sid, "cwd": "/projects/p", "originator": "codex_vscode"},
            },
            {"type": "event_msg", "payload": {"type": "user_message", "message": "do it"}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "on it"}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "done"}},
        ],
    )

    [entry] = list_sessions("/projects/p", home=tmp_path)
    assert (entry.provider, entry.session_id) == ("codex", sid)
    assert get_recent_exchanges("codex", path) == [("do it", "done")]
