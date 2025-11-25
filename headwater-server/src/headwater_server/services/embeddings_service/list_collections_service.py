from dbclients.clients.chroma import get_client
from headwater_api.classes import ListCollectionsResponse, CollectionRecord
import logging

logger = logging.getLogger(__name__)


async def list_collections_service() -> ListCollectionsResponse:
    """
    List all collections in the Chroma database.

    Returns:
        list[str]: A list of collection names.
    """
    logger.info("Listing all collections.")
    client = await get_client()
    collections = await client.list_collections()
    collection_records: list[CollectionRecord] = []
    for collection in collections:
        if not collection:
            continue
        metadata = getattr(client, "metadata", {})
        if metadata:
            model = metadata.get("embedding_model", None)
        else:
            model = None
        count = await collection.count()
        collection_records.append(
            CollectionRecord(
                name=collection.name,
                metadata=metadata,
                model=model,
                no_of_ids=count,
                no_of_documents=count,
            )
        )
    return ListCollectionsResponse(collections=collection_records)
