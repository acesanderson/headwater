from __future__ import annotations
import pytest
from pydantic import ValidationError

from headwater_api.classes import AnthropicMessage
from headwater_api.classes import AnthropicRequest


def test_anthropic_request_minimal():
    """AC-1: AnthropicRequest accepts model, max_tokens, messages"""
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[AnthropicMessage(role="user", content="Hello")],
    )
    assert req.model == "claude-sonnet-4-6"
    assert req.max_tokens == 1024
    assert req.stream is False


def test_anthropic_request_with_system():
    """AC-1: system is optional, defaults to None"""
    req = AnthropicRequest(
        model="gpt-oss:latest",
        max_tokens=512,
        messages=[AnthropicMessage(role="user", content="Hi")],
        system="You are a helpful assistant.",
    )
    assert req.system == "You are a helpful assistant."


def test_anthropic_message_content_as_blocks():
    """AC-1: content can be a list of content blocks"""
    msg = AnthropicMessage(
        role="user",
        content=[{"type": "text", "text": "Hello from block"}],
    )
    assert msg.content[0].text == "Hello from block"


def test_anthropic_request_rejects_invalid_max_tokens():
    """AC-1: max_tokens must be >= 1"""
    with pytest.raises(ValidationError):
        AnthropicRequest(
            model="gpt-oss:latest",
            max_tokens=0,
            messages=[AnthropicMessage(role="user", content="Hi")],
        )


def test_anthropic_request_rejects_empty_messages():
    """AC-1: messages must have at least one item"""
    with pytest.raises(ValidationError):
        AnthropicRequest(
            model="gpt-oss:latest",
            max_tokens=512,
            messages=[],
        )


from unittest.mock import patch, MagicMock, AsyncMock
from tests.conftest import make_mock_result

VALID_ANTHROPIC_PAYLOAD = {
    "model": "gpt-oss:latest",
    "max_tokens": 512,
    "messages": [{"role": "user", "content": "Hello"}],
}


def test_anthropic_valid_request_returns_200(client):
    """AC-2: valid non-streaming request -> HTTP 200"""
    mock_result = make_mock_result(content="Hi there!", input_tokens=10, output_tokens=5)
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=VALID_ANTHROPIC_PAYLOAD)
    assert response.status_code == 200


def test_anthropic_response_shape(client):
    """AC-2: response has type, role, content list, stop_reason, usage"""
    mock_result = make_mock_result(content="Hi there!", input_tokens=10, output_tokens=5)
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=VALID_ANTHROPIC_PAYLOAD)
    body = response.json()
    assert body["type"] == "message"
    assert body["role"] == "assistant"
    assert isinstance(body["content"], list)
    assert body["content"][0]["type"] == "text"
    assert body["content"][0]["text"] == "Hi there!"
    assert body["stop_reason"] == "end_turn"
    assert body["usage"]["input_tokens"] == 10
    assert body["usage"]["output_tokens"] == 5


def test_anthropic_response_model_echoes_request(client):
    """AC-2: response.model matches request.model"""
    mock_result = make_mock_result()
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=VALID_ANTHROPIC_PAYLOAD)
    assert response.json()["model"] == VALID_ANTHROPIC_PAYLOAD["model"]


def test_stream_true_returns_422(client):
    """AC-3: stream=true rejected with 422 in Phase 1"""
    payload = {**VALID_ANTHROPIC_PAYLOAD, "stream": True}
    response = client.post("/v1/messages", json=payload)
    assert response.status_code == 422
    assert "Streaming" in response.text
