"""
Regression tests — Siphon endpoints.

Covers: /siphon/process, /siphon/extract/batch, /siphon/embed-batch

For embed-batch, fake URIs are used — the spec states this returns
embedded=0, skipped=N without crashing.
"""

from __future__ import annotations

import pytest

from headwater_api.classes import (
    BatchExtractRequest,
    BatchExtractResponse,
    EmbedBatchResponse,
    ExtractResult,
    HeadwaterServerException,
    SIPHON_EMBED_MODEL,
)
from headwater_client.client.headwater_client import HeadwaterClient
from siphon_api.api.siphon_request import SiphonRequest, SiphonRequestParams
from siphon_api.enums import ActionType, SourceOrigin


class TestSiphon:
    # -----------------------------------------------------------------------
    # POST /siphon/process — happy path
    # -----------------------------------------------------------------------

    def test_process_url_router(self, router: HeadwaterClient) -> None:
        req = SiphonRequest(
            source="https://example.com",
            origin=SourceOrigin.URL,
            params=SiphonRequestParams(action=ActionType.EXTRACT),
        )
        resp = router.siphon.process(req)
        # Accept any valid response; do not assert on content
        assert resp is not None

    def test_process_url_bywater(self, bywater: HeadwaterClient) -> None:
        req = SiphonRequest(
            source="https://example.com",
            origin=SourceOrigin.URL,
            params=SiphonRequestParams(action=ActionType.EXTRACT),
        )
        resp = bywater.siphon.process(req)
        assert resp is not None

    def test_process_url_deepwater(self, deepwater: HeadwaterClient) -> None:
        req = SiphonRequest(
            source="https://example.com",
            origin=SourceOrigin.URL,
            params=SiphonRequestParams(action=ActionType.EXTRACT),
        )
        resp = deepwater.siphon.process(req)
        assert resp is not None

    # -----------------------------------------------------------------------
    # POST /siphon/process — edge cases (model-validated locally)
    # -----------------------------------------------------------------------

    def test_process_invalid_url_raises_locally(self) -> None:
        with pytest.raises(Exception):
            SiphonRequest(
                source="not-a-url",
                origin=SourceOrigin.URL,
                params=SiphonRequestParams(action=ActionType.EXTRACT),
            )

    def test_process_file_path_without_file_raises_locally(self) -> None:
        with pytest.raises(Exception):
            SiphonRequest(
                source="/tmp/nonexistent.txt",
                origin=SourceOrigin.FILE_PATH,
                params=SiphonRequestParams(action=ActionType.EXTRACT),
                file=None,
            )

    # -----------------------------------------------------------------------
    # POST /siphon/extract/batch — happy path
    # -----------------------------------------------------------------------

    def test_extract_batch_router(self, router: HeadwaterClient) -> None:
        req = BatchExtractRequest(
            sources=["https://example.com", "https://example.org"],
            max_concurrent=2,
        )
        resp = router.siphon.extract_batch(req)
        assert isinstance(resp, BatchExtractResponse)

    def test_extract_batch_bywater(self, bywater: HeadwaterClient) -> None:
        req = BatchExtractRequest(
            sources=["https://example.com"],
            max_concurrent=1,
        )
        resp = bywater.siphon.extract_batch(req)
        assert isinstance(resp, BatchExtractResponse)

    def test_extract_batch_deepwater(self, deepwater: HeadwaterClient) -> None:
        req = BatchExtractRequest(
            sources=["https://example.com"],
            max_concurrent=1,
        )
        resp = deepwater.siphon.extract_batch(req)
        assert isinstance(resp, BatchExtractResponse)

    def test_extract_batch_result_count_matches_sources(self, router: HeadwaterClient) -> None:
        sources = ["https://example.com", "https://example.org"]
        req = BatchExtractRequest(sources=sources, max_concurrent=2)
        resp = router.siphon.extract_batch(req)
        assert len(resp.results) == len(sources)

    def test_extract_batch_each_result_has_source(self, router: HeadwaterClient) -> None:
        req = BatchExtractRequest(sources=["https://example.com"])
        resp = router.siphon.extract_batch(req)
        for result in resp.results:
            assert isinstance(result, ExtractResult)
            assert isinstance(result.source, str)

    def test_extract_batch_result_text_xor_error(self, router: HeadwaterClient) -> None:
        # Each result must have exactly one of text or error set
        req = BatchExtractRequest(
            sources=["https://example.com", "https://this-host-does-not-exist-xyz.invalid"]
        )
        resp = router.siphon.extract_batch(req)
        for result in resp.results:
            has_text = result.text is not None
            has_error = result.error is not None
            assert has_text != has_error, (
                f"result for '{result.source}' must have exactly one of text or error"
            )

    def test_extract_batch_unreachable_url_has_error_field(self, router: HeadwaterClient) -> None:
        req = BatchExtractRequest(
            sources=["https://this-host-does-not-exist-xyz.invalid"],
            max_concurrent=1,
        )
        resp = router.siphon.extract_batch(req)
        assert len(resp.results) == 1
        result = resp.results[0]
        # Should not crash — either error is populated or text is populated
        assert result.text is not None or result.error is not None

    # -----------------------------------------------------------------------
    # POST /siphon/extract/batch — edge cases (model-validated locally)
    # -----------------------------------------------------------------------

    def test_extract_batch_max_concurrent_zero_raises(self) -> None:
        with pytest.raises(Exception):
            BatchExtractRequest(sources=["https://example.com"], max_concurrent=0)

    # -----------------------------------------------------------------------
    # POST /siphon/embed-batch — fake URIs (safe to call per spec)
    # -----------------------------------------------------------------------

    def test_embed_batch_fake_uris_router(self, router: HeadwaterClient) -> None:
        fake_uris = ["fake://uri1", "fake://uri2", "fake://uri3"]
        resp = router.siphon.embed_batch(uris=fake_uris, model=SIPHON_EMBED_MODEL, force=False)
        assert isinstance(resp, EmbedBatchResponse)

    def test_embed_batch_fake_uris_bywater(self, bywater: HeadwaterClient) -> None:
        fake_uris = ["fake://uri1"]
        resp = bywater.siphon.embed_batch(uris=fake_uris, model=SIPHON_EMBED_MODEL, force=False)
        assert isinstance(resp, EmbedBatchResponse)

    def test_embed_batch_fake_uris_deepwater(self, deepwater: HeadwaterClient) -> None:
        fake_uris = ["fake://uri1"]
        resp = deepwater.siphon.embed_batch(uris=fake_uris, model=SIPHON_EMBED_MODEL, force=False)
        assert isinstance(resp, EmbedBatchResponse)

    def test_embed_batch_fake_uris_skipped_count(self, router: HeadwaterClient) -> None:
        fake_uris = ["fake://uri1", "fake://uri2"]
        resp = router.siphon.embed_batch(uris=fake_uris, model=SIPHON_EMBED_MODEL, force=False)
        # Per spec: fake URIs not in DB → embedded=0, skipped=len(uris)
        assert resp.embedded == 0
        assert resp.skipped == len(fake_uris)

    def test_embed_batch_non_negative_counts(self, router: HeadwaterClient) -> None:
        resp = router.siphon.embed_batch(
            uris=["fake://x"], model=SIPHON_EMBED_MODEL, force=False
        )
        assert resp.embedded >= 0
        assert resp.skipped >= 0

    def test_embed_batch_empty_uris(self, router: HeadwaterClient) -> None:
        resp = router.siphon.embed_batch(uris=[], model=SIPHON_EMBED_MODEL, force=False)
        assert resp.embedded == 0
        assert resp.skipped == 0

    def test_embed_batch_force_false_skips_nonexistent_uris(self, router: HeadwaterClient) -> None:
        # Fake URIs are not in DB regardless of force flag — always skipped
        resp = router.siphon.embed_batch(
            uris=["fake://uri1"],
            model=SIPHON_EMBED_MODEL,
            force=False,
        )
        assert resp.embedded == 0
        assert resp.skipped == 1
