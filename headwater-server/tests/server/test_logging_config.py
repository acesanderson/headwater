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
