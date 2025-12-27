from __future__ import annotations
from headwater_api.classes import (
    BatchRequest,
    BatchResponse,
)
from typing import TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from conduit.domain.conversation.conversation import Conversation

logger = logging.getLogger(__name__)


async def conduit_batch_service(
    batch: BatchRequest,
) -> BatchResponse:
    """
    Normalize BatchRequest into a list of query_async coroutines and execute them.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from conduit.core.conduit.batch.conduit_batch_async import ConduitBatchAsync
    from conduit.core.prompt.prompt import Prompt

    conduit = ConduitBatchAsync(
        prompt=Prompt(batch.prompt_str) if batch.prompt_str else None,
    )

    if batch.input_variables_list:
        results: list[Conversation] = await conduit.run(
            input_variables_list=batch.input_variables_list,
            prompt_strings_list=None,
            params=batch.params,
            options=batch.options,
        )
    else:
        results: list[Conversation] = await conduit.run(
            prompt_strings_list=batch.prompt_strings_list,
            input_variables_list=None,
            params=batch.params,
            options=batch.options,
        )

    return BatchResponse(results=results)
