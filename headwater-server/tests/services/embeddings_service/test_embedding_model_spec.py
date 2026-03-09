from __future__ import annotations

import pytest
from pydantic import ValidationError

from headwater_api.classes.embeddings_classes.embedding_model_spec import EmbeddingModelSpec
from headwater_api.classes.embeddings_classes.embedding_provider import EmbeddingProvider


def _minimal_spec(**overrides) -> dict:
    base = dict(
        model="BAAI/bge-m3",
        provider=EmbeddingProvider.HUGGINGFACE,
        description=None,
        embedding_dim=None,
        max_seq_length=None,
        multilingual=False,
        parameter_count=None,
        prompt_required=False,
        valid_prefixes=None,
        prompt_unsupported=False,
        task_map=None,
    )
    base.update(overrides)
    return base


def test_basic_construction_succeeds():
    spec = EmbeddingModelSpec(**_minimal_spec())
    assert spec.model == "BAAI/bge-m3"
    assert spec.provider == EmbeddingProvider.HUGGINGFACE
    assert spec.embedding_dim is None
    assert spec.prompt_required is False


def test_contradictory_prompt_flags_raise():
    with pytest.raises(ValidationError, match="prompt_required and prompt_unsupported"):
        EmbeddingModelSpec(**_minimal_spec(prompt_required=True, prompt_unsupported=True))


def test_round_trip_lossless():
    original = EmbeddingModelSpec(**_minimal_spec(
        description="A test model.",
        embedding_dim=768,
        max_seq_length=512,
        multilingual=True,
        parameter_count="110m",
        prompt_required=True,
        valid_prefixes=["query: ", "passage: "],
        task_map={"query": "query: ", "document": "passage: "},
    ))
    restored = EmbeddingModelSpec.model_validate(original.model_dump())
    assert original == restored
