from __future__ import annotations
import asyncio
import logging
import math
import time
from fastapi import HTTPException
from headwater_api.classes import RerankDocument, RerankRequest, RerankResponse, RerankResult
from headwater_server.services.reranker_service.config import (
    resolve_model_name,
    get_model_config,
)
from headwater_server.services.reranker_service.model_cache import get_reranker

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


async def run_rerank(request: RerankRequest) -> RerankResponse:
    start = time.monotonic()

    try:
        resolved_name = resolve_model_name(request.model_name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    model_config = get_model_config(resolved_name)
    documents: list[RerankDocument] = request.documents  # type: ignore[assignment]
    n = len(documents)

    if request.k is None:
        effective_k = n
    else:
        effective_k = min(request.k, n)
        if effective_k < request.k:
            logger.warning(
                "k=%d exceeds document count=%d; clamping to %d",
                request.k, n, effective_k,
            )

    logger.info("rerank: model=%s docs=%d effective_k=%d", resolved_name, n, effective_k)

    ranker = get_reranker(resolved_name, model_config)
    docs_text = [d.text for d in documents]

    loop = asyncio.get_running_loop()
    ranked = await loop.run_in_executor(
        None, lambda: ranker.rank(query=request.query, docs=docs_text, max_length=request.max_length)
    )

    top_results = ranked.top_k(effective_k)

    results = []
    for result in top_results:
        original_index = result.document.doc_id
        if not isinstance(original_index, int):
            raise ValueError(
                f"Unexpected doc_id type {type(original_index).__name__} from reranker; expected int"
            )
        score = _sigmoid(result.score) if request.normalize_scores else result.score
        results.append(
            RerankResult(
                document=documents[original_index],
                index=original_index,
                score=score,
            )
        )

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info("rerank complete: model=%s duration_ms=%.1f", resolved_name, elapsed_ms)

    return RerankResponse(results=results, model_name=resolved_name)
