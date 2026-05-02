from __future__ import annotations
import time
import hw_log


def make_entry(message: str, request_id: str, extra: dict | None = None, ts: float | None = None) -> dict:
    return {
        "timestamp": ts or time.time(),
        "level": "DEBUG",
        "logger": "router",
        "message": message,
        "pathname": "/x.py",
        "request_id": request_id,
        "extra": extra,
    }


def test_proxy_request_creates_pending_row():
    """AC-4: proxy_request entry creates a pending row keyed by request_id."""
    pending: dict[str, hw_log.PendingRow] = {}
    seen: set[str] = set()
    completed: list[hw_log.PendingRow] = []

    entries = [make_entry("proxy_request", "req-1", {"service": "conduit", "backend": "http://x:8080", "path": "conduit/generate", "route": "conduit", "model": None})]
    hw_log.process_entries(entries, pending, seen, completed)

    assert "req-1" in pending
    assert pending["req-1"].service == "conduit"
    assert pending["req-1"].route == "conduit"
    assert not completed


def test_complete_row_emitted_after_all_three_events():
    """AC-4: row is completed and emitted when proxy_response + request_finished arrive."""
    pending: dict[str, hw_log.PendingRow] = {}
    seen: set[str] = set()
    completed: list[hw_log.PendingRow] = []

    entries = [
        make_entry("proxy_request", "req-2", {"service": "conduit", "backend": "http://x:8080", "path": "conduit/generate", "route": "conduit", "model": None}),
        make_entry("proxy_response", "req-2", {"upstream_status": 200}),
        make_entry("request_finished", "req-2", {"method": "POST", "duration_ms": 312.0}),
    ]
    hw_log.process_entries(entries, pending, seen, completed)

    assert "req-2" not in pending
    assert "req-2" in seen
    assert len(completed) == 1
    row = completed[0]
    assert row.upstream_status == 200
    assert row.method == "POST"
    assert row.duration_ms == 312.0


def test_internal_path_not_added_to_pending():
    """AC-9: proxy_request for /ping is not added to pending rows."""
    pending: dict[str, hw_log.PendingRow] = {}
    seen: set[str] = set()
    completed: list[hw_log.PendingRow] = []

    entries = [make_entry("proxy_request", "req-3", {"service": "ping", "backend": "http://x:8080", "path": "ping", "route": "ping", "model": None})]
    hw_log.process_entries(entries, pending, seen, completed)

    assert "req-3" not in pending
    assert not completed


def test_pending_row_timed_out_after_max_cycles():
    """AC-4: incomplete rows are emitted with None fields after MAX_PENDING_CYCLES poll increments."""
    pending: dict[str, hw_log.PendingRow] = {}
    seen: set[str] = set()
    completed: list[hw_log.PendingRow] = []

    entries = [make_entry("proxy_request", "req-4", {"service": "conduit", "backend": "http://x:8080", "path": "conduit/generate", "route": "conduit", "model": None})]
    hw_log.process_entries(entries, pending, seen, completed)

    for _ in range(hw_log.MAX_PENDING_CYCLES + 1):
        hw_log.process_entries([], pending, seen, completed)

    assert "req-4" not in pending
    assert len(completed) == 1
    assert completed[0].upstream_status is None


def test_already_seen_request_id_ignored():
    """AC-4: duplicate proxy_request for same request_id is ignored."""
    pending: dict[str, hw_log.PendingRow] = {}
    seen: set[str] = set(["req-5"])
    completed: list[hw_log.PendingRow] = []

    entries = [make_entry("proxy_request", "req-5", {"service": "conduit", "backend": "http://x:8080", "path": "conduit/generate", "route": "conduit", "model": None})]
    hw_log.process_entries(entries, pending, seen, completed)

    assert "req-5" not in pending
