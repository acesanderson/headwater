"""
Client for interacting with the Curator service.
"""

from __future__ import annotations
from pydantic import TypeAdapter
from headwater_client.api.base_api import BaseAPI
from headwater_api.classes import (
    EmbeddingsRequest,
    EmbeddingsResponse,
    EmbeddingModelSpec,
    QuickEmbeddingRequest,
    QuickEmbeddingResponse,
    GetCollectionRequest,
    CollectionRecord,
    ListCollectionsResponse,
    QueryCollectionRequest,
    QueryCollectionResponse,
)


class EmbeddingsAPI(BaseAPI):
    # Embeddings API methods
    def generate_embeddings(
        self,
        request: EmbeddingsRequest,
    ) -> EmbeddingsResponse:
        """
        Generate embeddings using the server.
        """
        method = "POST"
        endpoint = "/conduit/embeddings"
        json_payload = request.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        return EmbeddingsResponse.model_validate_json(response)

    def list_embedding_models(
        self,
    ) -> list[EmbeddingModelSpec]:
        """
        List available embedding models from the server.
        """
        method = "GET"
        endpoint = "/conduit/embeddings/models"
        response = self._request(method, endpoint)
        return TypeAdapter(list[EmbeddingModelSpec]).validate_json(response)

    def quick_embedding(
        self,
        request: QuickEmbeddingRequest,
    ) -> QuickEmbeddingResponse:
        """
        Generate quick embeddings using the server.
        """
        method = "POST"
        endpoint = "/conduit/embeddings/quick"
        json_payload = request.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        return QuickEmbeddingResponse.model_validate_json(response)

    def get_collection(self, request: GetCollectionRequest) -> CollectionRecord:
        """
        Get an embedding collection by name.
        """
        method = "POST"
        endpoint = "/conduit/embeddings/collections/get"
        json_payload = request.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        return CollectionRecord.model_validate_json(response)

    def list_collections(
        self,
    ) -> ListCollectionsResponse:
        """
        List all embedding collections.
        """
        method = "GET"
        endpoint = "/conduit/embeddings/collections"
        response = self._request(method, endpoint)
        return ListCollectionsResponse.model_validate_json(response)

    def query_collection(
        self,
        request: QueryCollectionRequest,
    ) -> QueryCollectionResponse:
        """
        Query embeddings from a collection.
        """
        method = "POST"
        endpoint = "/conduit/embeddings/collections/query"
        json_payload = request.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        return QueryCollectionResponse.model_validate_json(response)

