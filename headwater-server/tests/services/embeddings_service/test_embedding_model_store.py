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
