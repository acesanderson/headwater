from __future__ import annotations
from headwater_api.classes import RerankRequest, RerankResponse


async def reranker_service(request: RerankRequest) -> RerankResponse:
    from headwater_server.services.reranker_service.rerank import run_rerank
    return await run_rerank(request)
