from __future__ import annotations

import pytest
import yaml
from pathlib import Path
from fastapi.testclient import TestClient


VALID_CONFIG = {
    "backends": {
        "deepwater": "http://172.16.0.2:8080",
        "bywater": "http://172.16.0.4:8080",
        "backwater": "http://172.16.0.9:8080",
        "stillwater": "http://172.16.0.3:8080",
    },
    "routes": {
        "conduit": "bywater",
        "heavy_inference": "deepwater",
        "siphon": "deepwater",
        "curator": "bywater",
        "embeddings": "backwater",
        "reranker_light": "backwater",
        "reranker_heavy": "bywater",
        "ambient_inference": "stillwater",
    },
    "heavy_models": ["qwq:latest", "deepseek-r1:70b"],
}


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "routes.yaml"
    path.write_text(yaml.dump(VALID_CONFIG))
    return path


@pytest.fixture
def router_client(config_path: Path) -> TestClient:
    from headwater_server.server.router import HeadwaterRouter
    r = HeadwaterRouter(config_path=config_path)
    return TestClient(r.app)


def test_ping_returns_pong_without_proxying(router_client: TestClient):
    """AC-13: GET /ping returns 200 {"message": "pong"} and does not proxy."""
    response = router_client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"message": "pong"}


from unittest.mock import AsyncMock, MagicMock, patch
import httpx


def test_proxy_forwards_x_request_id_to_backend(router_client: TestClient):
    """AC-11: Every proxied request includes X-Request-ID on the upstream call."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.content = b'{"result": "ok"}'
    mock_response.headers = {}

    with patch("headwater_server.server.router.httpx") as mock_httpx:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.request = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value = mock_async_client

        router_client.post(
            "/conduit/generate",
            json={"model": "llama3.2:3b", "prompt": "hello"},
        )

    call_kwargs = mock_async_client.request.call_args.kwargs
    assert "x-request-id" in {k.lower() for k in call_kwargs["headers"].keys()}


def test_proxy_propagates_422_status_and_body_verbatim(router_client: TestClient):
    """AC-7: Backend 422 is forwarded with identical status code and body; hop-by-hop headers stripped."""
    error_body = b'{"detail": "validation error from backend"}'
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 422
    mock_response.content = error_body
    mock_response.headers = {
        "content-type": "application/json",
        "transfer-encoding": "chunked",  # hop-by-hop — must be stripped
        "x-custom-header": "keep-this",
    }

    with patch("headwater_server.server.router.httpx") as mock_httpx:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.request = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value = mock_async_client

        response = router_client.post(
            "/conduit/generate",
            json={"model": "llama3.2:3b"},
        )

    assert response.status_code == 422
    assert response.content == error_body
    assert "transfer-encoding" not in {k.lower() for k in response.headers}
    assert response.headers.get("x-custom-header") == "keep-this"


def test_proxy_returns_503_with_backend_unavailable_when_unreachable(router_client: TestClient):
    """AC-8: Backend ConnectError → HTTP 503 with error_type='backend_unavailable'."""
    with patch("headwater_server.server.router.httpx") as mock_httpx:
        mock_httpx.ConnectError = httpx.ConnectError
        mock_httpx.TimeoutException = httpx.TimeoutException
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        mock_httpx.AsyncClient.return_value = mock_async_client

        response = router_client.post(
            "/conduit/generate",
            json={"model": "llama3.2:3b"},
        )

    assert response.status_code == 503
    body = response.json()
    assert body["error_type"] == "backend_unavailable"
    assert "172.16.0.4" in body["message"] or "172.16.0.4" in str(body.get("context", ""))


def test_router_app_module_level_app_is_importable():
    """router.py exposes a module-level `app` for uvicorn."""
    from headwater_server.server import router as router_module
    assert hasattr(router_module, "app")
    assert router_module.app.title == "Headwater Router"


def test_router_main_is_callable():
    """router_main entry point function exists and is callable."""
    from headwater_server.server.main import router_main
    assert callable(router_main)
