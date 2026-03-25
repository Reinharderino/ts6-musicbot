import aiohttp
import os


class WebQueryClient:
    def __init__(self):
        self.base_url = (
            f"http://{os.getenv('TS_WEBQUERY_HOST', 'localhost')}"
            f":{os.getenv('TS_WEBQUERY_PORT', '10081')}"
        )
        self.api_key = os.getenv("TS_WEBQUERY_APIKEY", "")
        self.vserver = "1"
        self.session: aiohttp.ClientSession | None = None

    async def start(self):
        self.session = aiohttp.ClientSession(
            headers={"X-API-Key": self.api_key}
        )

    async def stop(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def get(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}/{self.vserver}/{endpoint}"
        async with self.session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def post(self, endpoint: str, data: dict | None = None) -> dict:
        url = f"{self.base_url}/{self.vserver}/{endpoint}"
        async with self.session.post(url, json=data) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def send_channel_message(self, message: str) -> None:
        await self.post("sendtextmessage", {"targetmode": 2, "msg": message})

    async def get_clients(self) -> dict:
        return await self.get("clientlist")

    async def get_channels(self) -> dict:
        return await self.get("channellist")

    async def get_text_messages(self) -> dict:
        """Polls for pending text messages. Returns list or empty body on no new messages."""
        return await self.get("textmessagereceive")

    async def move_client(self, client_id: int, channel_id: int) -> dict:
        return await self.post("clientmove", {"clid": client_id, "cid": channel_id})

    async def get_channel_info(self, channel_id: int) -> dict:
        return await self.get("channelinfo", {"cid": channel_id})
