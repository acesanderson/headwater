from __future__ import annotations
import json
from unittest.mock import AsyncMock, MagicMock


FAKE_CHAT_COMPLETION = {
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "headwater/claude-sonnet-4-6",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello!"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


async def test_chat_completions_returns_chat_completion_instance():
    """AC19: chat_completions() returns openai.types.chat.ChatCompletion"""
    from openai.types.chat import ChatCompletion
    from headwater_client.api.openai_async_api import OpenAICompatAsyncAPI
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest

    mock_transport = MagicMock()
    api = OpenAICompatAsyncAPI(mock_transport)
    api._request = AsyncMock(return_value=json.dumps(FAKE_CHAT_COMPLETION))

    request = OpenAIChatRequest(
        model="headwater/claude-sonnet-4-6",
        messages=[{"role": "user", "content": "Hello"}],
    )
    result = await api.chat_completions(request)

    assert isinstance(result, ChatCompletion)
    assert result.model == "headwater/claude-sonnet-4-6"
    assert result.choices[0].message.content == "Hello!"
