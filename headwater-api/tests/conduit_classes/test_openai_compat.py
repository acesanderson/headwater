from __future__ import annotations
import json
import pytest
from pydantic import ValidationError


def test_stream_true_raises_validation_error():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError) as exc_info:
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,
        )
    errors = exc_info.value.errors()
    assert any("Streaming is not supported" in str(e["msg"]) for e in errors)


def test_model_missing_prefix_raises_validation_error():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError):
        OpenAIChatRequest(
            model="claude-sonnet-4-6",
            messages=[{"role": "user", "content": "Hello"}],
        )


def test_model_empty_suffix_raises_validation_error():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError):
        OpenAIChatRequest(
            model="headwater/",
            messages=[{"role": "user", "content": "Hello"}],
        )


def test_tool_message_missing_tool_call_id_raises():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError) as exc_info:
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "tool", "content": "result", "tool_call_id": None},
            ],
        )
    errors = exc_info.value.errors()
    assert any("tool_call_id is required" in str(e["msg"]) for e in errors)


def test_assistant_null_content_raises():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError) as exc_info:
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": None},
            ],
        )
    errors = exc_info.value.errors()
    assert any("null content" in str(e["msg"]) for e in errors)


def test_response_format_type_text_raises():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError):
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "Hello"}],
            response_format={"type": "text"},
        )


def test_response_format_type_json_object_raises():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError):
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "Hello"}],
            response_format={"type": "json_object"},
        )


def test_response_format_missing_name_raises():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError):
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "Hello"}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
                },
            },
        )


def test_schema_field_serialized_as_schema_by_alias():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    request = OpenAIChatRequest(
        model="headwater/claude-sonnet-4-6",
        messages=[{"role": "user", "content": "Hello"}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "my_schema",
                "schema": {"type": "object"},
            },
        },
    )
    serialized = json.loads(request.model_dump_json(by_alias=True))
    assert "schema" in serialized["response_format"]["json_schema"]
    assert "schema_" not in serialized["response_format"]["json_schema"]
