from __future__ import annotations

from headwater_api.classes import QuickEmbeddingRequest, QuickEmbeddingResponse
from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel


def quick_embedding_service(
    request: QuickEmbeddingRequest,
) -> QuickEmbeddingResponse:
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec

    query = request.query
    model = request.model

    prompt: str | None = request.prompt
    if request.task is not None:
        spec = get_model_prompt_spec(model)
        prompt = spec.task_map[request.task.value]

    embedding_model = EmbeddingModel(model)
    embedding = embedding_model.generate_embedding(query, prompt=prompt)
    return QuickEmbeddingResponse(embedding=embedding)
