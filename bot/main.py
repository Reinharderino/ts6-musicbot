"""
Orchestrator entry point. Wires all modules and runs the async event loop.
"""

import asyncio
import logging
import os
from dotenv import load_dotenv

from ts6.webquery import WebQueryClient
from ts6.chat_listener import ChatListener
from audio.player import AudioPlayer
from commands.parser import CommandParser
from ts_voice.ts3voice_client import TS3VoiceClient
import commands.parser as parser_module

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
log = logging.getLogger("main")


async def main():
    parser_module.BOT_NICKNAME = os.getenv("TS_BOT_NICKNAME", "MusicBot")

    ts_client = WebQueryClient()
    await ts_client.start()

    # ts3voice Rust binary — connects directly to the TS server as a voice client
    voice_client = TS3VoiceClient()
    host = os.getenv("TS_SERVER_HOST", "")
    port = int(os.getenv("TS_SERVER_PORT", "9987"))
    nickname = os.getenv("TS_BOT_NICKNAME", "tendroaudio")
    channel = os.getenv("TS_CHANNEL", "")
    server_password = os.getenv("TS_SERVER_PASSWORD", "")

    log.info("Connecting ts3voice to %s:%d ...", host, port)
    voice_ready = await voice_client.start(host, port, nickname, channel, server_password)
    if not voice_ready:
        log.warning("ts3voice failed to connect — voice playback will not work.")
    else:
        await voice_client.set_volume(int(os.getenv("AUDIO_VOLUME", "85")))

    player = AudioPlayer(voice_client)

    # ChatListener created first so the parser can reference it for !move
    listener = ChatListener(ts_client, None)
    cmd_parser = CommandParser(player, ts_client, listener)

    async def on_message(sender: str, message: str):
        await cmd_parser.handle(sender, message)

    listener.on_message = on_message

    log.info("Bot started. Channel: %s", channel)

    # Move the serverquery session into the target channel
    if channel:
        try:
            ok = await ts_client.join_channel(channel)
            if ok:
                log.info("Query session joined channel: %s", channel)
            else:
                log.warning("Channel not found: %s", channel)
        except Exception as e:
            log.warning("Could not join channel: %s", e)

    try:
        await ts_client.send_channel_message(
            "MusicBot connected. Type !help for commands."
        )
    except Exception as e:
        log.warning("Could not send startup message: %s", e)

    try:
        await listener.start()
    except asyncio.CancelledError:
        log.info("Shutting down...")
    finally:
        await ts_client.stop()
        await voice_client.stop()


if __name__ == "__main__":
    asyncio.run(main())
