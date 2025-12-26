"""
Async client for interacting with the Curator service.
"""

from headwater_client.api.base_async_api import BaseAsyncAPI
from headwater_api.classes import (
    CuratorRequest,
    CuratorResponse,
)


class CuratorAsyncAPI(BaseAsyncAPI):
    async def curate(self, request: CuratorRequest) -> CuratorResponse:
        """
        Curate items using the server.
        """
        method = "POST"
        endpoint = "/curator/curate"
        response_json = request.model_dump_json()
        response = await self._request(method, endpoint, json_payload=response_json)
        return CuratorResponse.model_validate_json(response)