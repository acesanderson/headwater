from __future__ import annotations
import pytest
from pydantic import ValidationError


def test_empty_documents_raises():
    """AC4: documents=[] -> 422 (Pydantic ValidationError)"""
    from headwater_api.classes import RerankRequest
    with pytest.raises(ValidationError):
        RerankRequest(query="hello", documents=[])


def test_empty_query_raises():
    """AC5: query="" -> 422 (Pydantic ValidationError)"""
    from headwater_api.classes import RerankRequest
    with pytest.raises(ValidationError):
        RerankRequest(query="", documents=["doc"])


def test_str_normalized_to_rerank_document():
    """AC13: bare strings coerced to RerankDocument with id=None, metadata=None"""
    from headwater_api.classes import RerankRequest, RerankDocument
    req = RerankRequest(query="hello", documents=["doc one", "doc two"])
    assert all(isinstance(d, RerankDocument) for d in req.documents)
    assert req.documents[0].text == "doc one"
    assert req.documents[0].id is None
    assert req.documents[0].metadata is None
