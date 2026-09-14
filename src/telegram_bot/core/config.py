"""Core configuration loading from environment variables.

Core settings cover generic bot functionality: token, auth, Claude Code,
voice transcription, sessions, tmux, and topics. Downstream projects can layer
their own settings on top of these generic core settings.
"""

import functools
from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from pydantic_settings.sources.utils import parse_env_vars

from telegram_bot.core.env_file import read_exact_env_file

# Voice message size cap enforced at every ingestion point (incoming
# voice, forwarded voice, media-content router). Telegram itself caps
# voice files, but an up-front byte check avoids a pointless download
# when a relay or future bot API change lets a large payload through.
MAX_VOICE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


class _ExactDotEnvSettingsSource(DotEnvSettingsSource):
    """Dotenv source that treats credentials as opaque values."""

    def _read_env_file(self, file_path: Path) -> dict[str, str | None]:
        return dict(
            parse_env_vars(
                read_exact_env_file(file_path),
                case_sensitive=self.case_sensitive,
                ignore_empty=self.env_ignore_empty,
                parse_none_str=self.env_parse_none_str,
            )
        )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str
    allowed_user_ids: list[int] = []
    bot_lang: str = "en"
    # Directory where handlers download media before forwarding to CC.
    # Core-owned generic bot feature. Override via `FILE_CACHE_DIR` in .env.
    file_cache_dir: str = "/tmp/telegram-bot-cache"
    # ``project_root`` remains the legacy workspace root. Deployments that
    # separate immutable application code from live data set ``app_root`` and
    # ``agent_workspace_root`` explicitly; empty values preserve the historical
    # single-checkout layout used by the reusable public bot.
    project_root: str = "."
    app_root: str = ""
    agent_workspace_root: str = ""
    projects_base_dir: str = ""
    default_cwd: str = "."
    session_timeout_sec: int = 86400
    session_cleanup_interval_sec: int = 300
    cc_query_timeout_sec: int = 21600
    deepgram_api_key: str = ""
    # Local OpenAI-compatible STT server (e.g. speaches). When set, voice messages
    # go there instead of Deepgram; ``stt_model`` is the ``model`` form field.
    stt_url: str = ""
    stt_model: str = "deepdml/faster-whisper-large-v3-turbo-ct2"
    cc_wait_timeout_sec: int = 10
    cc_inactivity_kill_sec: float = 3600
    cc_agent_progress_throttle_sec: float = 10
    cc_max_turns: int = 100
    session_mapping_path: str = "./session_mapping.json"
    channel_sessions_path: str = ""
    session_mapping_max_size: int = 5000  # each interaction records multiple response chunks
    shutdown_timeout_sec: int = 7  # Gives the service manager time to stop cleanly.
    topic_config_path: str = "./topic_config.json"
    notification_chat_id: int | None = None
    tmux_sessions_dir: str = "./tmux_sessions"
    codex_update_timeout_sec: float = 180
    codex_update_cooldown_sec: float = 86400
    codex_auto_update_enabled: bool = True

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Keep normal precedence while disabling dotenv interpolation."""
        dotenv = _ExactDotEnvSettingsSource(
            settings_cls,
            env_file=getattr(dotenv_settings, "env_file", None),
            env_file_encoding=getattr(dotenv_settings, "env_file_encoding", "utf-8"),
        )
        return init_settings, env_settings, dotenv, file_secret_settings

    @property
    def app_root_path(self) -> Path:
        """Directory containing production code, dependencies, and app config."""
        return Path(self.app_root or self.project_root)

    @property
    def workspace_root_path(self) -> Path:
        """Directory containing editable projects and live runtime data."""
        return Path(self.agent_workspace_root or self.project_root)

    @property
    def projects_base_path(self) -> Path:
        """Parent directory for agent project working directories."""
        if self.projects_base_dir:
            return Path(self.projects_base_dir)
        return self.workspace_root_path.parent

    @property
    def mcp_profiles_path(self) -> Path:
        """Use tracked compatibility profiles or generated production profiles."""
        if self.app_root_path == self.workspace_root_path:
            return self.app_root_path / "mcp-configs"
        return self.app_root_path / ".mcp.production"

    def resolve_app_path(self, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.app_root_path / path

    def resolve_workspace_path(self, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.workspace_root_path / path


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
