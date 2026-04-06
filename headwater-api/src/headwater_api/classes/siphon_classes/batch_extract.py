from __future__ import annotations

from pydantic import BaseModel


class BatchExtractRequest(BaseModel):
    sources: list[str]
    max_concurrent: int = 10


class ExtractResult(BaseModel):
    source: str
    text: str | None
    error: str | None


class BatchExtractResponse(BaseModel):
    results: list[ExtractResult]
