from dbclients.clients.chroma import get_client


async def list_collections_service() -> list[str]:
    """
    List all collections in the Chroma database.

    Returns:
        list[str]: A list of collection names.
    """
    client = await get_client()
    collections = await client.list_collections()
    collection_names = [collection.name for collection in collections]
    return collection_names
