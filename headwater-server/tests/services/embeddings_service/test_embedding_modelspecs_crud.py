from __future__ import annotations
import pytest
from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider
from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
    add_embedding_spec,
    get_all_embedding_specs,
    get_embedding_spec_by_name,
    get_all_spec_model_names,
    delete_embedding_spec,
    in_db,
)


def _make_spec(model="BAAI/bge-m3") -> EmbeddingModelSpec:
    return EmbeddingModelSpec(
        model=model,
        provider=EmbeddingProvider.HUGGINGFACE,
        description="Test model.",
        embedding_dim=768,
        max_seq_length=512,
        multilingual=False,
        parameter_count="110m",
        prompt_required=False,
        valid_prefixes=None,
        prompt_unsupported=False,
        task_map=None,
    )


def test_add_and_retrieve(patched_store):
    spec = _make_spec()
    add_embedding_spec(spec)
    result = get_embedding_spec_by_name("BAAI/bge-m3")
    assert result.model == "BAAI/bge-m3"
    assert result.embedding_dim == 768


def test_get_missing_raises(patched_store):
    with pytest.raises(ValueError, match="not found"):
        get_embedding_spec_by_name("nonexistent/model")


def test_in_db(patched_store):
    assert not in_db("BAAI/bge-m3")
    add_embedding_spec(_make_spec())
    assert in_db("BAAI/bge-m3")


def test_delete(patched_store):
    add_embedding_spec(_make_spec())
    delete_embedding_spec("BAAI/bge-m3")
    assert not in_db("BAAI/bge-m3")


def test_delete_missing_is_noop(patched_store):
    delete_embedding_spec("nonexistent/model")  # must not raise


def test_get_all_spec_model_names(patched_store):
    add_embedding_spec(_make_spec("BAAI/bge-m3"))
    add_embedding_spec(_make_spec("BAAI/bge-base-en-v1.5"))
    names = get_all_spec_model_names()
    assert set(names) == {"BAAI/bge-m3", "BAAI/bge-base-en-v1.5"}
