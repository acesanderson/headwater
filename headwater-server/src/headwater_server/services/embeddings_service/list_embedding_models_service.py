from __future__ import annotations
import logging
from headwater_api.classes import EmbeddingModelSpec
from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore

logger = logging.getLogger(__name__)


async def list_embedding_models_service() -> list[EmbeddingModelSpec]:
    logger.info("Listing available embedding model specs.")
    return EmbeddingModelStore.get_all_specs()
