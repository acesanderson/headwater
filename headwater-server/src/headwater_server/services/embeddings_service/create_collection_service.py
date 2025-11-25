from headwater_api.classes import (
    load_embedding_models,
    GetCollectionRequest,
    CollectionRecord,
    CreateCollectionRequest,
    CreateCollectionResponse,
    DeleteCollectionRequest,
    DeleteCollectionResponse,
    QueryCollectionResult,
    QueryCollectionRequest,
    QueryCollectionResponse,
)
from pydantic import BaseModel, Field
from dbclients.clients.chroma import get_client
from typing import Any
import logging

logger = logging.getLogger(__name__)


async def get_collection_service(request: GetCollectionRequest) -> CollectionRecord:
    """
    Retrieve a collection by name.
    This function simulates retrieving a collection.
    """
    logger.info(f"Retrieving collection '{request.collection_name}'.")

    client = await get_client()
    collection = await client.get_collection(name=request.collection_name)
    return CollectionRecord(
        name=collection.name,
        model=collection.model,
        no_of_ids=collection.num_ids,
        no_of_documents=collection.num_documents,
        metadata=collection.metadata,
    )


async def create_collection_service(
    request: CreateCollectionRequest,
) -> CreateCollectionResponse:
    """
    Create a new collection with the specified name and embedding model.
    This function simulates the creation of a collection.
    """
    collection_name = request.collection_name
    embedding_model = request.embedding_model
    metadata = request.metadata
    # Update metadata with embedding model info
    metadata["embedding_model"] = embedding_model

    logger.info(
        f"Creating collection '{collection_name}' with embedding model '{embedding_model}'."
    )

    client = await get_client()
    try:
        collection = await client.create_collection(
            name=collection_name, metadata=metadata
        )
        result = "created"
    except Exception as e:
        logger.warning(f"Collection '{collection_name}' already exists. {e}")
        collection = await client.get_collection(name=collection_name)
        result = "already_exists"

    return CreateCollectionResponse(
        collection_name=collection.name,
        embedding_model=embedding_model,
        result=result,
    )


async def delete_collection_service(
    request: DeleteCollectionRequest,
) -> DeleteCollectionResponse:
    """
    Delete an existing collection by name.
    This function simulates the deletion of a collection.
    """
    collection_name = request.collection_name

    logger.info(f"Deleting collection '{collection_name}'.")

    client = await get_client()
    try:
        await client.delete_collection(name=collection_name)
        result = "deleted"
    except Exception as e:
        logger.error(f"Error deleting collection '{collection_name}': {e}")
        result = "not_found"
    return DeleteCollectionResponse(collection_name=collection_name, result=result)


async def query_collection_service(
    request: QueryCollectionRequest,
) -> QueryCollectionResponse:
    """
    Query a collection with the specified query string.
    This function simulates querying a collection.
    """
    logger.info(f"Querying collection with query: '{query}'.")

    client = await get_client()
