from __future__ import annotations
import logging
from headwater_api.classes import EmbeddingsRequest, EmbeddingsResponse
from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel
from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore

logger = logging.getLogger(__name__)


async def generate_embeddings_service(request: EmbeddingsRequest) -> EmbeddingsResponse:
    from headwater_api.classes import ChromaBatch

    model: str = request.model
    batch: ChromaBatch = request.batch

    logger.info(
        "Generating embeddings",
        extra={
            "model": model,
            "task": request.task.value if request.task else None,
            "prompt_provided": request.prompt is not None,
            "batch_size": len(batch.documents),
        },
    )

    if batch.embeddings:
        raise ValueError("Embeddings already exist in the provided batch.")

    prompt: str | None = request.prompt
    if request.task is not None:
        spec = EmbeddingModelStore.get_spec(model)
        prompt = spec.task_map[request.task.value]

    embedding_model = EmbeddingModel(model)
    new_batch: ChromaBatch = embedding_model.generate_embeddings(batch, prompt=prompt)
    return EmbeddingsResponse(embeddings=new_batch.embeddings)
