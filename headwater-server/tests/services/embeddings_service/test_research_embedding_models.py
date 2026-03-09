from __future__ import annotations
import pytest
from unittest.mock import patch
from headwater_server.services.embeddings_service.embedding_modelspecs_crud import in_db


def test_perplexity_failure_halts_no_partial_writes(patched_store, monkeypatch):
    """AC15: update() with Conduit raising ConnectionError must raise and write zero records."""
    from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore

    with patch(
        "headwater_server.services.embeddings_service.research_embedding_models.Conduit"
    ) as mock_conduit_cls:
        mock_conduit_cls.return_value.run.side_effect = ConnectionError("Perplexity unreachable")
        with pytest.raises(ConnectionError):
            EmbeddingModelStore.update()

    # Registry has 2 models; neither should have been written
    assert not in_db("BAAI/bge-m3")
    assert not in_db("BAAI/bge-base-en-v1.5")
