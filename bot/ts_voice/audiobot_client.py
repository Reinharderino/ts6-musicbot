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
        """Set volume 0–100.  TS3AudioBot uses the same 0–100 range."""
        await self._invoke(f"volume {vol}")

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
                # v0.12.0 uses {"bot": {...}, "music": {"active": bool, ...}}
                music = status.get("music", {})
                if not music.get("active", False):
                    break
            except Exception as exc:
                log.warning("[audiobot] status poll failed: %s", exc)
                break

            if deadline is not None and asyncio.get_event_loop().time() >= deadline:
                log.warning("[audiobot] wait_for_finish timed out")
                break

            await asyncio.sleep(_POLL_INTERVAL)

    async def wait_ready(self, attempts: int = 30, delay: float = 2.0) -> bool:
        """Block until a bot is connected and the API is ready.

        Phase 1: wait for the web API to respond at all.
        Phase 2: wait for bot ID 0 to appear in the bot list
                 (meaning TS3AudioBot successfully connected to the TS server).
        """
        # Phase 1 — API reachable
        for i in range(attempts):
            try:
                url = f"{_BASE}/api/bot/list"
                async with self._session.get(url) as resp:
                    if resp.status < 500:
                        log.info("[audiobot] API up after %d attempt(s)", i + 1)
                        break
            except Exception:
                pass
            await asyncio.sleep(delay)
        else:
            log.error("[audiobot] API never became reachable")
            return False

        # Phase 2 — wait for at least one bot to be connected
        for i in range(attempts):
            try:
                url = f"{_BASE}/api/bot/list"
                async with self._session.get(url) as resp:
                    bots = await resp.json(content_type=None)
                    if isinstance(bots, list) and len(bots) > 0:
                        log.info("[audiobot] Bot connected (attempt %d)", i + 1)
                        return True
            except Exception as exc:
                log.debug("[audiobot] bot list poll: %s", exc)
            await asyncio.sleep(delay)

        log.error("[audiobot] No bot connected after %d attempts", attempts)
        return False
