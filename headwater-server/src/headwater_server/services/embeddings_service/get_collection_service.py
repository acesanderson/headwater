from headwater_api.classes import (
    GetCollectionRequest,
    CollectionRecord,
)
from dbclients.clients.chroma import get_client
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
    metadata = getattr(client, "metadata", {})
    if metadata:
        model = metadata.get("embedding_model", None)
    else:
        model = None
    count = await collection.count()
    return CollectionRecord(
        name=collection.name,
        metadata=metadata,
        model=model,
        no_of_ids=count,
        no_of_documents=count,
    )
