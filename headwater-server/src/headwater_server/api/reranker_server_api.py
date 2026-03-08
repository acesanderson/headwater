from __future__ import annotations
from fastapi import FastAPI
from headwater_api.classes import RerankRequest, RerankResponse, RerankerModelInfo


class RerankerServerAPI:
    def __init__(self, app: FastAPI):
        self.app: FastAPI = app

    def register_routes(self):
        @self.app.post("/reranker/rerank", response_model=RerankResponse)
        async def rerank(request: RerankRequest):
            from headwater_server.services.reranker_service.reranker_service import (
                reranker_service,
            )
            return await reranker_service(request)

        @self.app.get("/reranker/models", response_model=list[RerankerModelInfo])
        async def list_reranker_models():
            from headwater_server.services.reranker_service.list_reranker_models_service import (
                list_reranker_models_service,
            )
            return await list_reranker_models_service()
