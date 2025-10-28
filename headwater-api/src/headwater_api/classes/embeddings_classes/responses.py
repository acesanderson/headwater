from typing import Literal
from pydantic import BaseModel, Field


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
    model: str = Field(..., description="Embedding model used for the collection")
    no_of_ids: int = Field(..., description="Number of unique IDs in the collection")
    no_of_documents: int = Field(
        ..., description="Number of documents in the collection"
    )
    metadata: dict[str, str] | None = Field(
        default=None, description="Optional metadata for the collection"
    )


class CreateCollectionResponse(BaseModel):
    collection: CollectionRecord = Field(
        ..., description="Details of the created collection"
    )
    result: Literal["already_exists", "created"] = Field(
        ..., description="Result of the create operation"
    )


class DeleteCollectionResponse(BaseModel):
    collection: CollectionRecord = Field(
        ..., description="Details of the deleted collection"
    )
    result: Literal["not_found", "deleted"] = Field(
        ..., description="Result of the delete operation"
    )


class InsertCollectionResponse(BaseModel):
    collection: CollectionRecord = Field(..., description="Details of the collection")
    result: Literal["collection_not_found", "inserted"] = Field(
        ..., description="Result of the insert operation"
    )
    inserted_count: int = Field(..., description="Number of documents inserted")


class ListCollectionsResponse(BaseModel):
    collections: list[CollectionRecord] = Field(
        ..., description="List of collection names"
    )


class QueryCollectionResponse(BaseModel):
    query: str = Field(..., description="The query string used for searching")
    ids: list[str] = Field(..., description="List of matching document IDs")
    documents: list[str] = Field(..., description="List of matching documents")
    distances: list[float] = Field(..., description="List of distances for each match")


__all__ = [
    "EmbeddingsResponse",
    "QuickEmbeddingResponse",
    "CollectionRecord",
    "CreateCollectionResponse",
    "DeleteCollectionResponse",
    "InsertCollectionResponse",
    "ListCollectionResponse",
    "QueryCollectionResponse",
]
