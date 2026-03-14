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
