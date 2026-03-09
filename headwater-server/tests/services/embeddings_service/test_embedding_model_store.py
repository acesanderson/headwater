from __future__ import annotations
import pytest
from unittest.mock import patch
from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore


def test_models_returns_provider_keyed_dict(patched_store):
    result = EmbeddingModelStore.models()
    assert set(result.keys()) == {"huggingface", "openai", "cohere", "jina"}
    assert "BAAI/bge-m3" in result["huggingface"]
    assert result["openai"] == []


def test_list_models_flat_no_duplicates(patched_store):
    result = EmbeddingModelStore.list_models()
    assert isinstance(result, list)
    assert len(result) == len(set(result))
    assert "BAAI/bge-m3" in result
    assert "BAAI/bge-base-en-v1.5" in result
    assert result.count("BAAI/bge-m3") == 1


# Task 8 — AC6, AC7: identify_provider()

from headwater_api.classes import EmbeddingProvider


def test_identify_provider_found(patched_store):
    result = EmbeddingModelStore.identify_provider("BAAI/bge-m3")
    assert result == EmbeddingProvider.HUGGINGFACE


def test_identify_provider_not_found_raises(patched_store):
    with pytest.raises(ValueError, match="Provider not found"):
        EmbeddingModelStore.identify_provider("not-a-real-model")
