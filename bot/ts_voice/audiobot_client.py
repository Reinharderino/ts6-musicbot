"""
HTTP client for TS3AudioBot (https://github.com/Splamy/TS3AudioBot).

TS3AudioBot runs as a sidecar container and handles the TeamSpeak voice
protocol directly — no Chromium, no Xvfb, no PulseAudio.

This module speaks to its REST API to start/stop playback from local files.
API base: http://ts3audiobot:58913  (configurable via AUDIOBOT_URL env var)
"""

import asyncio
import logging
import os

import aiohttp

log = logging.getLogger(__name__)

_BASE = os.getenv("AUDIOBOT_URL", "http://localhost:58913")
_BOT_ID = int(os.getenv("AUDIOBOT_BOT_ID", "0"))

# How often we poll the status endpoint while waiting for a track to finish.
_POLL_INTERVAL = 1.5  # seconds


class AudioBotClient:
    """Async wrapper around the TS3AudioBot REST API."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )

    async def stop(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    # ── Low-level command invoke ─────────────────────────────────────────────

    async def _invoke(self, command: str) -> dict:
        """Send any TS3AudioBot text command via the REST API."""
        url = f"{_BASE}/api/bot/command/invoke/{_BOT_ID}"
        async with self._session.post(url, json={"command": command}) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 400:
                raise RuntimeError(
                    f"AudioBot API error {resp.status}: {data}"
                )
            return data

    async def _status(self) -> dict:
        """Return the current bot status dict."""
        url = f"{_BASE}/api/bot/info/{_BOT_ID}"
        async with self._session.get(url) as resp:
            return await resp.json(content_type=None)

    # ── Playback control ─────────────────────────────────────────────────────

    async def play_file(self, path: str) -> None:
        """Tell TS3AudioBot to play a local file (full absolute path)."""
        await self._invoke(f"play file://{path}")
        log.info("[audiobot] play file://%s", path)

    async def stop_playback(self) -> None:
        """Stop playback immediately."""
        await self._invoke("stop")
        log.info("[audiobot] stop")

    async def set_volume(self, vol: int) -> None:
        """Set volume 0–100."""
        await self._invoke(f"volume set {vol}")

    # ── Playback completion ──────────────────────────────────────────────────

    async def wait_for_finish(self, timeout: float | None = None) -> None:
        """Poll status until TS3AudioBot stops playing, or timeout elapses.

        TS3AudioBot transitions from "Playing" → "Stopped" automatically when
        the file finishes.  We give it a 2 s grace period before we start
        polling so the bot has time to register the new track.
        """
        await asyncio.sleep(2.0)

        deadline = (
            asyncio.get_event_loop().time() + timeout
            if timeout is not None
            else None
        )

        while True:
            try:
                status = await self._status()
                music = status.get("music", {})
                if not music.get("playing", False):
                    break
            except Exception as exc:
                log.warning("[audiobot] status poll failed: %s", exc)
                break

            if deadline is not None and asyncio.get_event_loop().time() >= deadline:
                log.warning("[audiobot] wait_for_finish timed out")
                break

            await asyncio.sleep(_POLL_INTERVAL)

    async def wait_ready(self, attempts: int = 20, delay: float = 3.0) -> bool:
        """Block until the TS3AudioBot API is reachable (used at startup)."""
        for i in range(attempts):
            try:
                await self._status()
                log.info("[audiobot] API ready after %d attempt(s)", i + 1)
                return True
            except Exception:
                await asyncio.sleep(delay)
        log.error("[audiobot] API did not become ready after %d attempts", attempts)
        return False
