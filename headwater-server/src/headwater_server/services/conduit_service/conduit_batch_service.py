from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from headwater_api.classes import BatchRequest
from headwater_api.classes import BatchResponse

if TYPE_CHECKING:
    from conduit.domain.conversation.conversation import Conversation

logger = logging.getLogger(__name__)


async def conduit_batch_service(batch: BatchRequest) -> BatchResponse:
    from conduit.core.conduit.batch.conduit_batch_async import ConduitBatchAsync
    from conduit.batch import Verbosity
    from conduit.core.prompt.prompt import Prompt

    model = batch.params.model
    n = len(batch.prompt_strings_list or batch.input_variables_list or [])

    logger.info(
        "batch_started",
        extra={
            "model": model,
            "n": n,
            "max_concurrent": batch.max_concurrent,
        },
    )

    # Set Verbosity to silent
    batch.options.verbosity = Verbosity.SILENT

    conduit = ConduitBatchAsync(
        prompt=Prompt(batch.prompt_str) if batch.prompt_str else None,
    )

    start = time.monotonic()

    if batch.input_variables_list:
        raw_results = await conduit.run(
            input_variables_list=batch.input_variables_list,
            prompt_strings_list=None,
            params=batch.params,
            options=batch.options,
            max_concurrent=batch.max_concurrent,
        )
    else:
        raw_results = await conduit.run(
            prompt_strings_list=batch.prompt_strings_list,
            input_variables_list=None,
            params=batch.params,
            options=batch.options,
            max_concurrent=batch.max_concurrent,
        )

    duration_ms = round((time.monotonic() - start) * 1000, 1)
    succeeded = 0
    failed = 0
    clean_results: list = []

    for i, result in enumerate(raw_results):
        if isinstance(result, Exception):
            failed += 1
            logger.error(
                "batch_item_failed",
                extra={
                    "model": model,
                    "index": i,
                    "error_type": type(result).__name__,
                },
                exc_info=result,
            )
            clean_results.append(None)
        else:
            succeeded += 1
            clean_results.append(result)

    logger.info(
        "batch_completed",
        extra={
            "model": model,
            "n": n,
            "succeeded": succeeded,
            "failed": failed,
            "duration_ms": duration_ms,
        },
    )

    return BatchResponse(results=clean_results)
