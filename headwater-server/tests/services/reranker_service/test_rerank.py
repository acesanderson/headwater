from __future__ import annotations
import math
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

def _make_mock_ranker(texts: list[str], scores: list[float]) -> MagicMock:
    """
    Build a mock Reranker whose .rank() returns results sorted by descending score.
    doc_id is assigned as the index in the input texts list.
    """
    results = []
    for i, (text, score) in enumerate(zip(texts, scores)):
        r = MagicMock()
        r.text = text
        r.score = score
        r.rank = i + 1
        r.document = MagicMock()
        r.document.doc_id = i
        results.append(r)

    sorted_results = sorted(results, key=lambda x: x.score, reverse=True)

    ranked = MagicMock()
    ranked.results = sorted_results
    ranked.top_k = lambda k: sorted_results[:k]

    mock_ranker = MagicMock()
    mock_ranker.rank.return_value = ranked
    return mock_ranker


def _patch_reranker(mock_ranker):
    """Context manager: patches get_reranker to return mock_ranker."""
    return patch(
        "headwater_server.services.reranker_service.rerank.get_reranker",
        return_value=mock_ranker,
    )


# ---------------------------------------------------------------------------
# AC1: results ordered highest score first
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_results_ordered_highest_score_first():
    """AC1: results are ordered from highest to lowest score."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    docs = ["low relevance", "high relevance", "medium relevance"]
    scores = [0.1, 0.9, 0.5]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(query="test query", documents=docs, model_name="flash", k=3)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    result_scores = [r.score for r in response.results]
    assert result_scores == sorted(result_scores, reverse=True)


# ---------------------------------------------------------------------------
# AC2: index is zero-based original position
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_result_index_is_original_position():
    """AC2: results[i].index is zero-based position in the original documents list."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    docs = ["doc A", "doc B", "doc C"]
    scores = [0.1, 0.9, 0.5]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(query="test", documents=docs, model_name="flash", k=3)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    assert response.results[0].index == 1
    assert response.results[0].document.text == "doc B"


# ---------------------------------------------------------------------------
# AC3: id and metadata echoed unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_id_and_metadata_echoed_unchanged():
    """AC3: id and metadata on RerankDocument are echoed back in the response unchanged."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest, RerankDocument

    docs = [
        RerankDocument(text="doc A", id="abc-123", metadata={"source": "db"}),
        RerankDocument(text="doc B", id=42, metadata={"source": "api"}),
    ]
    scores = [0.3, 0.9]
    mock_ranker = _make_mock_ranker([d.text for d in docs], scores)

    request = RerankRequest(query="test", documents=docs, model_name="flash", k=2)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    top = response.results[0]
    assert top.document.id == 42
    assert top.document.metadata == {"source": "api"}

    second = response.results[1]
    assert second.document.id == "abc-123"
    assert second.document.metadata == {"source": "db"}


# ---------------------------------------------------------------------------
# AC6: k > len(documents) → clamped silently
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_k_greater_than_docs_clamped_silently():
    """AC6: k=10 with 3 documents returns 3 results, no error."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    docs = ["doc A", "doc B", "doc C"]
    scores = [0.1, 0.9, 0.5]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(query="test", documents=docs, model_name="flash", k=10)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    assert len(response.results) == 3


# ---------------------------------------------------------------------------
# AC7: k=None returns all documents
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_k_none_returns_all_documents():
    """AC7: k=None returns all len(documents) results, ordered highest score first."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    docs = ["doc A", "doc B", "doc C", "doc D"]
    scores = [0.1, 0.9, 0.5, 0.3]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(query="test", documents=docs, model_name="flash", k=None)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    assert len(response.results) == 4
    result_scores = [r.score for r in response.results]
    assert result_scores == sorted(result_scores, reverse=True)


# ---------------------------------------------------------------------------
# AC8: alias resolved, echoed in response.model_name
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_alias_resolved_and_echoed_in_response():
    """AC8: model_name='bge' resolves to 'BAAI/bge-reranker-large'; response.model_name equals resolved name."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    docs = ["doc A", "doc B"]
    scores = [0.1, 0.9]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(query="test", documents=docs, model_name="bge", k=2)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    assert response.model_name == "BAAI/bge-reranker-large"


# ---------------------------------------------------------------------------
# AC9: unknown model → HTTPException 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_model_raises_http_422():
    """AC9: model_name not in aliases or allowlist → HTTPException with status_code=422."""
    from fastapi import HTTPException
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    request = RerankRequest(query="test", documents=["doc"], model_name="not-a-model")

    with pytest.raises(HTTPException) as exc_info:
        await run_rerank(request)

    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# AC10: normalize_scores applies sigmoid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normalize_scores_applies_sigmoid():
    """AC10: normalize_scores=True → all scores strictly in (0.0, 1.0)."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    docs = ["doc A", "doc B", "doc C"]
    scores = [-5.0, 2.3, 0.0]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(
        query="test", documents=docs, model_name="flash", k=3, normalize_scores=True
    )

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    for result in response.results:
        assert 0.0 < result.score < 1.0


# ---------------------------------------------------------------------------
# AC13: str and RerankDocument inputs produce same index and score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_str_and_rerank_document_produce_same_index_and_score():
    """AC13: list[str] input produces same index and score as list[RerankDocument(text=...)]."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest, RerankDocument

    docs_str = ["doc A", "doc B"]
    docs_obj = [RerankDocument(text="doc A"), RerankDocument(text="doc B")]
    scores = [0.2, 0.8]

    mock_ranker_str = _make_mock_ranker(docs_str, scores)
    mock_ranker_obj = _make_mock_ranker(docs_str, scores)

    request_str = RerankRequest(query="test", documents=docs_str, model_name="flash", k=2)
    request_obj = RerankRequest(query="test", documents=docs_obj, model_name="flash", k=2)

    with _patch_reranker(mock_ranker_str):
        response_str = await run_rerank(request_str)

    with _patch_reranker(mock_ranker_obj):
        response_obj = await run_rerank(request_obj)

    for r_str, r_obj in zip(response_str.results, response_obj.results):
        assert r_str.index == r_obj.index
        assert r_str.score == r_obj.score
        assert r_str.document.id is None
        assert r_obj.document.id is None
