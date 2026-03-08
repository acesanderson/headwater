from __future__ import annotations
from headwater_api.classes import RerankerModelInfo
from headwater_server.services.reranker_service.config import list_models


async def list_reranker_models_service() -> list[RerankerModelInfo]:
    return [RerankerModelInfo(**entry) for entry in list_models()]
