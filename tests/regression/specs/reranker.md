# Reranker Spec — Headwater Regression Tests

All `/reranker/*` endpoints for document reranking and model listing.

---

### POST /reranker/rerank
- **Description**: Rerank a list of documents against a query. Returns top-k results with scores.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `query` (str, min_length=1): search query; example `"machine learning basics"`
  - `documents` (list[str|RerankDocument], min_length=1): documents to rank
    - Simple form: list of strings, e.g. `["doc one text", "doc two text", "doc three text"]`
    - Rich form: list of `RerankDocument` objects with `text`, optional `id`, optional `metadata`
  - `model_name` (str, default `"flash"`): reranker model alias; example `"flash"`
  - `k` (int|None, default 5): number of top results to return
  - `normalize_scores` (bool, default False): whether to normalize relevance scores
  - `max_length` (int, default 512): max token length per document
- **Expected response**:
  - 200
  - Shape: `RerankResponse` — fields `results` (list[RerankResult]), `model_name` (str)
  - Each `RerankResult`: `document` (RerankDocument), `index` (int), `score` (float)
  - `len(results)` ≤ `k` (if k is set)
  - `model_name` should match the requested model
  - Results should be ordered by `score` descending
  - `index` values should reference original document positions
- **Edge cases**:
  - Empty `query` (length 0) → 422 (min_length=1)
  - Empty `documents` list → 422 (min_length=1)
  - `k` larger than number of documents → returns all documents ranked
  - `k=None` → returns all documents ranked
  - Unknown `model_name` → 4xx with structured error
  - Mixed string and RerankDocument inputs in `documents` list → should work (normalized by validator)
  - Single document → returns one result
- **Already covered**: no

---

### GET /reranker/models
- **Description**: List available reranker models.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**: none
- **Expected response**:
  - 200
  - Shape: `list[RerankerModelInfo]`
  - Each `RerankerModelInfo`: `name` (str), `output_type` (str)
  - List must be non-empty
- **Edge cases**: none — read-only, no inputs
- **Already covered**: no
