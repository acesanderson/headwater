from __future__ import annotations

import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_request(model: str = "test-model", content: str = "hello world") -> MagicMock:
    req = MagicMock()
    req.params.model = model
    req.messages = [MagicMock(content=content)]
    req.options.project_name = "test"
    req.use_cache = False
    req.include_history = False
    req.verbosity_override = None
    return req


def _make_mock_response(stop_reason=None) -> MagicMock:
    from conduit.domain.result.response_metadata import StopReason
    meta = MagicMock()
    meta.model_slug = "test-model"
    meta.duration = 1234.5
    meta.input_tokens = 10
    meta.output_tokens = 5
    meta.stop_reason = stop_reason or StopReason.STOP
    meta.cache_hit = False
    resp = MagicMock()
    resp.metadata = meta
    return resp


@pytest.mark.asyncio
async def test_llm_call_started_and_completed_logged(caplog):
    """AC-1: Happy path emits llm_call_started and llm_call_completed at INFO."""
    from headwater_server.services.conduit_service.conduit_generate_service import (
        conduit_generate_service,
    )

    mock_response = _make_mock_response()

    with patch("conduit.core.model.model_async.ModelAsync") as mock_cls, \
         patch("conduit.config.settings") as mock_settings, \
         patch("headwater_server.services.conduit_service.conduit_generate_service.GenerationRequest") as mock_gen_req:

        mock_settings.default_cache.return_value = MagicMock()
        mock_settings.default_repository.return_value = MagicMock()
        mock_gen_req.return_value = MagicMock()
        instance = AsyncMock()
        mock_cls.return_value = instance
        instance.query.return_value = mock_response

        with caplog.at_level(logging.INFO):
            await conduit_generate_service(_make_mock_request())

    messages = [r.message for r in caplog.records]
    assert "llm_call_started" in messages, f"llm_call_started not found in {messages}"
    assert "llm_call_completed" in messages, f"llm_call_completed not found in {messages}"


@pytest.mark.asyncio
async def test_llm_call_completed_carries_metadata_fields(caplog):
    """AC-1: llm_call_completed record contains model, duration_ms, tokens, stop_reason, cache_hit."""
    from headwater_server.services.conduit_service.conduit_generate_service import (
        conduit_generate_service,
    )

    mock_response = _make_mock_response()

    with patch("conduit.core.model.model_async.ModelAsync") as mock_cls, \
         patch("conduit.config.settings") as mock_settings, \
         patch("headwater_server.services.conduit_service.conduit_generate_service.GenerationRequest") as mock_gen_req:

        mock_settings.default_cache.return_value = MagicMock()
        mock_settings.default_repository.return_value = MagicMock()
        mock_gen_req.return_value = MagicMock()
        instance = AsyncMock()
        mock_cls.return_value = instance
        instance.query.return_value = mock_response

        with caplog.at_level(logging.INFO):
            await conduit_generate_service(_make_mock_request())

    completed = next(r for r in caplog.records if r.message == "llm_call_completed")
    assert completed.model == "test-model"
    assert completed.duration_ms == round(1234.5, 1)
    assert completed.input_tokens == 10
    assert completed.output_tokens == 5
    assert completed.cache_hit is False


@pytest.mark.asyncio
async def test_llm_call_failed_logged_on_exception(caplog):
    """AC-11: When model.query() raises, llm_call_failed is emitted; llm_call_completed is NOT."""
    from headwater_server.services.conduit_service.conduit_generate_service import (
        conduit_generate_service,
    )

    with patch("conduit.core.model.model_async.ModelAsync") as mock_cls, \
         patch("conduit.config.settings") as mock_settings, \
         patch("headwater_server.services.conduit_service.conduit_generate_service.GenerationRequest") as mock_gen_req:

        mock_settings.default_cache.return_value = MagicMock()
        mock_settings.default_repository.return_value = MagicMock()
        mock_gen_req.return_value = MagicMock()
        instance = AsyncMock()
        mock_cls.return_value = instance
        instance.query.side_effect = RuntimeError("model exploded")

        with caplog.at_level(logging.INFO):
            with pytest.raises(RuntimeError, match="model exploded"):
                await conduit_generate_service(_make_mock_request())

    messages = [r.message for r in caplog.records]
    assert "llm_call_failed" in messages, f"llm_call_failed not found in {messages}"
    assert "llm_call_completed" not in messages, "llm_call_completed must not be emitted on failure"

    failed_record = next(r for r in caplog.records if r.message == "llm_call_failed")
    assert failed_record.levelno == logging.ERROR
    assert failed_record.error_type == "RuntimeError"
    assert failed_record.duration_ms >= 0  # may be 0.0 with fast mocks; field must exist and be numeric
    assert failed_record.exc_info is not None


@pytest.mark.asyncio
async def test_length_truncation_emits_warning_not_completed(caplog):
    """AC-12: stop_reason=LENGTH emits llm_call_length_truncated at WARNING; llm_call_completed NOT emitted."""
    from conduit.domain.result.response_metadata import StopReason
    from headwater_server.services.conduit_service.conduit_generate_service import (
        conduit_generate_service,
    )

    mock_response = _make_mock_response(stop_reason=StopReason.LENGTH)

    with patch("conduit.core.model.model_async.ModelAsync") as mock_cls, \
         patch("conduit.config.settings") as mock_settings, \
         patch("headwater_server.services.conduit_service.conduit_generate_service.GenerationRequest") as mock_gen_req:

        mock_settings.default_cache.return_value = MagicMock()
        mock_settings.default_repository.return_value = MagicMock()
        mock_gen_req.return_value = MagicMock()
        instance = AsyncMock()
        mock_cls.return_value = instance
        instance.query.return_value = mock_response

        with caplog.at_level(logging.DEBUG):
            await conduit_generate_service(_make_mock_request())

    messages = [r.message for r in caplog.records]
    assert "llm_call_length_truncated" in messages, f"llm_call_length_truncated not found in {messages}"
    assert "llm_call_completed" not in messages, "llm_call_completed must not be emitted when stop_reason=LENGTH"

    trunc_record = next(r for r in caplog.records if r.message == "llm_call_length_truncated")
    assert trunc_record.levelno == logging.WARNING
