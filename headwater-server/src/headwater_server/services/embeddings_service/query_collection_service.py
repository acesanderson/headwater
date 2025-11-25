from headwater_api.classes import (
    QueryCollectionRequest,
    QueryCollectionResult,
    QueryCollectionResponse,
)
from pydantic import BaseModel, Field
from dbclients.clients.chroma import get_client
from typing import Any
import logging

logger = logging.getLogger(__name__)


async def query_collection_service(
    request: QueryCollectionRequest,
) -> QueryCollectionResponse:
    name = request.name
    query = request.query
    query_embeddings = request.query_embeddings
    n_results = request.n_results

    logger.info(f"Querying collection with query: '{query}'.")

    client = await get_client()
    collection = await client.get_collection(name=name)
    # Get model, or default model if not specified
    metadata = getattr(collection, "metadata", {})
    if metadata:
        embedding_model = metadata.get(
            "embedding_model", "sentence-transformers/all-MiniLM-L6-v2"
        )
    else:
        embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
    logger.info(f"Using embedding model: '{embedding_model}'.")
    if query_embeddings is None:
        from headwater_server.services.embeddings_service.embedding_model import (
            EmbeddingModel,
        )

        embedding_model_instance = EmbeddingModel(model_name=embedding_model)
        query_embeddings = embedding_model_instance.embedding_function([query])[
            0
        ]  # Get first (and only) embedding
    results = await collection.query(
        query_embeddings=query_embeddings,
        n_results=n_results,
        include=["metadatas", "documents", "distances"],
    )
    logger.info(f"Retrieved {len(results['documents'])} results from collection.")
    query_results = []
    for i in range(len(results["documents"])):
        query_results.append(
            QueryCollectionResult(
                id=results["ids"][i],
                document=results["documents"][i],
                metadata=results["metadatas"][i],
                score=results["distances"][i],
            )
        )
    response = QueryCollectionResponse(query=query, results=query_results)
    return response
