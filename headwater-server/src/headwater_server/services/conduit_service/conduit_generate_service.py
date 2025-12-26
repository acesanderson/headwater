from headwater_api.classes import GenerationRequest, GenerationResponse
import logging

logger = logging.getLogger(__name__)


async def conduit_generate_service(request: GenerationRequest) -> GenerationResponse:
    """
    Synchronous Conduit processing function.
    Accepts GenerationRequest; returns GenerationResponse.
    """
    from conduit.core.model.model_async import ModelAsync
    from conduit.utils.progress.verbosity import Verbosity
    from conduit.storage.cache.postgres_cache import get_postgres_cache, PostgresCache
    from conduit.storage.repository.postgres_repository import (
        get_postgres_repository,
        PostgresRepository,
    )
    from rich.console import Console

    # First recreate the request -- we have python objects that need to be recreated
    messages = request.messages
    params = request.params
    options = request.options

    # Recreate options with proper excluded objects
    project_name = options.project_name
    cache: PostgresCache = get_postgres_cache(project_name)
    repository: PostgresRepository = get_postgres_repository(project_name)
    console = Console()
    options = options.model_copy(
        update={
            "cache": cache,
            "repository": repository,
            "console": console,
            "verbosity": Verbosity.SUMMARY,
        }
    )
    # Fresh request with updated options
    request = GenerationRequest(
        messages=messages,
        params=params,
        options=options,
        use_cache=request.use_cache,
        include_history=request.include_history,
        verbosity_override=request.verbosity_override,
    )

    logger.info(f"Processing sync query for model: {request.params.model}")

    model = ModelAsync(request.params.model)
    response = await model.query(request)
    return response
