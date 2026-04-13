from __future__ import annotations
import pytest
from headwater_api.classes import AnthropicMessage, AnthropicRequest


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
