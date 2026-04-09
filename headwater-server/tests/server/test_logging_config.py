from __future__ import annotations

import logging

from rich.logging import RichHandler


def test_rich_handler_format_is_message_only():
    """AC-1: RichHandler must use '%(message)s' only — no level embedded in message body."""
    # Import the logging_config module which runs its top-level code
    from headwater_server.server import logging_config

    # Access the rich_handler object directly from the module
    handler = logging_config.rich_handler
    assert handler is not None, "rich_handler not found in logging_config module"
    assert isinstance(handler, RichHandler), f"Expected RichHandler, got {type(handler)}"
    assert handler.formatter is not None, "RichHandler has no formatter set"
    assert handler.formatter._fmt == "%(message)s", (
        f"Expected '%(message)s', got '{handler.formatter._fmt}'"
    )


def test_request_id_var_default_is_system():
    """AC-5: Outside any request context, request_id_var defaults to 'system'."""
    from headwater_server.server.context import request_id_var
    assert request_id_var.get() == "system"


def test_request_id_injected_into_log_record(caplog):
    """AC-5: Every log record carries request_id='system' outside a request context."""
    import logging
    import headwater_server.server.logging_config  # ensure record factory is registered

    with caplog.at_level(logging.INFO, logger="test.sentinel"):
        logging.getLogger("test.sentinel").info("startup event")

    assert caplog.records, "No log records captured"
    record = caplog.records[-1]
    assert hasattr(record, "request_id"), "request_id not injected into LogRecord"
    assert record.request_id == "system"


def test_third_party_loggers_suppressed_at_warning():
    """AC-9: Noisy third-party loggers are set to WARNING; uvicorn.error is untouched."""
    import logging
    import headwater_server.server.logging_config

    suppressed = ["httpx", "httpcore", "sentence_transformers", "conduit", "uvicorn.access"]
    for name in suppressed:
        level = logging.getLogger(name).level
        assert level == logging.WARNING, (
            f"Logger '{name}' has level {logging.getLevelName(level)}, expected WARNING"
        )

    # uvicorn.error must NOT be suppressed
    uvicorn_error_level = logging.getLogger("uvicorn.error").level
    assert uvicorn_error_level != logging.WARNING, (
        "uvicorn.error must not be suppressed — it reports worker crashes"
    )


def test_log_entry_has_extra_field():
    """LogEntry accepts extra dict with primitive values."""
    from headwater_api.classes.server_classes.logs import LogEntry
    entry = LogEntry(
        timestamp=1.0, level="DEBUG", logger="test", message="msg",
        pathname="/x.py", request_id="abc",
        extra={"service": "conduit", "upstream_status": 200, "model": None},
    )
    assert entry.extra == {"service": "conduit", "upstream_status": 200, "model": None}


def test_log_entry_extra_defaults_to_none():
    """LogEntry.extra is None when not provided (backward compat)."""
    from headwater_api.classes.server_classes.logs import LogEntry
    entry = LogEntry(timestamp=1.0, level="DEBUG", logger="t", message="m", pathname="/p")
    assert entry.extra is None


def test_ring_buffer_extra_serializes_service_field(caplog):
    """Ring buffer get_records() includes 'service' from logger.extra in the LogEntry.extra dict."""
    import logging
    import headwater_server.server.logging_config  # ensure record factory registered
    from headwater_server.server.logging_config import ring_buffer

    before = len(list(ring_buffer._buffer))
    logging.getLogger("test.extra").debug("proxy_request", extra={"service": "conduit", "backend": "http://x:8080"})

    records = ring_buffer.get_records(500)
    new = [r for r in records[before:] if r["message"] == "proxy_request"]
    assert new, "proxy_request record not found in ring buffer"
    assert new[-1].get("extra", {}).get("service") == "conduit"
    assert new[-1].get("extra", {}).get("backend") == "http://x:8080"


def test_ring_buffer_extra_excludes_standard_log_attrs(caplog):
    """Standard LogRecord attributes are not duplicated in extra."""
    import logging
    import headwater_server.server.logging_config
    from headwater_server.server.logging_config import ring_buffer

    before = len(list(ring_buffer._buffer))
    logging.getLogger("test.nodup").debug("sentinel_noduplicate", extra={"my_field": "value"})

    records = ring_buffer.get_records(500)
    new = [r for r in records[before:] if r["message"] == "sentinel_noduplicate"]
    assert new, "record not found"
    extra = new[-1].get("extra") or {}
    # Standard attrs must not appear in extra
    for banned in ("name", "levelname", "pathname", "filename", "lineno", "funcName"):
        assert banned not in extra, f"standard attr '{banned}' leaked into extra"
    assert extra.get("my_field") == "value"
