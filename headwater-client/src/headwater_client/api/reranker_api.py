from __future__ import annotations

from headwater_client.api.base_api import BaseAPI
from headwater_api.classes import RerankRequest, RerankResponse, RerankerModelInfo


class RerankerAPI(BaseAPI):
    def rerank(self, request: RerankRequest) -> RerankResponse:
        response = self._request("POST", "/reranker/rerank", json_payload=request.model_dump_json())
        return RerankResponse.model_validate_json(response)

    def list_reranker_models(self) -> list[RerankerModelInfo]:
        response = self._request("GET", "/reranker/models")
        return [RerankerModelInfo.model_validate(m) for m in response]
