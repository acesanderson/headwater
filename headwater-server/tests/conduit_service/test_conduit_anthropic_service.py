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



def test_unknown_model_returns_400(client):
    """AC-4: unrecognized model -> HTTP 400 with model name in detail"""
    payload = {**VALID_ANTHROPIC_PAYLOAD, "model": "nonexistent-model-xyz"}
    with patch(
        "conduit.core.model.models.modelstore.ModelStore.validate_model",
        side_effect=ValueError("Model not found"),
    ):
        response = client.post("/v1/messages", json=payload)
    assert response.status_code == 400
    assert "nonexistent-model-xyz" in response.json()["detail"]


def test_model_store_unavailable_returns_502(client):
    """AC-4: missing model store -> HTTP 502"""
    with patch(
        "conduit.core.model.models.modelstore.ModelStore.validate_model",
        side_effect=FileNotFoundError("aliases.json not found"),
    ):
        response = client.post("/v1/messages", json=VALID_ANTHROPIC_PAYLOAD)
    assert response.status_code == 502
    assert "unavailable" in response.json()["detail"]


import json


def _parse_sse_events(body: str) -> list[dict]:
    """Parse raw SSE body into list of {event, data} dicts."""
    events = []
    for block in body.split("\n\n"):
        lines = [l for l in block.strip().split("\n") if l]
        if not lines:
            continue
        event_type = None
        data = None
        for line in lines:
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_type and data is not None:
            events.append({"event": event_type, "data": data})
    return events


def test_stream_true_returns_event_stream(client):
    """AC-5: stream=true -> Content-Type: text/event-stream"""
    mock_result = make_mock_result(content="Streaming response.", input_tokens=10, output_tokens=4)
    payload = {**VALID_ANTHROPIC_PAYLOAD, "stream": True}
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


def test_stream_sse_event_sequence(client):
    """AC-5: SSE body contains valid Anthropic event sequence in correct order"""
    mock_result = make_mock_result(content="Hello!", input_tokens=8, output_tokens=3)
    payload = {**VALID_ANTHROPIC_PAYLOAD, "stream": True}
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=payload)
    events = _parse_sse_events(response.text)
    event_types = [e["event"] for e in events]
    assert event_types == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


def test_stream_content_block_delta_has_text(client):
    """AC-5: content_block_delta carries the full response text"""
    mock_result = make_mock_result(content="Hello!", input_tokens=8, output_tokens=3)
    payload = {**VALID_ANTHROPIC_PAYLOAD, "stream": True}
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=payload)
    events = _parse_sse_events(response.text)
    delta_event = next(e for e in events if e["event"] == "content_block_delta")
    assert delta_event["data"]["delta"]["text"] == "Hello!"


def test_stream_message_delta_has_stop_reason(client):
    """AC-5: message_delta carries stop_reason=end_turn and output_tokens"""
    mock_result = make_mock_result(content="Done.", input_tokens=5, output_tokens=2)
    payload = {**VALID_ANTHROPIC_PAYLOAD, "stream": True}
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=payload)
    events = _parse_sse_events(response.text)
    msg_delta = next(e for e in events if e["event"] == "message_delta")
    assert msg_delta["data"]["delta"]["stop_reason"] == "end_turn"
    assert msg_delta["data"]["usage"]["output_tokens"] == 2
