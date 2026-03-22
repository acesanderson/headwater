from __future__ import annotations
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest

logger = logging.getLogger(__name__)


async def conduit_openai_service(request: OpenAIChatRequest) -> dict:
    from conduit.core.model.model_async import ModelAsync
    from conduit.core.model.models.modelstore import ModelStore
    from conduit.domain.config.conduit_options import ConduitOptions
    from conduit.domain.message.message import AssistantMessage, SystemMessage, ToolMessage, UserMessage
    from conduit.domain.request.generation_params import GenerationParams
    from conduit.domain.request.request import GenerationRequest
    from conduit.domain.result.response_metadata import StopReason
    from conduit.utils.progress.verbosity import Verbosity
    from fastapi import HTTPException
    from pydantic import BaseModel as PydanticBaseModel

    logger.info(
        "OpenAI-compat request: model=%s structured_output=%s use_cache=%s",
        request.model,
        request.response_format is not None,
        request.use_cache,
    )

    # 1. Validate model
    try:
        model_name = ModelStore.validate_model(request.model)
    except FileNotFoundError as exc:
        logger.error("Model store unavailable: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Model store unavailable. Server configuration error.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unrecognized model: '{request.model}'. Check ModelStore for supported models.",
        ) from exc

    # 2. Reject messages-only-system edge case
    non_system = [m for m in request.messages if m.role != "system"]
    if not non_system:
        raise HTTPException(
            status_code=400,
            detail="messages must contain at least one non-system message.",
        )

    # 3. Convert messages
    messages = []
    for msg in request.messages:
        if msg.role == "system":
            messages.append(SystemMessage(content=msg.content))
        elif msg.role == "user":
            messages.append(UserMessage(content=msg.content, name=msg.name))
        elif msg.role == "assistant":
            messages.append(AssistantMessage(content=msg.content))
        elif msg.role == "tool":
            messages.append(ToolMessage(
                content=str(msg.content),
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            ))

    # 4. Build GenerationParams
    params_kwargs: dict = {"model": model_name}
    if request.temperature is not None:
        params_kwargs["temperature"] = request.temperature
    if request.top_p is not None:
        params_kwargs["top_p"] = request.top_p
    if request.max_tokens is not None:
        params_kwargs["max_tokens"] = request.max_tokens
    if request.normalized_stop is not None:
        params_kwargs["stop"] = request.normalized_stop
    if request.response_format is not None:
        params_kwargs["response_model_schema"] = request.response_format.json_schema.schema_

    params = GenerationParams(**params_kwargs)

    # 5. Build ConduitOptions
    options = ConduitOptions(
        project_name="headwater",
        verbosity=Verbosity.SILENT,
        include_history=False,
        use_cache=request.use_cache,
    )

    # 6. Build GenerationRequest and query
    gen_request = GenerationRequest(
        messages=messages,
        params=params,
        options=options,
        use_cache=request.use_cache,
        include_history=False,
    )

    model = ModelAsync(model_name)
    result = await model.query(gen_request)

    # 7. Content coercion
    if request.response_format is not None:
        if result.message.parsed is None:
            logger.error("Structured output failed: parsed=None for model=%s", model_name)
            raise HTTPException(
                status_code=500,
                detail="Structured output failed: instructor did not return a parsed result.",
            )
        if isinstance(result.message.parsed, PydanticBaseModel):
            content = result.message.parsed.model_dump_json()
        elif isinstance(result.message.parsed, list):
            content = json.dumps([
                item.model_dump() if isinstance(item, PydanticBaseModel) else item
                for item in result.message.parsed
            ])
        else:
            content = json.dumps(result.message.parsed)
    else:
        content = str(result.message)
        if not content:
            logger.error("Model returned empty response: model=%s", model_name)
            raise HTTPException(status_code=500, detail="Model returned an empty response.")

    # 8. Map finish_reason
    _stop_map = {
        StopReason.STOP: "stop",
        StopReason.LENGTH: "length",
        StopReason.TOOL_CALLS: "tool_calls",
        StopReason.CONTENT_FILTER: "content_filter",
        StopReason.ERROR: "error",
    }
    finish_reason = _stop_map.get(result.metadata.stop_reason)
    if finish_reason is None:
        logger.warning(
            "Unknown StopReason '%s', defaulting finish_reason to 'error'",
            result.metadata.stop_reason,
        )
        finish_reason = "error"

    logger.info(
        "OpenAI-compat response: model=%s finish_reason=%s input_tokens=%d output_tokens=%d cache_hit=%s duration_ms=%.1f",
        model_name,
        finish_reason,
        result.metadata.input_tokens,
        result.metadata.output_tokens,
        result.metadata.cache_hit,
        result.metadata.duration,
    )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": result.metadata.input_tokens,
            "completion_tokens": result.metadata.output_tokens,
            "total_tokens": result.metadata.input_tokens + result.metadata.output_tokens,
        },
    }
