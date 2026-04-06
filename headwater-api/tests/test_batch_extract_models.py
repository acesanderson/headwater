# $BC/headwater/headwater-api/tests/test_batch_extract_models.py
import pytest
from pydantic import ValidationError


def test_batch_extract_request_stores_sources():
    from headwater_api.classes import BatchExtractRequest
    req = BatchExtractRequest(sources=["doc.pdf", "article.html"], max_concurrent=5)
    assert req.sources == ["doc.pdf", "article.html"]
    assert req.max_concurrent == 5


def test_batch_extract_request_default_concurrent_is_10():
    from headwater_api.classes import BatchExtractRequest
    req = BatchExtractRequest(sources=["doc.pdf"])
    assert req.max_concurrent == 10


def test_extract_result_success_state():
    from headwater_api.classes import ExtractResult
    r = ExtractResult(source="doc.pdf", text="hello world", error=None)
    assert r.text == "hello world"
    assert r.error is None


def test_extract_result_failure_state():
    from headwater_api.classes import ExtractResult
    r = ExtractResult(source="doc.pdf", text=None, error="docling timeout")
    assert r.text is None
    assert r.error == "docling timeout"


def test_extract_result_rejects_both_none():
    from headwater_api.classes import ExtractResult
    with pytest.raises(ValidationError):
        ExtractResult(source="a.pdf", text=None, error=None)


def test_extract_result_rejects_both_set():
    from headwater_api.classes import ExtractResult
    with pytest.raises(ValidationError):
        ExtractResult(source="a.pdf", text="content", error="also failed")


def test_batch_extract_request_rejects_zero_concurrent():
    from headwater_api.classes import BatchExtractRequest
    with pytest.raises(ValidationError):
        BatchExtractRequest(sources=["a.pdf"], max_concurrent=0)


def test_batch_extract_response_round_trips_json():
    from headwater_api.classes import BatchExtractResponse, ExtractResult
    resp = BatchExtractResponse(results=[
        ExtractResult(source="a.pdf", text="content", error=None),
        ExtractResult(source="b.pdf", text=None, error="failed"),
    ])
    json_str = resp.model_dump_json()
    restored = BatchExtractResponse.model_validate_json(json_str)
    assert len(restored.results) == 2
    assert restored.results[1].error == "failed"
    assert restored.results[0].text == "content"
