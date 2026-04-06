from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch


@pytest.mark.asyncio
async def test_service_returns_one_result_per_source():
    from headwater_server.services.siphon_service.batch_extract_siphon_service import batch_extract_siphon_service
    from headwater_api.classes import BatchExtractRequest

    mock_content = MagicMock()
    mock_content.text = "extracted text"

    with patch(
        "headwater_server.services.siphon_service.batch_extract_siphon_service.SiphonPipeline"
    ) as MockPipeline:
        instance = MagicMock()
        instance.process = AsyncMock(return_value=mock_content)
        MockPipeline.return_value = instance

        req = BatchExtractRequest(sources=["a.pdf", "b.txt"], max_concurrent=10)
        resp = await batch_extract_siphon_service(req)

    assert len(resp.results) == 2
    assert all(r.text == "extracted text" for r in resp.results)
    assert all(r.error is None for r in resp.results)


@pytest.mark.asyncio
async def test_service_captures_per_item_error_without_aborting():
    from headwater_server.services.siphon_service.batch_extract_siphon_service import batch_extract_siphon_service
    from headwater_api.classes import BatchExtractRequest

    good = MagicMock()
    good.text = "good text"

    async def side_effect(source, action):
        if "bad" in source:
            raise RuntimeError("docling timeout")
        return good

    with patch(
        "headwater_server.services.siphon_service.batch_extract_siphon_service.SiphonPipeline"
    ) as MockPipeline:
        instance = MagicMock()
        instance.process = side_effect
        MockPipeline.return_value = instance

        req = BatchExtractRequest(sources=["good.pdf", "bad.pdf"], max_concurrent=10)
        resp = await batch_extract_siphon_service(req)

    by_source = {r.source: r for r in resp.results}
    assert by_source["good.pdf"].text == "good text"
    assert by_source["good.pdf"].error is None
    assert by_source["bad.pdf"].text is None
    assert "docling timeout" in by_source["bad.pdf"].error


@pytest.mark.asyncio
async def test_service_treats_empty_text_as_failure():
    from headwater_server.services.siphon_service.batch_extract_siphon_service import batch_extract_siphon_service
    from headwater_api.classes import BatchExtractRequest

    empty = MagicMock()
    empty.text = ""

    with patch(
        "headwater_server.services.siphon_service.batch_extract_siphon_service.SiphonPipeline"
    ) as MockPipeline:
        instance = MagicMock()
        instance.process = AsyncMock(return_value=empty)
        MockPipeline.return_value = instance

        req = BatchExtractRequest(sources=["scanned.pdf"], max_concurrent=10)
        resp = await batch_extract_siphon_service(req)

    assert resp.results[0].text is None
    assert resp.results[0].error == "empty extraction"
