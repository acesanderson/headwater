from __future__ import annotations
from fastapi import FastAPI
from contextlib import asynccontextmanager
from headwater_server.api.conduit_server_api import ConduitServerAPI
from headwater_server.api.embeddings_server_api import EmbeddingsServerAPI
from headwater_server.api.curator_server_api import CuratorServerAPI
from headwater_server.api.siphon_server_api import SiphonServerAPI
from headwater_server.api.headwater_api import HeadwaterServerAPI
from headwater_server.api.reranker_server_api import RerankerServerAPI

import logging

logger = logging.getLogger(__name__)


class HeadwaterServer:
    def __init__(self, name: str = "Headwater API Server"):
        self._name = name
        self.app: FastAPI = self._create_app()
        self._register_routes()
        self._register_middleware()
        self._register_error_handlers()

    def _create_app(self) -> FastAPI:
        name = self._name  # capture for closure

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info(f"{name} starting up...")
            from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore
            if not EmbeddingModelStore._is_consistent():
                logger.warning(
                    "Embedding model specs are inconsistent with registry — run update_embedding_modelstore.",
                    extra={
                        "models_in_registry": len(EmbeddingModelStore.list_models()),
                        "models_in_db": len(EmbeddingModelStore.get_all_specs()),
                    },
                )
            yield
            # Shutdown
            logger.info(f"{name} shutting down...")

        return FastAPI(
            title=self._name,
            description="Universal content ingestion and LLM processing API",
            version="1.0.0",
            lifespan=lifespan,
        )

    def _register_routes(self):
        """
        Register all domain API routes
        """

        ConduitServerAPI(self.app).register_routes()
        EmbeddingsServerAPI(self.app).register_routes()
        CuratorServerAPI(self.app).register_routes()
        SiphonServerAPI(self.app).register_routes()
        HeadwaterServerAPI(self.app, server_name=self._name).register_routes()
        RerankerServerAPI(self.app).register_routes()

    def _register_middleware(self):
        """
        Configure middleware.
        """
        from fastapi.middleware.cors import CORSMiddleware

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _register_error_handlers(self):
        """
        Register global error handlers.
        """
        from headwater_server.server.error_handlers import ErrorHandlers

        er = ErrorHandlers(self.app)
        er.register_error_handlers()


_server = HeadwaterServer()
app = _server.app
