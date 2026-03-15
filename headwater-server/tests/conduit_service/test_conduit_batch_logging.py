from __future__ import annotations

import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_batch_started_and_completed_logged(caplog):
    """AC-6: batch_started (n=N) and batch_completed (succeeded+failed==N) are emitted."""
    from headwater_server.services.conduit_service.conduit_batch_service import (
        conduit_batch_service,
    )

    mock_batch = MagicMock()
    mock_batch.prompt_strings_list = ["prompt one", "prompt two", "prompt three"]
    mock_batch.prompt_str = None
    mock_batch.input_variables_list = None
    mock_batch.params.model = "test-model"
    mock_batch.options = MagicMock()
    mock_batch.max_concurrent = 2

    mock_results = [MagicMock(), MagicMock(), MagicMock()]

    with patch(
        "conduit.core.conduit.batch.conduit_batch_async.ConduitBatchAsync"
    ) as mock_batch_cls, patch(
        "headwater_server.services.conduit_service.conduit_batch_service.BatchResponse"
    ):
        mock_instance = AsyncMock()
        mock_batch_cls.return_value = mock_instance
        mock_instance.run.return_value = mock_results

        with caplog.at_level(logging.INFO):
            await conduit_batch_service(mock_batch)

    messages = [r.message for r in caplog.records]
    assert "batch_started" in messages, f"batch_started not found in {messages}"
    assert "batch_completed" in messages, f"batch_completed not found in {messages}"

    started = next(r for r in caplog.records if r.message == "batch_started")
    assert started.n == 3
    assert started.max_concurrent == 2

    completed = next(r for r in caplog.records if r.message == "batch_completed")
    assert completed.succeeded + completed.failed == 3


@pytest.mark.asyncio
async def test_batch_partial_failure_logs_item_failed_and_still_completes(caplog):
    """AC-6: If one item raises, batch_item_failed is emitted and batch_completed still fires."""
    from headwater_server.services.conduit_service.conduit_batch_service import (
        conduit_batch_service,
    )

    mock_batch = MagicMock()
    mock_batch.prompt_strings_list = ["p1", "p2"]
    mock_batch.prompt_str = None
    mock_batch.input_variables_list = None
    mock_batch.params.model = "test-model"
    mock_batch.options = MagicMock()
    mock_batch.max_concurrent = 2

    error = RuntimeError("item failed")

    with patch(
        "conduit.core.conduit.batch.conduit_batch_async.ConduitBatchAsync"
    ) as mock_batch_cls, patch(
        "headwater_server.services.conduit_service.conduit_batch_service.BatchResponse"
    ):
        mock_instance = AsyncMock()
        mock_batch_cls.return_value = mock_instance
        mock_instance.run.return_value = [MagicMock(), error]

        with caplog.at_level(logging.INFO):
            await conduit_batch_service(mock_batch)

    messages = [r.message for r in caplog.records]
    assert "batch_item_failed" in messages
    assert "batch_completed" in messages

    completed = next(r for r in caplog.records if r.message == "batch_completed")
    assert completed.succeeded == 1
    assert completed.failed == 1

    item_failed = next(r for r in caplog.records if r.message == "batch_item_failed")
    assert item_failed.levelno == logging.ERROR
    assert item_failed.index == 1
    assert item_failed.exc_info is not None
