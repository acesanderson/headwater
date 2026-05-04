from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


__all__ = [
    "OpenAIChatMessage",
    "JsonSchemaFormat",
    "ResponseFormat",
    "OpenAIChatRequest",
    "ResponsesInputMessage",
    "ResponsesTextFormat",
    "ResponsesText",
    "OpenAIResponsesRequest",
]


class OpenAIChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None


class JsonSchemaFormat(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str | None = None
    schema_: dict[str, Any] = Field(alias="schema")
    strict: bool | None = None


class ResponseFormat(BaseModel):
    type: Literal["json_schema"]
    json_schema: JsonSchemaFormat


class OpenAIChatRequest(BaseModel):
    model: str
    messages: list[OpenAIChatMessage] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
    stop: list[str] | str | None = None
    stream: bool = False
    response_format: ResponseFormat | None = None
    use_cache: bool = True

    @property
    def normalized_stop(self) -> list[str] | None:
        if isinstance(self.stop, str):
            return [self.stop]
        return self.stop

    @model_validator(mode="after")
    def _validate_request(self) -> OpenAIChatRequest:
        if self.stream:
            raise ValueError("Streaming is not supported on this endpoint.")
        for msg in self.messages:
            if msg.role == "tool" and msg.tool_call_id is None:
                raise ValueError("tool_call_id is required for messages with role='tool'.")
            if msg.role == "assistant" and msg.content is None:
                raise ValueError(
                    "Assistant messages with null content are not supported. "
                    "While null content is valid per OpenAI spec (e.g. for tool-call-only turns), "
                    "Conduit requires at least one payload field on AssistantMessage."
                )
        return self


class ResponsesInputContentPart(BaseModel):
    type: str
    text: str | None = None


class ResponsesInputMessage(BaseModel):
    role: str
    content: str | list[ResponsesInputContentPart] | list[dict[str, Any]]

    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        parts = []
        for part in self.content:
            if isinstance(part, dict):
                parts.append(part.get("text") or "")
            else:
                parts.append(part.text or "")
        return " ".join(p for p in parts if p)


class ResponsesTextFormat(BaseModel):
    type: Literal["json_schema", "json_object", "text"]
    json_schema: JsonSchemaFormat | None = None


class ResponsesText(BaseModel):
    format: ResponsesTextFormat | None = None


class OpenAIResponsesRequest(BaseModel):
    model: str
    input: str | list[ResponsesInputMessage]
    text: ResponsesText | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    use_cache: bool = True
