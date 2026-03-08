from __future__ import annotations
import pytest


def test_alias_resolves_known_key():
    """Alias 'bge' resolves to its full model name."""
    from headwater_server.services.reranker_service.config import resolve_model_name
    assert resolve_model_name("bge") == "BAAI/bge-reranker-large"


def test_full_model_name_passes_through():
    """A name already in reranking_models.json is returned unchanged."""
    from headwater_server.services.reranker_service.config import resolve_model_name
    assert resolve_model_name("ce-esci-MiniLM-L12-v2") == "ce-esci-MiniLM-L12-v2"


def test_unknown_model_raises_value_error():
    """A name not in aliases or allowlist raises ValueError."""
    from headwater_server.services.reranker_service.config import resolve_model_name
    with pytest.raises(ValueError, match="not-a-model"):
        resolve_model_name("not-a-model")


def test_alias_pointing_to_unknown_model_raises():
    """Config error: alias resolves to a name not in reranking_models.json → ValueError."""
    from headwater_server.services.reranker_service import config as cfg
    original = cfg._ALIASES.copy()
    cfg._ALIASES["broken"] = "nonexistent-model"
    try:
        with pytest.raises(ValueError, match="nonexistent-model"):
            cfg.resolve_model_name("broken")
    finally:
        cfg._ALIASES.clear()
        cfg._ALIASES.update(original)


def test_get_model_config_returns_dict():
    """get_model_config returns the full entry from reranking_models.json."""
    from headwater_server.services.reranker_service.config import get_model_config
    config = get_model_config("ce-esci-MiniLM-L12-v2")
    assert config["model_type"] == "flashrank"
    assert config["output_type"] == "bounded"


def test_list_models_returns_name_and_output_type_for_all_models():
    """list_models returns one entry per model in reranking_models.json, each with name and output_type."""
    from headwater_server.services.reranker_service.config import list_models, _MODELS
    result = list_models()
    assert len(result) == len(_MODELS)
    for entry in result:
        assert set(entry.keys()) == {"name", "output_type"}
        assert entry["output_type"] in {"logits", "bounded"}
    names = {e["name"] for e in result}
    assert names == set(_MODELS.keys())


@pytest.mark.asyncio
async def test_list_models_service_returns_model_info_for_every_allowlisted_model():
    """AC11: list_reranker_models_service returns a RerankerModelInfo for every key in reranking_models.json."""
    from headwater_server.services.reranker_service.list_reranker_models_service import (
        list_reranker_models_service,
    )
    from headwater_server.services.reranker_service.config import _MODELS
    from headwater_api.classes import RerankerModelInfo

    result = await list_reranker_models_service()

    assert len(result) == len(_MODELS)
    assert all(isinstance(m, RerankerModelInfo) for m in result)

    names = {m.name for m in result}
    assert names == set(_MODELS.keys())

    for m in result:
        assert m.output_type in {"logits", "bounded"}
