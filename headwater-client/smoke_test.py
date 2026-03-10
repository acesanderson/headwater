"""
Smoke test for headwater-client.
Run with: uv run python smoke_test.py
"""

from __future__ import annotations

import traceback

from headwater_client.client.headwater_client import HeadwaterClient
from headwater_api.classes import (
    QuickEmbeddingRequest,
    RerankRequest,
    CuratorRequest,
    TokenizationRequest,
    GenerationRequest,
)
from headwater_api.classes import EmbeddingTask
from conduit.domain.request.generation_params import GenerationParams
from conduit.domain.config.conduit_options import ConduitOptions
from conduit.domain.message.message import UserMessage

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

results: list[tuple[str, str, str]] = []  # (name, status, note)


def run(name: str, fn):
    try:
        result = fn()
        results.append((name, PASS, str(result)[:120]))
    except Exception as e:
        results.append((name, FAIL, f"{type(e).__name__}: {e}"))


client = HeadwaterClient()

# --- Server health ---

run("ping", lambda: client.ping())
run("get_status", lambda: client.get_status())
run("list_routes", lambda: client.list_routes())

# --- Embeddings ---

run(
    "embeddings.list_embedding_models",
    lambda: client.embeddings.list_embedding_models(),
)

run(
    "embeddings.quick_embedding",
    lambda: client.embeddings.quick_embedding(
        QuickEmbeddingRequest(
            query="What is machine learning?",
            model="sentence-transformers/all-MiniLM-L6-v2",
        )
    ),
)

run(
    "embeddings.list_collections",
    lambda: client.embeddings.list_collections(),
)

# --- Reranker ---

run(
    "reranker.list_reranker_models",
    lambda: client.reranker.list_reranker_models(),
)

_rerank_query = "machine learning fundamentals"
_rerank_docs = [
    "Introduction to neural networks and deep learning.",
    "Cooking recipes for pasta dishes.",
    "Supervised learning with decision trees.",
    "The history of the Roman Empire.",
    "Gradient descent optimization techniques.",
]

try:
    _reranker_models = client.reranker.list_reranker_models()
except Exception as e:
    _reranker_models = []
    results.append(("reranker.list_reranker_models (fetch)", FAIL, f"{type(e).__name__}: {e}"))

for _model_info in _reranker_models:
    run(
        f"reranker.rerank[{_model_info.name}]",
        lambda m=_model_info.name: client.reranker.rerank(
            RerankRequest(
                query=_rerank_query,
                documents=_rerank_docs,
                model_name=m,
                k=3,
            )
        ),
    )

# --- Curator ---

run(
    "curator.curate",
    lambda: client.curator.curate(
        CuratorRequest(
            query_string="machine learning fundamentals",
            k=3,
        )
    ),
)

# --- Conduit ---

run(
    "conduit.tokenize",
    lambda: client.conduit.tokenize(
        TokenizationRequest(
            model="haiku",
            text="The quick brown fox jumps over the lazy dog.",
        )
    ),
)

run(
    "conduit.query_generate",
    lambda: client.conduit.query_generate(
        GenerationRequest(
            messages=[UserMessage(content="Reply with one word: hello.")],
            params=GenerationParams(model="haiku", max_tokens=10),
            options=ConduitOptions(project_name="smoke-test"),
        )
    ),
)

# --- Siphon (skipped — requires a real URI in the system) ---

results.append(("siphon.process", SKIP, "Requires a live siphon URI"))
results.append(("siphon.embed_batch", SKIP, "Requires a live siphon URI"))

# --- Report ---

width = 40
print()
print("=" * (width + 30))
print(f"{'TEST':<{width}} {'STATUS':<8} NOTE")
print("=" * (width + 30))
for name, status, note in results:
    truncated = note[:60] + "..." if len(note) > 60 else note
    print(f"{name:<{width}} {status:<8} {truncated}")
print("=" * (width + 30))

passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)
skipped = sum(1 for _, s, _ in results if s == SKIP)
print(f"\n{passed} passed  {failed} failed  {skipped} skipped")
print()
