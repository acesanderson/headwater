from __future__ import annotations
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIResponsesRequest

logger = logging.getLogger(__name__)


async def conduit_responses_service(request: OpenAIResponsesRequest) -> dict:
    from conduit.core.model.model_async import ModelAsync
    from conduit.core.model.models.modelstore import ModelStore
    from conduit.domain.config.conduit_options import ConduitOptions
    from conduit.domain.message.message import AssistantMessage, SystemMessage, UserMessage
    from conduit.domain.request.generation_params import GenerationParams
    from conduit.domain.request.request import GenerationRequest
    from conduit.domain.result.response_metadata import StopReason
    from conduit.utils.progress.verbosity import Verbosity
    from fastapi import HTTPException
    from pydantic import BaseModel as PydanticBaseModel

    fmt = request.text.format if request.text and request.text.format else None
    json_schema_format = fmt.json_schema if fmt and fmt.type == "json_schema" else None
    json_object_mode = fmt is not None and fmt.type == "json_object"

    logger.info(
        "Responses API request: model=%s structured_output=%s json_object=%s",
        request.model,
        json_schema_format is not None,
        json_object_mode,
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

    # 2. Convert input to messages
    if isinstance(request.input, str):
        messages = [UserMessage(content=request.input)]
    else:
        messages = []
        for msg in request.input:
            text = msg.text()
            if msg.role == "system":
                messages.append(SystemMessage(content=text))
            elif msg.role == "assistant":
                messages.append(AssistantMessage(content=text))
            else:
                messages.append(UserMessage(content=text))

    if not messages:
        raise HTTPException(status_code=400, detail="input must contain at least one message.")

    # 3. Build GenerationParams
    params_kwargs: dict = {"model": model_name}
    if request.temperature is not None:
        params_kwargs["temperature"] = request.temperature
    # Always cap tokens: callers that don't set max_output_tokens (e.g. Firecrawl) would
    # otherwise let a thinking model consume unlimited CoT budget before producing output.
    params_kwargs["max_tokens"] = request.max_output_tokens if request.max_output_tokens is not None else 2048
    if json_schema_format is not None:
        params_kwargs["response_model_schema"] = json_schema_format.schema_
        params_kwargs["output_type"] = "structured_response"
    elif json_object_mode:
        params_kwargs["response_model_schema"] = {"type": "object"}
        params_kwargs["output_type"] = "structured_response"

    params = GenerationParams(**params_kwargs)

    # 4. Build ConduitOptions
    options = ConduitOptions(
        project_name="headwater",
        verbosity=Verbosity.SILENT,
        include_history=False,
        use_cache=request.use_cache,
    )

    # 5. Build GenerationRequest and query
    gen_request = GenerationRequest(
        messages=messages,
        params=params,
        options=options,
        use_cache=request.use_cache,
        include_history=False,
    )

    model = ModelAsync(model_name)
    result = await model.query(gen_request)

    # 6. Content coercion
    if json_schema_format is not None or json_object_mode:
        if result.message.parsed is not None:
            # instructor path: parsed Pydantic object
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
            # schema path: raw JSON string already in content
            content = str(result.message)
            if not content:
                logger.error("Structured output failed: empty content for model=%s", model_name)
                raise HTTPException(
                    status_code=500,
                    detail="Structured output failed: model returned empty content.",
                )
    else:
        content = str(result.message)
        if not content and result.metadata.stop_reason != StopReason.LENGTH:
            logger.error("Model returned empty response: model=%s", model_name)
            raise HTTPException(status_code=500, detail="Model returned an empty response.")

    logger.info(
        "Responses API response: model=%s input_tokens=%d output_tokens=%d cache_hit=%s duration_ms=%.1f",
        model_name,
        result.metadata.input_tokens,
        result.metadata.output_tokens,
        result.metadata.cache_hit,
        result.metadata.duration,
    )

    msg_id = f"msg_{uuid.uuid4().hex[:16]}"
    return {
        "id": f"resp_{uuid.uuid4().hex[:16]}",
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": request.model,
        "output": [
            {
                "type": "message",
                "id": msg_id,
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": content, "annotations": []}
                ],
            }
        ],
        "usage": {
            "input_tokens": result.metadata.input_tokens,
            "output_tokens": result.metadata.output_tokens,
            "total_tokens": result.metadata.input_tokens + result.metadata.output_tokens,
        },
    }
