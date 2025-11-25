from headwater_api.classes import (
    GetCollectionRequest,
    CollectionRecord,
)
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
    name = collection.name
    metadata = collection.metadata
    model = metadata.get("embedding_model", "unknown")
    no_of_ids = collection.count()
    no_of_documents = collection.count()

    return CollectionRecord(
        name=collection.name,
        model=model,
        no_of_ids=no_of_ids,
        no_of_documents=no_of_documents,
        metadata=metadata,
    )
