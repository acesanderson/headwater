# Smoke Test Results

**Date:** 2026-03-08
**Result:** 7 passed | 4 failed | 2 skipped

## Results

| Test | Status | Notes |
|---|---|---|
| `ping` | PASS | Returns `True` |
| `get_status` | PASS | `status='healthy'`, server is running |
| `list_routes` | PASS | Routes enumerated correctly |
| `embeddings.list_embedding_models` | PASS | Returns model list |
| `embeddings.quick_embedding` | PASS | Embedding vector returned |
| `embeddings.list_collections` | FAIL | Server-side import error: `cannot import name 'get_network_context' from 'dbclients'` |
| `reranker.list_reranker_models` | FAIL | Client-side deserialization: `ValidationError for RerankerModelInfo` — server response does not match Pydantic model |
| `reranker.rerank` | FAIL | Server-side API mismatch: `FlashRankRanker.rank() got unexpected keyword argument 'max_length'` |
| `curator.curate` | PASS | Returns `CuratorResult` objects |
| `conduit.tokenize` | FAIL | Server-side async bug: `asyncio.run() cannot be called from a running event loop` |
| `conduit.query_generate` | PASS | Response received |
| `siphon.process` | SKIP | Requires a live siphon URI |
| `siphon.embed_batch` | SKIP | Requires a live siphon URI |

## Failures Detail

**`embeddings.list_collections`**
Server-side `ImportError`: `cannot import name 'get_network_context' from 'dbclients'`. The collections handler has a broken import, likely a stale reference to an old dbclients API.

**`reranker.list_reranker_models`**
Client-side `ValidationError` on `RerankerModelInfo`. The shape of the server's response does not match the Pydantic model — either the model or the server response schema has drifted.

**`reranker.rerank`**
Server-side `TypeError`: `FlashRankRanker.rank() got unexpected keyword argument 'max_length'`. The `max_length` field in `RerankRequest` is being forwarded to a version of FlashRank that does not support it.

**`conduit.tokenize`**
Server-side `RuntimeError`: `asyncio.run() cannot be called from a running event loop`. The tokenize handler calls `asyncio.run()` inside a context where an event loop is already running.
