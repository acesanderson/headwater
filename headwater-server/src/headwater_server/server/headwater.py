from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi import Response
from headwater_server.api.conduit_server_api import ConduitServerAPI
from headwater_server.api.embeddings_server_api import EmbeddingsServerAPI
from headwater_server.api.curator_server_api import CuratorServerAPI
from headwater_server.api.siphon_server_api import SiphonServerAPI
from headwater_server.api.headwater_api import HeadwaterServerAPI
from headwater_server.api.reranker_server_api import RerankerServerAPI

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
        Configure middleware. Correlation middleware is registered via @app.middleware("http")
        and runs before CORSMiddleware (which is added last via add_middleware).
        """
        from fastapi.middleware.cors import CORSMiddleware
        from headwater_server.server.context import request_id_var

        @self.app.middleware("http")
        async def correlation_middleware(request: Request, call_next: Callable) -> Response:
            header_value = request.headers.get("X-Request-ID", "")
            try:
                parsed = uuid.UUID(header_value)
                assert parsed.version == 4
                request_id = header_value
            except (ValueError, AttributeError, AssertionError):
                request_id = str(uuid.uuid4())

            request.state.request_id = request_id
            token = request_id_var.set(request_id)
            start = time.monotonic()
            status_code = 500

            logger.info(
                "request_started",
                extra={
                    "request_id": request_id,
                    "path": request.url.path,
                    "method": request.method,
                },
            )

            response: Response | None = None
            try:
                response = await call_next(request)
                status_code = response.status_code
            except Exception as exc:
                # Starlette 0.49 re-raises exceptions from _exception_handler.py
                # even after exception handlers send a response. That response is
                # discarded by BaseHTTPMiddleware's send_no_error. Rebuild it here
                # so we can attach the X-Request-ID header. Inner handlers already
                # logged the error; don't log again.
                import traceback as _tb
                from fastapi.responses import JSONResponse
                from headwater_api.classes import HeadwaterServerError, ErrorType
                error = HeadwaterServerError(
                    error_type=ErrorType.INTERNAL_ERROR,
                    message=f"Internal server error: {str(exc)}",
                    status_code=500,
                    path=request.url.path,
                    method=request.method,
                    request_id=request_id,
                    original_exception=str(exc),
                    traceback=_tb.format_exc(),
                    context={"exception_type": type(exc).__name__},
                )
                response = JSONResponse(status_code=500, content=error.model_dump())
                status_code = 500
            finally:
                duration_ms = round((time.monotonic() - start) * 1000, 1)
                logger.info(
                    "request_finished",
                    extra={
                        "request_id": request_id,
                        "path": request.url.path,
                        "method": request.method,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                )
                request_id_var.reset(token)

            if response is not None:
                response.headers["X-Request-ID"] = request_id
            return response

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
