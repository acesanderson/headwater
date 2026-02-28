from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from headwater_api.classes import EmbedBatchRequest, EmbedBatchResponse, SIPHON_EMBED_MODEL

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 128


@lru_cache(maxsize=4)
def _get_embedding_model(model_name: str):
    """Return a cached EmbeddingModel instance for model_name.

    lru_cache ensures the model is loaded from disk at most once per process
    per model name, regardless of how many embed-batch requests arrive.
    """
    from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel
    return EmbeddingModel(model_name)


async def embed_batch_siphon_service(request: EmbedBatchRequest) -> EmbedBatchResponse:
    """Batch-embed siphon records by URI.

    Workflow:
    1. Fetch (title, summary) from DB for requested URIs (skips already-embedded
       unless force=True).
    2. Filter URIs where title+summary is empty — counted as skipped.
    3. Encode non-empty texts in chunks of _CHUNK_SIZE using run_in_executor so
       the event loop stays free (encode is CPU/GPU-bound).
    4. Write vectors back to DB in the same chunk, one transaction per chunk.
    """
    from siphon_server.database.postgres.repository import ContentRepository

    repository = ContentRepository()
    model_name = request.model
    skip_existing = not request.force

    embed_texts = repository.get_embed_texts(request.uris, skip_existing=skip_existing)

    to_embed: list[tuple[str, str]] = []
    skipped = len(request.uris) - len(embed_texts)  # URIs not in DB or already embedded

    for uri, (title, summary) in embed_texts.items():
        text = f"{title}\n{summary}".strip()
        if not text:
            skipped += 1
        else:
            to_embed.append((uri, text))

    if not to_embed:
        return EmbedBatchResponse(embedded=0, skipped=skipped)

    embedding_model = _get_embedding_model(model_name)
    loop = asyncio.get_event_loop()
    embedded_count = 0

    for i in range(0, len(to_embed), _CHUNK_SIZE):
        chunk = to_embed[i : i + _CHUNK_SIZE]
        chunk_uris = [uri for uri, _ in chunk]
        chunk_texts = [text for _, text in chunk]

        vectors: list[list[float]] = await loop.run_in_executor(
            None,
            embedding_model.embedding_function,
            chunk_texts,
        )

        stored = repository.set_embeddings_batch(
            list(zip(chunk_uris, vectors)),
            model=model_name,
            force=request.force,
        )
        embedded_count += stored
        logger.info(f"embed-batch: stored {stored} vectors (chunk {i // _CHUNK_SIZE + 1})")

    return EmbedBatchResponse(embedded=embedded_count, skipped=skipped)
