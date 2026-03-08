from __future__ import annotations
import pytest


def test_load_embedding_models_returns_list_of_strings():
    from headwater_api.classes import load_embedding_models
    models = load_embedding_models()
    assert isinstance(models, list)
    assert all(isinstance(m, str) for m in models)
    assert "nomic-ai/nomic-embed-text-v1.5" in models
    assert "intfloat/e5-large-v2" in models


def test_get_model_prompt_spec_nomic():
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec
    spec = get_model_prompt_spec("nomic-ai/nomic-embed-text-v1.5")
    assert spec.prompt_required is True
    assert spec.prompt_unsupported is False
    assert spec.valid_prefixes == [
        "search_query: ", "search_document: ", "classification: ", "clustering: "
    ]
    assert spec.task_map == {
        "query": "search_query: ",
        "document": "search_document: ",
        "classification": "classification: ",
        "clustering": "clustering: ",
    }


def test_get_model_prompt_spec_e5():
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec
    spec = get_model_prompt_spec("intfloat/e5-large-v2")
    assert spec.prompt_required is True
    assert spec.valid_prefixes == ["query: ", "passage: "]
    assert spec.task_map == {"query": "query: ", "document": "passage: "}


def test_get_model_prompt_spec_minilm_is_unsupported():
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec
    spec = get_model_prompt_spec("sentence-transformers/all-MiniLM-L6-v2")
    assert spec.prompt_unsupported is True
    assert spec.prompt_required is False


def test_get_model_prompt_spec_bge_is_optional():
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec
    spec = get_model_prompt_spec("BAAI/bge-large-en-v1.5")
    assert spec.prompt_required is False
    assert spec.prompt_unsupported is False


def test_embedding_task_enum_values():
    from headwater_api.classes import EmbeddingTask
    assert EmbeddingTask.query.value == "query"
    assert EmbeddingTask.document.value == "document"
    assert EmbeddingTask.classification.value == "classification"
    assert EmbeddingTask.clustering.value == "clustering"
