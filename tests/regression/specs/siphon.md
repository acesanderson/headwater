# Siphon Spec — Headwater Regression Tests

All `/siphon/*` endpoints for content ingestion, extraction, and embedding.

---

### POST /siphon/process
- **Description**: Process a content source through the Siphon pipeline (fetch, extract, parse). Returns structured `SiphonResponse`.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - Shape: `SiphonRequest` (from siphon_api library — verify exact fields)
  - Minimal example: a single URI/URL to process
- **Expected response**:
  - 200
  - Shape: `SiphonResponse` (from siphon_api library)
  - Response should include extracted text or structured content
- **Edge cases**:
  - Missing required fields → 422
  - Unreachable URI → error field populated, not a 5xx crash
  - Malformed URI → 422 or structured error
- **Already covered**: no

---

### POST /siphon/extract/batch
- **Description**: Batch-extract raw text from multiple sources (URLs, file paths, etc.). Concurrent extraction.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `sources` (list[str]): list of URIs/URLs to extract from; example `["https://example.com", "https://example.org"]`
  - `max_concurrent` (int, default 10, ge=1): concurrency cap
- **Expected response**:
  - 200
  - Shape: `BatchExtractResponse` — field `results` (list[ExtractResult])
  - Each `ExtractResult`: `source` (str), `text` (str|None), `error` (str|None)
  - Invariant: each result has exactly one of `text` or `error` set (not both, not neither)
  - `len(results)` must equal `len(sources)`
- **Edge cases**:
  - Empty `sources` list → may return empty results or 422
  - `max_concurrent=0` → 422 (ge=1)
  - Mix of reachable and unreachable URLs → partial success; reachable have `text`, unreachable have `error`
  - Single source that fails → `error` field populated, HTTP status still 200
  - Malformed URL in sources → `error` field populated, not a 5xx crash
- **Already covered**: no

---

### POST /siphon/embed-batch
- **Description**: Batch-embed siphon records by URI. Fetches title+summary from DB, skips already-embedded rows (unless force=True), encodes in chunks of 128, writes vectors back. Safe to call with fake/non-existent URIs — returns `embedded=0, skipped=N`.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `uris` (list[str]): URIs of siphon DB records; example `["fake://uri1", "fake://uri2"]`
  - `model` (str, default `"sentence-transformers/all-MiniLM-L6-v2"`): embedding model name
  - `force` (bool, default False): re-embed even if embedding already exists
- **Expected response**:
  - 200
  - Shape: `EmbedBatchResponse` — fields `embedded` (int), `skipped` (int)
  - Both fields must be non-negative
  - `embedded + skipped` should equal `len(uris)` (for URIs present in DB)
  - With fake URIs: `embedded=0`, `skipped=len(uris)`
- **Edge cases**:
  - Empty `uris` list → `embedded=0, skipped=0`
  - `force=True` with already-embedded URIs → `embedded` should be > 0
  - Unknown `model` → 4xx with structured error
  - Fake URIs (not in DB) → `embedded=0, skipped=len(uris)` — does not crash
- **Already covered**: no
