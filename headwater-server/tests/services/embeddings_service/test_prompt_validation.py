from __future__ import annotations
import pytest
from pydantic import ValidationError


# ── helpers ────────────────────────────────────────────────────────────────────

def _batch():
    from headwater_api.classes import ChromaBatch
    return ChromaBatch(ids=["1"], documents=["hello"])


# ── AC3: mutually exclusive ────────────────────────────────────────────────────

def test_ac3_embeddings_request_task_and_prompt_both_raises():
    """AC3: providing both task and prompt raises ValidationError."""
    from headwater_api.classes import EmbeddingsRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="not both"):
        EmbeddingsRequest(
            model="nomic-ai/nomic-embed-text-v1.5",
            batch=_batch(),
            task=EmbeddingTask.query,
            prompt="search_query: ",
        )


# ── AC9: QuickEmbeddingRequest mirrors EmbeddingsRequest validation ────────────

def test_ac9_quick_task_and_prompt_both_raises():
    """AC9/AC3: QuickEmbeddingRequest with both task and prompt raises ValidationError."""
    from headwater_api.classes import QuickEmbeddingRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="not both"):
        QuickEmbeddingRequest(
            query="hello",
            model="nomic-ai/nomic-embed-text-v1.5",
            task=EmbeddingTask.query,
            prompt="search_query: ",
        )

