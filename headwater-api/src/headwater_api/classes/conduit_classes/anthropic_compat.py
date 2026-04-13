from __future__ import annotations
from typing import Literal
from pydantic import BaseModel
from pydantic import Field


__all__ = [
    "AnthropicContentBlock",
    "AnthropicMessage",
    "AnthropicRequest",
]


class AnthropicContentBlock(BaseModel):
    type: Literal["text"]
    text: str


class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[AnthropicContentBlock]


class AnthropicRequest(BaseModel):
    model: str
    max_tokens: int = Field(ge=1)
    messages: list[AnthropicMessage] = Field(min_length=1)
    system: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    stop_sequences: list[str] | None = None
    stream: bool = False
