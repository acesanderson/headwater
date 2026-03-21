from __future__ import annotations

import logging
import time

from headwater_api.classes import GenerationRequest
from headwater_api.classes import GenerationResponse

logger = logging.getLogger(__name__)


async def conduit_generate_service(request: GenerationRequest) -> GenerationResponse:
    from conduit.core.model.model_async import ModelAsync
    from conduit.utils.progress.verbosity import Verbosity
    from conduit.config import settings
    from conduit.domain.result.response_metadata import StopReason
    from rich.console import Console

    messages = request.messages
    params = request.params
    options = request.options

    project_name = options.project_name
    cache = settings.default_cache(project_name)
    repository = settings.default_repository(project_name)
    console = Console()
    options = options.model_copy(
        update={
            "cache": cache,
            "repository": repository,
            "console": console,
            "verbosity": Verbosity.SILENT,
        }
    )
    request = GenerationRequest(
        messages=messages,
        params=params,
        options=options,
        use_cache=request.use_cache,
        include_history=request.include_history,
        verbosity_override=request.verbosity_override,
    )

    model = params.model
    preview_content = messages[0].content if messages else ""
    if isinstance(preview_content, list):
        preview_content = " ".join(
            item.text if hasattr(item, "text") else "[image]"
            for item in preview_content
        )
    prompt_preview = (preview_content or "")[:80] + "..."

    logger.info(
        "llm_call_started",
        extra={
            "model": model,
            "prompt_preview": prompt_preview,
        },
    )

    start = time.monotonic()
    try:
        response = await ModelAsync(model).query(request)
    except Exception as exc:
        logger.error(
            "llm_call_failed",
            extra={
                "model": model,
                "duration_ms": round((time.monotonic() - start) * 1000, 1),
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        raise

    if response.metadata is None:
        logger.error(
            "llm_call_failed",
            extra={
                "model": model,
                "duration_ms": round((time.monotonic() - start) * 1000, 1),
                "error_type": "MissingMetadata",
            },
        )
        raise RuntimeError("ResponseMetadata missing from conduit response")

    meta = response.metadata

    if meta.stop_reason == StopReason.LENGTH:
        logger.warning(
            "llm_call_length_truncated",
            extra={
                "model": meta.model_slug,
                "duration_ms": round(meta.duration, 1),
                "input_tokens": meta.input_tokens,
                "output_tokens": meta.output_tokens,
                "cache_hit": meta.cache_hit,
            },
        )
    else:
        logger.info(
            "llm_call_completed",
            extra={
                "model": meta.model_slug,
                "duration_ms": round(meta.duration, 1),
                "input_tokens": meta.input_tokens,
                "output_tokens": meta.output_tokens,
                "stop_reason": str(meta.stop_reason),
                "cache_hit": meta.cache_hit,
            },
        )

    return response
