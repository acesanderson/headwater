from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_metrics_state():
    """Reset OTel and prometheus_client state between tests for isolation.

    OTel's set_meter_provider is one-shot (Once object). We reset the internal
    _done flag and _METER_PROVIDER directly so each test gets a fresh provider.
    """
    import opentelemetry.metrics._internal as _otel_int
    from prometheus_client import REGISTRY

    def _reset_otel():
        _otel_int._METER_PROVIDER_SET_ONCE._done = False
        _otel_int._METER_PROVIDER = None

    _reset_otel()
    before = set(REGISTRY._names_to_collectors.keys())

    yield

    _reset_otel()
    for name in set(REGISTRY._names_to_collectors.keys()) - before:
        collector = REGISTRY._names_to_collectors.get(name)
        if collector is not None:
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    try:
        FastAPIInstrumentor().uninstrument()
    except Exception:
        pass


def _make_client(server_name: str = "bywater") -> TestClient:
    from headwater_server.server.metrics import register_metrics
    app = FastAPI()
    register_metrics(app, server_name)
    return TestClient(app)


def test_bywater_metrics_returns_200_with_prometheus_content_type():
    """AC-1: GET /metrics on bywater returns 200 with text/plain; version=0.0.4."""
    client = _make_client("bywater")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "version=0.0.4" in response.headers["content-type"]


def test_deepwater_metrics_returns_200_with_prometheus_content_type():
    """AC-2: GET /metrics on deepwater returns 200 with text/plain; version=0.0.4."""
    client = _make_client("deepwater")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "version=0.0.4" in response.headers["content-type"]


def test_router_metrics_returns_200_with_prometheus_content_type():
    """AC-3: GET /metrics on headwaterrouter returns 200 with text/plain; version=0.0.4."""
    import yaml
    from pathlib import Path
    from fastapi.testclient import TestClient
    from headwater_server.server.router import HeadwaterRouter
    from headwater_server.server.metrics import register_router_metrics

    config = {
        "backends": {"bywater": "http://localhost:8080"},
        "routes": {"conduit": "bywater"},
        "heavy_models": [],
    }
    tmp = Path("/tmp/test_routes_ac3.yaml")
    tmp.write_text(yaml.dump(config))

    router = HeadwaterRouter(config_path=tmp)
    register_router_metrics(router.app, router._name, router._config)
    client = TestClient(router.app)

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "version=0.0.4" in response.headers["content-type"]


def test_gpu_unavailable_shows_zero_and_omits_gpu_gauges():
    """AC-4: When pynvml.nvmlInit raises, gpu_available=0 and no GPU memory/util lines."""
    from unittest.mock import patch

    client = _make_client("bywater")

    with patch("pynvml.nvmlInit", side_effect=Exception("no GPU")):
        response = client.get("/metrics")

    assert response.status_code == 200
    text = response.text

    # headwater_gpu_available must be present with value 0
    lines = [l for l in text.splitlines() if "headwater_gpu_available" in l and not l.startswith("#")]
    assert lines, "headwater_gpu_available metric missing from response"
    assert any("0.0" in l for l in lines), f"expected gpu_available=0, got: {lines}"

    # GPU detail metrics must be absent when GPU is unavailable
    assert "headwater_gpu_memory_used" not in text
    assert "headwater_gpu_memory_free" not in text
    assert "headwater_gpu_memory_total" not in text
    assert "headwater_gpu_utilization" not in text
    assert "headwater_gpu_temperature" not in text

    # HTTP metrics from auto-instrumentation must still be present
    assert "http_server" in text or "http_request" in text


def test_ollama_unreachable_omits_ollama_metrics():
    """AC-5: When Ollama HTTP call raises ConnectError, no headwater_ollama_* lines appear."""
    from unittest.mock import patch
    import httpx

    client = _make_client("bywater")

    with patch("httpx.get", side_effect=httpx.ConnectError("ollama not running")):
        response = client.get("/metrics")

    assert response.status_code == 200
    text = response.text

    assert "headwater_ollama" not in text
