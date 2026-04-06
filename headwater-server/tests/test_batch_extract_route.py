from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from headwater_api.classes import BatchExtractResponse
from headwater_api.classes import ExtractResult


@pytest.fixture()
def client():
    from headwater_server.api.siphon_server_api import SiphonServerAPI
    app = FastAPI()
    SiphonServerAPI(app).register_routes()
    return TestClient(app)


def test_batch_extract_route_returns_200(client):
    mock_resp = BatchExtractResponse(results=[
        ExtractResult(source="a.pdf", text="text", error=None),
    ])
    with patch(
        "headwater_server.api.siphon_server_api.batch_extract_siphon_service",
        new=AsyncMock(return_value=mock_resp),
    ):
        resp = client.post(
            "/siphon/extract/batch",
            json={"sources": ["a.pdf"], "max_concurrent": 5},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["source"] == "a.pdf"
    assert data["results"][0]["text"] == "text"


def test_batch_extract_route_does_not_500_on_per_item_error(client):
    """Per-item errors are encoded in ExtractResult.error, never HTTP 500."""
    mock_resp = BatchExtractResponse(results=[
        ExtractResult(source="bad.pdf", text=None, error="docling failed"),
    ])
    with patch(
        "headwater_server.api.siphon_server_api.batch_extract_siphon_service",
        new=AsyncMock(return_value=mock_resp),
    ):
        resp = client.post(
            "/siphon/extract/batch",
            json={"sources": ["bad.pdf"], "max_concurrent": 5},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["text"] is None
    assert data["results"][0]["error"] == "docling failed"
