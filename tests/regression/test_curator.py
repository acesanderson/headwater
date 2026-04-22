"""
Regression tests — Curator endpoint.

Covers: /curator/curate
"""

from __future__ import annotations

import pytest

from headwater_api.classes import (
    CuratorRequest,
    CuratorResponse,
    CuratorResult,
    HeadwaterServerException,
)
from headwater_client.client.headwater_client import HeadwaterClient


class TestCurator:
    # -----------------------------------------------------------------------
    # POST /curator/curate — happy path
    # -----------------------------------------------------------------------

    def test_curate_router(self, router: HeadwaterClient) -> None:
        req = CuratorRequest(query_string="introduction to neural networks")
        resp = router.curator.curate(req)
        assert isinstance(resp, CuratorResponse)

    def test_curate_bywater(self, bywater: HeadwaterClient) -> None:
        req = CuratorRequest(query_string="machine learning fundamentals")
        resp = bywater.curator.curate(req)
        assert isinstance(resp, CuratorResponse)

    def test_curate_deepwater(self, deepwater: HeadwaterClient) -> None:
        req = CuratorRequest(query_string="deep learning basics")
        resp = deepwater.curator.curate(req)
        assert isinstance(resp, CuratorResponse)

    def test_curate_results_is_list(self, router: HeadwaterClient) -> None:
        req = CuratorRequest(query_string="data science")
        resp = router.curator.curate(req)
        assert isinstance(resp.results, list)

    def test_curate_results_respect_k(self, router: HeadwaterClient) -> None:
        k = 3
        req = CuratorRequest(query_string="python programming", k=k)
        resp = router.curator.curate(req)
        assert len(resp.results) <= k

    def test_curate_result_fields(self, router: HeadwaterClient) -> None:
        req = CuratorRequest(query_string="supervised learning", k=5)
        resp = router.curator.curate(req)
        for result in resp.results:
            assert isinstance(result, CuratorResult)
            assert isinstance(result.id, str)
            assert isinstance(result.score, float)

    def test_curate_results_ordered_by_score_descending(self, router: HeadwaterClient) -> None:
        req = CuratorRequest(query_string="natural language processing", k=5)
        resp = router.curator.curate(req)
        if len(resp.results) > 1:
            scores = [r.score for r in resp.results]
            assert scores == sorted(scores, reverse=True), (
                "curator results must be ordered by score descending"
            )

    def test_curate_cached_false_still_returns_valid(self, router: HeadwaterClient) -> None:
        req = CuratorRequest(query_string="reinforcement learning", cached=False)
        resp = router.curator.curate(req)
        assert isinstance(resp, CuratorResponse)

    def test_curate_custom_n_results(self, router: HeadwaterClient) -> None:
        req = CuratorRequest(query_string="statistics", k=5, n_results=10)
        resp = router.curator.curate(req)
        assert isinstance(resp, CuratorResponse)
        assert len(resp.results) <= 5

    # -----------------------------------------------------------------------
    # POST /curator/curate — edge cases
    # -----------------------------------------------------------------------

    def test_curate_missing_query_string_raises(self) -> None:
        with pytest.raises(Exception):
            CuratorRequest()  # type: ignore[call-arg]

    def test_curate_unknown_model_raises(self, router: HeadwaterClient) -> None:
        req = CuratorRequest(
            query_string="test query", model_name="nonexistent-model-xyz"
        )
        with pytest.raises((HeadwaterServerException, Exception)):
            router.curator.curate(req)
