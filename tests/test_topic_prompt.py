"""topic_config.json `prompt`: none by default, top-level default, per-topic override."""

import json
from pathlib import Path

from telegram_bot.core.services.claude import SessionManager
from telegram_bot.core.services.topic_config import TopicConfig


def _config(tmp_path: Path, raw: dict[str, object]) -> TopicConfig:
    path = tmp_path / "topic_config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return TopicConfig(str(path), ".")


def test_no_prompt_by_default(tmp_path: Path) -> None:
    config = _config(tmp_path, {"topics": {"1": {"name": "a"}}})
    assert config.get_topic(1).prompt == ""
    assert config.get_topic(None).prompt == ""


def test_default_and_override(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        {
            "prompt": "global",
            "topics": {"1": {}, "2": {"prompt": "own"}, "3": {"prompt": ""}, "4": {"prompt": 5}},
        },
    )
    assert config.get_topic(1).prompt == "global"
    assert config.get_topic(2).prompt == "own"
    assert config.get_topic(3).prompt == ""  # explicit "" switches the default off
    assert config.get_topic(4).prompt == "global"  # invalid → default
    assert config.get_topic(99).prompt == "global"  # unknown topic
    assert config.get_topic(None).prompt == "global"  # private chat


def test_prompt_prepended_only_when_set(tmp_path: Path) -> None:
    manager = SessionManager.__new__(SessionManager)
    manager._topic_config = _config(tmp_path, {"topics": {"1": {}, "2": {"prompt": " hi \n"}}})
    assert manager._with_topic_prompt(1, "task") == "task"
    assert manager._with_topic_prompt(2, "task") == "hi\n\ntask"
