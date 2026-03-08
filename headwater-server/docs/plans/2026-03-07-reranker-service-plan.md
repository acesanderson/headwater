# Reranker Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a standalone `/reranker/rerank` and `/reranker/models` FastAPI endpoint backed by the `rerankers` library, with alias-based model selection, a thread-safe lazy model cache, and optional score normalization.

**Architecture:** Changes span two packages: `headwater-api` (Pydantic models) and `headwater-server` (service logic, config, cache, routes). The service follows the same structure as `embeddings_service/` — a thin service function, a dedicated rerank module, JSON config files, and a `*ServerAPI` class registered in `headwater.py`. The `Reranker` is cached module-level behind a `threading.Lock`; inference is offloaded to a thread via `asyncio.run_in_executor`.

**Tech Stack:** FastAPI, Pydantic v2, `rerankers` (AnswerDotAI), `asyncio.run_in_executor`, `threading.Lock`, `pytest`, `pytest-asyncio`, `unittest.mock`.

**Design doc:** `docs/plans/2026-03-07-reranker-service-design.md` — read it before starting. All acceptance criteria (AC) are numbered there; every TDD step below references its AC.

---

## Acceptance Criteria Reference

| AC | Description |
|----|-------------|
| AC1 | Valid input → results ordered highest score first |
| AC2 | `results[i].index` is zero-based position in original `documents` list |
| AC3 | `id` and `metadata` on `RerankDocument` echoed back unchanged |
| AC4 | `documents=[]` → 422 |
| AC5 | `query=""` → 422 |
| AC6 | `k=10`, `len(documents)=3` → 3 results, no error |
| AC7 | `k=None` → all `len(documents)` results, highest score first |
| AC8 | `model_name="bge"` → resolves, `response.model_name == "BAAI/bge-reranker-large"` |
| AC9 | `model_name="not-a-model"` → 422 |
| AC10 | `normalize_scores=True` → all scores in `(0.0, 1.0)` |
| AC11 | `GET /reranker/models` returns `RerankerModelInfo` for every key in `reranking_models.json` |
| AC12 | `get_reranker` called N times for same model → `Reranker` constructor called exactly once |
| AC13 | `list[str]` input produces same `index`/`score` as `list[RerankDocument(text=...)]` |

---

## Task 1: Add `rerankers` dependency

**Files:**
- Modify: `headwater-server/pyproject.toml`

**Step 1: Add dependency**

In `headwater-server/pyproject.toml`, add to `dependencies`:

```toml
"rerankers[flashrank]>=0.10.0",
```

**Step 2: Sync**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv sync
```

Expected: resolves without conflict.

**Step 3: Verify import**

```bash
uv run python -c "from rerankers import Reranker; print('ok')"
```

Expected: `ok`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add rerankers[flashrank] dependency"
```

---

## Task 2: Pydantic models in headwater-api

**Files:**
- Create: `headwater-api/src/headwater_api/classes/reranker_classes/__init__.py`
- Create: `headwater-api/src/headwater_api/classes/reranker_classes/requests.py`
- Create: `headwater-api/src/headwater_api/classes/reranker_classes/responses.py`
- Modify: `headwater-api/src/headwater_api/classes/__init__.py`
- Create: `headwater-api/tests/classes/test_reranker_classes.py`

### Step 1: Write failing tests for AC4, AC5, AC13

Create `headwater-api/tests/classes/test_reranker_classes.py`:

```python
from __future__ import annotations
import pytest
from pydantic import ValidationError


def test_empty_documents_raises():
    """AC4: documents=[] → 422 (Pydantic ValidationError)"""
    from headwater_api.classes import RerankRequest
    with pytest.raises(ValidationError):
        RerankRequest(query="hello", documents=[])


def test_empty_query_raises():
    """AC5: query="" → 422 (Pydantic ValidationError)"""
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
```

**Step 2: Run tests — verify they fail**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-api
uv run pytest tests/classes/test_reranker_classes.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — classes don't exist yet.

**Step 3: Create `reranker_classes/__init__.py`**

```python
```

(Empty file.)

**Step 4: Create `requests.py`**

Create `headwater-api/src/headwater_api/classes/reranker_classes/requests.py`:

```python
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
        self.documents = [
            d if isinstance(d, RerankDocument) else RerankDocument(text=d)
            for d in self.documents
        ]
        return self
```

**Step 5: Create `responses.py`**

Create `headwater-api/src/headwater_api/classes/reranker_classes/responses.py`:

```python
from __future__ import annotations
from pydantic import BaseModel, Field
from headwater_api.classes.reranker_classes.requests import RerankDocument


class RerankResult(BaseModel):
    document: RerankDocument
    index: int
    score: float


class RerankResponse(BaseModel):
    results: list[RerankResult]
    model_name: str


class RerankerModelInfo(BaseModel):
    name: str
    output_type: str
```

**Step 6: Export from `reranker_classes/__init__.py`**

```python
from headwater_api.classes.reranker_classes.requests import RerankDocument, RerankRequest
from headwater_api.classes.reranker_classes.responses import (
    RerankResult,
    RerankResponse,
    RerankerModelInfo,
)

__all__ = [
    "RerankDocument",
    "RerankRequest",
    "RerankResult",
    "RerankResponse",
    "RerankerModelInfo",
]
```

**Step 7: Add exports to `classes/__init__.py`**

Add these imports to `headwater-api/src/headwater_api/classes/__init__.py` after the existing siphon imports:

```python
from headwater_api.classes.reranker_classes.requests import RerankDocument, RerankRequest
from headwater_api.classes.reranker_classes.responses import (
    RerankResult,
    RerankResponse,
    RerankerModelInfo,
)
```

And add to `__all__`:

```python
"RerankDocument",
"RerankRequest",
"RerankResult",
"RerankResponse",
"RerankerModelInfo",
```

**Step 8: Run tests — verify they pass**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-api
uv run pytest tests/classes/test_reranker_classes.py -v
```

Expected: 3 PASSED.

**Step 9: Commit**

```bash
git add \
  headwater-api/src/headwater_api/classes/reranker_classes/ \
  headwater-api/src/headwater_api/classes/__init__.py \
  headwater-api/tests/classes/test_reranker_classes.py
git commit -m "feat: add RerankRequest, RerankResponse, RerankerModelInfo Pydantic models (AC4, AC5, AC13)"
```

---

## Task 3: Config files and loader

**Files:**
- Create: `headwater-server/src/headwater_server/services/reranker_service/aliases.json`
- Create: `headwater-server/src/headwater_server/services/reranker_service/reranking_models.json`
- Create: `headwater-server/src/headwater_server/services/reranker_service/__init__.py`
- Create: `headwater-server/src/headwater_server/services/reranker_service/config.py`
- Create: `headwater-server/tests/services/reranker_service/test_config.py`

**Step 1: Create `__init__.py`**

```python
```

(Empty file.)

**Step 2: Create `aliases.json`**

```json
{
  "flash":   "ce-esci-MiniLM-L12-v2",
  "mini":    "ce-esci-MiniLM-L12-v2",
  "bge":     "BAAI/bge-reranker-large",
  "mxbai":   "mixedbread-ai/mxbai-rerank-large-v1",
  "ce":      "cross-encoder",
  "colbert": "colbert",
  "llm":     "llm-layerwise",
  "t5":      "t5",
  "jina":    "jina-reranker-v2-base-multilingual",
  "cohere":  "cohere",
  "rankllm": "rankllm"
}
```

**Step 3: Create `reranking_models.json`**

```json
{
  "ce-esci-MiniLM-L12-v2":               { "model_type": "flashrank",     "output_type": "bounded" },
  "cross-encoder":                        { "model_type": "cross-encoder", "output_type": "logits"  },
  "BAAI/bge-reranker-large":             { "model_type": "llm-layerwise", "output_type": "logits"  },
  "mixedbread-ai/mxbai-rerank-large-v1": { "model_type": "cross-encoder", "output_type": "logits"  },
  "colbert":                              { "model_type": "colbert",       "output_type": "bounded" },
  "llm-layerwise":                        { "model_type": "llm-layerwise", "output_type": "logits"  },
  "t5":                                   { "model_type": "t5",            "output_type": "logits"  },
  "jina-reranker-v2-base-multilingual":   { "model_type": "api", "api_key_env": "JINA_API_KEY",    "output_type": "bounded" },
  "cohere":                               { "model_type": "api", "api_key_env": "COHERE_API_KEY", "lang": "en", "output_type": "bounded" },
  "rankllm":                              { "model_type": "api", "api_key_env": "OPENAI_API_KEY",  "output_type": "logits"  }
}
```

**Step 4: Write failing config tests**

Create `headwater-server/tests/services/reranker_service/test_config.py`:

```python
from __future__ import annotations
import pytest


def test_alias_resolves_known_key():
    """Alias 'bge' resolves to its full model name."""
    from headwater_server.services.reranker_service.config import resolve_model_name
    assert resolve_model_name("bge") == "BAAI/bge-reranker-large"


def test_full_model_name_passes_through():
    """A name already in reranking_models.json is returned unchanged."""
    from headwater_server.services.reranker_service.config import resolve_model_name
    assert resolve_model_name("ce-esci-MiniLM-L12-v2") == "ce-esci-MiniLM-L12-v2"


def test_unknown_model_raises_value_error():
    """A name not in aliases or allowlist raises ValueError."""
    from headwater_server.services.reranker_service.config import resolve_model_name
    with pytest.raises(ValueError, match="not-a-model"):
        resolve_model_name("not-a-model")


def test_alias_pointing_to_unknown_model_raises():
    """Config error: alias resolves to a name not in reranking_models.json → ValueError."""
    from headwater_server.services.reranker_service import config as cfg
    original = cfg._ALIASES.copy()
    cfg._ALIASES["broken"] = "nonexistent-model"
    try:
        with pytest.raises(ValueError, match="nonexistent-model"):
            cfg.resolve_model_name("broken")
    finally:
        cfg._ALIASES.clear()
        cfg._ALIASES.update(original)


def test_get_model_config_returns_dict():
    """get_model_config returns the full entry from reranking_models.json."""
    from headwater_server.services.reranker_service.config import get_model_config
    config = get_model_config("ce-esci-MiniLM-L12-v2")
    assert config["model_type"] == "flashrank"
    assert config["output_type"] == "bounded"
```

**Step 5: Run tests — verify they fail**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/reranker_service/test_config.py -v
```

Expected: `ModuleNotFoundError` for `config`.

**Step 6: Create `config.py`**

Create `headwater-server/src/headwater_server/services/reranker_service/config.py`:

```python
from __future__ import annotations
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DIR = Path(__file__).parent

try:
    with open(_DIR / "aliases.json") as f:
        _ALIASES: dict[str, str] = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    logger.error("Failed to load aliases.json: %s", e)
    raise

try:
    with open(_DIR / "reranking_models.json") as f:
        _MODELS: dict[str, dict] = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    logger.error("Failed to load reranking_models.json: %s", e)
    raise


def resolve_model_name(model_name: str) -> str:
    resolved = _ALIASES.get(model_name, model_name)
    if resolved not in _MODELS:
        raise ValueError(f"Model '{resolved}' is not in the allowlist (requested: '{model_name}')")
    return resolved


def get_model_config(resolved_name: str) -> dict:
    return _MODELS[resolved_name]


def list_models() -> list[dict]:
    return [
        {"name": name, "output_type": cfg["output_type"]}
        for name, cfg in _MODELS.items()
    ]
```

**Step 7: Create test `__init__.py` files**

```bash
mkdir -p /Users/bianders/Brian_Code/headwater/headwater-server/tests/services/reranker_service
touch /Users/bianders/Brian_Code/headwater/headwater-server/tests/__init__.py
touch /Users/bianders/Brian_Code/headwater/headwater-server/tests/services/__init__.py
touch /Users/bianders/Brian_Code/headwater/headwater-server/tests/services/reranker_service/__init__.py
```

**Step 8: Run tests — verify they pass**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/reranker_service/test_config.py -v
```

Expected: 5 PASSED.

**Step 9: Commit**

```bash
git add \
  src/headwater_server/services/reranker_service/__init__.py \
  src/headwater_server/services/reranker_service/aliases.json \
  src/headwater_server/services/reranker_service/reranking_models.json \
  src/headwater_server/services/reranker_service/config.py \
  tests/services/reranker_service/test_config.py \
  tests/__init__.py tests/services/__init__.py \
  tests/services/reranker_service/__init__.py
git commit -m "feat: add reranker config loader with alias resolution"
```

---

## Task 4: Model cache (AC12)

**Files:**
- Create: `headwater-server/src/headwater_server/services/reranker_service/model_cache.py`
- Modify: `headwater-server/tests/services/reranker_service/test_config.py` → new file below

**Step 1: Write failing test for AC12**

Create `headwater-server/tests/services/reranker_service/test_model_cache.py`:

```python
from __future__ import annotations
from unittest.mock import patch, MagicMock


def test_reranker_constructor_called_once():
    """AC12: get_reranker called N times for same model → Reranker() instantiated exactly once."""
    mock_instance = MagicMock()
    with patch(
        "headwater_server.services.reranker_service.model_cache.Reranker",
        return_value=mock_instance,
    ) as mock_cls:
        from headwater_server.services.reranker_service.model_cache import get_reranker, _cache
        _cache.clear()

        config = {"model_type": "flashrank", "output_type": "bounded"}
        result1 = get_reranker("ce-esci-MiniLM-L12-v2", config)
        result2 = get_reranker("ce-esci-MiniLM-L12-v2", config)
        result3 = get_reranker("ce-esci-MiniLM-L12-v2", config)

        assert mock_cls.call_count == 1
        assert result1 is result2 is result3


def test_metadata_keys_stripped_from_constructor():
    """output_type and api_key_env must not be passed to Reranker()."""
    mock_instance = MagicMock()
    with patch(
        "headwater_server.services.reranker_service.model_cache.Reranker",
        return_value=mock_instance,
    ) as mock_cls:
        from headwater_server.services.reranker_service.model_cache import get_reranker, _cache
        _cache.clear()

        config = {"model_type": "flashrank", "output_type": "bounded"}
        get_reranker("ce-esci-MiniLM-L12-v2", config)

        _, kwargs = mock_cls.call_args
        assert "output_type" not in kwargs
        assert "api_key_env" not in kwargs
        assert kwargs.get("model_type") == "flashrank"


def test_api_key_env_resolved_to_api_key(monkeypatch):
    """api_key_env is resolved via os.getenv and passed as api_key."""
    monkeypatch.setenv("COHERE_API_KEY", "test-key-123")
    mock_instance = MagicMock()
    with patch(
        "headwater_server.services.reranker_service.model_cache.Reranker",
        return_value=mock_instance,
    ) as mock_cls:
        from headwater_server.services.reranker_service.model_cache import get_reranker, _cache
        _cache.clear()

        config = {
            "model_type": "api",
            "api_key_env": "COHERE_API_KEY",
            "lang": "en",
            "output_type": "bounded",
        }
        get_reranker("cohere", config)

        _, kwargs = mock_cls.call_args
        assert kwargs["api_key"] == "test-key-123"
        assert "api_key_env" not in kwargs
```

**Step 2: Run tests — verify they fail**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/reranker_service/test_model_cache.py -v
```

Expected: `ModuleNotFoundError` for `model_cache`.

**Step 3: Create `model_cache.py`**

Create `headwater-server/src/headwater_server/services/reranker_service/model_cache.py`:

```python
from __future__ import annotations
import logging
import os
import threading
from rerankers import Reranker

logger = logging.getLogger(__name__)

_cache: dict[str, Reranker] = {}
_lock = threading.Lock()

_METADATA_KEYS = {"output_type", "api_key_env"}


def get_reranker(resolved_name: str, model_config: dict) -> Reranker:
    if resolved_name not in _cache:
        with _lock:
            if resolved_name not in _cache:
                kwargs = {k: v for k, v in model_config.items() if k not in _METADATA_KEYS}
                if "api_key_env" in model_config:
                    kwargs["api_key"] = os.getenv(model_config["api_key_env"])
                logger.info("loading model: %s", resolved_name)
                _cache[resolved_name] = Reranker(resolved_name, verbose=False, **kwargs)
                logger.info("model loaded and cached: %s", resolved_name)
    else:
        logger.info("cache hit: %s", resolved_name)
    return _cache[resolved_name]
```

**Step 4: Run tests — verify they pass**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/reranker_service/test_model_cache.py -v
```

Expected: 3 PASSED.

**Step 5: Commit**

```bash
git add \
  src/headwater_server/services/reranker_service/model_cache.py \
  tests/services/reranker_service/test_model_cache.py
git commit -m "feat: add thread-safe lazy model cache (AC12)"
```

---

## Task 5: Core rerank — ordering (AC1)

**Files:**
- Create: `headwater-server/src/headwater_server/services/reranker_service/rerank.py`
- Create: `headwater-server/tests/services/reranker_service/test_rerank.py`

This task creates the `run_rerank` function and the shared test mock helper. Subsequent tasks (6–12) each add one test + minimal implementation change to the same two files.

**Step 1: Write mock helper and AC1 failing test**

Create `headwater-server/tests/services/reranker_service/test_rerank.py`:

```python
from __future__ import annotations
import math
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

def _make_mock_ranker(texts: list[str], scores: list[float]) -> MagicMock:
    """
    Build a mock Reranker whose .rank() returns results in the given order,
    with doc_ids assigned as 0, 1, 2, ... matching the input texts list order.
    """
    results = []
    for i, (text, score) in enumerate(zip(texts, scores)):
        r = MagicMock()
        r.text = text
        r.score = score
        r.rank = i + 1
        r.document = MagicMock()
        r.document.doc_id = i
        results.append(r)

    # Sort by descending score to simulate what the library returns
    sorted_results = sorted(results, key=lambda x: x.score, reverse=True)

    ranked = MagicMock()
    ranked.results = sorted_results
    ranked.top_k = lambda k: sorted_results[:k]

    mock_ranker = MagicMock()
    mock_ranker.rank.return_value = ranked
    return mock_ranker


def _patch_reranker(mock_ranker):
    """Context manager: patches get_reranker to return mock_ranker."""
    return patch(
        "headwater_server.services.reranker_service.rerank.get_reranker",
        return_value=mock_ranker,
    )


# ---------------------------------------------------------------------------
# AC1: results ordered highest score first
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_results_ordered_highest_score_first():
    """AC1: results are ordered from highest to lowest score."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    docs = ["low relevance", "high relevance", "medium relevance"]
    scores = [0.1, 0.9, 0.5]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(query="test query", documents=docs, model_name="flash", k=3)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    result_scores = [r.score for r in response.results]
    assert result_scores == sorted(result_scores, reverse=True)
```

**Step 2: Run test — verify it fails**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/reranker_service/test_rerank.py::test_results_ordered_highest_score_first -v
```

Expected: `ModuleNotFoundError` — `rerank.py` doesn't exist yet.

**Step 3: Create `rerank.py`**

Create `headwater-server/src/headwater_server/services/reranker_service/rerank.py`:

```python
from __future__ import annotations
import asyncio
import logging
import math
from headwater_api.classes import RerankDocument, RerankRequest, RerankResponse, RerankResult
from headwater_server.services.reranker_service.config import (
    resolve_model_name,
    get_model_config,
)
from headwater_server.services.reranker_service.model_cache import get_reranker

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


async def run_rerank(request: RerankRequest) -> RerankResponse:
    import time
    start = time.monotonic()

    # Resolve and validate model name — raises ValueError on unknown model
    resolved_name = resolve_model_name(request.model_name)
    model_config = get_model_config(resolved_name)

    # documents are already normalized to list[RerankDocument] by Pydantic
    documents: list[RerankDocument] = request.documents  # type: ignore[assignment]
    n = len(documents)

    # Clamp k
    if request.k is None:
        effective_k = n
    else:
        effective_k = min(request.k, n)
        if effective_k < request.k:
            logger.warning(
                "k=%d exceeds document count=%d; clamping to %d",
                request.k, n, effective_k,
            )

    logger.info(
        "rerank: model=%s docs=%d effective_k=%d",
        resolved_name, n, effective_k,
    )

    ranker = get_reranker(resolved_name, model_config)
    docs_text = [d.text for d in documents]

    loop = asyncio.get_event_loop()
    ranked = await loop.run_in_executor(
        None, lambda: ranker.rank(query=request.query, docs=docs_text)
    )

    top_results = ranked.top_k(effective_k)

    results = []
    for result in top_results:
        original_index: int = result.document.doc_id
        score = _sigmoid(result.score) if request.normalize_scores else result.score
        results.append(
            RerankResult(
                document=documents[original_index],
                index=original_index,
                score=score,
            )
        )

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info("rerank complete: model=%s duration_ms=%.1f", resolved_name, elapsed_ms)

    return RerankResponse(results=results, model_name=resolved_name)
```

**Step 4: Run test — verify it passes**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/reranker_service/test_rerank.py::test_results_ordered_highest_score_first -v
```

Expected: PASSED.

**Step 5: Commit**

```bash
git add \
  src/headwater_server/services/reranker_service/rerank.py \
  tests/services/reranker_service/test_rerank.py
git commit -m "feat: add run_rerank with ordering (AC1)"
```

---

## Task 6: Core rerank — index is zero-based (AC2)

**Files:**
- Modify: `headwater-server/tests/services/reranker_service/test_rerank.py`

**Step 1: Add failing test for AC2**

Append to `test_rerank.py`:

```python
@pytest.mark.asyncio
async def test_result_index_is_original_position():
    """AC2: results[i].index is zero-based position in the original documents list."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    docs = ["doc A", "doc B", "doc C"]
    # Give doc B (index=1) the highest score so it sorts first
    scores = [0.1, 0.9, 0.5]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(query="test", documents=docs, model_name="flash", k=3)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    # The top result should have index=1 (doc B), not index=0
    assert response.results[0].index == 1
    assert response.results[0].document.text == "doc B"
```

**Step 2: Run test — verify it fails**

```bash
uv run pytest tests/services/reranker_service/test_rerank.py::test_result_index_is_original_position -v
```

Expected: FAIL — `run_rerank` doesn't exist yet in test context / index behavior not verified.

**Step 3: Verify existing implementation already handles this**

The `doc_id` from the mock is set to the original list index. `run_rerank` uses `result.document.doc_id` as the index. Re-run:

```bash
uv run pytest tests/services/reranker_service/test_rerank.py::test_result_index_is_original_position -v
```

Expected: PASSED. If not, ensure `_make_mock_ranker` assigns `doc_id = i` (index in input list, not sorted position).

**Step 4: Commit**

```bash
git add tests/services/reranker_service/test_rerank.py
git commit -m "test: verify result index is zero-based original position (AC2)"
```

---

## Task 7: Core rerank — metadata passthrough (AC3)

**Files:**
- Modify: `headwater-server/tests/services/reranker_service/test_rerank.py`

**Step 1: Add failing test for AC3**

Append to `test_rerank.py`:

```python
@pytest.mark.asyncio
async def test_id_and_metadata_echoed_unchanged():
    """AC3: id and metadata on RerankDocument are echoed back in the response unchanged."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest, RerankDocument

    docs = [
        RerankDocument(text="doc A", id="abc-123", metadata={"source": "db"}),
        RerankDocument(text="doc B", id=42, metadata={"source": "api"}),
    ]
    scores = [0.3, 0.9]
    mock_ranker = _make_mock_ranker([d.text for d in docs], scores)

    request = RerankRequest(query="test", documents=docs, model_name="flash", k=2)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    top = response.results[0]
    assert top.document.id == 42
    assert top.document.metadata == {"source": "api"}

    second = response.results[1]
    assert second.document.id == "abc-123"
    assert second.document.metadata == {"source": "db"}
```

**Step 2: Run test — verify it fails**

```bash
uv run pytest tests/services/reranker_service/test_rerank.py::test_id_and_metadata_echoed_unchanged -v
```

**Step 3: Verify existing implementation handles this**

`run_rerank` passes `documents[original_index]` directly into `RerankResult`, which preserves the full `RerankDocument` including `id` and `metadata`. Re-run:

```bash
uv run pytest tests/services/reranker_service/test_rerank.py::test_id_and_metadata_echoed_unchanged -v
```

Expected: PASSED.

**Step 4: Commit**

```bash
git add tests/services/reranker_service/test_rerank.py
git commit -m "test: verify id and metadata passthrough (AC3)"
```

---

## Task 8: Core rerank — k clamp (AC6)

**Files:**
- Modify: `headwater-server/tests/services/reranker_service/test_rerank.py`

**Step 1: Add failing test for AC6**

Append to `test_rerank.py`:

```python
@pytest.mark.asyncio
async def test_k_greater_than_docs_clamped_silently():
    """AC6: k=10 with 3 documents returns 3 results, no error."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    docs = ["doc A", "doc B", "doc C"]
    scores = [0.1, 0.9, 0.5]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(query="test", documents=docs, model_name="flash", k=10)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    assert len(response.results) == 3
```

**Step 2: Run and verify passes (clamp already implemented)**

```bash
uv run pytest tests/services/reranker_service/test_rerank.py::test_k_greater_than_docs_clamped_silently -v
```

Expected: PASSED. The clamp `min(request.k, n)` in `run_rerank` handles this.

**Step 3: Commit**

```bash
git add tests/services/reranker_service/test_rerank.py
git commit -m "test: verify k>len(documents) clamped silently (AC6)"
```

---

## Task 9: Core rerank — k=None returns all (AC7)

**Files:**
- Modify: `headwater-server/tests/services/reranker_service/test_rerank.py`

**Step 1: Add failing test for AC7**

Append to `test_rerank.py`:

```python
@pytest.mark.asyncio
async def test_k_none_returns_all_documents():
    """AC7: k=None returns all len(documents) results, ordered highest score first."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    docs = ["doc A", "doc B", "doc C", "doc D"]
    scores = [0.1, 0.9, 0.5, 0.3]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(query="test", documents=docs, model_name="flash", k=None)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    assert len(response.results) == 4
    result_scores = [r.score for r in response.results]
    assert result_scores == sorted(result_scores, reverse=True)
```

**Step 2: Run and verify passes**

```bash
uv run pytest tests/services/reranker_service/test_rerank.py::test_k_none_returns_all_documents -v
```

Expected: PASSED.

**Step 3: Commit**

```bash
git add tests/services/reranker_service/test_rerank.py
git commit -m "test: verify k=None returns all documents sorted (AC7)"
```

---

## Task 10: Core rerank — alias resolution in response (AC8)

**Files:**
- Modify: `headwater-server/tests/services/reranker_service/test_rerank.py`

**Step 1: Add failing test for AC8**

Append to `test_rerank.py`:

```python
@pytest.mark.asyncio
async def test_alias_resolved_and_echoed_in_response():
    """AC8: model_name='bge' resolves to 'BAAI/bge-reranker-large'; response.model_name equals resolved name."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    docs = ["doc A", "doc B"]
    scores = [0.1, 0.9]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(query="test", documents=docs, model_name="bge", k=2)

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    assert response.model_name == "BAAI/bge-reranker-large"
```

**Step 2: Run and verify passes**

```bash
uv run pytest tests/services/reranker_service/test_rerank.py::test_alias_resolved_and_echoed_in_response -v
```

Expected: PASSED. `resolve_model_name("bge")` returns `"BAAI/bge-reranker-large"` and that is set on the response.

**Step 3: Commit**

```bash
git add tests/services/reranker_service/test_rerank.py
git commit -m "test: verify alias resolves and echoes in response.model_name (AC8)"
```

---

## Task 11: Core rerank — unknown model raises HTTP 422 (AC9)

**Files:**
- Modify: `headwater-server/src/headwater_server/services/reranker_service/rerank.py`
- Modify: `headwater-server/tests/services/reranker_service/test_rerank.py`

**Step 1: Add failing test for AC9**

Append to `test_rerank.py`:

```python
@pytest.mark.asyncio
async def test_unknown_model_raises_http_422():
    """AC9: model_name not in aliases or allowlist → HTTPException with status_code=422."""
    from fastapi import HTTPException
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    request = RerankRequest(query="test", documents=["doc"], model_name="not-a-model")

    with pytest.raises(HTTPException) as exc_info:
        await run_rerank(request)

    assert exc_info.value.status_code == 422
```

**Step 2: Run test — verify it fails**

```bash
uv run pytest tests/services/reranker_service/test_rerank.py::test_unknown_model_raises_http_422 -v
```

Expected: FAIL — currently `run_rerank` raises `ValueError`, not `HTTPException`.

**Step 3: Update `run_rerank` to convert `ValueError` to `HTTPException`**

In `rerank.py`, replace the `resolve_model_name` call block:

```python
from fastapi import HTTPException

# inside run_rerank, replace:
resolved_name = resolve_model_name(request.model_name)

# with:
try:
    resolved_name = resolve_model_name(request.model_name)
except ValueError as e:
    raise HTTPException(status_code=422, detail=str(e)) from e
```

**Step 4: Run test — verify it passes**

```bash
uv run pytest tests/services/reranker_service/test_rerank.py::test_unknown_model_raises_http_422 -v
```

Expected: PASSED.

**Step 5: Commit**

```bash
git add \
  src/headwater_server/services/reranker_service/rerank.py \
  tests/services/reranker_service/test_rerank.py
git commit -m "feat: convert unknown model ValueError to HTTP 422 (AC9)"
```

---

## Task 12: Core rerank — normalize_scores (AC10)

**Files:**
- Modify: `headwater-server/tests/services/reranker_service/test_rerank.py`

**Step 1: Add failing test for AC10**

Append to `test_rerank.py`:

```python
@pytest.mark.asyncio
async def test_normalize_scores_applies_sigmoid():
    """AC10: normalize_scores=True → all scores strictly in (0.0, 1.0)."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest

    # Use raw logit-style scores (unbounded) to confirm sigmoid is applied
    docs = ["doc A", "doc B", "doc C"]
    scores = [-5.0, 2.3, 0.0]
    mock_ranker = _make_mock_ranker(docs, scores)

    request = RerankRequest(
        query="test", documents=docs, model_name="flash", k=3, normalize_scores=True
    )

    with _patch_reranker(mock_ranker):
        response = await run_rerank(request)

    for result in response.results:
        assert 0.0 < result.score < 1.0
```

**Step 2: Run and verify passes**

```bash
uv run pytest tests/services/reranker_service/test_rerank.py::test_normalize_scores_applies_sigmoid -v
```

Expected: PASSED. `_sigmoid` is already applied in `run_rerank` when `normalize_scores=True`.

**Step 3: Run all rerank tests together**

```bash
uv run pytest tests/services/reranker_service/test_rerank.py -v
```

Expected: all PASSED.

**Step 4: Commit**

```bash
git add tests/services/reranker_service/test_rerank.py
git commit -m "test: verify normalize_scores applies sigmoid (AC10)"
```

---

## Task 13: str input equivalence (AC13 — service level)

**Files:**
- Modify: `headwater-server/tests/services/reranker_service/test_rerank.py`

**Step 1: Add failing test for AC13 (service level)**

Append to `test_rerank.py`:

```python
@pytest.mark.asyncio
async def test_str_and_rerank_document_produce_same_index_and_score():
    """AC13: list[str] input produces same index and score as list[RerankDocument(text=...)]."""
    from headwater_server.services.reranker_service.rerank import run_rerank
    from headwater_api.classes import RerankRequest, RerankDocument

    docs_str = ["doc A", "doc B"]
    docs_obj = [RerankDocument(text="doc A"), RerankDocument(text="doc B")]
    scores = [0.2, 0.8]

    mock_ranker_str = _make_mock_ranker(docs_str, scores)
    mock_ranker_obj = _make_mock_ranker(docs_str, scores)

    request_str = RerankRequest(query="test", documents=docs_str, model_name="flash", k=2)
    request_obj = RerankRequest(query="test", documents=docs_obj, model_name="flash", k=2)

    with _patch_reranker(mock_ranker_str):
        response_str = await run_rerank(request_str)

    with _patch_reranker(mock_ranker_obj):
        response_obj = await run_rerank(request_obj)

    for r_str, r_obj in zip(response_str.results, response_obj.results):
        assert r_str.index == r_obj.index
        assert r_str.score == r_obj.score
        assert r_str.document.id is None
        assert r_obj.document.id is None
```

**Step 2: Run and verify passes**

```bash
uv run pytest tests/services/reranker_service/test_rerank.py::test_str_and_rerank_document_produce_same_index_and_score -v
```

Expected: PASSED.

**Step 3: Commit**

```bash
git add tests/services/reranker_service/test_rerank.py
git commit -m "test: verify str and RerankDocument inputs produce identical index/score (AC13)"
```

---

## Task 14: List models service (AC11)

**Files:**
- Create: `headwater-server/src/headwater_server/services/reranker_service/list_reranker_models_service.py`
- Modify: `headwater-server/tests/services/reranker_service/test_config.py`

**Step 1: Write failing test for AC11**

Append to `headwater-server/tests/services/reranker_service/test_config.py`:

```python
@pytest.mark.asyncio
async def test_list_models_returns_model_info_for_every_allowlisted_model():
    """AC11: GET /reranker/models returns a RerankerModelInfo for every key in reranking_models.json."""
    from headwater_server.services.reranker_service.list_reranker_models_service import (
        list_reranker_models_service,
    )
    from headwater_server.services.reranker_service.config import _MODELS
    from headwater_api.classes import RerankerModelInfo

    result = await list_reranker_models_service()

    assert len(result) == len(_MODELS)
    assert all(isinstance(m, RerankerModelInfo) for m in result)

    names = {m.name for m in result}
    assert names == set(_MODELS.keys())

    for m in result:
        assert m.output_type in {"logits", "bounded"}
```

**Step 2: Run test — verify it fails**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/reranker_service/test_config.py::test_list_models_returns_model_info_for_every_allowlisted_model -v
```

Expected: `ModuleNotFoundError`.

**Step 3: Create `list_reranker_models_service.py`**

```python
from __future__ import annotations
from headwater_api.classes import RerankerModelInfo
from headwater_server.services.reranker_service.config import list_models


async def list_reranker_models_service() -> list[RerankerModelInfo]:
    return [RerankerModelInfo(**entry) for entry in list_models()]
```

**Step 4: Run test — verify it passes**

```bash
uv run pytest tests/services/reranker_service/test_config.py::test_list_models_returns_model_info_for_every_allowlisted_model -v
```

Expected: PASSED.

**Step 5: Commit**

```bash
git add \
  src/headwater_server/services/reranker_service/list_reranker_models_service.py \
  tests/services/reranker_service/test_config.py
git commit -m "feat: add list_reranker_models_service (AC11)"
```

---

## Task 15: Service function + API wiring

**Files:**
- Create: `headwater-server/src/headwater_server/services/reranker_service/reranker_service.py`
- Create: `headwater-server/src/headwater_server/api/reranker_server_api.py`
- Modify: `headwater-server/src/headwater_server/server/headwater.py`

**Step 1: Create `reranker_service.py`**

```python
from __future__ import annotations
from headwater_api.classes import RerankRequest, RerankResponse


async def reranker_service(request: RerankRequest) -> RerankResponse:
    from headwater_server.services.reranker_service.rerank import run_rerank
    return await run_rerank(request)
```

**Step 2: Create `reranker_server_api.py`**

Create `headwater-server/src/headwater_server/api/reranker_server_api.py`:

```python
from __future__ import annotations
from fastapi import FastAPI
from headwater_api.classes import RerankRequest, RerankResponse, RerankerModelInfo


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

**Step 3: Register in `headwater.py`**

In `headwater-server/src/headwater_server/server/headwater.py`, add the import and registration:

```python
# add import at top with the others:
from headwater_server.api.reranker_server_api import RerankerServerAPI

# add in _register_routes():
RerankerServerAPI(self.app).register_routes()
```

**Step 4: Smoke test — verify server starts**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run python -c "
from headwater_server.server.headwater import app
routes = [r.path for r in app.routes]
assert '/reranker/rerank' in routes, f'missing route, got: {routes}'
assert '/reranker/models' in routes
print('routes registered OK')
"
```

Expected: `routes registered OK`

**Step 5: Run full test suite**

```bash
uv run pytest tests/services/reranker_service/ -v
```

Expected: all PASSED.

**Step 6: Commit**

```bash
git add \
  src/headwater_server/services/reranker_service/reranker_service.py \
  src/headwater_server/api/reranker_server_api.py \
  src/headwater_server/server/headwater.py
git commit -m "feat: wire reranker routes into FastAPI app"
```

---

## Final check

Run the entire test suite from both packages:

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-api
uv run pytest tests/classes/test_reranker_classes.py -v

cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/reranker_service/ -v
```

All tests should pass before declaring the feature complete.
