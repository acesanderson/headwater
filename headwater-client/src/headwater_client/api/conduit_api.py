"""
Client for interacting with the Conduit service.
"""

from headwater_client.api.base_api import BaseAPI
from headwater_api.classes import (
    GenerationRequest,
    GenerationResponse,
    BatchRequest,
    BatchResponse,
    TokenizationRequest,
    TokenizationResponse,
)


class ConduitAPI(BaseAPI):
    def query_sync(self, request: GenerationRequest) -> GenerationResponse:
        """Send a synchronous query to the server"""
        method = "POST"
        endpoint = "/conduit/sync"
        json_payload = request.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        return GenerationResponse.model_validate_json(response)

    def query_async(self, batch: BatchRequest) -> BatchResponse:
        """Send an asynchronous batch query to the server"""
        method = "POST"
        endpoint = "/conduit/async"
        json_payload = batch.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        return BatchResponse.model_validate_json(response)

    def tokenize(self, request: TokenizationRequest) -> TokenizationResponse:
        """Tokenize text using the Conduit service"""
        method = "POST"
        endpoint = "/conduit/tokenize"
        json_payload = request.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        return TokenizationResponse.model_validate_json(response)
