# Reranker Service — Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** [One sentence] Add a standalone `/reranker/rerank` FastAPI endpoint that scores and re-orders a list of documents against a query using the `rerankers` library, with alias-based model selection and a module-level model cache.

**Architecture:** A new `reranker_service/` directory under `services/` following the same structure as `embeddings_service/`. Model config and aliases live in two JSON files; a module-level dict caches loaded `Reranker` instances. A new `RerankerServerAPI` registers routes on the FastAPI app exactly as `EmbeddingsServerAPI` does.

**Tech Stack:** FastAPI, Pydantic v2, `rerankers` (AnswerDotAI), `asyncio.run_in_executor` for thread-offloaded inference.

---

## 1. Goal

Expose a domain-agnostic reranking endpoint so any caller can score an ordered list of documents against a query, swap reranking models by name, and receive ranked results with scores and optional metadata passthrough. This service is independent of the curator service, which retains its own reranking logic unchanged.

---

## 2. Constraints and Non-Goals

**In scope:**
- `POST /reranker/rerank` — score and sort documents
- `GET /reranker/models` — list allowlisted model names
- Alias resolution via `aliases.json`
- Model allowlist + constructor kwargs via `reranking_models.json`
- Module-level lazy model cache (no eviction)
- Optional `id` / `metadata` passthrough on documents
- `normalize_scores` flag (sigmoid, dumb passthrough — caller consults `output_type` to decide validity)
- `RerankerModelInfo` response shape for `GET /reranker/models`
- `max_length` request parameter (default 512)
- 422 validation for empty `documents` and unknown `model_name`
- Silent clamp when `k > len(documents)`
- `output_type` field per model in `reranking_models.json` (`"logits"` or `"bounded"`)

**Not in scope (v1):**
- Replacing curator's internal reranking
- Score normalization that is aware of model type
- Model cache eviction or memory management
- Hot-reload of JSON config files without restart
- Exposing arbitrary `Reranker()` constructor kwargs to callers
- Validating API key presence at startup
- Per-model truncation strategy (truncation is model-dependent, documented only)
- Training or fine-tuning rerankers
- Request timeouts on inference (do not add `asyncio.wait_for()`)
- Auth or CORS middleware
- A health/warmup endpoint (`/reranker/health` etc.)
- Metrics collection or instrumentation beyond structured logging

---

## 3. Interface Contracts

### Data shapes (headwater-api)

These classes live in `headwater-api/src/headwater_api/classes/reranker_classes/`.

```python
# requests.py
from __future__ import annotations
from pydantic import BaseModel, Field, model_validator

class RerankDocument(BaseModel):
    text: str
    id: str | int | None = None
    metadata: dict | None = None

class RerankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    documents: list[str | RerankDocument] = Field(..., min_length=1)
    model_name: str = Field(default="flash")
    k: int | None = Field(default=5)
    normalize_scores: bool = Field(default=False)
    max_length: int = Field(default=512)

    @model_validator(mode="after")
    def normalize_documents(self) -> RerankRequest:
        """Coerce bare strings to RerankDocument. Runs after field validation."""
        self.documents = [
            d if isinstance(d, RerankDocument) else RerankDocument(text=d)
            for d in self.documents
        ]
        return self

# responses.py
class RerankResult(BaseModel):
    document: RerankDocument
    index: int
    score: float

class RerankResponse(BaseModel):
    results: list[RerankResult]
    model_name: str   # resolved (post-alias) name

class RerankerModelInfo(BaseModel):
    name: str
    output_type: str  # "logits" | "bounded"
```

### Service function

```python
# reranker_service/reranker_service.py
async def reranker_service(request: RerankRequest) -> RerankResponse: ...
```

### Route

```
POST /reranker/rerank
  Body: RerankRequest
  Response: RerankResponse

GET /reranker/models
  Response: list[RerankerModelInfo]   # name + output_type from reranking_models.json
```

### Config files (`reranker_service/`)

**`aliases.json`** — short alias → resolved model name
```json
{
  "flash":  "ce-esci-MiniLM-L12-v2",
  "mini":   "ce-esci-MiniLM-L12-v2",
  "bge":    "BAAI/bge-reranker-large",
  "mxbai":  "mixedbread-ai/mxbai-rerank-large-v1",
  "ce":     "cross-encoder",
  "colbert": "colbert",
  "llm":    "llm-layerwise",
  "t5":     "t5",
  "jina":   "jina-reranker-v2-base-multilingual",
  "cohere": "cohere",
  "rankllm": "rankllm"
}
```

**`reranking_models.json`** — allowlist + Reranker constructor kwargs + output type
```json
{
  "ce-esci-MiniLM-L12-v2":              { "model_type": "flashrank",     "output_type": "bounded" },
  "cross-encoder":                       { "model_type": "cross-encoder", "output_type": "logits" },
  "BAAI/bge-reranker-large":            { "model_type": "llm-layerwise", "output_type": "logits" },
  "mixedbread-ai/mxbai-rerank-large-v1": { "model_type": "cross-encoder", "output_type": "logits" },
  "colbert":                             { "model_type": "colbert",       "output_type": "bounded" },
  "llm-layerwise":                       { "model_type": "llm-layerwise", "output_type": "logits" },
  "t5":                                  { "model_type": "t5",            "output_type": "logits" },
  "jina-reranker-v2-base-multilingual":  { "model_type": "api", "api_key_env": "JINA_API_KEY",    "output_type": "bounded" },
  "cohere":                              { "model_type": "api", "api_key_env": "COHERE_API_KEY", "lang": "en", "output_type": "bounded" },
  "rankllm":                             { "model_type": "api", "api_key_env": "OPENAI_API_KEY",  "output_type": "logits" }
}
```

### Config loading

Both JSON files are loaded **at module import time** (not per-request, not lazily).
If either file is missing or contains invalid JSON, the import raises and the server
fails to start. This is intentional — config errors must surface at startup, not
mid-request.

### Model cache

```python
# reranker_service/model_cache.py
from __future__ import annotations
import os
import threading
from rerankers import Reranker

_cache: dict[str, Reranker] = {}
_lock = threading.Lock()

# Keys in reranking_models.json that are NOT passed to Reranker()
_METADATA_KEYS = {"output_type", "api_key_env"}

def get_reranker(resolved_name: str, model_config: dict) -> Reranker:
    if resolved_name not in _cache:
        with _lock:
            if resolved_name not in _cache:  # double-checked locking
                kwargs = {k: v for k, v in model_config.items() if k not in _METADATA_KEYS}
                if "api_key_env" in model_config:
                    kwargs["api_key"] = os.getenv(model_config["api_key_env"])
                _cache[resolved_name] = Reranker(resolved_name, verbose=False, **kwargs)
    return _cache[resolved_name]
```

`output_type` and `api_key_env` are stripped before calling `Reranker()`.
`api_key_env` is resolved to an actual key via `os.getenv` at cache-population time.
`max_length` from the request is passed to `rank()` where supported; it is silently
ignored by models that do not accept it (API models, some local models). This is
expected — do not raise.

---

## 4. Acceptance Criteria

- `POST /reranker/rerank` with valid input returns `RerankResponse` with results ordered highest score first
- `results[i].index` is the zero-based position of that document in the original request `documents` list
- `results[i].document.id` and `results[i].document.metadata` are echoed back unchanged when provided
- `POST /reranker/rerank` with `documents=[]` returns 422
- `POST /reranker/rerank` with `query=""` (empty string) returns 422
- `POST /reranker/rerank` with `k=10` and `len(documents)=3` returns 3 results (clamped, no error)
- `POST /reranker/rerank` with `k=None` returns all `len(documents)` results ordered highest score first
- `POST /reranker/rerank` with `model_name="bge"` resolves to `"BAAI/bge-reranker-large"` and `response.model_name == "BAAI/bge-reranker-large"`
- `POST /reranker/rerank` with `model_name="not-a-model"` returns 422
- `POST /reranker/rerank` with `normalize_scores=True` returns scores where `0.0 < score < 1.0` for all results (sigmoid applied)
- `GET /reranker/models` returns a `RerankerModelInfo` entry for every key in `reranking_models.json`, each with correct `output_type`
- **(unit test)** `get_reranker` called N times with the same `resolved_name` calls the `Reranker` constructor exactly once — assert via mock
- Passing `documents` as `list[str]` produces results with identical `index` and `score` values as passing equivalent `list[RerankDocument(text=...)]`; `id` and `metadata` will be `None` in both cases

---

## 5. Error Handling / Failure Modes

| Condition | HTTP Status | Detail |
|-----------|-------------|--------|
| `documents` is empty | 422 | Pydantic `min_length=1` on `documents` |
| `query` is empty string | 422 | Pydantic `min_length=1` on `query` |
| `k > len(documents)` | — | Silently clamp `k` to `len(documents)`; no error, no warning in response |
| `model_name` not in aliases or allowlist | 422 | Eager resolution check before cache is touched |
| Alias resolves to name absent from allowlist | 500 | Config error — raises at resolution time, not a caller error |
| `reranking_models.json` or `aliases.json` missing/malformed | startup failure | Server does not start; logged at ERROR |
| `Reranker` instantiation fails (e.g. model not downloaded) | 500 | Bubble as internal server error; do not cache the failed instance |
| API-backed model called without env key set | 500 | `rerankers` library raises; bubble as 500 |
| `normalize_scores=True` on a `bounded` model | — | Expected; sigmoid compresses `[0,1]` to `~[0.5, 0.73]`. Not an error. Caller's responsibility. |
| `max_length` passed to a model that ignores it (API, some local) | — | Silently ignored by `rerankers` library. Not an error. |

API key absence is **not** validated at startup — failure surfaces at inference time as a 500.

---

## 6. Code Style Reference

Follow the pattern established by `embeddings_service/`:

```python
# reranker_service/reranker_service.py
from __future__ import annotations
from headwater_api.classes import RerankRequest, RerankResponse

async def reranker_service(request: RerankRequest) -> RerankResponse:
    from headwater_server.services.reranker_service.rerank import run_rerank
    return await run_rerank(request)
```

```python
# api/reranker_server_api.py
from fastapi import FastAPI
from headwater_api.classes import RerankRequest, RerankResponse

class RerankerServerAPI:
    def __init__(self, app: FastAPI):
        self.app = app

    def register_routes(self):
        @self.app.post("/reranker/rerank", response_model=RerankResponse)
        async def rerank(request: RerankRequest):
            from headwater_server.services.reranker_service.reranker_service import (
                reranker_service,
            )
            return await reranker_service(request)

        @self.app.get("/reranker/models", response_model=list[RerankerModelInfo])
        async def list_reranker_models():
            from headwater_server.services.reranker_service.list_reranker_models_service import (
                list_reranker_models_service,
            )
            return await list_reranker_models_service()
```

---

## 7. Domain Language

| Term | Definition |
|------|-----------|
| **alias** | A short human-readable name (e.g. `"bge"`) that maps to a resolved model name |
| **resolved model name** | The canonical model identifier used as the key in `reranking_models.json` and in the model cache (e.g. `"BAAI/bge-reranker-large"`) |
| **allowlist** | The set of resolved model names present in `reranking_models.json` |
| **model cache** | The module-level `dict[str, Reranker]` holding loaded `Reranker` instances keyed by resolved model name |
| **constructor kwargs** | The dict of keyword arguments from `reranking_models.json` passed to `Reranker()` (e.g. `model_type`, `api_key`) |
| **document** | A unit of text to be scored, optionally carrying `id` and `metadata` for passthrough |
| **index** | The zero-based integer position of a document in the original request `documents` list, before any reordering |
| **score** | A float on a model-dependent scale representing relevance of a document to the query |
| **normalize** | Apply sigmoid to convert a raw logit score to `[0, 1]`; validity is caller's responsibility |

---

## 8. Observability

Use `logging.getLogger(__name__)` in each module, consistent with the rest of the
codebase (see `generate_embeddings_service.py`). Do not use `print()`.

**Per-request (INFO):**
- Resolved model name
- Number of documents received
- Effective `k` after clamping
- Cache hit or miss (`"cache hit: {resolved_name}"` / `"loading model: {resolved_name}"`)
- Request duration in ms

**On clamp (WARNING):**
- `"k={requested_k} exceeds document count={n}; clamping to {n}"`

**On model load (INFO):**
- `"model loaded and cached: {resolved_name}"`

**On error (ERROR):**
- `Reranker` instantiation failure with resolved name and exception message
- Config file load failure with file path and exception message

Do not log raw document text or scores — these may be large or sensitive.

---

## 9. Invalid State Transitions

- **Loading a model not in `reranking_models.json`** must raise before touching the model cache
- **Caching a model under its alias** (rather than its resolved name) must not happen — cache keys are always resolved names
- **Calling `rank()` with an empty document list** must not reach the `Reranker` — validation fires first
- **Returning more than `min(k, len(documents))` results** must not happen when `k` is set
- **Returning fewer than `len(documents)` results when `k=None`** must not happen — all documents are returned
- **Mutating `id` or `metadata` on a passed-through document** must not happen — echo exactly as received
- **Resolving an alias to a name absent from `reranking_models.json`** — this is a config error and must raise at resolution time, not silently fall through
