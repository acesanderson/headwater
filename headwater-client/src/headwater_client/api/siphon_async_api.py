"""
Async client for interacting with the Siphon service.
"""

from headwater_client.api.base_async_api import BaseAsyncAPI
from siphon_api.api.siphon_request import SiphonRequest
from siphon_api.api.siphon_response import SiphonResponse


class SiphonAsyncAPI(BaseAsyncAPI):
    async def process(self, request: SiphonRequest) -> SiphonResponse:
        """
        Process content through the Siphon service and return structured results.
        """
        method = "POST"
        endpoint = "/siphon/process"
        json_payload = request.model_dump_json()
        response = await self._request(method, endpoint, json_payload=json_payload)
        try:
            return SiphonResponse.model_validate_json(response)
        except Exception as e:
            raise ValueError(
                "Response could not be validated as SiphonResponse."
            ) from e