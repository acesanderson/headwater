from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

import headwater_server.server.logging_config  # noqa: F401

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from headwater_server.server.routing_config import (
    RouterConfig,
    RoutingError,
    load_router_config,
    ROUTES_YAML_PATH,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

HOP_BY_HOP = frozenset({
    "connection", "transfer-encoding", "te", "trailer",
    "upgrade", "keep-alive", "proxy-authorization", "proxy-authenticate",
})


class HeadwaterRouter:
    def __init__(
        self,
        name: str = "Headwater Router",
        config_path: Path | None = None,
    ):
        self._name = name
        self._config: RouterConfig = load_router_config(config_path or ROUTES_YAML_PATH)
        self.app: FastAPI = FastAPI(
            title=self._name,
            description="Headwater routing gateway",
            version="1.0.0",
        )
        self._register_routes()
        self._register_middleware()

    def _register_routes(self) -> None:
        from headwater_api.classes import HeadwaterServerError, ErrorType

        config = self._config

        @self.app.get("/ping")
        async def ping() -> dict:
            return {"message": "pong"}

        @self.app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
        async def proxy(request: Request, path: str) -> Response:
            service = path.split("/")[0]

            body = await request.body()
            model: str | None = None
            if body:
                try:
                    parsed = json.loads(body)
                    # Top-level "model" (OpenAI-style) or nested under "params" (GenerationRequest/BatchRequest)
                    model = parsed.get("model") or (parsed.get("params") or {}).get("model")
                except Exception:
                    pass

            try:
                from headwater_server.server.routing_config import resolve_backend
                backend_url = resolve_backend(service, model, config)
            except RoutingError as exc:
                error = HeadwaterServerError(
                    error_type=ErrorType.ROUTING_ERROR,
                    message=str(exc),
                    status_code=400,
                    path=request.url.path,
                    method=request.method,
                    request_id=request.state.request_id,
                )
                return JSONResponse(status_code=400, content=error.model_dump(mode="json"))

            target = f"{backend_url}/{path}"
            if request.url.query:
                target = f"{target}?{request.url.query}"

            forward_headers = {
                k: v for k, v in request.headers.items()
                if k.lower() not in HOP_BY_HOP
            }
            forward_headers["x-request-id"] = request.state.request_id

            logger.debug(
                "proxy_request",
                extra={
                    "service": service,
                    "backend": backend_url,
                    "model": model,
                    "path": path,
                },
            )

            try:
                async with httpx.AsyncClient() as client:
                    upstream = await client.request(
                        method=request.method,
                        url=target,
                        headers=forward_headers,
                        content=body,
                        timeout=300.0,
                    )
            except httpx.ConnectError as exc:
                logger.error(
                    "backend_unavailable",
                    extra={
                        "backend": backend_url,
                        "path": path,
                        "error": str(exc),
                        "req_id": request.state.request_id,
                    },
                )
                error = HeadwaterServerError(
                    error_type=ErrorType.BACKEND_UNAVAILABLE,
                    message=f"Backend unreachable: {backend_url}",
                    status_code=503,
                    path=request.url.path,
                    method=request.method,
                    request_id=request.state.request_id,
                    context={"backend": backend_url},
                )
                return JSONResponse(status_code=503, content=error.model_dump(mode="json"))
            except httpx.TimeoutException as exc:
                logger.error(
                    "backend_timeout",
                    extra={
                        "backend": backend_url,
                        "path": path,
                        "error": str(exc),
                        "req_id": request.state.request_id,
                    },
                )
                error = HeadwaterServerError(
                    error_type=ErrorType.BACKEND_TIMEOUT,
                    message=f"Backend timed out after 300s: {backend_url}",
                    status_code=503,
                    path=request.url.path,
                    method=request.method,
                    request_id=request.state.request_id,
                    context={"backend": backend_url},
                )
                return JSONResponse(status_code=503, content=error.model_dump(mode="json"))

            response_headers = {
                k: v for k, v in upstream.headers.items()
                if k.lower() not in HOP_BY_HOP
            }
            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                headers=response_headers,
            )

    def _register_middleware(self) -> None:
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
            start = time.monotonic()

            response = await call_next(request)

            duration_ms = round((time.monotonic() - start) * 1000, 1)
            logger.debug(
                "request_finished",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            response.headers["X-Request-ID"] = request_id
            return response


# Module-level app for uvicorn and import checks.
# On machines without routes.yaml, falls back to a bare FastAPI instance.
try:
    _router = HeadwaterRouter()
    app = _router.app
except FileNotFoundError:
    app = FastAPI(
        title="Headwater Router",
        description="Headwater routing gateway",
        version="1.0.0",
    )
