from __future__ import annotations
from unittest.mock import patch
from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider


def _sample_spec() -> EmbeddingModelSpec:
    return EmbeddingModelSpec(
        model="BAAI/bge-m3",
        provider=EmbeddingProvider.HUGGINGFACE,
        description="Test.",
        embedding_dim=1024,
        max_seq_length=8192,
        multilingual=True,
        parameter_count="568m",
        prompt_required=False,
        valid_prefixes=None,
        prompt_unsupported=False,
        task_map=None,
    )


def test_list_embedding_models_returns_200(client):
    with patch(
        "headwater_server.services.embeddings_service.list_embedding_models_service.EmbeddingModelStore.get_all_specs",
        return_value=[_sample_spec()],
    ):
        response = client.get("/conduit/embeddings/models")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_embedding_models_elements_are_valid_specs(client):
    with patch(
        "headwater_server.services.embeddings_service.list_embedding_models_service.EmbeddingModelStore.get_all_specs",
        return_value=[_sample_spec()],
    ):
        response = client.get("/conduit/embeddings/models")
    data = response.json()
    assert len(data) == 1
    spec = EmbeddingModelSpec.model_validate(data[0])
    assert spec.model == "BAAI/bge-m3"
    assert spec.embedding_dim == 1024
    assert "description" in data[0]
    assert "task_map" in data[0]
