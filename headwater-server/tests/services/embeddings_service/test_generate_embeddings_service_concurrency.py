from __future__ import annotations
import asyncio
import time
from unittest.mock import MagicMock, patch
import pytest
from headwater_api.classes import ChromaBatch, EmbeddingsRequest


def _make_request() -> EmbeddingsRequest:
    return EmbeddingsRequest(
        model="BAAI/bge-m3",
        batch=ChromaBatch(ids=["1"], documents=["hello"]),
        task=None,
        prompt=None,
    )


def test_event_loop_not_blocked_during_inference():
    """AC3: a fast coroutine completes before slow inference finishes, proving the event loop is not blocked."""
    completion_order: list[str] = []

    def slow_inference(batch, prompt=None):
        time.sleep(0.15)
        completion_order.append("inference")
        return MagicMock(embeddings=[[0.1, 0.2]])

    mock_model = MagicMock()
    mock_model.generate_embeddings.side_effect = slow_inference

    async def fast_task():
        await asyncio.sleep(0.05)
        completion_order.append("fast")

    async def run():
        from headwater_server.services.embeddings_service.generate_embeddings_service import (
            generate_embeddings_service,
        )
        with patch(
            "headwater_server.services.embeddings_service.generate_embeddings_service.EmbeddingModel.get",
            return_value=mock_model,
        ):
            await asyncio.gather(
                asyncio.create_task(generate_embeddings_service(_make_request())),
                asyncio.create_task(fast_task()),
            )

    asyncio.run(run())

    # fast_task sleeps 50ms, inference takes 150ms.
    # If event loop was blocked: fast_task couldn't run until inference finished → order is ["inference", "fast"].
    # If event loop is not blocked: fast_task completes at ~50ms → order is ["fast", "inference"].
    assert completion_order == ["fast", "inference"], (
        f"Expected fast task to complete before inference. Got order: {completion_order}. "
        "This means the event loop was blocked during inference."
    )


def test_inference_exception_propagates():
    """AC5: a RuntimeError raised inside run_in_executor surfaces at the await site, not swallowed."""
    def exploding_inference(batch, prompt=None):
        raise RuntimeError("CUDA out of memory")

    mock_model = MagicMock()
    mock_model.generate_embeddings.side_effect = exploding_inference

    async def run():
        from headwater_server.services.embeddings_service.generate_embeddings_service import (
            generate_embeddings_service,
        )
        with patch(
            "headwater_server.services.embeddings_service.generate_embeddings_service.EmbeddingModel.get",
            return_value=mock_model,
        ):
            with pytest.raises(RuntimeError, match="CUDA out of memory"):
                await generate_embeddings_service(_make_request())

    asyncio.run(run())
