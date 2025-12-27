"""
Async client for interacting with Headwater APIs.
Usage:
```python
from headwater_client.client.headwater_client_async import HeadwaterAsyncClient

# Using context manager (recommended)
async with HeadwaterAsyncClient() as client:
    response = await client.conduit.query_generate(request)
    embeddings = await client.embeddings.generate_embeddings(request)
    curated_courses = await client.curator.curate(request)

# Or manual management
client = HeadwaterAsyncClient()
try:
    response = await client.conduit.query_generate(request)
finally:
    await client.close()
```
"""

from headwater_client.api.conduit_async_api import ConduitAsyncAPI
from headwater_client.api.curator_async_api import CuratorAsyncAPI
from headwater_client.api.embeddings_async_api import EmbeddingsAsyncAPI
from headwater_client.api.siphon_async_api import SiphonAsyncAPI
from headwater_client.transport.headwater_async_transport import HeadwaterAsyncTransport
from headwater_api.classes import StatusResponse


class HeadwaterAsyncClient:
    def __init__(self, base_url: str = ""):
        self._transport = HeadwaterAsyncTransport(base_url)
        self.conduit = ConduitAsyncAPI(self._transport)
        self.curator = CuratorAsyncAPI(self._transport)
        self.embeddings = EmbeddingsAsyncAPI(self._transport)
        self.siphon = SiphonAsyncAPI(self._transport)

    async def __aenter__(self):
        """Async context manager entry"""
        await self._transport.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._transport.__aexit__(exc_type, exc_val, exc_tb)

    async def close(self):
        """Manually close the client"""
        await self._transport.__aexit__(None, None, None)

    async def ping(self) -> bool:
        """Ping the Headwater service to check connectivity."""
        return await self._transport.ping()

    async def get_status(self) -> StatusResponse:
        """Get the status of the Headwater service."""
        return await self._transport.get_status()

    async def list_routes(self) -> dict:
        """List available API routes."""
        return await self._transport.list_routes()

