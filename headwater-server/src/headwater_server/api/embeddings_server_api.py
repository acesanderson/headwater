from fastapi import FastAPI
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


class EmbeddingsServerAPI:
    def __init__(self, app: FastAPI):
        self.app: FastAPI = app

    def register_routes(self):
        """
        Register all conduit routes
        """

        # Embeddings
        @self.app.post("/conduit/embeddings", response_model=EmbeddingsResponse)
        async def generate_embeddings(request: EmbeddingsRequest):
            """Generate synthetic data with structured error handling"""
            from headwater_server.services.embeddings_service.generate_embeddings_service import (
                generate_embeddings_service,
            )

            return await generate_embeddings_service(request)

        @self.app.get("/conduit/embeddings/models", response_model=list[str])
        async def list_embedding_models() -> list[str]:
            from headwater_server.services.embeddings_service.list_embedding_models_service import (
                list_embedding_models_service,
            )

            return await list_embedding_models_service()

        @self.app.post(
            "/conduit/embeddings/quick", response_model=QuickEmbeddingResponse
        )
        async def quick_embedding(
            request: QuickEmbeddingRequest,
        ) -> QuickEmbeddingResponse:
            from headwater_server.services.embeddings_service.quick_embedding_service import (
                quick_embedding_service,
            )

            return quick_embedding_service(request)

        # Get Collection
        @self.app.post(
            "/conduit/embeddings/collections/get",
            response_model=CollectionRecord,
        )
        async def get_collection(request: GetCollectionRequest) -> CollectionRecord:
            from headwater_server.services.embeddings_service.get_collection_service import (
                get_collection_service,
            )

            return await get_collection_service(request)

        @self.app.get("/conduit/embeddings/collections")
        async def list_collections() -> ListCollectionsResponse:
            from headwater_server.services.embeddings_service.list_collections_service import (
                list_collections_service,
            )

            return await list_collections_service()

        @self.app.post(
            "/conduit/embeddings/collections/query",
            response_model=QueryCollectionResponse,
        )
        async def query_collection(
            request: QueryCollectionRequest,
        ) -> QueryCollectionResponse:
            from headwater_server.services.embeddings_service.query_collection_service import (
                query_collection_service,
            )

            return await query_collection_service(request)

        # # Collections
        # @self.app.post(
        #     "/conduit/embeddings/collections", response_model=CreateCollectionResponse
        # )
        # def create_collection(
        #     request: CreateCollectionRequest,
        # ) -> CreateCollectionResponse:
        #     from headwater_server.services.embeddings_service.create_collection_service import (
        #         create_collection_service,
        #     )
        #
        #     return create_collection_service(request)
        # @self.app.delete(
        #     "/conduit/embeddings/collections", response_model=DeleteCollectionResponse
        # )
        # def delete_collection(
        #     request: DeleteCollectionRequest,
        # ) -> DeleteCollectionResponse:
        #     from headwater_server.services.embeddings_service.delete_collection_service import (
        #         delete_collection_service,
        #     )
        #
        #     return delete_collection_service(request)
        #
