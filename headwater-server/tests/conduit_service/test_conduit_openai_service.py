from __future__ import annotations
import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from tests.conftest import VALID_PAYLOAD, make_mock_result


def test_unrecognized_model_returns_400(client):
    """AC10: unrecognized model name after prefix strip -> HTTP 400"""
    bad_payload = {**VALID_PAYLOAD, "model": "nonexistent-model-xyz"}
    with patch(
        "conduit.core.model.models.modelstore.ModelStore.validate_model",
        side_effect=ValueError("Model not found"),
    ):
        response = client.post("/v1/chat/completions", json=bad_payload)
    assert response.status_code == 400
    assert "nonexistent-model-xyz" in response.json()["detail"]


def test_model_store_unavailable_returns_502(client):
    """AC11: missing/corrupt aliases.json or models.json -> HTTP 502"""
    with patch(
        "conduit.core.model.models.modelstore.ModelStore.validate_model",
        side_effect=FileNotFoundError("aliases.json not found"),
    ):
        response = client.post("/v1/chat/completions", json=VALID_PAYLOAD)
    assert response.status_code == 502
    assert "Model store unavailable" in response.json()["detail"]


def test_valid_request_returns_200_and_validates_as_chat_completion(client):
    """AC1: valid request -> HTTP 200, body passes ChatCompletion.model_validate()"""
    from openai.types.chat import ChatCompletion
    mock_result = make_mock_result()
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/chat/completions", json=VALID_PAYLOAD)
    assert response.status_code == 200
    ChatCompletion.model_validate(response.json())


def test_response_content_is_non_empty_string(client):
    """AC2: choices[0].message.content is a non-empty string"""
    mock_result = make_mock_result(content="This is the response.")
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/chat/completions", json=VALID_PAYLOAD)
    content = response.json()["choices"][0]["message"]["content"]
    assert isinstance(content, str)
    assert len(content) > 0


def test_finish_reason_is_valid_value(client):
    """AC3: finish_reason is one of the allowed OpenAI values"""
    from conduit.domain.result.response_metadata import StopReason
    VALID_FINISH_REASONS = {"stop", "length", "tool_calls", "content_filter", "error"}
    mock_result = make_mock_result(stop_reason=StopReason.STOP)
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/chat/completions", json=VALID_PAYLOAD)
    finish_reason = response.json()["choices"][0]["finish_reason"]
    assert finish_reason in VALID_FINISH_REASONS


def test_usage_total_equals_prompt_plus_completion(client):
    """AC4: usage.total_tokens == usage.prompt_tokens + usage.completion_tokens"""
    mock_result = make_mock_result(input_tokens=42, output_tokens=17)
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/chat/completions", json=VALID_PAYLOAD)
    usage = response.json()["usage"]
    assert usage["prompt_tokens"] == 42
    assert usage["completion_tokens"] == 17
    assert usage["total_tokens"] == 59


def test_response_model_echoes_request_model(client):
    """AC5: response.model is identical to request.model"""
    mock_result = make_mock_result()
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/chat/completions", json=VALID_PAYLOAD)
    assert response.json()["model"] == VALID_PAYLOAD["model"]


def test_structured_output_returns_valid_json_content(client):
    """AC17: request with valid response_format.json_schema -> content is valid JSON string"""
    from pydantic import BaseModel as PydanticBaseModel

    class FakeAnswer(PydanticBaseModel):
        answer: str

    parsed_instance = FakeAnswer(answer="Paris")
    mock_result = make_mock_result(parsed=parsed_instance)

    payload = {
        **VALID_PAYLOAD,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "answer_schema",
                "schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
            },
        },
    }
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    assert parsed["answer"] == "Paris"


def test_structured_output_parsed_none_returns_500(client):
    """AC18: response_format present but instructor returns parsed=None -> HTTP 500"""
    mock_result = make_mock_result(parsed=None)

    payload = {
        **VALID_PAYLOAD,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "my_schema",
                "schema": {"type": "object"},
            },
        },
    }
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 500
    assert "Structured output failed" in response.json()["detail"]
