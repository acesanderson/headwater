from __future__ import annotations

import uuid
from fastapi.testclient import TestClient


def _make_client():
    from headwater_server.server.headwater import HeadwaterServer
    return TestClient(HeadwaterServer().app)


def test_valid_request_id_is_echoed_in_response_header():
    """AC-3: A valid UUID4 X-Request-ID header is echoed back unchanged."""
    client = _make_client()
    supplied_id = str(uuid.uuid4())
    response = client.get("/ping", headers={"X-Request-ID": supplied_id})
    assert response.headers.get("X-Request-ID") == supplied_id


def test_no_request_id_header_generates_uuid4():
    """AC-3: When no header is supplied, a UUID4 is generated and returned."""
    client = _make_client()
    response = client.get("/ping")
    returned_id = response.headers.get("X-Request-ID")
    assert returned_id is not None
    parsed = uuid.UUID(returned_id)
    assert parsed.version == 4
