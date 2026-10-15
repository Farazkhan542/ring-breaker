"""Thin A2A client: sends one structured question to a bank agent over HTTP JSON-RPC and returns its data answer."""
import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_data_parts, new_data_message
from a2a.types import Role, SendMessageRequest


class A2APeers:
    """Caches one A2A client per bank (agent card is fetched once from /.well-known/agent-card.json)."""

    def __init__(self, base_url: str, banks: list[str], timeout: float = 20.0):
        self.urls = {b: f"{base_url}/a2a/{b.lower()}" for b in banks}
        self._http = httpx.AsyncClient(timeout=timeout)
        self._clients = {}

    async def _client(self, bank: str):
        if bank not in self._clients:
            cfg = ClientConfig(streaming=False, httpx_client=self._http)
            self._clients[bank] = await create_client(self.urls[bank], client_config=cfg)
        return self._clients[bank]

    async def ask(self, bank: str, question: dict) -> dict:
        client = await self._client(bank)
        msg = new_data_message(question, role=Role.ROLE_USER)
        async for event in client.send_message(SendMessageRequest(message=msg)):
            if event.HasField("message"):
                data = get_data_parts(event.message.parts)
                return data[0] if data else {}
            if event.HasField("task") and event.task.status.HasField("message"):
                data = get_data_parts(event.task.status.message.parts)
                return data[0] if data else {}
        return {}

    async def close(self):
        await self._http.aclose()
