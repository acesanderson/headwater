# Curator Spec — Headwater Regression Tests

All `/curator/*` endpoints for embedding-based content retrieval/curation.

---

### POST /curator/curate
- **Description**: Retrieve top-k curated items from the embedding store for a query string. Uses cached embeddings and a vector index. Returns item IDs with relevance scores.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `query_string` (str): the retrieval query; example `"introduction to neural networks"`
  - `k` (int, default 5): number of top items to return
  - `n_results` (int, default 30): total candidates to consider before selecting top k
  - `model_name` (str, default `"bge"`): embedding model alias used for retrieval
  - `cached` (bool, default True): whether to use cached query results
- **Expected response**:
  - 200
  - Shape: `CuratorResponse` — field `results` (list[CuratorResult])
  - Each `CuratorResult`: `id` (str), `score` (float)
  - `len(results)` ≤ `k`
  - Scores should be floats; higher score = more relevant
  - Results should be ordered by score descending
- **Edge cases**:
  - Missing `query_string` → 422
  - Empty `query_string` → behavior TBD (may 422 or return empty results)
  - `k=0` → may return empty list or 422
  - `k > n_results` → returns at most `n_results` items (n_results is the candidate pool)
  - Unknown `model_name` → 4xx with structured error
  - `cached=False` forces re-computation — should still return valid results
- **Already covered**: no
