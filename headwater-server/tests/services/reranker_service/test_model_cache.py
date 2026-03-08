from __future__ import annotations
from unittest.mock import patch, MagicMock


def test_reranker_constructor_called_once():
    """AC12: get_reranker called N times for same model → Reranker() instantiated exactly once."""
    mock_instance = MagicMock()
    with patch(
        "headwater_server.services.reranker_service.model_cache.Reranker",
        return_value=mock_instance,
    ) as mock_cls:
        from headwater_server.services.reranker_service.model_cache import get_reranker, _cache
        _cache.clear()

        config = {"model_type": "flashrank", "output_type": "bounded"}
        result1 = get_reranker("ce-esci-MiniLM-L12-v2", config)
        result2 = get_reranker("ce-esci-MiniLM-L12-v2", config)
        result3 = get_reranker("ce-esci-MiniLM-L12-v2", config)

        assert mock_cls.call_count == 1
        assert result1 is result2 is result3


def test_metadata_keys_stripped_from_constructor():
    """output_type and api_key_env must not be passed to Reranker()."""
    mock_instance = MagicMock()
    with patch(
        "headwater_server.services.reranker_service.model_cache.Reranker",
        return_value=mock_instance,
    ) as mock_cls:
        from headwater_server.services.reranker_service.model_cache import get_reranker, _cache
        _cache.clear()

        config = {"model_type": "flashrank", "output_type": "bounded"}
        get_reranker("ce-esci-MiniLM-L12-v2", config)

        _, kwargs = mock_cls.call_args
        assert "output_type" not in kwargs
        assert "api_key_env" not in kwargs
        assert kwargs.get("model_type") == "flashrank"


def test_api_key_env_resolved_to_api_key(monkeypatch):
    """api_key_env is resolved via os.getenv and passed as api_key."""
    monkeypatch.setenv("COHERE_API_KEY", "test-key-123")
    mock_instance = MagicMock()
    with patch(
        "headwater_server.services.reranker_service.model_cache.Reranker",
        return_value=mock_instance,
    ) as mock_cls:
        from headwater_server.services.reranker_service.model_cache import get_reranker, _cache
        _cache.clear()

        config = {
            "model_type": "api",
            "api_key_env": "COHERE_API_KEY",
            "lang": "en",
            "output_type": "bounded",
        }
        get_reranker("cohere", config)

        _, kwargs = mock_cls.call_args
        assert kwargs["api_key"] == "test-key-123"
        assert "api_key_env" not in kwargs
