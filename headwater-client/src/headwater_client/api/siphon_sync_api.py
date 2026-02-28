"""
Client for interacting with the Siphon service.
"""

from headwater_api.classes import EmbedBatchRequest, EmbedBatchResponse, SIPHON_EMBED_MODEL
from headwater_client.api.base_api import BaseAPI
from siphon_api.api.siphon_request import SiphonRequest
from siphon_api.api.siphon_response import SiphonResponse


class SiphonAPI(BaseAPI):
    def process(self, request: SiphonRequest) -> SiphonResponse:
        """
        Process content through the Siphon service and return structured results.
        """
        method = "POST"
        endpoint = "/siphon/process"
        json_payload = request.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        try:
            return SiphonResponse.model_validate_json(response)
        except Exception as e:
            raise ValueError(
                "Response could not be validated as SiphonResponse."
            ) from e

    def embed_batch(
        self,
        uris: list[str],
        model: str = SIPHON_EMBED_MODEL,
        force: bool = False,
    ) -> EmbedBatchResponse:
        """Batch-embed siphon records by URI via /siphon/embed-batch."""
        request = EmbedBatchRequest(uris=uris, model=model, force=force)
        json_payload = request.model_dump_json()
        response = self._request("POST", "/siphon/embed-batch", json_payload=json_payload)
        try:
            return EmbedBatchResponse.model_validate_json(response)
        except Exception as e:
            raise ValueError(
                "Response could not be validated as EmbedBatchResponse."
            ) from e
