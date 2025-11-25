from typing import Literal
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


# Collection Operations
class CollectionRecord(BaseModel):
    name: str = Field(..., description="Name of the collection")
    no_of_ids: int = Field(..., description="Number of unique IDs in the collection")
    no_of_documents: int = Field(
        ..., description="Number of documents in the collection"
    )
    model: str | None = Field(
        ..., description="Embedding model used for the collection"
    )
    metadata: dict[str, str] | None = Field(
        default=None, description="Optional metadata for the collection"
    )


class ListCollectionsResponse(BaseModel):
    collections: list[CollectionRecord] = Field(
        ..., description="List of collections available"
    )


class CreateCollectionResponse(BaseModel):
    collection_name: str = Field(..., description="The name of the created collection.")
    embedding_model: str = Field(
        ..., description="The embedding model used for the collection."
    )
    result: Literal["already_exists", "created"] = Field(
        ..., description="Result of the create operation"
    )


class DeleteCollectionResponse(BaseModel):
    collection_name: str = Field(
        ..., description="The name of the collection to delete."
    )
    result: Literal["not_found", "deleted"] = Field(
        ..., description="Result of the delete operation"
    )


class QueryCollectionResult(BaseModel):
    id: str = Field(..., description="The ID of the document.")
    document: str = Field(..., description="The content of the document.")
    metadata: dict[str, Any] = Field(
        ..., description="The metadata associated with the document."
    )
    score: float = Field(..., description="The similarity score of the document.")


class QueryCollectionResponse(BaseModel):
    query: str = Field(..., description="The query string used for the search.")
    results: list[QueryCollectionResult] = Field(
        ..., description="The list of results returned from the query."
    )


__all__ = [
    "EmbeddingsResponse",
    "QuickEmbeddingResponse",
    "CollectionRecord",
    "CreateCollectionResponse",
    "DeleteCollectionResponse",
    "QueryCollectionResult",
    "QueryCollectionResponse",
]
