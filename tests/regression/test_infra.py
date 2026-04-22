"""
Regression tests — infrastructure endpoints.

Covers: /ping, /status, /routes, /logs/last, /sysinfo, /gpu, /metrics
across router (headwater), bywater, and deepwater.
"""

from __future__ import annotations

import pytest

from headwater_api.classes import (
    GpuResponse,
    GpuInfo,
    LogsLastResponse,
    RouterGpuResponse,
    StatusResponse,
)
from headwater_client.client.headwater_client import HeadwaterClient


class TestInfra:
    # -----------------------------------------------------------------------
    # /ping — all hosts
    # -----------------------------------------------------------------------

    def test_ping_router(self, router: HeadwaterClient) -> None:
        assert router.ping() is True

    def test_ping_bywater(self, bywater: HeadwaterClient) -> None:
        assert bywater.ping() is True

    def test_ping_deepwater(self, deepwater: HeadwaterClient) -> None:
        assert deepwater.ping() is True

    # -----------------------------------------------------------------------
    # /status — all hosts
    # -----------------------------------------------------------------------

    def test_status_returns_status_response(self, any_host: HeadwaterClient) -> None:
        resp = any_host.get_status()
        assert isinstance(resp, StatusResponse)

    def test_status_fields_present(self, any_host: HeadwaterClient) -> None:
        resp = any_host.get_status()
        assert resp.status in {"healthy", "degraded", "error"}
        assert isinstance(resp.message, str)
        assert isinstance(resp.models_available, list)
        assert isinstance(resp.gpu_enabled, bool)
        assert isinstance(resp.server_name, str)

    def test_status_uptime_positive(self, any_host: HeadwaterClient) -> None:
        resp = any_host.get_status()
        if resp.uptime is not None:
            assert resp.uptime > 0

    def test_status_server_name_bywater(self, bywater: HeadwaterClient) -> None:
        resp = bywater.get_status()
        assert "bywater" in resp.server_name.lower() or "Bywater" in resp.server_name

    def test_status_server_name_deepwater(self, deepwater: HeadwaterClient) -> None:
        resp = deepwater.get_status()
        assert "deepwater" in resp.server_name.lower() or "Deepwater" in resp.server_name

    # -----------------------------------------------------------------------
    # /routes — all hosts
    # -----------------------------------------------------------------------

    def test_router_get_routes_has_required_keys(self, router: HeadwaterClient) -> None:
        resp = router.get_routes()
        assert isinstance(resp, dict)
        for key in ("backends", "routes", "heavy_models", "config_path"):
            assert key in resp, f"missing key: {key}"

    def test_router_backends_non_empty(self, router: HeadwaterClient) -> None:
        resp = router.get_routes()
        assert len(resp["backends"]) > 0

    def test_router_routes_reference_known_backends(self, router: HeadwaterClient) -> None:
        resp = router.get_routes()
        backend_keys = set(resp["backends"].keys())
        for service, backend in resp["routes"].items():
            assert backend in backend_keys, (
                f"route '{service}' points to unknown backend '{backend}'"
            )

    def test_subserver_routes_is_list_of_dicts(self, subserver: HeadwaterClient) -> None:
        resp = subserver.list_routes()
        assert isinstance(resp, list)
        assert len(resp) > 0
        for route in resp:
            assert isinstance(route, dict)

    def test_subserver_routes_have_path_and_methods(self, subserver: HeadwaterClient) -> None:
        resp = subserver.list_routes()
        for route in resp:
            assert "path" in route
            assert "methods" in route or "name" in route

    # -----------------------------------------------------------------------
    # /logs/last — all hosts
    # -----------------------------------------------------------------------

    def test_logs_last_returns_logs_response(self, any_host: HeadwaterClient) -> None:
        resp = any_host.get_logs_last(n=10)
        assert isinstance(resp, LogsLastResponse)

    def test_logs_last_n1_returns_at_most_one(self, any_host: HeadwaterClient) -> None:
        resp = any_host.get_logs_last(n=1)
        assert len(resp.entries) <= 1

    def test_logs_last_capacity_non_negative(self, any_host: HeadwaterClient) -> None:
        resp = any_host.get_logs_last(n=10)
        assert resp.total_buffered >= 0
        assert resp.capacity >= 0

    def test_logs_last_entry_fields(self, any_host: HeadwaterClient) -> None:
        resp = any_host.get_logs_last(n=5)
        for entry in resp.entries:
            assert isinstance(entry.timestamp, float)
            assert isinstance(entry.level, str)
            assert isinstance(entry.logger, str)
            assert isinstance(entry.message, str)
            assert isinstance(entry.pathname, str)

    def test_logs_last_n_exceeds_capacity(self, any_host: HeadwaterClient) -> None:
        # Large n should not exceed capacity
        resp = any_host.get_logs_last(n=999999)
        assert len(resp.entries) <= resp.capacity

    # -----------------------------------------------------------------------
    # /sysinfo — subservers only
    # -----------------------------------------------------------------------

    def test_sysinfo_returns_dict(self, subserver: HeadwaterClient) -> None:
        resp = subserver.get_sysinfo()
        assert isinstance(resp, dict)

    def test_sysinfo_has_cpu_and_memory_fields(self, subserver: HeadwaterClient) -> None:
        resp = subserver.get_sysinfo()
        assert "cpu_percent" in resp
        assert "ram_total_bytes" in resp
        assert "ram_used_bytes" in resp

    def test_sysinfo_numeric_values_non_negative(self, subserver: HeadwaterClient) -> None:
        resp = subserver.get_sysinfo()
        for key in ("ram_total_bytes", "ram_used_bytes"):
            assert resp[key] >= 0, f"{key} must be non-negative"

    def test_sysinfo_cpu_percent_in_range(self, subserver: HeadwaterClient) -> None:
        resp = subserver.get_sysinfo()
        assert 0 <= resp["cpu_percent"] <= 100

    # -----------------------------------------------------------------------
    # /gpu — subservers
    # -----------------------------------------------------------------------

    def test_gpu_subserver_returns_gpu_response(self, subserver: HeadwaterClient) -> None:
        resp = subserver.get_gpu()
        assert isinstance(resp, GpuResponse)

    def test_gpu_subserver_has_server_name(self, subserver: HeadwaterClient) -> None:
        resp = subserver.get_gpu()
        assert isinstance(resp.server_name, str)
        assert len(resp.server_name) > 0

    def test_gpu_subserver_gpus_is_list(self, subserver: HeadwaterClient) -> None:
        resp = subserver.get_gpu()
        assert isinstance(resp.gpus, list)

    def test_gpu_subserver_gpu_fields_valid(self, subserver: HeadwaterClient) -> None:
        resp = subserver.get_gpu()
        for gpu in resp.gpus:
            assert isinstance(gpu, GpuInfo)
            assert abs(gpu.vram_free_mb + gpu.vram_used_mb - gpu.vram_total_mb) <= 10
            assert 0 <= gpu.utilization_pct <= 100

    def test_gpu_subserver_error_or_gpus(self, subserver: HeadwaterClient) -> None:
        resp = subserver.get_gpu()
        # Either error is set and gpus is empty, or error is None and gpus may be populated
        if resp.error is not None:
            assert resp.gpus == []
        else:
            assert isinstance(resp.gpus, list)

    # -----------------------------------------------------------------------
    # /gpu — router aggregation
    # -----------------------------------------------------------------------

    def test_gpu_router_returns_router_gpu_response(self, router: HeadwaterClient) -> None:
        resp = router.get_gpu()
        assert isinstance(resp, RouterGpuResponse)

    def test_gpu_router_backends_is_dict(self, router: HeadwaterClient) -> None:
        resp = router.get_gpu()
        assert isinstance(resp.backends, dict)

    def test_gpu_router_backends_non_empty(self, router: HeadwaterClient) -> None:
        resp = router.get_gpu()
        assert len(resp.backends) > 0

    def test_gpu_router_backends_are_gpu_responses(self, router: HeadwaterClient) -> None:
        resp = router.get_gpu()
        for backend_name, gpu_resp in resp.backends.items():
            assert isinstance(gpu_resp, GpuResponse), (
                f"backend '{backend_name}' is not a GpuResponse"
            )

    # -----------------------------------------------------------------------
    # /metrics — all hosts
    # -----------------------------------------------------------------------

    def test_metrics_returns_string(self, any_host: HeadwaterClient) -> None:
        resp = any_host.get_metrics()
        assert isinstance(resp, str)

    def test_metrics_not_empty(self, any_host: HeadwaterClient) -> None:
        resp = any_host.get_metrics()
        assert len(resp.strip()) > 0

    def test_metrics_contains_help_or_type_line(self, any_host: HeadwaterClient) -> None:
        resp = any_host.get_metrics()
        lines = resp.splitlines()
        has_meta = any(line.startswith("# HELP") or line.startswith("# TYPE") for line in lines)
        assert has_meta, "metrics response must contain at least one # HELP or # TYPE line"

    def test_metrics_router_has_backend_up(self, router: HeadwaterClient) -> None:
        resp = router.get_metrics()
        assert "headwater_backend_up" in resp

    def test_metrics_subserver_has_gpu_metric(self, subserver: HeadwaterClient) -> None:
        resp = subserver.get_metrics()
        assert "headwater_gpu_available" in resp
