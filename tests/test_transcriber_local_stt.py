"""Local STT backend: request shape, response parsing, error mapping."""

from __future__ import annotations

import pytest
from aiohttp import web

from telegram_bot.core.services.transcriber import Transcriber, TranscriptionError


class _Settings:
    deepgram_api_key = ""
    stt_model = "test-model"

    def __init__(self, url: str) -> None:
        self.stt_url = url


@pytest.mark.asyncio
async def test_local_stt_roundtrip_and_errors() -> None:
    seen: dict[str, str] = {}

    async def ok(request: web.Request) -> web.Response:
        form = await request.post()
        seen["model"] = str(form["model"])
        seen["language"] = str(form["language"])
        seen["filename"] = form["file"].filename
        seen["bytes"] = form["file"].file.read()
        return web.json_response({"text": "  привет мир "})

    async def boom(request: web.Request) -> web.Response:
        return web.Response(status=500, text="model exploded")

    app = web.Application()
    app.router.add_post("/v1/audio/transcriptions", ok)
    app.router.add_post("/broken/v1/audio/transcriptions", boom)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    try:
        base = f"http://127.0.0.1:{port}"
        text = await Transcriber(_Settings(base + "/")).transcribe(b"OggS...")
        assert text == "привет мир"
        assert seen == {
            "model": "test-model",
            "language": "ru",
            "filename": "voice.ogg",
            "bytes": b"OggS...",
        }

        with pytest.raises(TranscriptionError, match="HTTP 500"):
            await Transcriber(_Settings(base + "/broken")).transcribe(b"x")

        with pytest.raises(TranscriptionError, match="Local STT error"):
            await Transcriber(_Settings("http://127.0.0.1:1")).transcribe(b"x")
    finally:
        await runner.cleanup()


def test_disabled_without_backend() -> None:
    t = Transcriber(_Settings(""))
    assert t._enabled is False
