"""
Chat command dispatcher.

Commands (channel chat only):
  !play <query|URL>   Enqueue track and start playback
  !skip               Skip current track
  !stop               Clear queue and stop playback
  !queue              Show queued tracks (first 10)
  !np                 Now playing
  !vol <0-100>        Set volume
  !help               List commands
"""

import logging
from audio.player import AudioPlayer
from audio.resolver import resolve
from ts6.webquery import WebQueryClient

log = logging.getLogger(__name__)

BOT_NICKNAME: str | None = None


class CommandParser:
    def __init__(self, player: AudioPlayer, ts_client: WebQueryClient):
        self.player = player
        self.ts = ts_client

    async def handle(self, sender: str, message: str) -> None:
        if not message.startswith("!"):
            return
        if sender == BOT_NICKNAME:
            return

        parts = message.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "!play": self._cmd_play,
            "!skip": self._cmd_skip,
            "!stop": self._cmd_stop,
            "!queue": self._cmd_queue,
            "!np": self._cmd_np,
            "!vol": self._cmd_vol,
            "!help": self._cmd_help,
        }

        handler = handlers.get(cmd)
        if handler:
            await handler(sender, args)

    async def _cmd_play(self, sender: str, args: str) -> None:
        if not args:
            await self.ts.send_channel_message("Uso: !play <busqueda o URL>")
            return
        await self.ts.send_channel_message(f"Buscando: {args}...")
        try:
            track = await resolve(args)
            pos = await self.player.enqueue(track)
            mins, secs = divmod(track["duration"], 60)
            await self.ts.send_channel_message(
                f"[{pos}] {track['title']} ({mins}:{secs:02d}) - pedido por {sender}"
            )
        except Exception as e:
            await self.ts.send_channel_message(f"No encontre nada: {e}")

    async def _cmd_skip(self, sender: str, _: str) -> None:
        await self.player.skip()
        await self.ts.send_channel_message(f"{sender} salto el track.")

    async def _cmd_stop(self, sender: str, _: str) -> None:
        await self.player.stop()
        await self.ts.send_channel_message(f"{sender} detuvo la reproduccion.")

    async def _cmd_queue(self, sender: str, _: str) -> None:
        if not self.player.queue:
            await self.ts.send_channel_message("La cola esta vacia.")
            return
        lines = [f"{i+1}. {t['title']}" for i, t in enumerate(self.player.queue[:10])]
        await self.ts.send_channel_message("Cola:\n" + "\n".join(lines))

    async def _cmd_np(self, sender: str, _: str) -> None:
        track = self.player.current_track()
        if track:
            mins, secs = divmod(track["duration"], 60)
            await self.ts.send_channel_message(
                f"Reproduciendo: {track['title']} ({mins}:{secs:02d})"
            )
        else:
            await self.ts.send_channel_message("No hay nada reproduciendose.")

    async def _cmd_vol(self, sender: str, args: str) -> None:
        try:
            vol = int(args)
            await self.player.set_volume(vol)
            await self.ts.send_channel_message(f"Volumen: {vol}%")
        except ValueError:
            await self.ts.send_channel_message("Uso: !vol <0-100>")

    async def _cmd_help(self, sender: str, _: str) -> None:
        await self.ts.send_channel_message(
            "Comandos: !play <query> | !skip | !stop | !queue | !np | !vol <n> | !help"
        )
