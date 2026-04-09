from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


@pytest.fixture
def bywater_client():
    from headwater_server.server.headwater import app
    return TestClient(app)


def test_sysinfo_endpoint_returns_200(bywater_client: TestClient):
    """AC-1: GET /sysinfo returns 200 with required fields."""
    mock_data = {"cpu_percent": 12.4, "ram_used_bytes": 4_000_000_000, "ram_total_bytes": 16_000_000_000}
    with patch(
        "headwater_server.services.status_service.sysinfo_service.get_sysinfo_service",
        new=AsyncMock(return_value=mock_data),
    ):
        resp = bywater_client.get("/sysinfo")
    assert resp.status_code == 200
    body = resp.json()
    assert "cpu_percent" in body
    assert "ram_used_bytes" in body
    assert "ram_total_bytes" in body


def test_sysinfo_endpoint_before_catch_all(bywater_client: TestClient):
    """AC-1: /sysinfo is reachable (not swallowed by any catch-all route)."""
    resp = bywater_client.get("/sysinfo")
    # Any response other than 404/405 is acceptable here
    assert resp.status_code != 404
