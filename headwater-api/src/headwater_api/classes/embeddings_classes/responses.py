from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any


# Embeddings
class EmbeddingsResponse(BaseModel):
    """Response model for embeddings generation"""

    embeddings: list[list[float]] = Field(
        ..., description="List of generated embeddings"
    )


class QuickEmbeddingResponse(BaseModel):
    embedding: list[float] = Field(..., description="Generated embedding for the input")


__all__ = [
    "EmbeddingsResponse",
    "QuickEmbeddingResponse",
]
