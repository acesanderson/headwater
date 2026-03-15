from __future__ import annotations

from fastapi.testclient import TestClient


def test_logs_last_entries_have_request_id_field():
    """AC-7: Every LogEntry in /logs/last response contains a request_id key."""
    from headwater_server.server.headwater import HeadwaterServer

    server = HeadwaterServer()
    client = TestClient(server.app)

    # Generate some log traffic
    client.get("/ping")
    client.get("/ping")

    response = client.get("/logs/last?n=10")
    assert response.status_code == 200

    data = response.json()
    entries = data.get("entries", [])
    assert entries, "No log entries returned — ring buffer may be empty"

    for entry in entries:
        assert "request_id" in entry, (
            f"LogEntry missing request_id field: {entry}"
        )


def test_logs_last_request_scoped_entries_carry_uuid():
    """AC-7: Entries from request-scoped events carry a UUID4 string as request_id."""
    import uuid
    from headwater_server.server.headwater import HeadwaterServer

    server = HeadwaterServer()
    client = TestClient(server.app)
    client.get("/ping")

    response = client.get("/logs/last?n=20")
    data = response.json()

    request_scoped = [
        e for e in data["entries"]
        if e.get("request_id") not in (None, "system")
    ]
    assert request_scoped, "No request-scoped entries found"

    for entry in request_scoped:
        rid = entry["request_id"]
        try:
            parsed = uuid.UUID(rid)
            assert parsed.version == 4
        except (ValueError, AssertionError):
            raise AssertionError(f"request_id '{rid}' is not a valid UUID4")
