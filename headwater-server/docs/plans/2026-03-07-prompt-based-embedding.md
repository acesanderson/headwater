# Prompt-Based Embedding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow callers to pass a `task` (enum) or raw `prompt` string when generating embeddings, with per-model validation that returns HTTP 422 on misuse.

**Architecture:** Model prompt metadata is stored in `embedding_models.json` alongside the model list. Pydantic `model_validator` on the request classes enforces all validation rules before any model is loaded, returning 422 naturally via FastAPI. Task-to-string resolution happens in the service layer; `EmbeddingModel` receives only a final `prompt: str | None`.

**Tech Stack:** Python 3.12, Pydantic v2, SentenceTransformers, FastAPI, pytest, uv. All packages are in `headwater-api` (editable dep of `headwater-server`). Tests run from `headwater-server/`.

---

## Acceptance Criteria Reference

- **AC1** — `EmbeddingsRequest` with `task="query"` + nomic model constructs without error.
- **AC2** — `EmbeddingsRequest` with `prompt="search_query: "` + nomic model constructs without error.
- **AC3** — `task` and `prompt` both set → `ValidationError`.
- **AC4** — Neither `task` nor `prompt` on a `prompt_required` model → `ValidationError`.
- **AC5** — `task="clustering"` on e5 (no clustering in task_map) → `ValidationError` naming model and task.
- **AC6** — `prompt="bad_prefix: "` on nomic → `ValidationError` listing valid prefixes.
- **AC7** — `prompt` set on a `prompt_unsupported` model → `ValidationError`.
- **AC8** — No `task` or `prompt` on BGE (optional) → constructs without error.
- **AC9** — `QuickEmbeddingRequest` satisfies ACs 1–8 equivalently.
- **AC10** — `task="query"` resolves to `"search_query: "` for nomic and `"query: "` for e5 (different strings per model).
- **AC11** — `google/embeddinggemma-300m` with no task or prompt calls `encode(prompt_name="STS")`, not `encode(prompt=None)`.

---

## Task 1: Restructure `embedding_models.json` and update the loader

**Files:**
- Modify: `headwater-api/src/headwater_api/classes/embeddings_classes/embedding_models.json`
- Modify: `headwater-api/src/headwater_api/classes/embeddings_classes/embedding_models.py`
- Modify: `headwater-api/src/headwater_api/classes/__init__.py`
- Create: `headwater-server/tests/services/embeddings_service/__init__.py`
- Create: `headwater-server/tests/services/embeddings_service/test_model_prompt_spec.py`

### Step 1: Write the failing tests

Create `headwater-server/tests/services/embeddings_service/__init__.py` (empty).

Create `headwater-server/tests/services/embeddings_service/test_model_prompt_spec.py`:

```python
from __future__ import annotations
import pytest


def test_load_embedding_models_returns_list_of_strings():
    from headwater_api.classes import load_embedding_models
    models = load_embedding_models()
    assert isinstance(models, list)
    assert all(isinstance(m, str) for m in models)
    assert "nomic-ai/nomic-embed-text-v1.5" in models
    assert "intfloat/e5-large-v2" in models


def test_get_model_prompt_spec_nomic():
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec
    spec = get_model_prompt_spec("nomic-ai/nomic-embed-text-v1.5")
    assert spec.prompt_required is True
    assert spec.prompt_unsupported is False
    assert spec.valid_prefixes == [
        "search_query: ", "search_document: ", "classification: ", "clustering: "
    ]
    assert spec.task_map == {
        "query": "search_query: ",
        "document": "search_document: ",
        "classification": "classification: ",
        "clustering": "clustering: ",
    }


def test_get_model_prompt_spec_e5():
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec
    spec = get_model_prompt_spec("intfloat/e5-large-v2")
    assert spec.prompt_required is True
    assert spec.valid_prefixes == ["query: ", "passage: "]
    assert spec.task_map == {"query": "query: ", "document": "passage: "}


def test_get_model_prompt_spec_minilm_is_unsupported():
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec
    spec = get_model_prompt_spec("sentence-transformers/all-MiniLM-L6-v2")
    assert spec.prompt_unsupported is True
    assert spec.prompt_required is False


def test_get_model_prompt_spec_bge_is_optional():
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec
    spec = get_model_prompt_spec("BAAI/bge-large-en-v1.5")
    assert spec.prompt_required is False
    assert spec.prompt_unsupported is False
```

### Step 2: Run tests to verify they fail

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_model_prompt_spec.py -v --no-header -p no:pdb
```

Expected: FAIL — `get_model_prompt_spec` does not exist yet; `load_embedding_models` may also fail if JSON is already restructured.

### Step 3: Restructure `embedding_models.json`

Replace the entire file at `headwater-api/src/headwater_api/classes/embeddings_classes/embedding_models.json`:

```json
{
  "embedding_models": {
    "BAAI/bge-large-en-v1.5": {
      "prompt_required": false,
      "valid_prefixes": null,
      "prompt_unsupported": false,
      "task_map": null
    },
    "BAAI/bge-base-en-v1.5": {
      "prompt_required": false,
      "valid_prefixes": null,
      "prompt_unsupported": false,
      "task_map": null
    },
    "BAAI/bge-reranker-v2-m3": {
      "prompt_required": false,
      "valid_prefixes": null,
      "prompt_unsupported": false,
      "task_map": null
    },
    "sentence-transformers/all-mpnet-base-v2": {
      "prompt_required": false,
      "valid_prefixes": null,
      "prompt_unsupported": true,
      "task_map": null
    },
    "sentence-transformers/all-MiniLM-L6-v2": {
      "prompt_required": false,
      "valid_prefixes": null,
      "prompt_unsupported": true,
      "task_map": null
    },
    "nomic-ai/nomic-embed-text-v1.5": {
      "prompt_required": true,
      "valid_prefixes": ["search_query: ", "search_document: ", "classification: ", "clustering: "],
      "prompt_unsupported": false,
      "task_map": {
        "query": "search_query: ",
        "document": "search_document: ",
        "classification": "classification: ",
        "clustering": "clustering: "
      }
    },
    "intfloat/e5-large-v2": {
      "prompt_required": true,
      "valid_prefixes": ["query: ", "passage: "],
      "prompt_unsupported": false,
      "task_map": {
        "query": "query: ",
        "document": "passage: "
      }
    },
    "google/embeddinggemma-300m": {
      "prompt_required": false,
      "valid_prefixes": null,
      "prompt_unsupported": false,
      "task_map": null
    }
  }
}
```

### Step 4: Update `embedding_models.py`

Replace the entire file at `headwater-api/src/headwater_api/classes/embeddings_classes/embedding_models.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_embedding_models_file = Path(__file__).parent / "embedding_models.json"


@dataclass
class ModelPromptSpec:
    prompt_required: bool
    valid_prefixes: list[str] | None
    prompt_unsupported: bool
    task_map: dict[str, str] | None


def load_embedding_models() -> list[str]:
    with open(_embedding_models_file, "r", encoding="utf-8") as f:
        data: dict = json.load(f)
    return list(data["embedding_models"].keys())


def get_model_prompt_spec(model_name: str) -> ModelPromptSpec:
    with open(_embedding_models_file, "r", encoding="utf-8") as f:
        data: dict = json.load(f)
    entry = data["embedding_models"][model_name]
    return ModelPromptSpec(
        prompt_required=entry["prompt_required"],
        valid_prefixes=entry["valid_prefixes"],
        prompt_unsupported=entry["prompt_unsupported"],
        task_map=entry["task_map"],
    )
```

### Step 5: Export `ModelPromptSpec` and `get_model_prompt_spec` from `__init__.py`

In `headwater-api/src/headwater_api/classes/__init__.py`, add to the `# Configs` section:

```python
from headwater_api.classes.embeddings_classes.embedding_models import (
    load_embedding_models,
    get_model_prompt_spec,
    ModelPromptSpec,
)
```

And add `"get_model_prompt_spec"` and `"ModelPromptSpec"` to `__all__`.

### Step 6: Run tests to verify they pass

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_model_prompt_spec.py -v --no-header -p no:pdb
```

Expected: all 5 tests PASS.

### Step 7: Commit

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
git add \
  ../headwater-api/src/headwater_api/classes/embeddings_classes/embedding_models.json \
  ../headwater-api/src/headwater_api/classes/embeddings_classes/embedding_models.py \
  ../headwater-api/src/headwater_api/classes/__init__.py \
  tests/services/embeddings_service/__init__.py \
  tests/services/embeddings_service/test_model_prompt_spec.py
git commit -m "feat: restructure embedding_models.json with prompt metadata; add ModelPromptSpec and get_model_prompt_spec"
```

---

## Task 2: Add `EmbeddingTask` enum

**Files:**
- Create: `headwater-api/src/headwater_api/classes/embeddings_classes/task.py`
- Modify: `headwater-api/src/headwater_api/classes/__init__.py`
- Modify: `headwater-server/tests/services/embeddings_service/test_model_prompt_spec.py`

### Step 1: Write the failing test

Add to `test_model_prompt_spec.py`:

```python
def test_embedding_task_enum_values():
    from headwater_api.classes import EmbeddingTask
    assert EmbeddingTask.query.value == "query"
    assert EmbeddingTask.document.value == "document"
    assert EmbeddingTask.classification.value == "classification"
    assert EmbeddingTask.clustering.value == "clustering"
```

### Step 2: Run test to verify it fails

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_model_prompt_spec.py::test_embedding_task_enum_values -v --no-header -p no:pdb
```

Expected: FAIL — `EmbeddingTask` does not exist.

### Step 3: Create `task.py`

Create `headwater-api/src/headwater_api/classes/embeddings_classes/task.py`:

```python
from __future__ import annotations

from enum import Enum


class EmbeddingTask(str, Enum):
    query = "query"
    document = "document"
    classification = "classification"
    clustering = "clustering"
```

### Step 4: Export from `__init__.py`

In `headwater-api/src/headwater_api/classes/__init__.py`, add to the imports:

```python
from headwater_api.classes.embeddings_classes.task import EmbeddingTask
```

Add `"EmbeddingTask"` to `__all__`.

### Step 5: Run test to verify it passes

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_model_prompt_spec.py::test_embedding_task_enum_values -v --no-header -p no:pdb
```

Expected: PASS.

### Step 6: Commit

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
git add \
  ../headwater-api/src/headwater_api/classes/embeddings_classes/task.py \
  ../headwater-api/src/headwater_api/classes/__init__.py \
  tests/services/embeddings_service/test_model_prompt_spec.py
git commit -m "feat: add EmbeddingTask enum"
```

---

## Task 3: Add `task` and `prompt` fields + validator to `EmbeddingsRequest` (ACs 3–8)

**Files:**
- Modify: `headwater-api/src/headwater_api/classes/embeddings_classes/requests.py`
- Create: `headwater-server/tests/services/embeddings_service/test_prompt_validation.py`

### Step 1: Write the failing tests

Create `headwater-server/tests/services/embeddings_service/test_prompt_validation.py`:

```python
from __future__ import annotations
import pytest
from pydantic import ValidationError


# ── helpers ────────────────────────────────────────────────────────────────────

def _batch():
    from headwater_api.classes import ChromaBatch
    return ChromaBatch(ids=["1"], documents=["hello"])


# ── AC3: mutually exclusive ────────────────────────────────────────────────────

def test_ac3_embeddings_request_task_and_prompt_both_raises():
    """AC3: providing both task and prompt raises ValidationError."""
    from headwater_api.classes import EmbeddingsRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="not both"):
        EmbeddingsRequest(
            model="nomic-ai/nomic-embed-text-v1.5",
            batch=_batch(),
            task=EmbeddingTask.query,
            prompt="search_query: ",
        )


# ── AC4: prompt_required ───────────────────────────────────────────────────────

def test_ac4_embeddings_request_required_model_no_task_no_prompt_raises():
    """AC4: prompt_required model with neither task nor prompt raises ValidationError."""
    from headwater_api.classes import EmbeddingsRequest
    with pytest.raises(ValidationError, match="requires"):
        EmbeddingsRequest(
            model="nomic-ai/nomic-embed-text-v1.5",
            batch=_batch(),
        )


# ── AC5: unknown task in task_map ──────────────────────────────────────────────

def test_ac5_embeddings_request_unsupported_task_for_model_raises():
    """AC5: task with no entry in model's task_map raises ValidationError naming model and task."""
    from headwater_api.classes import EmbeddingsRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="intfloat/e5-large-v2"):
        EmbeddingsRequest(
            model="intfloat/e5-large-v2",
            batch=_batch(),
            task=EmbeddingTask.clustering,
        )


def test_ac5_error_message_names_unsupported_task():
    """AC5: ValidationError message names the rejected task value."""
    from headwater_api.classes import EmbeddingsRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="clustering"):
        EmbeddingsRequest(
            model="intfloat/e5-large-v2",
            batch=_batch(),
            task=EmbeddingTask.clustering,
        )


# ── AC6: invalid prefix ────────────────────────────────────────────────────────

def test_ac6_embeddings_request_invalid_prefix_raises():
    """AC6: prompt not starting with a valid prefix raises ValidationError listing valid prefixes."""
    from headwater_api.classes import EmbeddingsRequest
    with pytest.raises(ValidationError, match="search_query"):
        EmbeddingsRequest(
            model="nomic-ai/nomic-embed-text-v1.5",
            batch=_batch(),
            prompt="bad_prefix: some text",
        )


# ── AC7: prompt_unsupported ────────────────────────────────────────────────────

def test_ac7_embeddings_request_prompt_on_unsupported_model_raises():
    """AC7: passing prompt to a prompt_unsupported model raises ValidationError."""
    from headwater_api.classes import EmbeddingsRequest
    with pytest.raises(ValidationError, match="does not support"):
        EmbeddingsRequest(
            model="sentence-transformers/all-MiniLM-L6-v2",
            batch=_batch(),
            prompt="query: hello",
        )


def test_ac7_embeddings_request_task_on_unsupported_model_raises():
    """AC7: passing task to a prompt_unsupported model raises ValidationError."""
    from headwater_api.classes import EmbeddingsRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="does not support"):
        EmbeddingsRequest(
            model="sentence-transformers/all-MiniLM-L6-v2",
            batch=_batch(),
            task=EmbeddingTask.query,
        )


# ── AC8: optional model, no prompt required ────────────────────────────────────

def test_ac8_embeddings_request_bge_no_prompt_is_valid():
    """AC8: BGE model with no task or prompt constructs without error."""
    from headwater_api.classes import EmbeddingsRequest
    req = EmbeddingsRequest(model="BAAI/bge-large-en-v1.5", batch=_batch())
    assert req.task is None
    assert req.prompt is None


# ── AC1/AC2: valid construction ────────────────────────────────────────────────

def test_ac1_embeddings_request_task_query_nomic_is_valid():
    """AC1: task='query' + nomic model constructs without error."""
    from headwater_api.classes import EmbeddingsRequest, EmbeddingTask
    req = EmbeddingsRequest(
        model="nomic-ai/nomic-embed-text-v1.5",
        batch=_batch(),
        task=EmbeddingTask.query,
    )
    assert req.task == EmbeddingTask.query


def test_ac2_embeddings_request_prompt_nomic_is_valid():
    """AC2: prompt='search_query: ' + nomic model constructs without error."""
    from headwater_api.classes import EmbeddingsRequest
    req = EmbeddingsRequest(
        model="nomic-ai/nomic-embed-text-v1.5",
        batch=_batch(),
        prompt="search_query: ",
    )
    assert req.prompt == "search_query: "
```

### Step 2: Run tests to verify they fail

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_prompt_validation.py -v --no-header -p no:pdb
```

Expected: FAIL — `EmbeddingsRequest` has no `task` or `prompt` fields yet.

### Step 3: Update `EmbeddingsRequest` in `requests.py`

In `headwater-api/src/headwater_api/classes/embeddings_classes/requests.py`, update the imports and `EmbeddingsRequest` class. The full updated file:

```python
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import Any

from headwater_api.classes.embeddings_classes.task import EmbeddingTask


class ChromaBatch(BaseModel):
    ids: list[str] = Field(
        ..., description="List of unique identifiers for each item in the batch."
    )
    documents: list[str] = Field(
        ..., description="List of documents or text associated with each item."
    )
    embeddings: list[list[float]] | None = Field(
        default=None, description="List of embeddings corresponding to each item."
    )
    metadatas: list[dict[str, Any]] | None = Field(
        default=None, description="List of metadata dictionaries for each item."
    )


class EmbeddingsRequest(BaseModel):
    model: str = Field(
        ...,
        description="The embedding model to use for generating embeddings.",
    )
    batch: ChromaBatch = Field(
        ...,
        description="Batch of documents to generate embeddings for.",
    )
    task: EmbeddingTask | None = Field(
        default=None,
        description=(
            "Model-agnostic task type. Resolved server-side to the model-specific "
            "prompt string. Mutually exclusive with 'prompt'."
        ),
    )
    prompt: str | None = Field(
        default=None,
        description=(
            "Raw prompt string prepended to each document via SentenceTransformers "
            "encode(prompt=...). Mutually exclusive with 'task'."
        ),
    )

    @model_validator(mode="after")
    def _validate_prompt_fields(self) -> EmbeddingsRequest:
        from headwater_api.classes.embeddings_classes.embedding_models import (
            load_embedding_models,
            get_model_prompt_spec,
        )

        if self.task is not None and self.prompt is not None:
            raise ValueError("Provide 'task' or 'prompt', not both.")

        if self.model not in load_embedding_models():
            return self  # unknown model: let EmbeddingModel.__init__ raise

        spec = get_model_prompt_spec(self.model)

        if spec.prompt_unsupported and (self.task is not None or self.prompt is not None):
            raise ValueError(
                f"Model '{self.model}' does not support prompt-based embedding."
            )

        if spec.prompt_required and self.task is None and self.prompt is None:
            raise ValueError(
                f"Model '{self.model}' requires a 'task' or 'prompt'."
            )

        if self.task is not None:
            if spec.task_map is None or self.task.value not in spec.task_map:
                supported = list(spec.task_map.keys()) if spec.task_map else []
                raise ValueError(
                    f"Model '{self.model}' does not support task '{self.task.value}'. "
                    f"Supported tasks: {supported}"
                )

        if self.prompt is not None and spec.valid_prefixes is not None:
            if not any(self.prompt.startswith(p) for p in spec.valid_prefixes):
                raise ValueError(
                    f"Invalid prompt for model '{self.model}'. "
                    f"Must start with one of: {spec.valid_prefixes}"
                )

        return self


class QuickEmbeddingRequest(BaseModel):
    query: str = Field(
        ...,
        description="The text query to generate an embedding for.",
    )
    model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="The embedding model to use for generating embeddings.",
    )


class GetCollectionRequest(BaseModel):
    collection_name: str = Field(
        ..., description="The name of the collection to retrieve."
    )


class CreateCollectionRequest(BaseModel):
    collection_name: str = Field(
        ..., description="The name of the collection to create."
    )
    embedding_model: str = Field(
        ..., description="The embedding model to use for the collection."
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata for the collection.",
    )


class DeleteCollectionRequest(BaseModel):
    collection_name: str = Field(
        ..., description="The name of the collection to delete."
    )


class QueryCollectionRequest(BaseModel):
    name: str = Field(
        ...,
        description="The name of the collection to query.",
    )
    query: str | None = Field(
        ...,
        description="The query string to search the collection.",
    )
    query_embeddings: list[list[float]] | None = Field(
        ...,
        description="List of query embeddings to search against the collection.",
    )
    k: int = Field(
        default=10,
        description="Number of nearest neighbors to retrieve for each query embedding.",
    )
    n_results: int = Field(
        default=10,
        description="Number of top results to return for each query embedding.",
    )

    @model_validator(mode="after")
    def _exactly_one_query(self):
        has_query = self.query is not None
        has_query_embeddings = self.query_embeddings is not None
        if has_query == has_query_embeddings:
            raise ValueError("Provide exactly one of 'query' or 'query_embeddings'.")
        return self


__all__ = [
    "ChromaBatch",
    "EmbeddingsRequest",
    "QuickEmbeddingRequest",
    "CreateCollectionRequest",
    "DeleteCollectionRequest",
    "QueryCollectionRequest",
]
```

### Step 4: Run tests to verify they pass

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_prompt_validation.py -v --no-header -p no:pdb
```

Expected: all tests PASS.

### Step 5: Commit

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
git add \
  ../headwater-api/src/headwater_api/classes/embeddings_classes/requests.py \
  tests/services/embeddings_service/test_prompt_validation.py
git commit -m "feat: add task/prompt fields and validator to EmbeddingsRequest (AC1-AC8)"
```

---

## Task 4: Add `task` and `prompt` fields + validator to `QuickEmbeddingRequest` (AC9)

**Files:**
- Modify: `headwater-api/src/headwater_api/classes/embeddings_classes/requests.py`
- Modify: `headwater-server/tests/services/embeddings_service/test_prompt_validation.py`

### Step 1: Write the failing tests

Add to `test_prompt_validation.py`:

```python
# ── AC9: QuickEmbeddingRequest mirrors EmbeddingsRequest validation ────────────

def test_ac9_quick_task_and_prompt_both_raises():
    """AC9/AC3: QuickEmbeddingRequest with both task and prompt raises ValidationError."""
    from headwater_api.classes import QuickEmbeddingRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="not both"):
        QuickEmbeddingRequest(
            query="hello",
            model="nomic-ai/nomic-embed-text-v1.5",
            task=EmbeddingTask.query,
            prompt="search_query: ",
        )


def test_ac9_quick_required_model_no_task_no_prompt_raises():
    """AC9/AC4: QuickEmbeddingRequest with prompt_required model, no task or prompt raises."""
    from headwater_api.classes import QuickEmbeddingRequest
    with pytest.raises(ValidationError, match="requires"):
        QuickEmbeddingRequest(
            query="hello",
            model="nomic-ai/nomic-embed-text-v1.5",
        )


def test_ac9_quick_unsupported_task_for_model_raises():
    """AC9/AC5: QuickEmbeddingRequest with unsupported task raises ValidationError."""
    from headwater_api.classes import QuickEmbeddingRequest, EmbeddingTask
    with pytest.raises(ValidationError, match="intfloat/e5-large-v2"):
        QuickEmbeddingRequest(
            query="hello",
            model="intfloat/e5-large-v2",
            task=EmbeddingTask.clustering,
        )


def test_ac9_quick_invalid_prefix_raises():
    """AC9/AC6: QuickEmbeddingRequest with invalid prefix raises ValidationError."""
    from headwater_api.classes import QuickEmbeddingRequest
    with pytest.raises(ValidationError, match="search_query"):
        QuickEmbeddingRequest(
            query="hello",
            model="nomic-ai/nomic-embed-text-v1.5",
            prompt="bad_prefix: ",
        )


def test_ac9_quick_prompt_on_unsupported_model_raises():
    """AC9/AC7: QuickEmbeddingRequest with prompt on unsupported model raises ValidationError."""
    from headwater_api.classes import QuickEmbeddingRequest
    with pytest.raises(ValidationError, match="does not support"):
        QuickEmbeddingRequest(
            query="hello",
            model="sentence-transformers/all-MiniLM-L6-v2",
            prompt="query: ",
        )


def test_ac9_quick_bge_no_prompt_is_valid():
    """AC9/AC8: QuickEmbeddingRequest with BGE and no prompt constructs without error."""
    from headwater_api.classes import QuickEmbeddingRequest
    req = QuickEmbeddingRequest(query="hello", model="BAAI/bge-large-en-v1.5")
    assert req.task is None
    assert req.prompt is None


def test_ac9_quick_task_query_nomic_is_valid():
    """AC9/AC1: QuickEmbeddingRequest with task='query' + nomic constructs without error."""
    from headwater_api.classes import QuickEmbeddingRequest, EmbeddingTask
    req = QuickEmbeddingRequest(
        query="hello",
        model="nomic-ai/nomic-embed-text-v1.5",
        task=EmbeddingTask.query,
    )
    assert req.task == EmbeddingTask.query


def test_ac9_quick_prompt_nomic_is_valid():
    """AC9/AC2: QuickEmbeddingRequest with valid prefix + nomic constructs without error."""
    from headwater_api.classes import QuickEmbeddingRequest
    req = QuickEmbeddingRequest(
        query="hello",
        model="nomic-ai/nomic-embed-text-v1.5",
        prompt="search_query: ",
    )
    assert req.prompt == "search_query: "
```

### Step 2: Run tests to verify they fail

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_prompt_validation.py -k "ac9" -v --no-header -p no:pdb
```

Expected: FAIL — `QuickEmbeddingRequest` has no `task` or `prompt` fields yet.

### Step 3: Update `QuickEmbeddingRequest` in `requests.py`

Replace the `QuickEmbeddingRequest` class in `requests.py` with:

```python
class QuickEmbeddingRequest(BaseModel):
    query: str = Field(
        ...,
        description="The text query to generate an embedding for.",
    )
    model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="The embedding model to use for generating embeddings.",
    )
    task: EmbeddingTask | None = Field(
        default=None,
        description=(
            "Model-agnostic task type. Resolved server-side to the model-specific "
            "prompt string. Mutually exclusive with 'prompt'."
        ),
    )
    prompt: str | None = Field(
        default=None,
        description=(
            "Raw prompt string prepended to each document via SentenceTransformers "
            "encode(prompt=...). Mutually exclusive with 'task'."
        ),
    )

    @model_validator(mode="after")
    def _validate_prompt_fields(self) -> QuickEmbeddingRequest:
        from headwater_api.classes.embeddings_classes.embedding_models import (
            load_embedding_models,
            get_model_prompt_spec,
        )

        if self.task is not None and self.prompt is not None:
            raise ValueError("Provide 'task' or 'prompt', not both.")

        if self.model not in load_embedding_models():
            return self

        spec = get_model_prompt_spec(self.model)

        if spec.prompt_unsupported and (self.task is not None or self.prompt is not None):
            raise ValueError(
                f"Model '{self.model}' does not support prompt-based embedding."
            )

        if spec.prompt_required and self.task is None and self.prompt is None:
            raise ValueError(
                f"Model '{self.model}' requires a 'task' or 'prompt'."
            )

        if self.task is not None:
            if spec.task_map is None or self.task.value not in spec.task_map:
                supported = list(spec.task_map.keys()) if spec.task_map else []
                raise ValueError(
                    f"Model '{self.model}' does not support task '{self.task.value}'. "
                    f"Supported tasks: {supported}"
                )

        if self.prompt is not None and spec.valid_prefixes is not None:
            if not any(self.prompt.startswith(p) for p in spec.valid_prefixes):
                raise ValueError(
                    f"Invalid prompt for model '{self.model}'. "
                    f"Must start with one of: {spec.valid_prefixes}"
                )

        return self
```

Note: the validation logic is identical to `EmbeddingsRequest`. Do not extract a shared helper — the duplication is minor and the classes may diverge. YAGNI.

### Step 4: Run tests to verify they pass

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_prompt_validation.py -v --no-header -p no:pdb
```

Expected: all tests PASS (including the previous Task 3 tests).

### Step 5: Commit

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
git add \
  ../headwater-api/src/headwater_api/classes/embeddings_classes/requests.py \
  tests/services/embeddings_service/test_prompt_validation.py
git commit -m "feat: add task/prompt fields and validator to QuickEmbeddingRequest (AC9)"
```

---

## Task 5: Update `EmbeddingModel` to accept and use `prompt` (ACs 10, 11)

**Files:**
- Modify: `headwater-server/src/headwater_server/services/embeddings_service/embedding_model.py`
- Create: `headwater-server/tests/services/embeddings_service/test_embedding_model_prompt.py`

### Step 1: Write the failing tests

Create `headwater-server/tests/services/embeddings_service/test_embedding_model_prompt.py`:

```python
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch


def _make_mock_st(embedding_dim: int = 4):
    """Return a SentenceTransformer mock whose encode() returns a numpy-like list."""
    import numpy as np
    mock = MagicMock()
    mock.encode.return_value = np.array([[0.1] * embedding_dim])
    return mock


# ── AC10: task resolves to different prompt strings per model ──────────────────

def test_ac10_task_query_nomic_passes_search_query_prefix(monkeypatch):
    """AC10: task='query' for nomic resolves to 'search_query: ' passed to encode()."""
    from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

    mock_st = _make_mock_st()
    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        return_value=mock_st,
    ):
        model = EmbeddingModel("nomic-ai/nomic-embed-text-v1.5")
        model.generate_embedding("hello", prompt="search_query: ")

    _, kwargs = mock_st.encode.call_args
    assert kwargs.get("prompt") == "search_query: "


def test_ac10_task_query_e5_passes_query_prefix(monkeypatch):
    """AC10: task='query' for e5 resolves to 'query: ' passed to encode()."""
    from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

    mock_st = _make_mock_st()
    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        return_value=mock_st,
    ):
        model = EmbeddingModel("intfloat/e5-large-v2")
        model.generate_embedding("hello", prompt="query: ")

    _, kwargs = mock_st.encode.call_args
    assert kwargs.get("prompt") == "query: "


def test_ac10_nomic_and_e5_query_prompts_differ():
    """AC10: 'query' task resolves to different prompt strings for nomic vs e5."""
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec
    nomic_spec = get_model_prompt_spec("nomic-ai/nomic-embed-text-v1.5")
    e5_spec = get_model_prompt_spec("intfloat/e5-large-v2")
    assert nomic_spec.task_map["query"] != e5_spec.task_map["query"]


# ── AC11: gemma fallback uses prompt_name="STS" when no prompt given ───────────

def test_ac11_gemma_no_prompt_uses_prompt_name_sts():
    """AC11: gemma with no task or prompt calls encode(prompt_name='STS')."""
    from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

    mock_st = _make_mock_st()
    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        return_value=mock_st,
    ):
        model = EmbeddingModel("google/embeddinggemma-300m")
        model.generate_embedding("hello", prompt=None)

    _, kwargs = mock_st.encode.call_args
    assert kwargs.get("prompt_name") == "STS"
    assert "prompt" not in kwargs or kwargs.get("prompt") is None


def test_ac11_gemma_with_prompt_uses_prompt_not_prompt_name():
    """AC11 (inverse): gemma with an explicit prompt uses encode(prompt=...) not prompt_name."""
    from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

    mock_st = _make_mock_st()
    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        return_value=mock_st,
    ):
        model = EmbeddingModel("google/embeddinggemma-300m")
        model.generate_embedding("hello", prompt="my custom prefix: ")

    _, kwargs = mock_st.encode.call_args
    assert kwargs.get("prompt") == "my custom prefix: "
    assert "prompt_name" not in kwargs
```

### Step 2: Run tests to verify they fail

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_embedding_model_prompt.py -v --no-header -p no:pdb
```

Expected: FAIL — `generate_embedding` does not accept a `prompt` argument yet.

### Step 3: Update `embedding_model.py`

Replace the entire file at `headwater-server/src/headwater_server/services/embeddings_service/embedding_model.py`:

```python
from __future__ import annotations

import logging
import os
from typing import Protocol

import torch
from sentence_transformers import SentenceTransformer

from headwater_api.classes import ChromaBatch, load_embedding_models

logger = logging.getLogger(__name__)
_DEVICE_CACHE = None
HUGGINGFACE_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")
os.environ["HF_TOKEN"] = HUGGINGFACE_API_TOKEN


class EmbeddingFunction(Protocol):
    def __call__(
        self, documents: list[str], prompt: str | None = None
    ) -> list[list[float]]: ...


class EmbeddingModel:
    def __init__(self, model_name: str):
        self.model_name = model_name
        if model_name not in self.models():
            raise ValueError(f"Model '{model_name}' is not supported.")

        self._st_model = SentenceTransformer(
            model_name,
            device=self.device(),
            model_kwargs={"torch_dtype": torch.bfloat16},
        )

        self.embedding_function: EmbeddingFunction = self._get_handler(model_name)

    def _get_handler(self, model_name: str) -> EmbeddingFunction:
        match model_name:
            case "google/embeddinggemma-300m":
                return self._gemma_handler
            case name if "bge-" in name:
                return self._bge_handler
            case _:
                return self._default_handler

    # --- Specialized Handlers ---

    def _gemma_handler(
        self, documents: list[str], prompt: str | None = None
    ) -> list[list[float]]:
        if prompt is not None:
            return self._st_model.encode(
                documents,
                prompt=prompt,
                batch_size=64,
                convert_to_tensor=False,
            ).tolist()
        return self._st_model.encode(
            documents,
            prompt_name="STS",
            batch_size=64,
            convert_to_tensor=False,
        ).tolist()

    def _bge_handler(
        self, documents: list[str], prompt: str | None = None
    ) -> list[list[float]]:
        kwargs: dict = {"batch_size": 128, "convert_to_tensor": False}
        if prompt is not None:
            kwargs["prompt"] = prompt
        return self._st_model.encode(documents, **kwargs).tolist()

    def _default_handler(
        self, documents: list[str], prompt: str | None = None
    ) -> list[list[float]]:
        kwargs: dict = {"batch_size": 128, "convert_to_tensor": False}
        if prompt is not None:
            kwargs["prompt"] = prompt
        return self._st_model.encode(documents, **kwargs).tolist()

    # --- Standard Interface Methods ---

    @classmethod
    def models(cls) -> list[str]:
        return load_embedding_models()

    @classmethod
    def device(cls) -> str:
        global _DEVICE_CACHE
        if _DEVICE_CACHE is None:
            _DEVICE_CACHE = "cuda" if torch.cuda.is_available() else "cpu"
        return _DEVICE_CACHE

    def generate_embeddings(
        self, batch: ChromaBatch, prompt: str | None = None
    ) -> ChromaBatch:
        embeddings = self.embedding_function(batch.documents, prompt=prompt)
        return ChromaBatch(
            ids=batch.ids,
            documents=batch.documents,
            metadatas=batch.metadatas,
            embeddings=embeddings,
        )

    def generate_embedding(self, document: str, prompt: str | None = None) -> list[float]:
        return self.embedding_function([document], prompt=prompt)[0]
```

### Step 4: Run tests to verify they pass

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_embedding_model_prompt.py -v --no-header -p no:pdb
```

Expected: all 5 tests PASS.

### Step 5: Commit

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
git add \
  src/headwater_server/services/embeddings_service/embedding_model.py \
  tests/services/embeddings_service/test_embedding_model_prompt.py
git commit -m "feat: update EmbeddingModel handlers to accept prompt; gemma falls back to prompt_name=STS (AC10, AC11)"
```

---

## Task 6: Wire `task`/`prompt` through the service layer

**Files:**
- Modify: `headwater-server/src/headwater_server/services/embeddings_service/generate_embeddings_service.py`
- Modify: `headwater-server/src/headwater_server/services/embeddings_service/quick_embedding_service.py`
- Modify: `headwater-server/tests/services/embeddings_service/test_prompt_validation.py`

The services resolve `task` → prompt string (via `task_map`) and pass the resulting prompt to `EmbeddingModel`. Validation already happened in the Pydantic layer, so by the time we reach the service, if `task` is set we know `task_map[task.value]` exists.

### Step 1: Write the failing tests

Add to `test_prompt_validation.py`:

```python
# ── Service-layer task resolution ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_resolves_task_to_prompt_string_before_model_call():
    """
    generate_embeddings_service resolves task='query' to the model-specific prompt
    string and passes it to EmbeddingModel.generate_embeddings.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from headwater_api.classes import EmbeddingsRequest, EmbeddingTask, ChromaBatch

    batch = ChromaBatch(ids=["1"], documents=["hello"])
    request = EmbeddingsRequest(
        model="nomic-ai/nomic-embed-text-v1.5",
        batch=batch,
        task=EmbeddingTask.query,
    )

    mock_model_instance = MagicMock()
    mock_model_instance.generate_embeddings.return_value = ChromaBatch(
        ids=["1"], documents=["hello"], embeddings=[[0.1, 0.2]]
    )

    with patch(
        "headwater_server.services.embeddings_service.generate_embeddings_service.EmbeddingModel",
        return_value=mock_model_instance,
    ):
        from headwater_server.services.embeddings_service.generate_embeddings_service import (
            generate_embeddings_service,
        )
        await generate_embeddings_service(request)

    mock_model_instance.generate_embeddings.assert_called_once()
    _, kwargs = mock_model_instance.generate_embeddings.call_args
    assert kwargs.get("prompt") == "search_query: "


def test_quick_service_resolves_task_to_prompt_string_before_model_call():
    """
    quick_embedding_service resolves task='query' to the model-specific prompt
    string and passes it to EmbeddingModel.generate_embedding.
    """
    from unittest.mock import MagicMock, patch
    from headwater_api.classes import QuickEmbeddingRequest, EmbeddingTask

    request = QuickEmbeddingRequest(
        query="hello",
        model="nomic-ai/nomic-embed-text-v1.5",
        task=EmbeddingTask.query,
    )

    mock_model_instance = MagicMock()
    mock_model_instance.generate_embedding.return_value = [0.1, 0.2]

    with patch(
        "headwater_server.services.embeddings_service.quick_embedding_service.EmbeddingModel",
        return_value=mock_model_instance,
    ):
        from headwater_server.services.embeddings_service.quick_embedding_service import (
            quick_embedding_service,
        )
        quick_embedding_service(request)

    mock_model_instance.generate_embedding.assert_called_once()
    _, kwargs = mock_model_instance.generate_embedding.call_args
    assert kwargs.get("prompt") == "search_query: "
```

### Step 2: Run tests to verify they fail

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_prompt_validation.py -k "service_resolves" -v --no-header -p no:pdb
```

Expected: FAIL — services don't pass prompt yet.

### Step 3: Update `generate_embeddings_service.py`

Replace the full file:

```python
from __future__ import annotations

import logging

from headwater_api.classes import EmbeddingsRequest, EmbeddingsResponse

logger = logging.getLogger(__name__)


async def generate_embeddings_service(
    request: EmbeddingsRequest,
) -> EmbeddingsResponse:
    from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel
    from headwater_api.classes import ChromaBatch
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec

    model: str = request.model
    batch: ChromaBatch = request.batch

    logger.info(
        "Generating embeddings",
        extra={
            "model": model,
            "task": request.task.value if request.task else None,
            "prompt_provided": request.prompt is not None,
            "batch_size": len(batch.documents),
        },
    )

    if batch.embeddings:
        raise ValueError("Embeddings already exist in the provided batch.")

    prompt: str | None = request.prompt
    if request.task is not None:
        spec = get_model_prompt_spec(model)
        prompt = spec.task_map[request.task.value]

    embedding_model = EmbeddingModel(model)
    new_batch: ChromaBatch = embedding_model.generate_embeddings(batch, prompt=prompt)
    return EmbeddingsResponse(embeddings=new_batch.embeddings)
```

### Step 4: Update `quick_embedding_service.py`

Replace the full file:

```python
from __future__ import annotations

from headwater_api.classes import QuickEmbeddingRequest, QuickEmbeddingResponse


def quick_embedding_service(
    request: QuickEmbeddingRequest,
) -> QuickEmbeddingResponse:
    from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel
    from headwater_api.classes.embeddings_classes.embedding_models import get_model_prompt_spec

    query = request.query
    model = request.model

    prompt: str | None = request.prompt
    if request.task is not None:
        spec = get_model_prompt_spec(model)
        prompt = spec.task_map[request.task.value]

    embedding_model = EmbeddingModel(model)
    embedding = embedding_model.generate_embedding(query, prompt=prompt)
    return QuickEmbeddingResponse(embedding=embedding)
```

### Step 5: Run all tests to verify they pass

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/ -v --no-header -p no:pdb
```

Expected: all tests across all three test files PASS.

### Step 6: Commit

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
git add \
  src/headwater_server/services/embeddings_service/generate_embeddings_service.py \
  src/headwater_server/services/embeddings_service/quick_embedding_service.py \
  tests/services/embeddings_service/test_prompt_validation.py
git commit -m "feat: resolve task->prompt in service layer; add structured logging (AC1, AC2, AC10)"
```

---

## Final Verification

Run the full embeddings test suite to confirm nothing regressed:

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/ tests/services/test_embeddings.py -v --no-header -p no:pdb
```

Note: `test_embeddings.py` loads a real SentenceTransformer model — it will be slow and requires the model weights on disk. If weights are unavailable in the current environment, skip it with `-k "not test_embeddings_server"`. All new tests are unit tests and will run without model weights.
