"""
AudioPlayer: queue management + playback via TS3 Client SDK.

Audio flow (tendroplayer branch):
  yt-dlp download  →  local file  →  TS3SDKClient._feed_audio_sync
                                      └─ ffmpeg → PCM → SDK OPUS → TS server UDP

No PulseAudio, no Xvfb, no Chromium.
"""

import asyncio
import logging
import os

from audio.resolver import delete_track_file
from ts_voice.ts3voice_client import TS3VoiceClient

log = logging.getLogger(__name__)


class AudioPlayer:
    def __init__(self, voice_client: TS3VoiceClient) -> None:
        self.voice_client = voice_client
        self.queue: list[dict] = []
        self._playing = False
        self.volume = int(os.getenv("AUDIO_VOLUME", "85"))
        self._loop_task: asyncio.Task | None = None
        self._current_track: dict | None = None
        self._skip_flag = False

    async def enqueue(self, track: dict) -> int:
        """Add track to queue. Returns 1-indexed position. Starts loop if idle."""
        self.queue.append(track)
        if not self._playing:
            self._playing = True  # set before task starts to block concurrent enqueues
            self._loop_task = asyncio.create_task(self._play_loop())
        return len(self.queue)

    async def skip(self) -> None:
        self._skip_flag = True
        await self.voice_client.stop_playback()
        log.info("Skipped current track.")

    async def stop(self) -> None:
        self.queue.clear()
        self._skip_flag = True
        await self.voice_client.stop_playback()
        if self._current_track and self._current_track.get("local_path"):
            delete_track_file(self._current_track["local_path"])
        self._playing = False

    async def set_volume(self, vol: int) -> None:
        self.volume = max(0, min(100, vol))
        await self.voice_client.set_volume(self.volume)

    def current_track(self) -> dict | None:
        return self._current_track

    # ── Internal play loop ────────────────────────────────────────────────────

    async def _play_loop(self) -> None:
        try:
            while self.queue:
                track = self.queue.pop(0)
                self._current_track = track
                self._skip_flag = False
                await self._play_track(track)
                if track.get("local_path"):
                    delete_track_file(track["local_path"])
        finally:
            self._current_track = None
            self._playing = False

    async def _play_track(self, track: dict) -> None:
        local_path = track.get("local_path")
        if not local_path:
            log.warning("No local_path for track '%s', skipping.", track.get("title"))
            return

        log.info("Playing via TS3 SDK: %s", track["title"])
        try:
            await self.voice_client.play_file(local_path)
        except Exception as exc:
            log.error("play_file failed: %s", exc)
            return

        timeout = (track.get("duration") or 600) + 30
        await self.voice_client.wait_for_finish(timeout=timeout)
