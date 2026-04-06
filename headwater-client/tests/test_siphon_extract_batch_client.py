from __future__ import annotations

import json
from unittest.mock import MagicMock, AsyncMock

import pytest

from headwater_api.classes import BatchExtractRequest
from headwater_api.classes import BatchExtractResponse
from headwater_api.classes import ExtractResult


def _make_sync_api(response_json: str):
    from headwater_client.api.siphon_sync_api import SiphonAPI
    transport = MagicMock()
    transport._request.return_value = response_json
    return SiphonAPI(transport)


def test_extract_batch_sends_correct_endpoint():
    resp = BatchExtractResponse(results=[
        ExtractResult(source="a.pdf", text="text", error=None),
    ])
    api = _make_sync_api(resp.model_dump_json())
    req = BatchExtractRequest(sources=["a.pdf"], max_concurrent=3)
    result = api.extract_batch(req)
    api._transport._request.assert_called_once_with(
        "POST", "/siphon/extract/batch", json_payload=req.model_dump_json()
    )
    assert isinstance(result, BatchExtractResponse)
    assert result.results[0].source == "a.pdf"


def _make_async_api(response_json: str):
    from headwater_client.api.siphon_async_api import SiphonAsyncAPI
    transport = MagicMock()
    transport._request = AsyncMock(return_value=response_json)
    return SiphonAsyncAPI(transport)


@pytest.mark.asyncio
async def test_async_extract_batch_sends_correct_endpoint():
    resp = BatchExtractResponse(results=[
        ExtractResult(source="a.pdf", text="text", error=None),
    ])
    api = _make_async_api(resp.model_dump_json())
    req = BatchExtractRequest(sources=["a.pdf"], max_concurrent=3)
    result = await api.extract_batch(req)
    api._transport._request.assert_called_once_with(
        "POST", "/siphon/extract/batch", json_payload=req.model_dump_json()
    )
    assert isinstance(result, BatchExtractResponse)
    assert result.results[0].text == "text"
