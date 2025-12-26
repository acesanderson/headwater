"""
Async client for interacting with the Conduit service.
"""

from headwater_client.api.base_async_api import BaseAsyncAPI
from headwater_api.classes import (
    GenerationRequest,
    GenerationResponse,
    BatchRequest,
    BatchResponse,
    TokenizationRequest,
    TokenizationResponse,
)


class ConduitAsyncAPI(BaseAsyncAPI):
    async def query_generate(self, request: GenerationRequest) -> GenerationResponse:
        """Send a synchronous query to the server"""
        method = "POST"
        endpoint = "/conduit/generate"
        json_payload = request.model_dump_json()
        response = await self._request(method, endpoint, json_payload=json_payload)
        return GenerationResponse.model_validate_json(response)

    async def query_batch(self, batch: BatchRequest) -> BatchResponse:
        """Send an asynchronous batch query to the server"""
        method = "POST"
        endpoint = "/conduit/batch"
        json_payload = batch.model_dump_json()
        response = await self._request(method, endpoint, json_payload=json_payload)
        return BatchResponse.model_validate_json(response)

    async def tokenize(self, request: TokenizationRequest) -> TokenizationResponse:
        """Tokenize text using the Conduit service"""
        method = "POST"
        endpoint = "/conduit/tokenize"
        json_payload = request.model_dump_json()
        response = await self._request(method, endpoint, json_payload=json_payload)
        return TokenizationResponse.model_validate_json(response)