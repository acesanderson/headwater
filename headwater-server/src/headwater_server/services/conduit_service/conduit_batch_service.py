from headwater_api.classes import (
    BatchRequest,
    BatchResponse,
)
import logging

logger = logging.getLogger(__name__)


async def conduit_batch_service(
    batch: BatchRequest,
) -> BatchResponse:
    """
    Normalize BatchRequest into a list of query_async coroutines and execute them.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from conduit.batch import ConduitBatch, Prompt

    prompt = Prompt(batch.prompt_str) if batch.prompt_str else None
    input_variables_list = batch.input_variables_list
    prompt_strings = batch.prompt_strings
    params = batch.params
    options = batch.options

    conduit = ConduitBatch(
        prompt=prompt,
        params=params,
        options=options,
    )

    logger.debug(f"Received batch request: {batch}")

    # Need to allow this to run from running event loop
    def func_for_executor():
        if input_variables_list:
            return conduit.run(
                input_variables_list=input_variables_list, verbosity=options.verbosity
            )
        else:
            return conduit.run(
                prompt_strings_list=prompt_strings, verbosity=options.verbosity
            )

    # results = conduit.run(
    #     input_variables_list=input_variables_list, prompt_strings_list=prompt_strings
    # )

    # Run the following in a thread pool to avoid blocking the event loop
    ## conduit.run(input_variables_list=input_variables_list, verbosity=Verbosity.PROGRESS)
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        results = await loop.run_in_executor(
            executor,
            func_for_executor,
        )
    batch_response = BatchResponse(results=results)
    return batch_response
