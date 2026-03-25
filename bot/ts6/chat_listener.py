"""
Polls GET /1/textmessagereceive for new channel messages.

TS6 WebQuery maintains a server-side message buffer per API session.
Each call consumes pending messages (like TS3 ServerQuery events).
Returns {"body": [...]} where each item has: msg, invokerid, invokername, targetmode.

PLAN B (if textmessagereceive returns 404 at runtime):
  - Poll clientlist every POLL_INTERVAL seconds
  - Detect new clients joining and send welcome; can't receive chat via clientlist
  - Real fallback: parse server log file mounted as Docker volume
"""

import asyncio
import logging
from ts6.webquery import WebQueryClient

log = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 1.5


class ChatListener:
    def __init__(self, client: WebQueryClient, on_message_callback, poll_interval: float = DEFAULT_POLL_INTERVAL):
        self.client = client
        self.on_message = on_message_callback
        self.poll_interval = poll_interval
        self._running = False

    async def start(self):
        self._running = True
        log.info("ChatListener started (polling every %.1fs)", self.poll_interval)
        while self._running:
            try:
                await self._poll()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("Poll error: %s", e)
            await asyncio.sleep(self.poll_interval)

    async def stop(self):
        self._running = False

    async def _poll(self):
        response = await self.client.get_text_messages()
        messages = response.get("body", [])
        if not isinstance(messages, list):
            return
        for msg in messages:
            sender = msg.get("invokername", "unknown")
            text = msg.get("msg", "")
            if text:
                await self.on_message(sender, text)
