from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch


def _make_mock_st(embedding_dim: int = 4):
    """Return a SentenceTransformer mock whose encode() returns a numpy-like list."""
    import numpy as np
    mock = MagicMock()
    mock.encode.return_value = np.array([[0.1] * embedding_dim])
    return mock


# ── AC10: task resolves to different prompt strings per model ──────────────────

def test_ac10_task_query_nomic_passes_search_query_prefix(monkeypatch):
    """AC10: task='query' for nomic resolves to 'search_query: ' passed to encode()."""
    from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

    mock_st = _make_mock_st()
    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        return_value=mock_st,
    ):
        model = EmbeddingModel("nomic-ai/nomic-embed-text-v1.5")
        model.generate_embedding("hello", prompt="search_query: ")

    _, kwargs = mock_st.encode.call_args
    assert kwargs.get("prompt") == "search_query: "


def test_ac10_task_query_e5_passes_query_prefix(monkeypatch):
    """AC10: task='query' for e5 resolves to 'query: ' passed to encode()."""
    from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

    mock_st = _make_mock_st()
    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        return_value=mock_st,
    ):
        model = EmbeddingModel("intfloat/e5-large-v2")
        model.generate_embedding("hello", prompt="query: ")

    _, kwargs = mock_st.encode.call_args
    assert kwargs.get("prompt") == "query: "


def test_ac10_nomic_and_e5_query_prompts_differ():
    """AC10: 'query' task resolves to different prompt strings for nomic vs e5."""
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec
    nomic_spec = get_model_prompt_spec("nomic-ai/nomic-embed-text-v1.5")
    e5_spec = get_model_prompt_spec("intfloat/e5-large-v2")
    assert nomic_spec.task_map["query"] != e5_spec.task_map["query"]


# ── AC11: gemma fallback uses prompt_name="STS" when no prompt given ───────────

def test_ac11_gemma_no_prompt_uses_prompt_name_sts():
    """AC11: gemma with no task or prompt calls encode(prompt_name='STS')."""
    from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

    mock_st = _make_mock_st()
    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        return_value=mock_st,
    ):
        model = EmbeddingModel("google/embeddinggemma-300m")
        model.generate_embedding("hello", prompt=None)

    _, kwargs = mock_st.encode.call_args
    assert kwargs.get("prompt_name") == "STS"
    assert "prompt" not in kwargs or kwargs.get("prompt") is None


def test_ac11_gemma_with_prompt_uses_prompt_not_prompt_name():
    """AC11 (inverse): gemma with an explicit prompt uses encode(prompt=...) not prompt_name."""
    from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

    mock_st = _make_mock_st()
    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        return_value=mock_st,
    ):
        model = EmbeddingModel("google/embeddinggemma-300m")
        model.generate_embedding("hello", prompt="my custom prefix: ")

    _, kwargs = mock_st.encode.call_args
    assert kwargs.get("prompt") == "my custom prefix: "
    assert "prompt_name" not in kwargs
