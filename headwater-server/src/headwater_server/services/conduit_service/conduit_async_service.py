from headwater_api.classes import (
    BatchRequest,
    BatchResponse,
)
import logging

logger = logging.getLogger(__name__)


async def conduit_async_service(
    batch: BatchRequest,
) -> BatchResponse:
    """
    Normalize BatchRequest into a list of query_async coroutines and execute them.
    """
    from conduit.batch import AsyncConduit, ModelAsync, Prompt, Verbosity
    from functools import partial
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    logger.debug(f"Received batch request: {batch}")

    model_str = batch.model
    prompt_str = batch.prompt_str
    input_variables_list = batch.input_variables_list
    prompt_strings = batch.prompt_strings
    model = ModelAsync(model_str)
    if prompt_str and input_variables_list:
        prompt = Prompt(prompt_str)
        conduit = AsyncConduit(model=model, prompt=prompt)
        func_for_executor = partial(
            conduit.run,
            input_variables_list=input_variables_list,
            verbose=Verbosity.PROGRESS,
        )
    elif prompt_strings:
        conduit = AsyncConduit(model=model)
        func_for_executor = partial(
            conduit.run,
            prompt_strings=prompt_strings,
            verbose=Verbosity.PROGRESS,
        )
    else:
        logger.error(
            "BatchRequest must contain either 'prompt_str' with 'input_variables_list' or 'prompt_strings'."
        )
        raise ValueError(
            "BatchRequest must contain either 'prompt_str' with 'input_variables_list' or 'prompt_strings'."
        )
    assert func_for_executor is not None, "Function for executor should not be None"
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
