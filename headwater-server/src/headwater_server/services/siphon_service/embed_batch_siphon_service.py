from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from headwater_api.classes import EmbedBatchRequest, EmbedBatchResponse, SIPHON_EMBED_MODEL
from headwater_api.classes.siphon_classes.requests import SIPHON_EMBED_MODEL_V2

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


def _fetch_source_artifact(
    repository, uris: list[str], model_name: str, skip_existing: bool
) -> tuple[dict[str, str], int]:
    """Pick the source artifact (text to embed) based on the embedding model.

    v1 (all-MiniLM): concat of (title, summary). Legacy production path.
    v2 (nomic-embed): the HyDE-shaped description column on its own. Bounded
    input (~150 words) so even 256-token-cap models would fit, but nomic's
    8K cap leaves plenty of headroom.

    Returns ({uri: text_to_embed}, count_skipped_empty).
    """
    if model_name == SIPHON_EMBED_MODEL_V2:
        descriptions = repository.get_embed_descriptions(uris, skip_existing=skip_existing)
        return descriptions, 0  # caller still filters empty strings below

    # v1 / legacy path. Same behavior as before.
    embed_texts = repository.get_embed_texts(uris, skip_existing=skip_existing)
    return {
        uri: f"{title}\n{summary}".strip()
        for uri, (title, summary) in embed_texts.items()
    }, 0


async def embed_batch_siphon_service(request: EmbedBatchRequest) -> EmbedBatchResponse:
    """Batch-embed siphon records by URI.

    Workflow:
    1. Fetch the source artifact (text to embed) per the requested model:
       v1 uses (title, summary) concat; v2 uses the description column. See
       `_fetch_source_artifact`.
    2. Filter URIs where the text is empty — counted as skipped.
    3. Encode non-empty texts in chunks of _CHUNK_SIZE using run_in_executor so
       the event loop stays free (encode is CPU/GPU-bound).
    4. Write vectors back to DB in the same chunk, one transaction per chunk.
    """
    from siphon_server.database.postgres.repository import ContentRepository

    repository = ContentRepository()
    model_name = request.model
    skip_existing = not request.force

    artifacts, _ = _fetch_source_artifact(
        repository, request.uris, model_name, skip_existing
    )

    to_embed: list[tuple[str, str]] = []
    skipped = len(request.uris) - len(artifacts)  # URIs not in DB or already embedded

    for uri, text in artifacts.items():
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
