from __future__ import annotations
import logging
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from headwater_api.classes.conduit_classes.anthropic_compat import AnthropicRequest

logger = logging.getLogger(__name__)

_STOP_MAP = {
    "STOP": "end_turn",
    "LENGTH": "max_tokens",
    "TOOL_CALLS": "tool_use",
    "CONTENT_FILTER": "end_turn",
    "ERROR": "end_turn",
}


async def conduit_anthropic_service(request: AnthropicRequest) -> dict:
    from conduit.core.model.model_async import ModelAsync
    from conduit.core.model.models.modelstore import ModelStore
    from conduit.domain.config.conduit_options import ConduitOptions
    from conduit.domain.message.message import AssistantMessage
    from conduit.domain.message.message import SystemMessage
    from conduit.domain.message.message import UserMessage
    from conduit.domain.request.generation_params import GenerationParams
    from conduit.domain.request.request import GenerationRequest
    from conduit.utils.progress.verbosity import Verbosity
    from fastapi import HTTPException

    logger.info(
        "Anthropic-compat request: model=%s stream=%s",
        request.model,
        request.stream,
    )

    # 1. Validate model
    try:
        model_name = ModelStore.validate_model(request.model)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=502, detail="Model store unavailable.") from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unrecognized model: '{request.model}'.",
        ) from exc

    # 2. Build message list
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

    # 3. Build params
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

    # 4. Query
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

    # 5. Build response
    content_text = str(result.message)
    stop_reason = _STOP_MAP.get(result.metadata.stop_reason.name, "end_turn")

    logger.info(
        "Anthropic-compat response: model=%s stop_reason=%s input=%d output=%d",
        model_name, stop_reason,
        result.metadata.input_tokens, result.metadata.output_tokens,
    )

    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content_text}],
        "model": request.model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": result.metadata.input_tokens,
            "output_tokens": result.metadata.output_tokens,
        },
    }
