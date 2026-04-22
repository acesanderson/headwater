"""
Regression tests — Embeddings endpoints.

Covers: /conduit/embeddings, /conduit/embeddings/models, /conduit/embeddings/quick
"""

from __future__ import annotations

import pytest

from headwater_api.classes import (
    ChromaBatch,
    EmbeddingModelSpec,
    EmbeddingsRequest,
    EmbeddingsResponse,
    HeadwaterServerException,
    QuickEmbeddingRequest,
    QuickEmbeddingResponse,
)
from headwater_client.client.headwater_client import HeadwaterClient

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class TestEmbeddings:
    # -----------------------------------------------------------------------
    # POST /conduit/embeddings — happy path
    # -----------------------------------------------------------------------

    def test_generate_embeddings_router(self, router: HeadwaterClient) -> None:
        req = EmbeddingsRequest(
            model=EMBED_MODEL,
            batch=ChromaBatch(
                ids=["doc1", "doc2"],
                documents=["hello world", "foo bar"],
            ),
        )
        resp = router.embeddings.generate_embeddings(req)
        assert isinstance(resp, EmbeddingsResponse)
        assert len(resp.embeddings) == 2

    def test_generate_embeddings_bywater(self, bywater: HeadwaterClient) -> None:
        req = EmbeddingsRequest(
            model=EMBED_MODEL,
            batch=ChromaBatch(ids=["a"], documents=["test document"]),
        )
        resp = bywater.embeddings.generate_embeddings(req)
        assert len(resp.embeddings) == 1

    def test_generate_embeddings_deepwater(self, deepwater: HeadwaterClient) -> None:
        req = EmbeddingsRequest(
            model=EMBED_MODEL,
            batch=ChromaBatch(ids=["b"], documents=["another test"]),
        )
        resp = deepwater.embeddings.generate_embeddings(req)
        assert len(resp.embeddings) == 1

    def test_generate_embeddings_vector_is_nonempty_floats(self, router: HeadwaterClient) -> None:
        req = EmbeddingsRequest(
            model=EMBED_MODEL,
            batch=ChromaBatch(ids=["x"], documents=["test"]),
        )
        resp = router.embeddings.generate_embeddings(req)
        vec = resp.embeddings[0]
        assert len(vec) > 0
        assert all(isinstance(v, float) for v in vec)

    def test_generate_embeddings_count_matches_documents(self, router: HeadwaterClient) -> None:
        docs = ["alpha", "beta", "gamma", "delta"]
        req = EmbeddingsRequest(
            model=EMBED_MODEL,
            batch=ChromaBatch(ids=[str(i) for i in range(len(docs))], documents=docs),
        )
        resp = router.embeddings.generate_embeddings(req)
        assert len(resp.embeddings) == len(docs)

    # -----------------------------------------------------------------------
    # POST /conduit/embeddings — edge cases (model-validated locally)
    # -----------------------------------------------------------------------

    def test_generate_embeddings_task_and_prompt_raises(self) -> None:
        with pytest.raises(Exception):
            EmbeddingsRequest(
                model=EMBED_MODEL,
                batch=ChromaBatch(ids=["x"], documents=["test"]),
                task="query",
                prompt="some prompt",
            )

    def test_generate_embeddings_unknown_model_raises(self, router: HeadwaterClient) -> None:
        req = EmbeddingsRequest(
            model="nonexistent-embed-model-xyz",
            batch=ChromaBatch(ids=["x"], documents=["test"]),
        )
        with pytest.raises((HeadwaterServerException, Exception)):
            router.embeddings.generate_embeddings(req)

    # -----------------------------------------------------------------------
    # GET /conduit/embeddings/models
    # -----------------------------------------------------------------------

    def test_list_embedding_models_returns_list(self, router: HeadwaterClient) -> None:
        resp = router.embeddings.list_embedding_models()
        assert isinstance(resp, list)
        assert len(resp) > 0

    def test_list_embedding_models_bywater(self, bywater: HeadwaterClient) -> None:
        resp = bywater.embeddings.list_embedding_models()
        assert isinstance(resp, list)
        assert len(resp) > 0

    def test_list_embedding_models_deepwater(self, deepwater: HeadwaterClient) -> None:
        resp = deepwater.embeddings.list_embedding_models()
        assert isinstance(resp, list)
        assert len(resp) > 0

    def test_list_embedding_models_each_is_spec(self, router: HeadwaterClient) -> None:
        resp = router.embeddings.list_embedding_models()
        for spec in resp:
            assert isinstance(spec, EmbeddingModelSpec)
            assert isinstance(spec.model, str)
            assert isinstance(spec.multilingual, bool)

    def test_list_embedding_models_no_contradictory_flags(self, router: HeadwaterClient) -> None:
        resp = router.embeddings.list_embedding_models()
        for spec in resp:
            assert not (spec.prompt_required and spec.prompt_unsupported), (
                f"model '{spec.model}' has both prompt_required=True and prompt_unsupported=True"
            )

    # -----------------------------------------------------------------------
    # POST /conduit/embeddings/quick
    # -----------------------------------------------------------------------

    def test_quick_embedding_router(self, router: HeadwaterClient) -> None:
        req = QuickEmbeddingRequest(query="what is machine learning")
        resp = router.embeddings.quick_embedding(req)
        assert isinstance(resp, QuickEmbeddingResponse)
        assert len(resp.embedding) > 0

    def test_quick_embedding_bywater(self, bywater: HeadwaterClient) -> None:
        req = QuickEmbeddingRequest(query="deep learning")
        resp = bywater.embeddings.quick_embedding(req)
        assert len(resp.embedding) > 0

    def test_quick_embedding_deepwater(self, deepwater: HeadwaterClient) -> None:
        req = QuickEmbeddingRequest(query="neural networks")
        resp = deepwater.embeddings.quick_embedding(req)
        assert len(resp.embedding) > 0

    def test_quick_embedding_returns_floats(self, router: HeadwaterClient) -> None:
        req = QuickEmbeddingRequest(query="test query")
        resp = router.embeddings.quick_embedding(req)
        assert all(isinstance(v, float) for v in resp.embedding)

    def test_quick_embedding_task_and_prompt_raises(self) -> None:
        with pytest.raises(Exception):
            QuickEmbeddingRequest(
                query="test", task="query", prompt="prefix: "
            )

    def test_quick_embedding_unknown_model_raises(self, router: HeadwaterClient) -> None:
        req = QuickEmbeddingRequest(
            query="test",
            model="nonexistent-embed-model-xyz",
        )
        with pytest.raises((HeadwaterServerException, Exception)):
            router.embeddings.quick_embedding(req)
