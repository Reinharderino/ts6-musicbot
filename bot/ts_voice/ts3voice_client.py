"""
TS3VoiceClient: thin Python wrapper around the ts3voice Rust binary.

Architecture:
  ffmpeg -i <track> ... -f s16le -ar 48000 -ac 1 pipe:1
        └─ stdout ──> voice_proc stdin ──> ts3voice (Rust)
                                            └─ Opus UDP ──> TS server

The Rust binary connects to TS as a voice client and blocks reading PCM from
stdin.  We feed it by pointing ffmpeg's stdout at voice_proc.stdin for each
track.  Between tracks, the Rust binary just blocks on stdin (no disconnect).
"""

import asyncio
import logging
import os
import subprocess
from typing import Optional

log = logging.getLogger(__name__)

_BINARY = os.getenv("TS3VOICE_BIN", "/usr/local/bin/ts3voice")


class TS3VoiceClient:
    def __init__(self) -> None:
        self._voice_proc: Optional[subprocess.Popen] = None
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._volume: int = int(os.getenv("AUDIO_VOLUME", "85"))
        self._stderr_task: Optional[asyncio.Task] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(
        self,
        host: str,
        port: int,
        nickname: str,
        channel: str = "",
        server_password: str = "",
    ) -> bool:
        env = {
            **os.environ,
            "TS_SERVER_HOST": host,
            "TS_SERVER_PORT": str(port),
            "TS_BOT_NICKNAME": nickname,
            "TS_CHANNEL": channel,
        }
        if server_password:
            env["TS_SERVER_PASSWORD"] = server_password

        try:
            self._voice_proc = subprocess.Popen(
                [_BINARY],
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            log.error("[ts3voice] Binary not found at %s", _BINARY)
            return False
        except Exception as exc:
            log.error("[ts3voice] Failed to launch binary: %s", exc)
            return False

        # Read stderr lines until "[ts3voice] Connected" or timeout (30s)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 30.0
        connected = False
        while loop.time() < deadline:
            remaining = max(0.5, deadline - loop.time())
            try:
                line = await asyncio.wait_for(
                    loop.run_in_executor(None, self._voice_proc.stderr.readline),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                break
            text = line.decode(errors="replace").strip()
            if text:
                log.info("[ts3voice] %s", text)
            if "Connected" in text:
                connected = True
                break
            if self._voice_proc.poll() is not None:
                log.error("[ts3voice] Process exited before connecting")
                return False

        if not connected:
            log.error("[ts3voice] Timed out waiting for connection")
            self._voice_proc.kill()
            return False

        if self._voice_proc.poll() is not None:
            log.error("[ts3voice] Process exited immediately")
            return False

        self._stderr_task = asyncio.create_task(self._drain_stderr())
        log.info("[ts3voice] Voice client ready")
        return True

    async def stop(self) -> None:
        await self.stop_playback()
        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None
        if self._voice_proc:
            try:
                self._voice_proc.stdin.close()
            except Exception:
                pass
            loop = asyncio.get_running_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, self._voice_proc.wait),
                    timeout=5.0,
                )
            except (asyncio.TimeoutError, Exception):
                self._voice_proc.kill()
            self._voice_proc = None

    # ── Playback ──────────────────────────────────────────────────────────────

    async def play_file(self, path: str) -> None:
        """Start streaming `path` to TS.  Returns immediately; use wait_for_finish()."""
        await self.stop_playback()

        if not self._voice_proc or self._voice_proc.poll() is not None:
            log.warning("[ts3voice] Voice process exited — restarting before playback")
            env = {k: v for k, v in __import__('os').environ.items()}
            restarted = await self.start(
                host=env.get("TS_SERVER_HOST", "localhost"),
                port=int(env.get("TS_SERVER_PORT", "9987")),
                nickname=env.get("TS_BOT_NICKNAME", "ts3voice"),
                channel=env.get("TS_CHANNEL", ""),
                server_password=env.get("TS_SERVER_PASSWORD", ""),
            )
            if not restarted:
                log.error("[ts3voice] Failed to restart voice process")
                return

        vol = self._volume / 100.0
        self._ffmpeg_proc = subprocess.Popen(
            [
                "ffmpeg", "-loglevel", "error",
                "-i", path,
                "-af", f"volume={vol:.2f}",
                "-f", "s16le",
                "-ar", "48000",
                "-ac", "1",
                "pipe:1",
            ],
            stdout=self._voice_proc.stdin,
            stderr=subprocess.DEVNULL,
        )
        log.info("[ts3voice] play_file: %s", path)

    async def stop_playback(self) -> None:
        if self._ffmpeg_proc:
            try:
                self._ffmpeg_proc.terminate()
                loop = asyncio.get_running_loop()
                try:
                    await asyncio.wait_for(
                        loop.run_in_executor(None, self._ffmpeg_proc.wait),
                        timeout=3.0,
                    )
                except asyncio.TimeoutError:
                    self._ffmpeg_proc.kill()
            except Exception:
                pass
            self._ffmpeg_proc = None

    async def wait_for_finish(self, timeout: Optional[float] = None) -> None:
        if not self._ffmpeg_proc:
            return
        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._ffmpeg_proc.wait),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            log.warning("[ts3voice] wait_for_finish timed out after %.0fs", timeout)
            await self.stop_playback()
            return
        except Exception:
            pass
        # Brief pause so the Rust binary can flush the last frames to the server
        await asyncio.sleep(0.3)
        self._ffmpeg_proc = None

    async def set_volume(self, vol: int) -> None:
        self._volume = max(0, min(100, vol))

    # ── Stderr logger ─────────────────────────────────────────────────────────

    async def _drain_stderr(self) -> None:
        loop = asyncio.get_running_loop()
        while self._voice_proc and self._voice_proc.poll() is None:
            try:
                line = await asyncio.wait_for(
                    loop.run_in_executor(None, self._voice_proc.stderr.readline),
                    timeout=5.0,
                )
                if line:
                    log.info("[ts3voice] %s", line.decode(errors="replace").strip())
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
