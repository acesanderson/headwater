from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_metrics_state():
    """Reset OTel and prometheus_client state between tests for isolation."""
    from opentelemetry import metrics as otel_metrics
    from prometheus_client import REGISTRY

    otel_metrics.set_meter_provider(otel_metrics.NoOpMeterProvider())
    before = set(REGISTRY._names_to_collectors.keys())

    yield

    otel_metrics.set_meter_provider(otel_metrics.NoOpMeterProvider())
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
