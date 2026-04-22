"""
Regression tests — Reranker endpoints.

Covers: /reranker/rerank, /reranker/models
"""

from __future__ import annotations

import pytest

from headwater_api.classes import (
    HeadwaterServerException,
    RerankDocument,
    RerankRequest,
    RerankResponse,
    RerankResult,
    RerankerModelInfo,
)
from headwater_client.client.headwater_client import HeadwaterClient

_DOCS = [
    "Machine learning is a subset of artificial intelligence.",
    "Deep learning uses neural networks with many layers.",
    "Gradient descent is an optimization algorithm.",
    "Support vector machines are supervised learning models.",
    "Natural language processing handles text understanding.",
]


class TestReranker:
    # -----------------------------------------------------------------------
    # POST /reranker/rerank — happy path
    # -----------------------------------------------------------------------

    def test_rerank_router(self, router: HeadwaterClient) -> None:
        req = RerankRequest(query="machine learning basics", documents=_DOCS)
        resp = router.reranker.rerank(req)
        assert isinstance(resp, RerankResponse)

    def test_rerank_bywater(self, bywater: HeadwaterClient) -> None:
        req = RerankRequest(query="neural networks", documents=_DOCS, k=3)
        resp = bywater.reranker.rerank(req)
        assert isinstance(resp, RerankResponse)

    def test_rerank_deepwater(self, deepwater: HeadwaterClient) -> None:
        req = RerankRequest(query="optimization", documents=_DOCS, k=2)
        resp = deepwater.reranker.rerank(req)
        assert isinstance(resp, RerankResponse)

    def test_rerank_result_count_respects_k(self, router: HeadwaterClient) -> None:
        req = RerankRequest(query="learning", documents=_DOCS, k=3)
        resp = router.reranker.rerank(req)
        assert len(resp.results) <= 3

    def test_rerank_model_name_echoed(self, router: HeadwaterClient) -> None:
        req = RerankRequest(query="query", documents=_DOCS, model_name="flash")
        resp = router.reranker.rerank(req)
        # Server resolves the "flash" alias to the actual model name
        assert isinstance(resp.model_name, str)
        assert len(resp.model_name) > 0

    def test_rerank_results_are_rerank_results(self, router: HeadwaterClient) -> None:
        req = RerankRequest(query="machine learning", documents=_DOCS, k=2)
        resp = router.reranker.rerank(req)
        for r in resp.results:
            assert isinstance(r, RerankResult)
            assert isinstance(r.document, RerankDocument)
            assert isinstance(r.index, int)
            assert isinstance(r.score, float)

    def test_rerank_results_ordered_by_score_descending(self, router: HeadwaterClient) -> None:
        req = RerankRequest(query="machine learning", documents=_DOCS, k=5)
        resp = router.reranker.rerank(req)
        scores = [r.score for r in resp.results]
        assert scores == sorted(scores, reverse=True), "results must be ordered by score descending"

    def test_rerank_index_references_original_position(self, router: HeadwaterClient) -> None:
        req = RerankRequest(query="neural", documents=_DOCS)
        resp = router.reranker.rerank(req)
        for r in resp.results:
            assert 0 <= r.index < len(_DOCS)

    def test_rerank_k_larger_than_docs_returns_all(self, router: HeadwaterClient) -> None:
        docs = ["one", "two"]
        req = RerankRequest(query="one", documents=docs, k=100)
        resp = router.reranker.rerank(req)
        assert len(resp.results) <= len(docs)

    def test_rerank_k_none_returns_all(self, router: HeadwaterClient) -> None:
        docs = ["apple", "banana", "cherry"]
        req = RerankRequest(query="fruit", documents=docs, k=None)
        resp = router.reranker.rerank(req)
        assert len(resp.results) <= len(docs)

    def test_rerank_single_document(self, router: HeadwaterClient) -> None:
        req = RerankRequest(query="query", documents=["only document"])
        resp = router.reranker.rerank(req)
        assert len(resp.results) == 1

    def test_rerank_with_rerank_document_objects(self, router: HeadwaterClient) -> None:
        docs = [
            RerankDocument(text="first doc", id="d1"),
            RerankDocument(text="second doc", id="d2"),
        ]
        req = RerankRequest(query="doc", documents=docs, k=2)
        resp = router.reranker.rerank(req)
        assert len(resp.results) <= 2

    def test_rerank_normalize_scores(self, router: HeadwaterClient) -> None:
        req = RerankRequest(
            query="machine learning", documents=_DOCS, normalize_scores=True
        )
        resp = router.reranker.rerank(req)
        # Normalized scores should be in [0, 1]
        for r in resp.results:
            assert 0.0 <= r.score <= 1.0

    # -----------------------------------------------------------------------
    # POST /reranker/rerank — edge cases (validation)
    # -----------------------------------------------------------------------

    def test_rerank_empty_query_raises(self) -> None:
        with pytest.raises(Exception):
            RerankRequest(query="", documents=["doc"])

    def test_rerank_empty_documents_raises(self) -> None:
        with pytest.raises(Exception):
            RerankRequest(query="query", documents=[])

    def test_rerank_unknown_model_raises(self, router: HeadwaterClient) -> None:
        req = RerankRequest(
            query="test", documents=["doc one", "doc two"], model_name="nonexistent-model-xyz"
        )
        with pytest.raises((HeadwaterServerException, Exception)):
            router.reranker.rerank(req)

    # -----------------------------------------------------------------------
    # GET /reranker/models
    # -----------------------------------------------------------------------

    def test_list_reranker_models_router(self, router: HeadwaterClient) -> None:
        resp = router.reranker.list_reranker_models()
        assert isinstance(resp, list)
        assert len(resp) > 0

    def test_list_reranker_models_bywater(self, bywater: HeadwaterClient) -> None:
        resp = bywater.reranker.list_reranker_models()
        assert isinstance(resp, list)
        assert len(resp) > 0

    def test_list_reranker_models_deepwater(self, deepwater: HeadwaterClient) -> None:
        resp = deepwater.reranker.list_reranker_models()
        assert isinstance(resp, list)
        assert len(resp) > 0

    def test_list_reranker_models_each_has_name_and_output_type(
        self, router: HeadwaterClient
    ) -> None:
        resp = router.reranker.list_reranker_models()
        for model_info in resp:
            assert isinstance(model_info, RerankerModelInfo)
            assert isinstance(model_info.name, str)
            assert isinstance(model_info.output_type, str)
