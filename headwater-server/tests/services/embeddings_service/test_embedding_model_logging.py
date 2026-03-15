from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch


def test_cache_hit_logged_at_debug_not_info(caplog):
    """AC-8: Cache hits on EmbeddingModel.get() are logged at DEBUG, not INFO."""
    from headwater_server.services.embeddings_service.embedding_model import (
        EmbeddingModel,
        _model_cache,
    )

    fake_model = MagicMock(spec=EmbeddingModel)
    _model_cache["test-model"] = fake_model

    try:
        with caplog.at_level(logging.INFO):
            caplog.clear()
            EmbeddingModel.get("test-model")

        cache_hit_records = [
            r for r in caplog.records
            if "cache hit" in r.message
        ]
        # At INFO level, cache hits must NOT appear
        assert not cache_hit_records, (
            f"Cache hit must not appear at INFO level, but got: {[r.message for r in cache_hit_records]}"
        )
    finally:
        _model_cache.pop("test-model", None)


def test_eviction_logged_at_warning(caplog):
    """AC-8: Model eviction from GPU cache is logged at WARNING."""
    from headwater_server.services.embeddings_service.embedding_model import (
        EmbeddingModel,
        _model_cache,
    )

    fake_old_model = MagicMock(spec=EmbeddingModel)
    _model_cache["old-model"] = fake_old_model

    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer"
    ) as mock_st, \
    patch(
        "headwater_server.services.embeddings_service.embedding_model.EmbeddingModelStore.list_models",
        return_value=["test-model"],
    ), \
    patch("torch.cuda.is_available", return_value=False), \
    patch("torch.cuda.empty_cache"):
        mock_st.return_value = MagicMock()
        with caplog.at_level(logging.DEBUG):
            try:
                EmbeddingModel.get("test-model")
            except Exception:
                pass

    eviction_records = [
        r for r in caplog.records
        if "evict" in r.message.lower()
    ]
    assert eviction_records, "No eviction log record found"
    for r in eviction_records:
        assert r.levelno == logging.WARNING, (
            f"Eviction logged at {logging.getLevelName(r.levelno)}, expected WARNING"
        )
    _model_cache.pop("test-model", None)
    _model_cache.pop("old-model", None)
