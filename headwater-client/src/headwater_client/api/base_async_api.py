"""
Base class for all async API classes.
Handles the async transport dependency injection.
"""

from headwater_client.transport.headwater_async_transport import HeadwaterAsyncTransport


class BaseAsyncAPI:
    def __init__(self, transport: HeadwaterAsyncTransport):
        self._transport = transport

    async def _request(
        self, method: str, endpoint: str, json_payload: str | None = None
    ) -> str:
        """
        Internal method to send requests via the async transport layer.
        Flattens the interface for subclasses while still allowing for composition.
        """
        if method.upper() == "GET":
            return await self._transport._request(method, endpoint)
        elif method.upper() in ["POST", "PUT", "DELETE", "PATCH"]:
            return await self._transport._request(method, endpoint, json_payload=json_payload)