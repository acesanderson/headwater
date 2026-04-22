# Embeddings Spec — Headwater Regression Tests

All `/conduit/embeddings/*` endpoints for generating, querying, and listing embedding collections.

---

### POST /conduit/embeddings
- **Description**: Generate embeddings for a batch of documents using a named embedding model. Stateless — no DB write.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `model` (str): embedding model name; example `"sentence-transformers/all-MiniLM-L6-v2"`
  - `batch` (ChromaBatch):
    - `ids` (list[str]): unique IDs per document; example `["doc1", "doc2"]`
    - `documents` (list[str]): text documents; example `["hello world", "foo bar"]`
    - `embeddings` (list[list[float]]|None): optional pre-computed embeddings
    - `metadatas` (list[dict]|None): optional metadata per document
  - `task` (EmbeddingTask|None): one of `"query"`, `"document"`, `"classification"`, `"clustering"` — mutually exclusive with `prompt`
  - `prompt` (str|None): raw prompt string — mutually exclusive with `task`
- **Expected response**:
  - 200
  - Shape: `EmbeddingsResponse` — field `embeddings` (list[list[float]])
  - `len(embeddings)` must equal `len(batch.documents)`
  - Each embedding vector should have a fixed positive dimension
- **Edge cases**:
  - Both `task` and `prompt` provided → 422
  - Missing `model` → 422
  - Missing `batch` → 422
  - Empty `batch.documents` list → 422 or empty embeddings
  - Mismatched `len(ids)` and `len(documents)` → may return 422 or error at service layer
  - Unknown model name → 4xx with structured error
- **Already covered**: no

---

### GET /conduit/embeddings/models
- **Description**: List all available embedding models with their specs.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**: none
- **Expected response**:
  - 200
  - Shape: `list[EmbeddingModelSpec]`
  - Each `EmbeddingModelSpec` has:
    - `model` (str): model name
    - `provider` (EmbeddingProvider): provider identifier
    - `description` (str|None)
    - `embedding_dim` (int|None)
    - `max_seq_length` (int|None)
    - `multilingual` (bool)
    - `parameter_count` (str|None)
    - `prompt_required` (bool)
    - `valid_prefixes` (list[str]|None)
    - `prompt_unsupported` (bool)
    - `task_map` (dict[str,str]|None)
  - List must be non-empty
  - No model spec should have both `prompt_required=True` and `prompt_unsupported=True`
- **Edge cases**: none — read-only, no inputs
- **Already covered**: no

---

### POST /conduit/embeddings/quick
- **Description**: Generate a single embedding for a query string. Convenience endpoint.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `query` (str): text to embed; example `"what is machine learning"`
  - `model` (str, default `"sentence-transformers/all-MiniLM-L6-v2"`): embedding model
  - `task` (EmbeddingTask|None): optional task type — mutually exclusive with `prompt`
  - `prompt` (str|None): raw prompt — mutually exclusive with `task`
- **Expected response**:
  - 200
  - Shape: `QuickEmbeddingResponse` — field `embedding` (list[float])
  - `embedding` must be a non-empty list of floats
- **Edge cases**:
  - Both `task` and `prompt` provided → 422
  - Missing `query` → 422
  - Empty string for `query` → may 422 or return embedding of empty input
  - Unknown model → 4xx with structured error
- **Already covered**: no

---

### POST /conduit/embeddings/collections/get
- **Description**: Retrieve metadata for a named embedding collection. Read-only.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `collection_name` (str): name of the collection; use an existing collection name
- **Expected response**:
  - 200
  - Shape: `CollectionRecord` — fields `name` (str), `no_of_ids` (int), `no_of_documents` (int), `model` (str|None), `metadata` (dict|None)
  - `no_of_ids` and `no_of_documents` should be non-negative
- **Edge cases**:
  - Unknown `collection_name` → 4xx (likely 404 or structured error)
  - Missing `collection_name` field → 422
- **Already covered**: no

---

### GET /conduit/embeddings/collections
- **Description**: List all available embedding collections. Read-only.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**: none
- **Expected response**:
  - 200
  - Shape: `ListCollectionsResponse` — field `collections` (list[CollectionRecord])
  - Each `CollectionRecord`: `name`, `no_of_ids`, `no_of_documents`, `model`, `metadata`
  - Response is valid even if list is empty
- **Edge cases**: none — read-only, no inputs
- **Already covered**: no

---

### POST /conduit/embeddings/collections/query
- **Description**: Query a collection using a text string or pre-computed embeddings. Read-only.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `name` (str): collection name
  - `query` (str|None): text query — mutually exclusive with `query_embeddings`
  - `query_embeddings` (list[list[float]]|None): pre-computed query vectors — mutually exclusive with `query`
  - `k` (int, default 10): number of nearest neighbors
  - `n_results` (int, default 10): number of top results
- **Expected response**:
  - 200
  - Shape: `QueryCollectionResponse` — fields `query` (str), `results` (list[QueryCollectionResult])
  - Each `QueryCollectionResult`: `id` (str), `document` (str), `metadata` (dict), `score` (float)
  - `len(results)` ≤ `n_results`
  - Scores should be floats (similarity scores, range varies by model)
- **Edge cases**:
  - Both `query` and `query_embeddings` provided → 422
  - Neither `query` nor `query_embeddings` provided → 422
  - Unknown collection → 4xx
  - Missing `name` → 422
  - `k=0` or `n_results=0` — behavior TBD; may return empty results or 422
- **Already covered**: no
