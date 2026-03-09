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


# Task 9 — AC8, AC9, AC10: get_spec()

def test_get_spec_unregistered_raises_before_db(patched_store):
    with patch(
        "headwater_server.services.embeddings_service.embedding_modelspecs_crud.in_db"
    ) as mock_in_db:
        with pytest.raises(ValueError, match="not in the embedding model registry"):
            EmbeddingModelStore.get_spec("not-a-real-model")
        mock_in_db.assert_not_called()


def test_get_spec_registered_but_no_db_record_raises(patched_store):
    with pytest.raises(ValueError, match="run update_embedding_modelstore"):
        EmbeddingModelStore.get_spec("BAAI/bge-m3")


from headwater_api.classes import EmbeddingModelSpec
from headwater_server.services.embeddings_service.embedding_modelspecs_crud import add_embedding_spec


def _make_spec(model="BAAI/bge-m3") -> EmbeddingModelSpec:
    return EmbeddingModelSpec(
        model=model, provider=EmbeddingProvider.HUGGINGFACE,
        description="A multilingual embedding model.", embedding_dim=1024,
        max_seq_length=8192, multilingual=True, parameter_count="568m",
        prompt_required=False, valid_prefixes=None,
        prompt_unsupported=False, task_map=None,
    )


def test_get_spec_returns_spec_when_populated(patched_store):
    add_embedding_spec(_make_spec())
    result = EmbeddingModelStore.get_spec("BAAI/bge-m3")
    assert isinstance(result, EmbeddingModelSpec)
    assert result.model == "BAAI/bge-m3"
    assert result.embedding_dim == 1024


# Task 10 — AC11: get_all_specs() and by_provider()

def test_by_provider_empty_when_none_registered(patched_store):
    result = EmbeddingModelStore.by_provider(EmbeddingProvider.OPENAI)
    assert result == []


# Task 11 — AC12, AC13, AC14: _is_consistent() and update()

def test_update_adds_new_model_without_overwriting(patched_store, monkeypatch):
    # Pre-populate bge-m3 in TinyDB
    add_embedding_spec(_make_spec("BAAI/bge-m3"))
    original_dump = EmbeddingModelStore.get_spec("BAAI/bge-m3").model_dump()

    # Mock create_embedding_spec so update() doesn't need research module
    new_spec = _make_spec("BAAI/bge-base-en-v1.5")

    def fake_create(model, provider):
        add_embedding_spec(new_spec)

    monkeypatch.setattr(
        "headwater_server.services.embeddings_service.embedding_model_store.create_embedding_spec",
        fake_create,
    )

    EmbeddingModelStore.update()

    # A is unchanged
    after_dump = EmbeddingModelStore.get_spec("BAAI/bge-m3").model_dump()
    assert original_dump == after_dump

    # B was added
    result = EmbeddingModelStore.get_spec("BAAI/bge-base-en-v1.5")
    assert result.model == "BAAI/bge-base-en-v1.5"


def test_update_deletes_orphaned_spec(patched_store, monkeypatch):
    from headwater_server.services.embeddings_service.embedding_modelspecs_crud import in_db

    # Insert an orphan directly into TinyDB (not in registry)
    orphan = _make_spec("orphaned/model-v1")
    add_embedding_spec(orphan)
    assert in_db("orphaned/model-v1")

    # Also pre-populate registry models so update() finds them
    add_embedding_spec(_make_spec("BAAI/bge-m3"))
    add_embedding_spec(_make_spec("BAAI/bge-base-en-v1.5"))

    # Mock create_embedding_spec (no new models to add, but need it importable)
    monkeypatch.setattr(
        "headwater_server.services.embeddings_service.embedding_model_store.create_embedding_spec",
        lambda model, provider: None,
    )

    EmbeddingModelStore.update()
    assert not in_db("orphaned/model-v1")


def test_is_consistent_after_update(patched_store, monkeypatch):
    def fake_create(model, provider):
        add_embedding_spec(_make_spec(model))

    monkeypatch.setattr(
        "headwater_server.services.embeddings_service.embedding_model_store.create_embedding_spec",
        fake_create,
    )
    EmbeddingModelStore.update()
    assert EmbeddingModelStore._is_consistent()
