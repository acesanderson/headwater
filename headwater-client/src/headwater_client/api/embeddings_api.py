"""
Client for interacting with the Curator service.
"""

from headwater_api.api.base_api import BaseAPI
from headwater_api.classes import (
    EmbeddingsRequest,
    EmbeddingsResponse,
    QuickEmbeddingRequest,
    QuickEmbeddingResponse,
    CreateCollectionRequest,
    CreateCollectionResponse,
    ListCollectionsRequest,
    ListCollectionsResponse,
    DeleteCollectionRequest,
    DeleteCollectionResponse,
    InsertCollectionRequest,
    InsertCollectionResponse,
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

    # Embedding Collections API methods
    def create_collection(
        self,
        request: CreateCollectionRequest,
    ) -> CreateCollectionResponse:
        """
        Create a new embedding collection.
        """
        method = "POST"
        endpoint = "/embeddings/collections"
        json_payload = request.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        return CreateCollectionResponse.model_validate_json(response)

    def list_collections(
        self,
        request: ListCollectionsRequest,
    ) -> ListCollectionsResponse:
        """
        List all embedding collections.
        """
        method = "GET"
        endpoint = "/embeddings/collections"
        response = self._request(method, endpoint)
        return ListCollectionsResponse.model_validate_json(response)

    def delete_collection(
        self,
        request: DeleteCollectionRequest,
    ) -> DeleteCollectionResponse:
        """
        Delete an embedding collection.
        """
        method = "DELETE"
        endpoint = f"/embeddings/collections/{request.name}"
        response = self._request(method, endpoint)
        return DeleteCollectionResponse.model_validate_json(response)

    def insert_into_collection(
        self,
        request: InsertCollectionRequest,
    ) -> InsertCollectionResponse:
        """
        Insert embeddings into a collection.
        """
        method = "POST"
        endpoint = f"/embeddings/collections/{request.name}/insert"
        json_payload = request.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        return InsertCollectionResponse.model_validate_json(response)

    def query_collection(
        self,
        request: QueryCollectionRequest,
    ) -> QueryCollectionResponse:
        """
        Query embeddings from a collection.
        """
        method = "POST"
        endpoint = f"/embeddings/collections/{request.name}/query"
        json_payload = request.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        return QueryCollectionResponse.model_validate_json(response)
