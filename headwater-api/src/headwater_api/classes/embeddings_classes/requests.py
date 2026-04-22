from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import Any

from headwater_api.classes.embeddings_classes.task import EmbeddingTask


class ChromaBatch(BaseModel):
    ids: list[str] = Field(
        ..., description="List of unique identifiers for each item in the batch."
    )
    documents: list[str] = Field(
        ..., description="List of documents or text associated with each item."
    )
    embeddings: list[list[float]] | None = Field(
        default=None, description="List of embeddings corresponding to each item."
    )
    metadatas: list[dict[str, Any]] | None = Field(
        default=None, description="List of metadata dictionaries for each item."
    )


class EmbeddingsRequest(BaseModel):
    model: str = Field(
        ...,
        description="The embedding model to use for generating embeddings.",
    )
    batch: ChromaBatch = Field(
        ...,
        description="Batch of documents to generate embeddings for.",
    )
    task: EmbeddingTask | None = Field(
        default=None,
        description=(
            "Model-agnostic task type. Resolved server-side to the model-specific "
            "prompt string. Mutually exclusive with 'prompt'."
        ),
    )
    prompt: str | None = Field(
        default=None,
        description=(
            "Raw prompt string prepended to each document via SentenceTransformers "
            "encode(prompt=...). Mutually exclusive with 'task'."
        ),
    )

    @model_validator(mode="after")
    def _validate_prompt_fields(self) -> EmbeddingsRequest:
        if self.task is not None and self.prompt is not None:
            raise ValueError("Provide 'task' or 'prompt', not both.")
        return self


class QuickEmbeddingRequest(BaseModel):
    query: str = Field(
        ...,
        description="The text query to generate an embedding for.",
    )
    model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="The embedding model to use for generating embeddings.",
    )
    task: EmbeddingTask | None = Field(
        default=None,
        description=(
            "Model-agnostic task type. Resolved server-side to the model-specific "
            "prompt string. Mutually exclusive with 'prompt'."
        ),
    )
    prompt: str | None = Field(
        default=None,
        description=(
            "Raw prompt string prepended to each document via SentenceTransformers "
            "encode(prompt=...). Mutually exclusive with 'task'."
        ),
    )

    @model_validator(mode="after")
    def _validate_prompt_fields(self) -> QuickEmbeddingRequest:
        if self.task is not None and self.prompt is not None:
            raise ValueError("Provide 'task' or 'prompt', not both.")
        return self


__all__ = [
    "ChromaBatch",
    "EmbeddingsRequest",
    "QuickEmbeddingRequest",
]
