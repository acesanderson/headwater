"""
Regression tests — Router-specific behavior.

Covers: catch-all proxy routing, heavy model routing, reranker routing,
        unknown service → 400, correlation middleware (X-Request-ID),
        /routes/ config contents, router-native endpoints registered before catch-all.

All tests hit the router (headwater) only.
Raw HTTP is used where the HeadwaterClient does not expose the needed interface.
"""

from __future__ import annotations

import json
import re
import uuid

import pytest
import requests

from conduit.domain.config.conduit_options import ConduitOptions
from conduit.domain.message.message import UserMessage
from conduit.domain.request.generation_params import GenerationParams
from conduit.domain.request.request import GenerationRequest
from headwater_api.classes import (
    HeadwaterServerException,
    RerankRequest,
    RouterGpuResponse,
)
from headwater_client.client.headwater_client import HeadwaterClient
from headwater_client.transport.headwater_transport import HeadwaterTransport

MODEL = "gpt-oss:latest"
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _router_base_url(router: HeadwaterClient) -> str:
    return router._transport.base_url


class TestRouting:
    # -----------------------------------------------------------------------
    # GET /routes/ — router config contents
    # -----------------------------------------------------------------------

    def test_routes_has_required_keys(self, router: HeadwaterClient) -> None:
        resp = router.get_routes()
        for key in ("backends", "routes", "heavy_models", "config_path"):
            assert key in resp, f"missing key: {key}"

    def test_routes_backends_non_empty(self, router: HeadwaterClient) -> None:
        resp = router.get_routes()
        assert isinstance(resp["backends"], dict)
        assert len(resp["backends"]) > 0

    def test_routes_all_route_values_are_known_backends(self, router: HeadwaterClient) -> None:
        resp = router.get_routes()
        backend_keys = set(resp["backends"].keys())
        for service, backend in resp["routes"].items():
            assert backend in backend_keys, (
                f"route '{service}' → '{backend}' is not a known backend"
            )

    def test_routes_heavy_models_is_list(self, router: HeadwaterClient) -> None:
        resp = router.get_routes()
        assert isinstance(resp["heavy_models"], list)

    def test_routes_config_path_is_string(self, router: HeadwaterClient) -> None:
        resp = router.get_routes()
        assert isinstance(resp["config_path"], str)

    # -----------------------------------------------------------------------
    # Catch-all proxy — light model routed correctly
    # -----------------------------------------------------------------------

    def test_light_model_proxied_successfully(self, router: HeadwaterClient) -> None:
        # gpt-oss:latest assumed not in heavy_models
        heavy_models = router.get_routes().get("heavy_models", [])
        if MODEL in heavy_models:
            pytest.skip(f"{MODEL} is in heavy_models on this deployment")
        req = GenerationRequest(
            messages=[UserMessage(content="Say hi.")],
            params=GenerationParams(model=MODEL),
            options=ConduitOptions(project_name="headwater-regression"),
        )
        resp = router.conduit.query_generate(req)
        assert resp is not None

    def test_light_model_proxy_request_logged(self, router: HeadwaterClient) -> None:
        heavy_models = router.get_routes().get("heavy_models", [])
        if MODEL in heavy_models:
            pytest.skip(f"{MODEL} is in heavy_models on this deployment")
        req = GenerationRequest(
            messages=[UserMessage(content="Say hi.")],
            params=GenerationParams(model=MODEL),
            options=ConduitOptions(project_name="headwater-regression"),
        )
        router.conduit.query_generate(req)
        logs = router.get_logs_last(n=30)
        log_messages = [e.message for e in logs.entries]
        has_proxy_log = any(
            "proxy_request" in m or "proxy_response" in m for m in log_messages
        )
        assert has_proxy_log, "router should log proxy_request or proxy_response for proxied call"

    # -----------------------------------------------------------------------
    # Catch-all proxy — unknown service → 400
    # -----------------------------------------------------------------------

    def test_unknown_service_returns_400(self, router: HeadwaterClient) -> None:
        base = _router_base_url(router)
        resp = requests.post(
            f"{base}/nonexistent_service_xyz/endpoint",
            json={"dummy": "payload"},
            timeout=10,
        )
        assert resp.status_code == 400

    def test_unknown_service_error_type_routing_error(self, router: HeadwaterClient) -> None:
        base = _router_base_url(router)
        resp = requests.post(
            f"{base}/nonexistent_service_xyz/endpoint",
            json={"dummy": "payload"},
            timeout=10,
        )
        data = resp.json()
        assert data.get("error_type") == "routing_error"

    def test_unknown_service_message_mentions_service(self, router: HeadwaterClient) -> None:
        base = _router_base_url(router)
        service_name = "nonexistent_service_xyz"
        resp = requests.post(
            f"{base}/{service_name}/endpoint",
            json={"dummy": "payload"},
            timeout=10,
        )
        data = resp.json()
        # message should reference the unknown service name
        assert service_name in data.get("message", "")

    # -----------------------------------------------------------------------
    # Correlation middleware — X-Request-ID header
    # -----------------------------------------------------------------------

    def test_response_always_has_x_request_id(self, router: HeadwaterClient) -> None:
        base = _router_base_url(router)
        resp = requests.get(f"{base}/ping", timeout=5)
        assert "x-request-id" in resp.headers or "X-Request-ID" in resp.headers

    def test_valid_uuid_echoed_back(self, router: HeadwaterClient) -> None:
        base = _router_base_url(router)
        client_uuid = str(uuid.uuid4())
        resp = requests.get(
            f"{base}/ping", headers={"X-Request-ID": client_uuid}, timeout=5
        )
        returned_id = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID", "")
        assert returned_id == client_uuid, (
            f"router should echo valid UUIDv4 back; got '{returned_id}'"
        )

    def test_no_request_id_gets_new_uuid(self, router: HeadwaterClient) -> None:
        base = _router_base_url(router)
        resp = requests.get(f"{base}/ping", timeout=5)
        returned_id = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID", "")
        assert _UUID4_RE.match(returned_id), (
            f"router should assign a UUIDv4 when none provided; got '{returned_id}'"
        )

    def test_invalid_request_id_gets_new_uuid(self, router: HeadwaterClient) -> None:
        base = _router_base_url(router)
        resp = requests.get(
            f"{base}/ping", headers={"X-Request-ID": "not-a-uuid"}, timeout=5
        )
        returned_id = resp.headers.get("x-request-id") or resp.headers.get("X-Request-ID", "")
        # Router should replace invalid value with a fresh UUID
        assert returned_id != "not-a-uuid"
        assert _UUID4_RE.match(returned_id), (
            f"router should assign a new UUIDv4 when given invalid value; got '{returned_id}'"
        )

    # -----------------------------------------------------------------------
    # Router-native endpoints (registered before catch-all)
    # -----------------------------------------------------------------------

    def test_ping_not_proxied(self, router: HeadwaterClient) -> None:
        # /ping must return {"message": "pong"} directly from the router, not be proxied
        base = _router_base_url(router)
        resp = requests.get(f"{base}/ping", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("message") == "pong"

    def test_status_not_proxied(self, router: HeadwaterClient) -> None:
        resp = router.get_status()
        # If this were proxied to bywater/deepwater the server_name would differ
        # We just assert the response is a well-formed status from the router
        assert resp.status in {"healthy", "degraded", "error"}

    def test_logs_last_not_proxied(self, router: HeadwaterClient) -> None:
        resp = router.get_logs_last(n=5)
        # Logs buffer exists on the router
        assert resp.capacity > 0

    # -----------------------------------------------------------------------
    # GET /metrics — router-native, contains headwater_backend_up
    # -----------------------------------------------------------------------

    def test_metrics_not_proxied_contains_backend_up(self, router: HeadwaterClient) -> None:
        resp = router.get_metrics()
        assert "headwater_backend_up" in resp, (
            "/metrics must be handled by the router (not proxied) and expose backend_up metric"
        )

    def test_metrics_content_type_prometheus(self, router: HeadwaterClient) -> None:
        base = _router_base_url(router)
        resp = requests.get(f"{base}/metrics", timeout=10)
        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "text/plain" in ct, f"unexpected Content-Type: {ct}"

    # -----------------------------------------------------------------------
    # GET /gpu — router aggregates all backends
    # -----------------------------------------------------------------------

    def test_router_gpu_backends_match_routes_config(self, router: HeadwaterClient) -> None:
        gpu_resp = router.get_gpu()
        assert isinstance(gpu_resp, RouterGpuResponse)
        routes_resp = router.get_routes()
        # Every backend in routes config should have a corresponding GPU entry
        config_backends = set(routes_resp["backends"].keys())
        gpu_backends = set(gpu_resp.backends.keys())
        assert config_backends == gpu_backends, (
            f"GPU backends {gpu_backends} differ from routes.yaml backends {config_backends}"
        )

    # -----------------------------------------------------------------------
    # Heavy model routing — conditional on deployment config
    # -----------------------------------------------------------------------

    def test_heavy_model_route_logged_if_present(self, router: HeadwaterClient) -> None:
        routes = router.get_routes()
        heavy_models = routes.get("heavy_models", [])
        if not heavy_models:
            pytest.skip("No heavy models configured in routes.yaml")
        heavy_model = heavy_models[0]
        req = GenerationRequest(
            messages=[UserMessage(content="Say hi.")],
            params=GenerationParams(model=heavy_model),
            options=ConduitOptions(project_name="headwater-regression"),
        )
        try:
            router.conduit.query_generate(req)
        except HeadwaterServerException as exc:
            # 503 backend_unavailable is acceptable if heavy backend is down
            if exc.server_error.error_type.value in (
                "backend_unavailable",
                "backend_timeout",
            ):
                pass
            else:
                raise
        logs = router.get_logs_last(n=30)
        log_messages = [e.message for e in logs.entries]
        # At minimum there should be a proxy_request or routing log
        assert any("proxy" in m.lower() or "route" in m.lower() for m in log_messages)

    # -----------------------------------------------------------------------
    # Reranker routing — light path (default model)
    # -----------------------------------------------------------------------

    def test_reranker_light_path_routed(self, router: HeadwaterClient) -> None:
        req = RerankRequest(
            query="machine learning",
            documents=["doc one", "doc two", "doc three"],
            model_name="flash",
        )
        resp = router.reranker.rerank(req)
        assert resp is not None
        assert len(resp.results) > 0
