"""
Regression tests — Conduit endpoints.

Covers: /conduit/generate, /conduit/batch, /conduit/tokenize,
        /conduit/models, /v1/chat/completions, /v1/messages (non-streaming).

All inference calls use model gpt-oss:latest.
v1/models is skipped here — already covered by tests/test_openai_compliance.py.
/v1/chat/completions and /v1/messages are subserver-only (/v1/ is not a routable
service prefix on the router).
"""

from __future__ import annotations

import json

import pytest
from conduit.domain.config.conduit_options import ConduitOptions
from conduit.domain.message.message import UserMessage
from conduit.domain.request.generation_params import GenerationParams
from conduit.domain.request.request import GenerationRequest

from headwater_api.classes import (
    AnthropicMessage,
    AnthropicRequest,
    BatchRequest,
    BatchResponse,
    GenerationResponse,
    HeadwaterServerException,
    OpenAIChatMessage,
    OpenAIChatRequest,
    TokenizationRequest,
    TokenizationResponse,
)
from headwater_client.client.headwater_client import HeadwaterClient

MODEL = "gpt-oss:latest"
_PROJECT = "headwater-regression"


class TestConduit:
    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _gen_request(prompt: str = "Say hello in one word.", model: str = MODEL) -> GenerationRequest:
        return GenerationRequest(
            messages=[UserMessage(content=prompt)],
            params=GenerationParams(model=model),
            options=ConduitOptions(project_name=_PROJECT),
        )

    # -----------------------------------------------------------------------
    # POST /conduit/generate — happy path
    # -----------------------------------------------------------------------

    def test_generate_router(self, router: HeadwaterClient) -> None:
        resp = router.conduit.query_generate(self._gen_request())
        assert isinstance(resp, GenerationResponse)

    def test_generate_bywater(self, bywater: HeadwaterClient) -> None:
        resp = bywater.conduit.query_generate(self._gen_request())
        assert isinstance(resp, GenerationResponse)

    def test_generate_deepwater(self, deepwater: HeadwaterClient) -> None:
        resp = deepwater.conduit.query_generate(self._gen_request())
        assert isinstance(resp, GenerationResponse)

    # -----------------------------------------------------------------------
    # POST /conduit/generate — edge cases
    # -----------------------------------------------------------------------

    def test_generate_unknown_model_raises(self, router: HeadwaterClient) -> None:
        req = self._gen_request(model="unknown-model-xyz-9999")
        with pytest.raises((HeadwaterServerException, Exception)):
            router.conduit.query_generate(req)

    # -----------------------------------------------------------------------
    # POST /conduit/batch — happy path
    # -----------------------------------------------------------------------

    def test_batch_router(self, router: HeadwaterClient) -> None:
        req = BatchRequest(
            prompt_strings_list=["Say hello.", "Say goodbye."],
            params=GenerationParams(model=MODEL),
            options=ConduitOptions(project_name=_PROJECT),
            max_concurrent=2,
        )
        resp = router.conduit.query_batch(req)
        assert isinstance(resp, BatchResponse)
        assert len(resp.results) == 2

    def test_batch_bywater(self, bywater: HeadwaterClient) -> None:
        req = BatchRequest(
            prompt_strings_list=["Count to three."],
            params=GenerationParams(model=MODEL),
            options=ConduitOptions(project_name=_PROJECT),
        )
        resp = bywater.conduit.query_batch(req)
        assert isinstance(resp, BatchResponse)
        assert len(resp.results) == 1

    def test_batch_deepwater(self, deepwater: HeadwaterClient) -> None:
        req = BatchRequest(
            prompt_strings_list=["What is 2+2?"],
            params=GenerationParams(model=MODEL),
            options=ConduitOptions(project_name=_PROJECT),
        )
        resp = deepwater.conduit.query_batch(req)
        assert isinstance(resp, BatchResponse)
        assert len(resp.results) == 1

    # -----------------------------------------------------------------------
    # POST /conduit/batch — edge cases (validated by BatchRequest model_validator)
    # -----------------------------------------------------------------------

    def test_batch_both_lists_raises_validation(self) -> None:
        with pytest.raises(Exception):
            BatchRequest(
                prompt_strings_list=["hello"],
                input_variables_list=[{"x": "y"}],
                params=GenerationParams(model=MODEL),
                options=ConduitOptions(project_name=_PROJECT),
            )

    def test_batch_neither_list_raises_validation(self) -> None:
        with pytest.raises(Exception):
            BatchRequest(
                params=GenerationParams(model=MODEL),
                options=ConduitOptions(project_name=_PROJECT),
            )

    def test_batch_input_variables_without_prompt_str_raises(self) -> None:
        with pytest.raises(Exception):
            BatchRequest(
                input_variables_list=[{"key": "value"}],
                params=GenerationParams(model=MODEL),
                options=ConduitOptions(project_name=_PROJECT),
            )

    # -----------------------------------------------------------------------
    # POST /conduit/tokenize — happy path
    # -----------------------------------------------------------------------

    def test_tokenize_router(self, router: HeadwaterClient) -> None:
        req = TokenizationRequest(model=MODEL, text="Hello world")
        resp = router.conduit.tokenize(req)
        assert isinstance(resp, TokenizationResponse)
        assert resp.model == MODEL
        assert resp.input_text == "Hello world"
        assert isinstance(resp.token_count, int)
        assert resp.token_count > 0

    def test_tokenize_bywater(self, bywater: HeadwaterClient) -> None:
        req = TokenizationRequest(model=MODEL, text="The quick brown fox")
        resp = bywater.conduit.tokenize(req)
        assert resp.token_count > 0

    def test_tokenize_deepwater(self, deepwater: HeadwaterClient) -> None:
        req = TokenizationRequest(model=MODEL, text="Testing tokenization")
        resp = deepwater.conduit.tokenize(req)
        assert resp.token_count > 0

    # -----------------------------------------------------------------------
    # POST /conduit/tokenize — edge cases
    # -----------------------------------------------------------------------

    def test_tokenize_unknown_model_raises(self, router: HeadwaterClient) -> None:
        req = TokenizationRequest(model="nonexistent-model-abc", text="hello")
        with pytest.raises((HeadwaterServerException, Exception)):
            router.conduit.tokenize(req)

    # -----------------------------------------------------------------------
    # GET /conduit/models
    # -----------------------------------------------------------------------

    def test_list_models_returns_dict(self, router: HeadwaterClient) -> None:
        resp = router.conduit.list_models()
        assert isinstance(resp, dict)
        assert len(resp) > 0

    def test_list_models_bywater(self, bywater: HeadwaterClient) -> None:
        resp = bywater.conduit.list_models()
        assert isinstance(resp, dict)
        assert len(resp) > 0

    def test_list_models_deepwater(self, deepwater: HeadwaterClient) -> None:
        resp = deepwater.conduit.list_models()
        assert isinstance(resp, dict)
        assert len(resp) > 0

    def test_list_models_filter_by_provider_ollama(self, router: HeadwaterClient) -> None:
        resp = router.conduit.list_models(provider="ollama")
        assert isinstance(resp, dict)

    # -----------------------------------------------------------------------
    # POST /v1/chat/completions — subserver only (/v1/ not routable via router)
    # -----------------------------------------------------------------------

    def _chat_request_payload(self, messages: list[dict], **kwargs) -> str:
        body = {"model": MODEL, "messages": messages, "stream": False}
        body.update(kwargs)
        return json.dumps(body)

    def test_chat_completions_non_streaming_bywater(self, bywater: HeadwaterClient) -> None:
        payload = self._chat_request_payload(
            [{"role": "user", "content": "Say hi."}], max_tokens=16
        )
        raw = bywater._transport._request("POST", "/v1/chat/completions", json_payload=payload)
        data = json.loads(raw)
        assert data.get("object") == "chat.completion"
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert data["choices"][0].get("message") is not None

    def test_chat_completions_usage_block(self, bywater: HeadwaterClient) -> None:
        payload = self._chat_request_payload(
            [{"role": "user", "content": "Say hi."}], max_tokens=16
        )
        raw = bywater._transport._request("POST", "/v1/chat/completions", json_payload=payload)
        data = json.loads(raw)
        usage = data.get("usage", {})
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage

    def test_chat_completions_stream_true_raises(self) -> None:
        with pytest.raises(Exception):
            OpenAIChatRequest(
                model=MODEL,
                messages=[OpenAIChatMessage(role="user", content="hi")],
                stream=True,
            )

    def test_chat_completions_empty_messages_raises_validation(self) -> None:
        with pytest.raises(Exception):
            OpenAIChatRequest(model=MODEL, messages=[])

    def test_chat_completions_temperature_out_of_range_raises(self) -> None:
        with pytest.raises(Exception):
            OpenAIChatRequest(
                model=MODEL,
                messages=[OpenAIChatMessage(role="user", content="hi")],
                temperature=3.0,
            )

    def test_chat_completions_max_tokens_zero_raises(self) -> None:
        with pytest.raises(Exception):
            OpenAIChatRequest(
                model=MODEL,
                messages=[OpenAIChatMessage(role="user", content="hi")],
                max_tokens=0,
            )

    def test_chat_completions_assistant_null_content_raises(self) -> None:
        with pytest.raises(Exception):
            OpenAIChatRequest(
                model=MODEL,
                messages=[OpenAIChatMessage(role="assistant", content=None)],
            )

    def test_chat_completions_tool_without_tool_call_id_raises(self) -> None:
        with pytest.raises(Exception):
            OpenAIChatRequest(
                model=MODEL,
                messages=[OpenAIChatMessage(role="tool", content="result", tool_call_id=None)],
            )

    # -----------------------------------------------------------------------
    # POST /v1/messages — subserver only (/v1/ not routable via router)
    # -----------------------------------------------------------------------

    def _messages_payload(self, messages: list[dict], **kwargs) -> str:
        body = {"model": MODEL, "max_tokens": 64, "messages": messages}
        body.update(kwargs)
        return json.dumps(body)

    def test_messages_non_streaming_bywater(self, bywater: HeadwaterClient) -> None:
        payload = self._messages_payload([{"role": "user", "content": "Say hi."}])
        raw = bywater._transport._request("POST", "/v1/messages", json_payload=payload)
        data = json.loads(raw)
        assert data.get("type") == "message"

    def test_messages_non_streaming_deepwater(self, deepwater: HeadwaterClient) -> None:
        payload = self._messages_payload([{"role": "user", "content": "Hello."}])
        raw = deepwater._transport._request("POST", "/v1/messages", json_payload=payload)
        data = json.loads(raw)
        assert data.get("type") == "message"

    def test_messages_stop_reason_present(self, bywater: HeadwaterClient) -> None:
        payload = self._messages_payload([{"role": "user", "content": "Say hi."}])
        raw = bywater._transport._request("POST", "/v1/messages", json_payload=payload)
        data = json.loads(raw)
        assert "stop_reason" in data

    def test_messages_usage_block_present(self, bywater: HeadwaterClient) -> None:
        payload = self._messages_payload([{"role": "user", "content": "Say hi."}])
        raw = bywater._transport._request("POST", "/v1/messages", json_payload=payload)
        data = json.loads(raw)
        assert "usage" in data

    def test_messages_with_system_prompt(self, bywater: HeadwaterClient) -> None:
        payload = self._messages_payload(
            [{"role": "user", "content": "What are you?"}],
            system="You are a helpful assistant.",
        )
        raw = bywater._transport._request("POST", "/v1/messages", json_payload=payload)
        data = json.loads(raw)
        assert data.get("type") == "message"

    def test_messages_content_block_format(self, bywater: HeadwaterClient) -> None:
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "Say hello."}]}
        ]
        payload = self._messages_payload(messages)
        raw = bywater._transport._request("POST", "/v1/messages", json_payload=payload)
        data = json.loads(raw)
        assert data.get("type") == "message"

    def test_messages_missing_max_tokens_raises_validation(self) -> None:
        with pytest.raises(Exception):
            AnthropicRequest(
                model=MODEL,
                messages=[AnthropicMessage(role="user", content="hi")],
            )

    def test_messages_empty_messages_raises_validation(self) -> None:
        with pytest.raises(Exception):
            AnthropicRequest(model=MODEL, max_tokens=64, messages=[])

    def test_messages_temperature_out_of_range_raises(self) -> None:
        with pytest.raises(Exception):
            AnthropicRequest(
                model=MODEL,
                max_tokens=64,
                messages=[AnthropicMessage(role="user", content="hi")],
                temperature=1.5,
            )

    def test_messages_max_tokens_zero_raises(self) -> None:
        with pytest.raises(Exception):
            AnthropicRequest(
                model=MODEL,
                max_tokens=0,
                messages=[AnthropicMessage(role="user", content="hi")],
            )

    def test_messages_unknown_model_raises(self, bywater: HeadwaterClient) -> None:
        payload = json.dumps(
            {
                "model": "unknown-model-xyz-9999",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "hi"}],
            }
        )
        with pytest.raises((HeadwaterServerException, Exception)):
            bywater._transport._request("POST", "/v1/messages", json_payload=payload)
