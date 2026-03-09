from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def clear_cache():
    from headwater_server.services.embeddings_service.embedding_model import _model_cache
    _model_cache.clear()
    yield
    _model_cache.clear()


def test_get_returns_same_instance():
    """AC1: calling get() twice with same name returns identical object."""
    mock_st = MagicMock()
    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        return_value=mock_st,
    ), patch(
        "headwater_server.services.embeddings_service.embedding_model.EmbeddingModelStore.list_models",
        return_value=["BAAI/bge-m3"],
    ):
        from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

        r1 = EmbeddingModel.get("BAAI/bge-m3")
        r2 = EmbeddingModel.get("BAAI/bge-m3")

        assert r1 is r2


def test_concurrent_get_instantiates_once(caplog):
    """AC2: two threads racing to get() the same uncached model → one SentenceTransformer construction."""
    import logging
    import threading

    construct_count = 0
    first_started = threading.Event()
    first_can_finish = threading.Event()

    def controlled_st(*args, **kwargs):
        nonlocal construct_count
        construct_count += 1
        first_started.set()
        first_can_finish.wait(timeout=2)
        return MagicMock()

    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        side_effect=controlled_st,
    ), patch(
        "headwater_server.services.embeddings_service.embedding_model.EmbeddingModelStore.list_models",
        return_value=["BAAI/bge-m3"],
    ), caplog.at_level(logging.INFO, logger="headwater_server.services.embeddings_service.embedding_model"):
        from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

        results = []

        def call_get():
            results.append(EmbeddingModel.get("BAAI/bge-m3"))

        t1 = threading.Thread(target=call_get)
        t2 = threading.Thread(target=call_get)

        t1.start()
        first_started.wait(timeout=2)
        t2.start()
        first_can_finish.set()
        t1.join(timeout=2)
        t2.join(timeout=2)

        assert construct_count == 1
        assert results[0] is results[1]
        assert any("cache hit" in r.message for r in caplog.records), \
            "Expected a cache-hit log for the thread that lost the race"


def test_failed_instantiation_does_not_poison_cache():
    """AC4: if SentenceTransformer() raises, the next get() retries rather than returning a cached failure."""
    call_count = 0

    def sometimes_fails(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated CUDA OOM on first load")
        return MagicMock()

    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        side_effect=sometimes_fails,
    ), patch(
        "headwater_server.services.embeddings_service.embedding_model.EmbeddingModelStore.list_models",
        return_value=["BAAI/bge-m3"],
    ):
        from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

        with pytest.raises(RuntimeError, match="simulated CUDA OOM"):
            EmbeddingModel.get("BAAI/bge-m3")

        # Second call must retry, not return a cached None or re-raise a stale exception
        result = EmbeddingModel.get("BAAI/bge-m3")

        assert result is not None
        assert call_count == 2
