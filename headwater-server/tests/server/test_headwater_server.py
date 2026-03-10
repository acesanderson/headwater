from __future__ import annotations

from headwater_server.server.headwater import HeadwaterServer


def test_headwater_server_default_title():
    """AC-8: Default title is 'Headwater API Server'."""
    server = HeadwaterServer()
    assert server.app.title == "Headwater API Server"


def test_headwater_server_custom_title():
    """AC-8: HeadwaterServer accepts a name parameter that sets the FastAPI app title."""
    server = HeadwaterServer(name="Bywater API Server")
    assert server.app.title == "Bywater API Server"


import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from headwater_api.classes import StatusResponse


def _make_mock_status(server_name: str) -> StatusResponse:
    return StatusResponse(
        status="healthy",
        message="Server is running",
        models_available=[],
        gpu_enabled=False,
        uptime=1.0,
        server_name=server_name,
    )


def test_status_response_has_server_name_field():
    """AC-11: StatusResponse model has a server_name field."""
    assert "server_name" in StatusResponse.model_fields


def test_status_endpoint_returns_server_name_headwater():
    """AC-11: /status returns server_name='Headwater API Server' by default."""
    server = HeadwaterServer()
    client = TestClient(server.app)

    with patch(
        "headwater_server.services.status_service.get_status.get_status_service",
        new=AsyncMock(return_value=_make_mock_status("Headwater API Server")),
    ):
        response = client.get("/status")

    assert response.status_code == 200
    assert response.json()["server_name"] == "Headwater API Server"


def test_status_endpoint_returns_server_name_bywater():
    """AC-11: /status returns server_name='Bywater API Server' when name is set."""
    server = HeadwaterServer(name="Bywater API Server")
    client = TestClient(server.app)

    with patch(
        "headwater_server.services.status_service.get_status.get_status_service",
        new=AsyncMock(return_value=_make_mock_status("Bywater API Server")),
    ):
        response = client.get("/status")

    assert response.status_code == 200
    assert response.json()["server_name"] == "Bywater API Server"


def test_get_status_service_receives_server_name():
    """AC-11: get_status_service is called with the correct server_name from HeadwaterServer."""
    server = HeadwaterServer(name="Bywater API Server")
    client = TestClient(server.app)

    captured_args = {}

    async def mock_status_service(startup_time, server_name="Headwater API Server"):
        captured_args["server_name"] = server_name
        return _make_mock_status(server_name)

    with patch(
        "headwater_server.services.status_service.get_status.get_status_service",
        new=mock_status_service,
    ):
        client.get("/status")

    assert captured_args["server_name"] == "Bywater API Server"
