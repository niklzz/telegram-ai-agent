"""Voice message transcription: local OpenAI-compatible STT server or Deepgram."""

from __future__ import annotations

import asyncio
import logging

import aiohttp
from deepgram import AsyncDeepgramClient

from telegram_bot.core.config import Settings

logger = logging.getLogger(__name__)

_TRANSCRIPTION_TIMEOUT_SEC = 30
# CPU inference: a one-minute voice note on large-v3-turbo/int8 takes ~15-30 s.
_LOCAL_TRANSCRIPTION_TIMEOUT_SEC = 120


class TranscriptionError(Exception):
    """Raised when transcription fails."""


class Transcriber:
    def __init__(self, settings: Settings) -> None:
        self._stt_url = settings.stt_url.rstrip("/")
        self._stt_model = settings.stt_model
        self._enabled = bool(self._stt_url or settings.deepgram_api_key)
        self._client = (
            AsyncDeepgramClient(api_key=settings.deepgram_api_key)
            if settings.deepgram_api_key and not self._stt_url
            else None
        )

    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio bytes.

        Returns transcript text (may be empty for non-speech audio).
        Raises TranscriptionError on API or network failures or if no backend is configured.
        """
        if not self._enabled:
            raise TranscriptionError("Neither STT_URL nor Deepgram API key configured")
        if self._stt_url:
            return await self._transcribe_local(audio_data)
        return await self._transcribe_deepgram(audio_data)

    async def _transcribe_local(self, audio_data: bytes) -> str:
        """POST /v1/audio/transcriptions (OpenAI shape) on the local STT server."""
        form = aiohttp.FormData()
        form.add_field("file", audio_data, filename="voice.ogg", content_type="audio/ogg")
        form.add_field("model", self._stt_model)
        form.add_field("language", "ru")
        form.add_field("response_format", "json")
        timeout = aiohttp.ClientTimeout(total=_LOCAL_TRANSCRIPTION_TIMEOUT_SEC)
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(f"{self._stt_url}/v1/audio/transcriptions", data=form) as resp,
            ):
                if resp.status != 200:
                    body = (await resp.text())[:200]
                    raise TranscriptionError(f"STT server HTTP {resp.status}: {body}")
                payload = await resp.json(content_type=None)
        except TranscriptionError:
            raise
        except TimeoutError:
            logger.warning("Local STT timed out after %ds", _LOCAL_TRANSCRIPTION_TIMEOUT_SEC)
            raise TranscriptionError("Local STT timed out") from None
        except aiohttp.ClientError as exc:
            logger.warning("Local STT error: %s", exc)
            raise TranscriptionError(f"Local STT error: {exc}") from exc

        transcript = payload.get("text", "") if isinstance(payload, dict) else ""
        transcript = transcript.strip()
        logger.info("Transcription done (local), length=%d chars", len(transcript))
        return transcript

    async def _transcribe_deepgram(self, audio_data: bytes) -> str:
        assert self._client is not None
        try:
            response = await asyncio.wait_for(
                self._client.listen.v1.media.transcribe_file(
                    request=audio_data,
                    model="nova-3",
                    language="ru",
                    smart_format=True,
                ),
                timeout=_TRANSCRIPTION_TIMEOUT_SEC,
            )
        except TimeoutError:
            logger.warning("Deepgram transcription timed out after %ds", _TRANSCRIPTION_TIMEOUT_SEC)
            raise TranscriptionError("Deepgram transcription timed out") from None
        except Exception as exc:
            logger.warning("Deepgram API error: %s", exc)
            raise TranscriptionError(f"Deepgram API error: {exc}") from exc

        channels = response.results.channels
        if not channels or not channels[0].alternatives:
            logger.info("Transcription done, empty response (silence or corrupted audio)")
            return ""

        transcript: str = channels[0].alternatives[0].transcript
        logger.info("Transcription done, length=%d chars", len(transcript))
        return transcript
