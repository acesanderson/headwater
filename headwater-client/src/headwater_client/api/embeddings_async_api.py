"""
Async client for interacting with the Embeddings service.
"""

from headwater_client.api.base_async_api import BaseAsyncAPI
from headwater_api.classes import (
    EmbeddingsRequest,
    EmbeddingsResponse,
    QuickEmbeddingRequest,
    QuickEmbeddingResponse,
    CreateCollectionRequest,
    CreateCollectionResponse,
    GetCollectionRequest,
    CollectionRecord,
    ListCollectionsResponse,
    DeleteCollectionRequest,
    DeleteCollectionResponse,
    QueryCollectionRequest,
    QueryCollectionResponse,
)


class EmbeddingsAsyncAPI(BaseAsyncAPI):
    # Embeddings API methods
    async def generate_embeddings(
        self,
        request: EmbeddingsRequest,
    ) -> EmbeddingsResponse:
        """
        Generate embeddings using the server.
        """
        method = "POST"
        endpoint = "/conduit/embeddings"
        json_payload = request.model_dump_json()
        response = await self._request(method, endpoint, json_payload=json_payload)
        return EmbeddingsResponse.model_validate_json(response)

    async def list_embedding_models(
        self,
    ) -> list[str]:
        """
        List available embedding models from the server.
        """
        method = "GET"
        endpoint = "/conduit/embeddings/models"
        json_payload = None
        response = await self._request(method, endpoint, json_payload=json_payload)
        return response

    async def quick_embedding(
        self,
        request: QuickEmbeddingRequest,
    ) -> QuickEmbeddingResponse:
        """
        Generate quick embeddings using the server.
        """
        method = "POST"
        endpoint = "/conduit/embeddings/quick"
        json_payload = request.model_dump_json()
        response = await self._request(method, endpoint, json_payload=json_payload)
        return QuickEmbeddingResponse.model_validate_json(response)

    async def get_collection(self, request: GetCollectionRequest) -> CollectionRecord:
        """
        Get an embedding collection by name.
        """
        method = "POST"
        endpoint = "/conduit/embeddings/collections/get"
        json_payload = request.model_dump_json()
        response = await self._request(method, endpoint, json_payload=json_payload)
        return CollectionRecord.model_validate_json(response)

    async def list_collections(
        self,
    ) -> ListCollectionsResponse:
        """
        List all embedding collections.
        """
        method = "GET"
        endpoint = "/conduit/embeddings/collections"
        response = await self._request(method, endpoint)
        return ListCollectionsResponse.model_validate_json(response)

    async def query_collection(
        self,
        request: QueryCollectionRequest,
    ) -> QueryCollectionResponse:
        """
        Query embeddings from a collection.
        """
        method = "POST"
        endpoint = "/conduit/embeddings/collections/query"
        json_payload = request.model_dump_json()
        response = await self._request(method, endpoint, json_payload=json_payload)
        return QueryCollectionResponse.model_validate_json(response)