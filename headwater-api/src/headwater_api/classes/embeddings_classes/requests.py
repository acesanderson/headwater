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
        from headwater_api.classes.embeddings_classes.embedding_models import (
            load_embedding_models,
            get_model_prompt_spec,
        )

        if self.task is not None and self.prompt is not None:
            raise ValueError("Provide 'task' or 'prompt', not both.")

        if self.model not in load_embedding_models():
            return self  # unknown model: let EmbeddingModel.__init__ raise

        spec = get_model_prompt_spec(self.model)

        if spec.prompt_unsupported and (self.task is not None or self.prompt is not None):
            raise ValueError(
                f"Model '{self.model}' does not support prompt-based embedding."
            )

        if spec.prompt_required and self.task is None and self.prompt is None:
            raise ValueError(
                f"Model '{self.model}' requires a 'task' or 'prompt'."
            )

        if self.task is not None:
            if spec.task_map is None or self.task.value not in spec.task_map:
                supported = list(spec.task_map.keys()) if spec.task_map else []
                raise ValueError(
                    f"Model '{self.model}' does not support task '{self.task.value}'. "
                    f"Supported tasks: {supported}"
                )

        if self.prompt is not None and spec.valid_prefixes is not None:
            if not any(self.prompt.startswith(p) for p in spec.valid_prefixes):
                raise ValueError(
                    f"Invalid prompt for model '{self.model}'. "
                    f"Must start with one of: {spec.valid_prefixes}"
                )

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
        from headwater_api.classes.embeddings_classes.embedding_models import (
            load_embedding_models,
            get_model_prompt_spec,
        )

        if self.task is not None and self.prompt is not None:
            raise ValueError("Provide 'task' or 'prompt', not both.")

        if self.model not in load_embedding_models():
            return self

        spec = get_model_prompt_spec(self.model)

        if spec.prompt_unsupported and (self.task is not None or self.prompt is not None):
            raise ValueError(
                f"Model '{self.model}' does not support prompt-based embedding."
            )

        if spec.prompt_required and self.task is None and self.prompt is None:
            raise ValueError(
                f"Model '{self.model}' requires a 'task' or 'prompt'."
            )

        if self.task is not None:
            if spec.task_map is None or self.task.value not in spec.task_map:
                supported = list(spec.task_map.keys()) if spec.task_map else []
                raise ValueError(
                    f"Model '{self.model}' does not support task '{self.task.value}'. "
                    f"Supported tasks: {supported}"
                )

        if self.prompt is not None and spec.valid_prefixes is not None:
            if not any(self.prompt.startswith(p) for p in spec.valid_prefixes):
                raise ValueError(
                    f"Invalid prompt for model '{self.model}'. "
                    f"Must start with one of: {spec.valid_prefixes}"
                )

        return self


# Collection Operations
class GetCollectionRequest(BaseModel):
    collection_name: str = Field(
        ..., description="The name of the collection to retrieve."
    )


class CreateCollectionRequest(BaseModel):
    collection_name: str = Field(
        ..., description="The name of the collection to create."
    )
    embedding_model: str = Field(
        ..., description="The embedding model to use for the collection."
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata for the collection.",
    )


class DeleteCollectionRequest(BaseModel):
    collection_name: str = Field(
        ..., description="The name of the collection to delete."
    )


class QueryCollectionRequest(BaseModel):
    name: str = Field(
        ...,
        description="The name of the collection to query.",
    )
    query: str | None = Field(
        ...,
        description="The query string to search the collection.",
    )
    query_embeddings: list[list[float]] | None = Field(
        ...,
        description="List of query embeddings to search against the collection.",
    )
    k: int = Field(
        default=10,
        description="Number of nearest neighbors to retrieve for each query embedding.",
    )
    n_results: int = Field(
        default=10,
        description="Number of top results to return for each query embedding.",
    )

    @model_validator(mode="after")
    def _exactly_one_query(self):
        has_query = self.query is not None
        has_query_embeddings = self.query_embeddings is not None
        if has_query == has_query_embeddings:
            raise ValueError("Provide exactly one of 'query' or 'query_embeddings'.")
        return self


__all__ = [
    "ChromaBatch",
    "EmbeddingsRequest",
    "QuickEmbeddingRequest",
    "CreateCollectionRequest",
    "DeleteCollectionRequest",
    "QueryCollectionRequest",
]
