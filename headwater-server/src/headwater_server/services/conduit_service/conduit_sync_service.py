from headwater_api.classes import ConduitRequest, ConduitResponse, ConduitError
import logging

logger = logging.getLogger(__name__)


def conduit_sync_service(request: ConduitRequest) -> ConduitResponse | ConduitError:
    """
    Synchronous Conduit processing function.
    Accepts ConduitRequest; returns ConduitResponse or ConduitError.
    """
    from conduit.sync import Model, Verbosity, ConduitCache

    Model.conduit_cache = ConduitCache(name="headwater")  # Initialize cache if needed

    logger.info(f"Processing sync query for model: {request.model}")

    model = Model(request.model)
    response = model.query(request=request, verbose=Verbosity.SUMMARY)
    return response
