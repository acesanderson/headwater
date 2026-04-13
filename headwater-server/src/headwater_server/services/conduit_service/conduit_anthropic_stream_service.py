from __future__ import annotations
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from headwater_api.classes.conduit_classes.anthropic_compat import AnthropicRequest

logger = logging.getLogger(__name__)


def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _sse_generator(request: AnthropicRequest) -> AsyncGenerator[str, None]:
    from conduit.core.model.model_async import ModelAsync
    from conduit.core.model.models.modelstore import ModelStore
    from conduit.domain.config.conduit_options import ConduitOptions
    from conduit.domain.message.message import AssistantMessage
    from conduit.domain.message.message import SystemMessage
    from conduit.domain.message.message import UserMessage
    from conduit.domain.request.generation_params import GenerationParams
    from conduit.domain.request.request import GenerationRequest
    from conduit.domain.result.response_metadata import StopReason
    from conduit.utils.progress.verbosity import Verbosity
    from fastapi import HTTPException

    try:
        model_name = ModelStore.validate_model(request.model)
    except FileNotFoundError as exc:
        logger.error("Model store unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="Model store unavailable.") from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unrecognized model: '{request.model}'.",
        ) from exc

    messages = []
    if request.system:
        messages.append(SystemMessage(content=request.system))
    for msg in request.messages:
        content = msg.content if isinstance(msg.content, str) else " ".join(
            b.text for b in msg.content if b.type == "text"
        )
        if msg.role == "user":
            messages.append(UserMessage(content=content))
        else:
            messages.append(AssistantMessage(content=content))

    params_kwargs: dict = {"model": model_name}
    if request.temperature is not None:
        params_kwargs["temperature"] = request.temperature
    if request.top_p is not None:
        params_kwargs["top_p"] = request.top_p
    if request.max_tokens is not None:
        params_kwargs["max_tokens"] = request.max_tokens
    if request.stop_sequences:
        params_kwargs["stop"] = request.stop_sequences

    params = GenerationParams(**params_kwargs)
    options = ConduitOptions(
        project_name="headwater",
        verbosity=Verbosity.SILENT,
        include_history=False,
    )
    gen_request = GenerationRequest(
        messages=messages,
        params=params,
        options=options,
        include_history=False,
    )
    model = ModelAsync(model_name)
    result = await model.query(gen_request)

    content_text = str(result.message)
    _stop_map = {
        StopReason.STOP: "end_turn",
        StopReason.LENGTH: "max_tokens",
        StopReason.TOOL_CALLS: "tool_use",
        StopReason.CONTENT_FILTER: "end_turn",
        StopReason.ERROR: "end_turn",
    }
    stop_reason = _stop_map.get(result.metadata.stop_reason)
    if stop_reason is None:
        logger.warning(
            "Unknown StopReason '%s', defaulting to 'end_turn'",
            result.metadata.stop_reason,
        )
        stop_reason = "end_turn"

    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    logger.info(
        "Anthropic-compat stream: model=%s stop_reason=%s input=%d output=%d",
        model_name, stop_reason,
        result.metadata.input_tokens, result.metadata.output_tokens,
    )

    yield _sse("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": request.model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": result.metadata.input_tokens,
                "output_tokens": 0,
            },
        },
    })
    yield _sse("content_block_start", {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""},
    })
    yield _sse("content_block_delta", {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": content_text},
    })
    yield _sse("content_block_stop", {
        "type": "content_block_stop",
        "index": 0,
    })
    yield _sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": result.metadata.output_tokens},
    })
    yield _sse("message_stop", {"type": "message_stop"})


async def conduit_anthropic_stream_service(request: AnthropicRequest):
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        _sse_generator(request),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
