from __future__ import annotations
import pytest
from unittest.mock import MagicMock


def make_mock_result(
    content: str = "Hello, world!",
    stop_reason=None,
    input_tokens: int = 10,
    output_tokens: int = 5,
    parsed=None,
):
    from conduit.domain.result.response_metadata import StopReason
    if stop_reason is None:
        stop_reason = StopReason.STOP
    message = MagicMock()
    message.__str__ = MagicMock(return_value=content)
    message.parsed = parsed
    metadata = MagicMock()
    metadata.stop_reason = stop_reason
    metadata.input_tokens = input_tokens
    metadata.output_tokens = output_tokens
    metadata.cache_hit = False
    metadata.duration = 100.0
    result = MagicMock()
    result.message = message
    result.metadata = metadata
    return result


VALID_PAYLOAD = {
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Hello"}],
}


@pytest.fixture
def client():
    from headwater_server.server.headwater import app
    from fastapi.testclient import TestClient
    return TestClient(app)
