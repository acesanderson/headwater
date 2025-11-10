from fastapi import FastAPI
from contextlib import asynccontextmanager
from headwater_server.api.conduit_server_api import ConduitServerAPI
from headwater_server.api.embeddings_server_api import EmbeddingsServerAPI
from headwater_server.api.curator_server_api import CuratorServerAPI
from headwater_server.api.siphon_server_api import SiphonServerAPI
from headwater_server.api.headwater_api import HeadwaterServerAPI

import logging

logger = logging.getLogger(__name__)


class HeadwaterServer:
    def __init__(self):
        self.app: FastAPI = self._create_app()
        self._register_routes()
        self._register_middleware()
        self._register_error_handlers()

    def _create_app(self) -> FastAPI:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info("🚀 Headwater Server starting up...")
            from conduit.sync import Model

            _ = Model._odometer_registry
            yield
            # Shutdown
            logger.info("🛑 Headwater Server shutting down...")

        return FastAPI(
            title="Headwater API Server",
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
        HeadwaterServerAPI(self.app).register_routes()

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
