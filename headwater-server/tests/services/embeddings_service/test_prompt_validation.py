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


# ── AC4: prompt_required ───────────────────────────────────────────────────────

def test_ac4_embeddings_request_required_model_no_task_no_prompt_raises():
    """AC4: prompt_required model with neither task nor prompt raises ValidationError."""
    from headwater_api.classes import EmbeddingsRequest
    with pytest.raises(ValidationError, match="requires"):
        EmbeddingsRequest(
            model="nomic-ai/nomic-embed-text-v1.5",
            batch=_batch(),
        )


# ── AC5: unknown task in task_map ──────────────────────────────────────────────

def test_ac5_embeddings_request_unsupported_task_for_model_raises():
    """AC5: task with no entry in model's task_map raises ValidationError naming model and task."""
    from headwater_api.classes import EmbeddingsRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="intfloat/e5-large-v2"):
        EmbeddingsRequest(
            model="intfloat/e5-large-v2",
            batch=_batch(),
            task=EmbeddingTask.clustering,
        )


def test_ac5_error_message_names_unsupported_task():
    """AC5: ValidationError message names the rejected task value."""
    from headwater_api.classes import EmbeddingsRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="clustering"):
        EmbeddingsRequest(
            model="intfloat/e5-large-v2",
            batch=_batch(),
            task=EmbeddingTask.clustering,
        )


# ── AC6: invalid prefix ────────────────────────────────────────────────────────

def test_ac6_embeddings_request_invalid_prefix_raises():
    """AC6: prompt not starting with a valid prefix raises ValidationError listing valid prefixes."""
    from headwater_api.classes import EmbeddingsRequest
    with pytest.raises(ValidationError, match="search_query"):
        EmbeddingsRequest(
            model="nomic-ai/nomic-embed-text-v1.5",
            batch=_batch(),
            prompt="bad_prefix: some text",
        )


# ── AC7: prompt_unsupported ────────────────────────────────────────────────────

def test_ac7_embeddings_request_prompt_on_unsupported_model_raises():
    """AC7: passing prompt to a prompt_unsupported model raises ValidationError."""
    from headwater_api.classes import EmbeddingsRequest
    with pytest.raises(ValidationError, match="does not support"):
        EmbeddingsRequest(
            model="sentence-transformers/all-MiniLM-L6-v2",
            batch=_batch(),
            prompt="query: hello",
        )


def test_ac7_embeddings_request_task_on_unsupported_model_raises():
    """AC7: passing task to a prompt_unsupported model raises ValidationError."""
    from headwater_api.classes import EmbeddingsRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="does not support"):
        EmbeddingsRequest(
            model="sentence-transformers/all-MiniLM-L6-v2",
            batch=_batch(),
            task=EmbeddingTask.query,
        )


# ── AC8: optional model, no prompt required ────────────────────────────────────

def test_ac8_embeddings_request_bge_no_prompt_is_valid():
    """AC8: BGE model with no task or prompt constructs without error."""
    from headwater_api.classes import EmbeddingsRequest
    req = EmbeddingsRequest(model="BAAI/bge-large-en-v1.5", batch=_batch())
    assert req.task is None
    assert req.prompt is None


# ── AC1/AC2: valid construction ────────────────────────────────────────────────

def test_ac1_embeddings_request_task_query_nomic_is_valid():
    """AC1: task='query' + nomic model constructs without error."""
    from headwater_api.classes import EmbeddingsRequest, EmbeddingTask
    req = EmbeddingsRequest(
        model="nomic-ai/nomic-embed-text-v1.5",
        batch=_batch(),
        task=EmbeddingTask.query,
    )
    assert req.task == EmbeddingTask.query


def test_ac2_embeddings_request_prompt_nomic_is_valid():
    """AC2: prompt='search_query: ' + nomic model constructs without error."""
    from headwater_api.classes import EmbeddingsRequest
    req = EmbeddingsRequest(
        model="nomic-ai/nomic-embed-text-v1.5",
        batch=_batch(),
        prompt="search_query: ",
    )
    assert req.prompt == "search_query: "


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


def test_ac9_quick_required_model_no_task_no_prompt_raises():
    """AC9/AC4: QuickEmbeddingRequest with prompt_required model, no task or prompt raises."""
    from headwater_api.classes import QuickEmbeddingRequest
    with pytest.raises(ValidationError, match="requires"):
        QuickEmbeddingRequest(
            query="hello",
            model="nomic-ai/nomic-embed-text-v1.5",
        )


def test_ac9_quick_unsupported_task_for_model_raises():
    """AC9/AC5: QuickEmbeddingRequest with unsupported task raises ValidationError."""
    from headwater_api.classes import QuickEmbeddingRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="intfloat/e5-large-v2"):
        QuickEmbeddingRequest(
            query="hello",
            model="intfloat/e5-large-v2",
            task=EmbeddingTask.clustering,
        )


def test_ac9_quick_invalid_prefix_raises():
    """AC9/AC6: QuickEmbeddingRequest with invalid prefix raises ValidationError."""
    from headwater_api.classes import QuickEmbeddingRequest
    with pytest.raises(ValidationError, match="search_query"):
        QuickEmbeddingRequest(
            query="hello",
            model="nomic-ai/nomic-embed-text-v1.5",
            prompt="bad_prefix: ",
        )


def test_ac9_quick_prompt_on_unsupported_model_raises():
    """AC9/AC7: QuickEmbeddingRequest with prompt on unsupported model raises ValidationError."""
    from headwater_api.classes import QuickEmbeddingRequest
    with pytest.raises(ValidationError, match="does not support"):
        QuickEmbeddingRequest(
            query="hello",
            model="sentence-transformers/all-MiniLM-L6-v2",
            prompt="query: ",
        )


def test_ac9_quick_bge_no_prompt_is_valid():
    """AC9/AC8: QuickEmbeddingRequest with BGE and no prompt constructs without error."""
    from headwater_api.classes import QuickEmbeddingRequest
    req = QuickEmbeddingRequest(query="hello", model="BAAI/bge-large-en-v1.5")
    assert req.task is None
    assert req.prompt is None


def test_ac9_quick_task_query_nomic_is_valid():
    """AC9/AC1: QuickEmbeddingRequest with task='query' + nomic constructs without error."""
    from headwater_api.classes import QuickEmbeddingRequest, EmbeddingTask
    req = QuickEmbeddingRequest(
        query="hello",
        model="nomic-ai/nomic-embed-text-v1.5",
        task=EmbeddingTask.query,
    )
    assert req.task == EmbeddingTask.query


def test_ac9_quick_prompt_nomic_is_valid():
    """AC9/AC2: QuickEmbeddingRequest with valid prefix + nomic constructs without error."""
    from headwater_api.classes import QuickEmbeddingRequest
    req = QuickEmbeddingRequest(
        query="hello",
        model="nomic-ai/nomic-embed-text-v1.5",
        prompt="search_query: ",
    )
    assert req.prompt == "search_query: "
