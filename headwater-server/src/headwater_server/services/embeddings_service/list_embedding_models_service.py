from headwater_api.classes import load_embedding_models
import logging

logger = logging.getLogger(__name__)


async def list_embedding_models_service() -> list[str]:
    """
    List available embedding models.
    This function simulates retrieving a list of embedding models.
    """
    logger.info("Listing available embedding models.")
    embedding_models: list[str] = load_embedding_models()
    return embedding_models
