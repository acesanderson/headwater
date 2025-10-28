from pydantic import BaseModel, Field, model_validator
from typing import Any


# Embeddings
class ChromaBatch(BaseModel):
    # Mandatory fields
    ids: list[str] = Field(
        ..., description="List of unique identifiers for each item in the batch."
    )
    documents: list[str] = Field(
        ..., description="List of documents or text associated with each item."
    )
    # Optional fields
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


class QuickEmbeddingRequest(BaseModel):
    query: str = Field(
        ...,
        description="The text query to generate an embedding for.",
    )
    model: str = Field(
        ...,
        description="The embedding model to use for generating embeddings.",
    )


# Collection Operations
class CreateCollectionRequest(BaseModel):
    name: str = Field(
        ...,
        description="The name of the collection to create.",
    )
    model: str = Field(
        ...,
        description="The embedding model to use for the collection.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata for the collection.",
    )


class DeleteCollectionRequest(BaseModel):
    name: str = Field(
        ...,
        description="The name of the collection to delete.",
    )


class InsertCollectionRequest(BaseModel):
    name: str = Field(
        ...,
        description="The name of the collection to insert into.",
    )
    model: str = Field(
        ...,
        description="The embedding model to use for the insertion.",
    )
    batch: ChromaBatch = Field(
        ...,
        description="Batch of documents to insert into the collection.",
    )


class ListCollectionsRequest(BaseModel): ...


class QueryCollectionRequest(BaseModel):
    # Mandatory fields
    name: str = Field(
        ...,
        description="The name of the collection to query.",
    )
    # Optional fields
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

    # Validate that exactly one of query or query_embeddings is provided
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
    "InsertCollectionRequest",
    "ListCollectionsRequest",
    "QueryCollectionRequest",
]
