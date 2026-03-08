from __future__ import annotations
from pydantic import BaseModel
from headwater_api.classes.reranker_classes.requests import RerankDocument


class RerankResult(BaseModel):
    document: RerankDocument
    index: int
    score: float


class RerankResponse(BaseModel):
    results: list[RerankResult]
    model_name: str


class RerankerModelInfo(BaseModel):
    name: str
    output_type: str
