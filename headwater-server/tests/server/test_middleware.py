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


import pytest


@pytest.mark.parametrize("bad_value", [
    "not-a-uuid",
    "",
    "12345",
    "550e8400-e29b-11d4-a716-446655440000",  # UUID v1 — invalid for our purposes
])
def test_invalid_request_id_falls_back_to_generated_uuid4(bad_value):
    """AC-4: Invalid X-Request-ID values produce a server-generated UUID4; no error raised."""
    client = _make_client()
    response = client.get("/ping", headers={"X-Request-ID": bad_value})
    assert response.status_code == 200
    returned_id = response.headers.get("X-Request-ID")
    assert returned_id is not None
    assert returned_id != bad_value or bad_value == ""  # always replaced
    parsed = uuid.UUID(returned_id)
    assert parsed.version == 4


def test_two_requests_carry_distinct_request_ids(caplog):
    """AC-2: Two requests produce distinct request_ids; filtering by either yields its own events."""
    import logging
    client = _make_client()

    with caplog.at_level(logging.INFO):
        r1 = client.get("/ping")
        r2 = client.get("/ping")

    id1 = r1.headers["X-Request-ID"]
    id2 = r2.headers["X-Request-ID"]
    assert id1 != id2, "Two sequential requests must have distinct request_ids"

    r1_records = [r for r in caplog.records if getattr(r, "request_id", None) == id1]
    r2_records = [r for r in caplog.records if getattr(r, "request_id", None) == id2]

    assert len(r1_records) >= 2, f"Expected at least request_started+request_finished for id1, got {len(r1_records)}"
    assert len(r2_records) >= 2, f"Expected at least request_started+request_finished for id2, got {len(r2_records)}"

    r1_messages = [r.message for r in r1_records]
    assert "request_started" in r1_messages
    assert "request_finished" in r1_messages

    r2_messages = [r.message for r in r2_records]
    assert "request_started" in r2_messages
    assert "request_finished" in r2_messages


def test_request_id_matches_in_500_error_body_and_header():
    """AC-10: On 500, X-Request-ID response header matches request_id in HeadwaterServerError body."""
    from headwater_server.server.headwater import HeadwaterServer

    server = HeadwaterServer()

    @server.app.get("/force-500")
    async def boom():
        raise RuntimeError("deliberate failure")

    client = TestClient(server.app, raise_server_exceptions=False)
    response = client.get("/force-500")

    assert response.status_code == 500
    header_id = response.headers.get("X-Request-ID")
    assert header_id is not None

    body = response.json()
    body_request_id = body.get("request_id")
    assert body_request_id == header_id, (
        f"Header request_id '{header_id}' != body request_id '{body_request_id}'"
    )
