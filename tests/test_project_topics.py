"""Project folders mirror forum topics: new folder → topic, removed folder → no topic."""

import json
from pathlib import Path
from types import SimpleNamespace

from telegram_bot.core.config import Settings
from telegram_bot.core.handlers.forum_topic import sync_project_topics


class FakeBot:
    def __init__(self) -> None:
        self.created: list[tuple[int, str]] = []
        self.deleted: list[int] = []

    async def create_forum_topic(self, chat_id: int, name: str) -> SimpleNamespace:
        self.created.append((chat_id, name))
        return SimpleNamespace(message_thread_id=100 + len(self.created))

    async def delete_forum_topic(self, chat_id: int, message_thread_id: int) -> None:
        self.deleted.append(message_thread_id)

    async def send_message(self, **kwargs: object) -> None:
        pass


def _setup(tmp_path: Path, topics: dict[str, dict[str, object]]) -> tuple[Path, Path, Settings]:
    projects = tmp_path / "DEV"
    projects.mkdir()
    config_path = tmp_path / "topic_config.json"
    config_path.write_text(json.dumps({"project_topics_ignore": ["skip"], "topics": topics}))
    settings = Settings(
        _env_file=None,
        telegram_bot_token="t",
        topic_config_path=str(config_path),
        notification_chat_id=-100,
        project_topics_dir=str(projects),
    )
    return projects, config_path, settings


async def test_sync_creates_topics_for_new_folders_only(tmp_path: Path) -> None:
    dev = str(tmp_path / "DEV")
    projects, config_path, settings = _setup(tmp_path, {"5": {"name": "old", "cwd": f"{dev}/old"}})
    for name in ("old", "new", "skip", "#recycle", "@eaDir", ".git"):
        (projects / name).mkdir()
    (projects / "file.txt").write_text("")
    bot = FakeBot()

    assert await sync_project_topics(bot, settings) == 1  # type: ignore[arg-type]
    assert await sync_project_topics(bot, settings) == 0  # type: ignore[arg-type]

    assert bot.created == [(-100, "new")]
    assert bot.deleted == []
    topics = json.loads(config_path.read_text())["topics"]
    assert topics["101"] == {**topics["101"], "name": "new", "cwd": f"{dev}/new"}
    assert topics["5"]["cwd"] == f"{dev}/old"


async def test_sync_deletes_topic_of_removed_folder(tmp_path: Path) -> None:
    dev = str(tmp_path / "DEV")
    projects, config_path, settings = _setup(
        tmp_path,
        {
            "5": {"name": "kept", "cwd": f"{dev}/kept"},
            "6": {"name": "gone", "cwd": f"{dev}/gone"},
            "7": {"name": "elsewhere", "cwd": "/somewhere/else"},  # not under root
            "8": {"name": "manual", "cwd": None},
            "9": {"name": "skip", "cwd": f"{dev}/skip"},  # ignored but still exists
        },
    )
    (projects / "kept").mkdir()
    (projects / "skip").mkdir()
    bot = FakeBot()

    await sync_project_topics(bot, settings)  # type: ignore[arg-type]

    assert bot.deleted == [6]
    assert sorted(json.loads(config_path.read_text())["topics"]) == ["5", "7", "8", "9"]


async def test_sync_never_deletes_when_share_looks_unmounted(tmp_path: Path) -> None:
    dev = str(tmp_path / "DEV")
    topics = {str(i): {"name": f"p{i}", "cwd": f"{dev}/p{i}"} for i in range(5)}
    projects, config_path, settings = _setup(tmp_path, topics)
    bot = FakeBot()

    await sync_project_topics(bot, settings)  # type: ignore[arg-type]  # empty root
    (projects / "p0").mkdir()
    await sync_project_topics(bot, settings)  # type: ignore[arg-type]  # 4 vanished at once

    assert bot.deleted == []
    assert len(json.loads(config_path.read_text())["topics"]) == 5
