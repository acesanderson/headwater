from __future__ import annotations
from fastapi import FastAPI
from headwater_api.classes import (
    EmbeddingsRequest,
    EmbeddingsResponse,
    EmbeddingModelSpec,
    QuickEmbeddingRequest,
    QuickEmbeddingResponse,
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

        @self.app.get("/conduit/embeddings/models", response_model=list[EmbeddingModelSpec])
        async def list_embedding_models() -> list[EmbeddingModelSpec]:
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



