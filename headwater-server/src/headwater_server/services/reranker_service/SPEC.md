# Reranker Service — Spec

## Status: FINAL (interview complete)

## Context

The curator service currently embeds a reranking step tightly coupled to the
course-search domain. This service extracts reranking into a standalone,
domain-agnostic FastAPI service backed by the `rerankers` library (AnswerDotAI).
It is independent of the curator service — curator will not be refactored to call
this endpoint.

---

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/reranker/rerank` | Score and sort documents against a query |
| GET | `/reranker/models` | List available model names (resolved, not aliases) |

---

## Request / Response shapes

```python
class RerankDocument(BaseModel):
    text: str
    id: str | int | None = None       # passed through, not used by reranker
    metadata: dict | None = None      # passed through, not used by reranker

class RerankRequest(BaseModel):
    query: str
    documents: list[str | RerankDocument]  # str normalized to RerankDocument internally
    model_name: str = Field(default="flash")
    k: int | None = Field(default=5)       # None = return all, sorted (explicit opt-in)
    normalize_scores: bool = Field(default=False)  # applies sigmoid; caller's responsibility
    max_length: int = Field(default=512)

class RerankResult(BaseModel):
    document: RerankDocument    # echoed back (id + metadata preserved)
    index: int                  # original position in input list
    score: float                # model-specific scale unless normalize_scores=True

class RerankResponse(BaseModel):
    results: list[RerankResult]
    model_name: str             # resolved model name (post-alias)
```

---

## Validation rules

- `documents` must have `min_length=1` — empty list → 422
- `k > len(documents)` → silently clamp `k` to `len(documents)`; no error
- `model_name` resolved via `aliases.json` then validated against `reranking_models.json` → 422 if not found

---

## Config files (both in `reranker_service/`)

### `aliases.json`
Maps short alias → full model name used in `reranking_models.json`.

```json
{
  "flash": "ce-esci-MiniLM-L12-v2",
  "bge": "BAAI/bge-reranker-large",
  "mxbai": "mixedbread-ai/mxbai-rerank-large-v1"
}
```

### `reranking_models.json`
Allowlist + constructor kwargs + output type. Single source of truth replacing the
hardcoded `rankers` dict in `curator_service/rerank.py`.

```json
{
  "BAAI/bge-reranker-large": {
    "model_type": "llm-layerwise",
    "output_type": "logits"
  },
  "ce-esci-MiniLM-L12-v2": {
    "model_type": "flashrank",
    "output_type": "bounded"
  },
  "cohere": {
    "model_type": "api",
    "api_key_env": "COHERE_API_KEY",
    "lang": "en",
    "output_type": "bounded"
  }
}
```

---

## Model cache

- Module-level lazy singleton: `dict[str, Reranker]`
- Key is the resolved (post-alias) model name
- Populated on first request per model
- No eviction — restart to free memory
- FastAPI lifecycle NOT used — cache lives entirely in service layer

---

## Async strategy

- `rank_async` from `rerankers` is NOT used (it is a thread facade, not true async)
- All inference runs via `asyncio.run_in_executor(None, ranker.rank, query, docs)`

---

## Score normalization

- `normalize_scores=True` applies `sigmoid()` to all scores
- No per-model awareness — caller is responsible for knowing when this is valid
- Cross-encoder logits: sigmoid is appropriate
- FlashRank / API models: already bounded; sigmoid may distort
- `reranking_models.json` carries an `output_type` field per model (`"logits"` or `"bounded"`)
- `GET /reranker/models` returns `list[RerankerModelInfo]` (not `list[str]`) so callers
  can inspect `output_type` before deciding whether to use `normalize_scores`

```python
class RerankerModelInfo(BaseModel):
    name: str
    output_type: str  # "logits" | "bounded"
```

---

## Truncation

- `max_length` on the request defaults to 512
- The existing 512-token monkey-patch in `curator_service/rerank.py` is NOT
  carried over; truncation is handled via `rerankers` library params where supported
- Truncation behavior is model-dependent and documented, not enforced uniformly

---

## What this service does NOT do

- Does not replace curator's internal reranking (curator is unchanged)
- Does not normalize scores across models automatically
- Does not support model eviction or hot-swap from the cache
- Does not accept arbitrary `Reranker()` kwargs from callers — only `max_length`
  is exposed; all other constructor params come from `reranking_models.json`
- Does not validate that API keys are present at startup (fails at inference time)
