from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest
from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider, ChromaBatch, EmbeddingsRequest
from headwater_api.classes.embeddings_classes.task import EmbeddingTask


def test_generate_embeddings_calls_get_spec_not_old_function(patched_store, monkeypatch):
    # Ensure get_spec is called (not the old get_model_prompt_spec)
    with patch(
        "headwater_server.services.embeddings_service.generate_embeddings_service.EmbeddingModelStore.get_spec"
    ) as mock_get_spec, patch(
        "headwater_server.services.embeddings_service.generate_embeddings_service.EmbeddingModel"
    ) as mock_model_cls:
        mock_spec = MagicMock(spec=EmbeddingModelSpec)
        mock_spec.task_map = {"query": "query: "}
        mock_spec.prompt_unsupported = False
        mock_spec.prompt_required = False
        mock_get_spec.return_value = mock_spec

        mock_instance = MagicMock()
        mock_instance.generate_embeddings.return_value = ChromaBatch(
            ids=["1"], documents=["test"], embeddings=[[0.1, 0.2]]
        )
        mock_model_cls.return_value = mock_instance

        import asyncio
        from headwater_server.services.embeddings_service.generate_embeddings_service import (
            generate_embeddings_service,
        )
        # Use an unknown model so the EmbeddingsRequest validator (which still uses the old
        # file-based get_model_prompt_spec) skips validation for unknown models.
        # Pass task=EmbeddingTask.query so the service actually calls EmbeddingModelStore.get_spec.
        request = EmbeddingsRequest(
            model="unknown-model/not-in-registry",
            batch=ChromaBatch(ids=["1"], documents=["hello"]),
            task=EmbeddingTask.query,
            prompt=None,
        )
        asyncio.run(generate_embeddings_service(request))
        mock_get_spec.assert_called_once_with("unknown-model/not-in-registry")
