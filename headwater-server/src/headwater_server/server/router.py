from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

import headwater_server.server.logging_config  # noqa: F401

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse

from headwater_api.classes import StatusResponse, LogsLastResponse, GpuResponse, RouterGpuResponse
from headwater_server.server.routing_config import (
    RouterConfig,
    RoutingError,
    get_fallback_urls,
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
        self._config_path: Path = config_path or ROUTES_YAML_PATH
        self._startup_time: float = time.time()
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

        startup_time = self._startup_time
        server_name = self._name
        config_path = self._config_path

        @self.app.get("/logs/last", response_model=LogsLastResponse)
        def logs_last(n: int = Query(default=50, ge=1)) -> LogsLastResponse:
            from headwater_server.server.logging_config import ring_buffer
            return ring_buffer.get_response(n)

        @self.app.get("/logs/journal")
        def logs_journal(n: int = Query(default=100, ge=1)) -> dict:
            import subprocess
            try:
                result = subprocess.run(
                    ["journalctl", "-u", "headwaterrouter", "-n", str(n), "--no-pager"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                lines = result.stdout.splitlines()
                return {"unit": "headwaterrouter", "n_requested": n, "lines": lines}
            except FileNotFoundError:
                return {"unit": "headwaterrouter", "n_requested": n, "lines": [], "error": "journalctl not available"}
            except subprocess.TimeoutExpired:
                return {"unit": "headwaterrouter", "n_requested": n, "lines": [], "error": "journalctl timed out"}

        @self.app.get("/status", response_model=StatusResponse)
        async def status() -> StatusResponse:
            from headwater_server.services.status_service.get_status import get_status_service
            return await get_status_service(startup_time, server_name=server_name)

        @self.app.get("/routes/")
        def routes_config() -> dict:
            return {
                "backends": config.backends,
                "routes": config.routes,
                "heavy_models": config.heavy_models,
                "config_path": str(config_path),
            }

        @self.app.get("/gpu", response_model=RouterGpuResponse)
        async def gpu() -> RouterGpuResponse:
            import asyncio

            async def fetch_backend_gpu(name: str, base_url: str) -> tuple[str, GpuResponse]:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.get(f"{base_url}/gpu")
                        resp.raise_for_status()
                        return name, GpuResponse.model_validate(resp.json())
                except Exception as exc:
                    return name, GpuResponse(
                        server_name=name,
                        gpus=[],
                        ollama_loaded_models=[],
                        error=str(exc),
                    )

            results = await asyncio.gather(
                *[fetch_backend_gpu(name, url) for name, url in config.backends.items()]
            )
            return RouterGpuResponse(backends=dict(results))

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
                backend_url, route_key = resolve_backend(service, model, config)
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
                    "route": route_key,
                },
            )

            backends_to_try = [backend_url] + get_fallback_urls(route_key, config)
            upstream = None
            for attempt_url in backends_to_try:
                attempt_target = f"{attempt_url}/{path}"
                if request.url.query:
                    attempt_target = f"{attempt_target}?{request.url.query}"
                try:
                    async with httpx.AsyncClient() as client:
                        upstream = await client.request(
                            method=request.method,
                            url=attempt_target,
                            headers=forward_headers,
                            content=body,
                            timeout=httpx.Timeout(300.0, connect=5.0),
                        )
                    backend_url = attempt_url
                    break
                except httpx.ConnectError as exc:
                    logger.warning(
                        "backend_unavailable",
                        extra={
                            "backend": attempt_url,
                            "path": path,
                            "error": str(exc),
                            "req_id": request.state.request_id,
                            "will_retry": attempt_url != backends_to_try[-1],
                        },
                    )
                except httpx.TimeoutException as exc:
                    logger.error(
                        "backend_timeout",
                        extra={
                            "backend": attempt_url,
                            "path": path,
                            "error": str(exc),
                            "req_id": request.state.request_id,
                        },
                    )
                    error = HeadwaterServerError(
                        error_type=ErrorType.BACKEND_TIMEOUT,
                        message=f"Backend timed out after 300s: {attempt_url}",
                        status_code=503,
                        path=request.url.path,
                        method=request.method,
                        request_id=request.state.request_id,
                        context={"backend": attempt_url},
                    )
                    return JSONResponse(status_code=503, content=error.model_dump(mode="json"))

            if upstream is None:
                logger.error(
                    "all_backends_unavailable",
                    extra={
                        "backends_tried": backends_to_try,
                        "path": path,
                        "req_id": request.state.request_id,
                    },
                )
                error = HeadwaterServerError(
                    error_type=ErrorType.BACKEND_UNAVAILABLE,
                    message=f"All backends unreachable for route '{route_key}': {backends_to_try}",
                    status_code=503,
                    path=request.url.path,
                    method=request.method,
                    request_id=request.state.request_id,
                    context={"backends_tried": backends_to_try},
                )
                return JSONResponse(status_code=503, content=error.model_dump(mode="json"))

            logger.debug(
                "proxy_response",
                extra={
                    "service": service,
                    "backend": backend_url,
                    "path": path,
                    "upstream_status": upstream.status_code,
                    "req_id": request.state.request_id,
                },
            )

            response_headers = {
                k: v for k, v in upstream.headers.items()
                if k.lower() not in HOP_BY_HOP
            }
            if backend_url != backends_to_try[0]:
                url_to_name = {v: k for k, v in config.backends.items()}
                response_headers["X-Headwater-Routed-Via"] = url_to_name.get(backend_url, backend_url)
                response_headers["X-Headwater-Primary-Backend"] = url_to_name.get(backends_to_try[0], backends_to_try[0])
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
_router = None
try:
    _router = HeadwaterRouter()
    app = _router.app
except FileNotFoundError:
    app = FastAPI(
        title="Headwater Router",
        description="Headwater routing gateway",
        version="1.0.0",
    )

if _router is not None:
    from headwater_server.server.metrics import register_router_metrics
    register_router_metrics(_router.app, _router._name, _router._config)
