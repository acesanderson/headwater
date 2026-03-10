from __future__ import annotations

from headwater_client.api.base_async_api import BaseAsyncAPI
from headwater_api.classes import RerankRequest, RerankResponse, RerankerModelInfo


class RerankerAsyncAPI(BaseAsyncAPI):
    async def rerank(self, request: RerankRequest) -> RerankResponse:
        response = await self._request("POST", "/reranker/rerank", json_payload=request.model_dump_json())
        return RerankResponse.model_validate_json(response)

    async def list_reranker_models(self) -> list[RerankerModelInfo]:
        import json
        response = await self._request("GET", "/reranker/models")
        return [RerankerModelInfo.model_validate(m) for m in json.loads(response)]
