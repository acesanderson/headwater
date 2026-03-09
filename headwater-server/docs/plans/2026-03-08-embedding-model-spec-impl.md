# EmbeddingModelSpec Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `ModelPromptSpec` (dataclass) and the merged `embedding_models.json` in headwater-api with a structured `EmbeddingModelSpec`/`EmbeddingModelStore` pattern modeled on conduit's `ModelSpec`/`ModelStore`, with all registry and spec-store logic living in headwater-server.

**Architecture:** `EmbeddingProvider` (enum) and `EmbeddingModelSpec` (Pydantic) live in headwater-api as shared data contracts. headwater-server owns a provider-keyed `embedding_models.json` registry and a TinyDB spec store (`embedding_modelspecs.json`). `EmbeddingModelStore` manages consistency between them; a Perplexity-powered research script populates informational fields for new models; a CLI script triggers sync. Clients get model info via the `/conduit/embeddings/models` API endpoint, not local file I/O.

**Tech Stack:** Python 3.12, Pydantic v2, TinyDB, FastAPI, Conduit (Perplexity/sonar-pro), pytest, unittest.mock

**Design doc:** `docs/plans/2026-03-08-embedding-model-spec-design.md` — every AC reference below is to that document's section 4.

---

## Dependency: add tinydb

Before any tasks, add `tinydb` to headwater-server's dependencies if not already present (check via `uv run python -c "import tinydb"`). If missing:

```bash
cd headwater-server
uv add tinydb
```

---

## Task 1: EmbeddingProvider enum

**Files:**
- Create: `headwater-api/src/headwater_api/classes/embeddings_classes/embedding_provider.py`
- Test: `headwater-server/tests/services/embeddings_service/test_embedding_provider.py`

### TDD Cycle — Provider enum values are correct strings

**Step 1: Write the failing test**

```python
# tests/services/embeddings_service/test_embedding_provider.py
from headwater_api.classes.embeddings_classes.embedding_provider import EmbeddingProvider


def test_provider_values():
    assert EmbeddingProvider.HUGGINGFACE == "huggingface"
    assert EmbeddingProvider.OPENAI == "openai"
    assert EmbeddingProvider.COHERE == "cohere"
    assert EmbeddingProvider.JINA == "jina"


def test_provider_from_string():
    assert EmbeddingProvider("huggingface") == EmbeddingProvider.HUGGINGFACE
```

**Step 2: Run test to verify it fails**

```bash
cd headwater-server
uv run pytest tests/services/embeddings_service/test_embedding_provider.py -v
```

Expected: `ImportError` or `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# headwater-api/src/headwater_api/classes/embeddings_classes/embedding_provider.py
from __future__ import annotations
from enum import Enum


class EmbeddingProvider(str, Enum):
    HUGGINGFACE = "huggingface"
    OPENAI = "openai"
    COHERE = "cohere"
    JINA = "jina"
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_provider.py -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add headwater-api/src/headwater_api/classes/embeddings_classes/embedding_provider.py \
        headwater-server/tests/services/embeddings_service/test_embedding_provider.py
git commit -m "feat: add EmbeddingProvider enum to headwater-api"
```

---

## Task 2: EmbeddingModelSpec — basic construction (AC2)

**Fulfills:** AC — `EmbeddingModelSpec(prompt_required=False, prompt_unsupported=False, embedding_dim=None, ...)` constructs without error.

**Files:**
- Create: `headwater-api/src/headwater_api/classes/embeddings_classes/embedding_model_spec.py`
- Test: `headwater-server/tests/services/embeddings_service/test_embedding_model_spec.py`

### TDD Cycle A — basic construction succeeds with None optional fields

**Step 1: Write the failing test**

```python
# tests/services/embeddings_service/test_embedding_model_spec.py
from headwater_api.classes.embeddings_classes.embedding_model_spec import EmbeddingModelSpec
from headwater_api.classes.embeddings_classes.embedding_provider import EmbeddingProvider


def _minimal_spec(**overrides) -> dict:
    base = dict(
        model="BAAI/bge-m3",
        provider=EmbeddingProvider.HUGGINGFACE,
        description=None,
        embedding_dim=None,
        max_seq_length=None,
        multilingual=False,
        parameter_count=None,
        prompt_required=False,
        valid_prefixes=None,
        prompt_unsupported=False,
        task_map=None,
    )
    base.update(overrides)
    return base


def test_basic_construction_succeeds():
    spec = EmbeddingModelSpec(**_minimal_spec())
    assert spec.model == "BAAI/bge-m3"
    assert spec.provider == EmbeddingProvider.HUGGINGFACE
    assert spec.embedding_dim is None
    assert spec.prompt_required is False
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_spec.py::test_basic_construction_succeeds -v
```

Expected: `ImportError`

**Step 3: Write minimal implementation**

```python
# headwater-api/src/headwater_api/classes/embeddings_classes/embedding_model_spec.py
from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
from headwater_api.classes.embeddings_classes.embedding_provider import EmbeddingProvider


class EmbeddingModelSpec(BaseModel):
    model: str
    provider: EmbeddingProvider
    description: str | None = Field(default=None)
    embedding_dim: int | None = Field(default=None)
    max_seq_length: int | None = Field(default=None)
    multilingual: bool = Field(default=False)
    parameter_count: str | None = Field(default=None)
    prompt_required: bool = Field(default=False)
    valid_prefixes: list[str] | None = Field(default=None)
    prompt_unsupported: bool = Field(default=False)
    task_map: dict[str, str] | None = Field(default=None)
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_spec.py::test_basic_construction_succeeds -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add headwater-api/src/headwater_api/classes/embeddings_classes/embedding_model_spec.py \
        headwater-server/tests/services/embeddings_service/test_embedding_model_spec.py
git commit -m "feat: add EmbeddingModelSpec Pydantic model to headwater-api"
```

---

## Task 3: EmbeddingModelSpec — contradictory flags validator (AC1)

**Fulfills:** AC — `EmbeddingModelSpec(prompt_required=True, prompt_unsupported=True, ...)` raises `ValidationError`.

**Files:**
- Modify: `headwater-api/src/headwater_api/classes/embeddings_classes/embedding_model_spec.py`
- Modify: `headwater-server/tests/services/embeddings_service/test_embedding_model_spec.py`

### TDD Cycle B — contradictory flags raise ValidationError

**Step 1: Write the failing test**

```python
# append to test_embedding_model_spec.py
import pytest
from pydantic import ValidationError


def test_contradictory_prompt_flags_raise():
    with pytest.raises(ValidationError, match="prompt_required and prompt_unsupported"):
        EmbeddingModelSpec(**_minimal_spec(prompt_required=True, prompt_unsupported=True))
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_spec.py::test_contradictory_prompt_flags_raise -v
```

Expected: FAILED — no ValidationError raised

**Step 3: Add validator to EmbeddingModelSpec**

```python
# add inside EmbeddingModelSpec class in embedding_model_spec.py
    @model_validator(mode="after")
    def _prompt_flags_not_contradictory(self) -> EmbeddingModelSpec:
        if self.prompt_required and self.prompt_unsupported:
            raise ValueError("prompt_required and prompt_unsupported cannot both be True.")
        return self
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_spec.py::test_contradictory_prompt_flags_raise -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add headwater-api/src/headwater_api/classes/embeddings_classes/embedding_model_spec.py \
        headwater-server/tests/services/embeddings_service/test_embedding_model_spec.py
git commit -m "feat: add contradictory-flags validator to EmbeddingModelSpec"
```

---

## Task 4: EmbeddingModelSpec — round-trip serialization (AC3)

**Fulfills:** AC — `EmbeddingModelSpec.model_validate(spec.model_dump())` round-trips without data loss for all field combinations.

**Files:**
- Modify: `headwater-server/tests/services/embeddings_service/test_embedding_model_spec.py`

### TDD Cycle C — round-trip is lossless

**Step 1: Write the failing test**

```python
# append to test_embedding_model_spec.py
def test_round_trip_lossless():
    original = EmbeddingModelSpec(**_minimal_spec(
        description="A test model.",
        embedding_dim=768,
        max_seq_length=512,
        multilingual=True,
        parameter_count="110m",
        prompt_required=True,
        valid_prefixes=["query: ", "passage: "],
        task_map={"query": "query: ", "document": "passage: "},
    ))
    restored = EmbeddingModelSpec.model_validate(original.model_dump())
    assert original == restored
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_spec.py::test_round_trip_lossless -v
```

Expected: FAILED (EmbeddingProvider enum round-trip may fail or model not yet importable from all paths)

**Step 3: Implement**

No code change needed if Pydantic handles enum serialization by default. If the test reveals an issue (e.g., provider serialized as raw string and not re-coerced), add to `EmbeddingModelSpec`:

```python
    model_config = {"use_enum_values": False}
```

Run the test; if it passes without changes, move on.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_spec.py -v
```

Expected: all 3 tests PASSED

**Step 5: Commit**

```bash
git add headwater-server/tests/services/embeddings_service/test_embedding_model_spec.py
git commit -m "test: add round-trip serialization test for EmbeddingModelSpec"
```

---

## Task 5: Update headwater-api exports

**Files:**
- Modify: `headwater-api/src/headwater_api/classes/__init__.py`

No new tests needed — existing import tests will catch regressions.

**Step 1: Edit `__init__.py`**

Remove:
```python
from headwater_api.classes.embeddings_classes.embedding_models import (
    load_embedding_models,
    get_model_prompt_spec,
    ModelPromptSpec,
)
```

Add:
```python
from headwater_api.classes.embeddings_classes.embedding_provider import EmbeddingProvider
from headwater_api.classes.embeddings_classes.embedding_model_spec import EmbeddingModelSpec
```

Update `__all__`: remove `"load_embedding_models"`, `"get_model_prompt_spec"`, `"ModelPromptSpec"`. Add `"EmbeddingProvider"`, `"EmbeddingModelSpec"`.

**Step 2: Verify imports work**

```bash
cd headwater-server
uv run python -c "from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add headwater-api/src/headwater_api/classes/__init__.py
git commit -m "feat: export EmbeddingModelSpec and EmbeddingProvider from headwater-api"
```

---

## Task 6: Registry JSON + CRUD layer

**Files:**
- Create: `headwater-server/src/headwater_server/services/embeddings_service/embedding_models.json`
- Create: `headwater-server/src/headwater_server/services/embeddings_service/embedding_modelspecs_crud.py`
- Create: `headwater-server/tests/services/embeddings_service/conftest.py`
- Create: `headwater-server/tests/services/embeddings_service/test_embedding_modelspecs_crud.py`

### Step 1: Create the registry JSON

```json
{
    "huggingface": [
        "BAAI/bge-m3",
        "BAAI/bge-base-en-v1.5",
        "Snowflake/snowflake-arctic-embed-l",
        "Alibaba-NLP/gte-large-en-v1.5",
        "sentence-transformers/all-mpnet-base-v2",
        "sentence-transformers/all-MiniLM-L6-v2",
        "nomic-ai/nomic-embed-text-v1.5",
        "intfloat/e5-large-v2",
        "google/embeddinggemma-300m"
    ],
    "openai": [],
    "cohere": [],
    "jina": []
}
```

Save to `headwater-server/src/headwater_server/services/embeddings_service/embedding_models.json`.

### Step 2: Create test conftest with TinyDB fixtures

```python
# tests/services/embeddings_service/conftest.py
from __future__ import annotations
import json
import pytest
from tinydb import TinyDB


REGISTRY_DATA = {
    "huggingface": ["BAAI/bge-m3", "BAAI/bge-base-en-v1.5"],
    "openai": [],
    "cohere": [],
    "jina": [],
}


@pytest.fixture
def registry_path(tmp_path):
    path = tmp_path / "embedding_models.json"
    path.write_text(json.dumps(REGISTRY_DATA))
    return path


@pytest.fixture
def tmp_db(tmp_path):
    return TinyDB(tmp_path / "embedding_modelspecs.json")


@pytest.fixture
def patched_store(monkeypatch, registry_path, tmp_db):
    import headwater_server.services.embeddings_service.embedding_modelspecs_crud as crud
    import headwater_server.services.embeddings_service.embedding_model_store as store_mod
    monkeypatch.setattr(crud, "db", tmp_db)
    monkeypatch.setattr(store_mod, "_REGISTRY_PATH", registry_path)
```

### Step 3: Write CRUD tests

```python
# tests/services/embeddings_service/test_embedding_modelspecs_crud.py
from __future__ import annotations
import pytest
from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider
from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
    add_embedding_spec,
    get_all_embedding_specs,
    get_embedding_spec_by_name,
    get_all_spec_model_names,
    delete_embedding_spec,
    in_db,
)


def _make_spec(model="BAAI/bge-m3") -> EmbeddingModelSpec:
    return EmbeddingModelSpec(
        model=model,
        provider=EmbeddingProvider.HUGGINGFACE,
        description="Test model.",
        embedding_dim=768,
        max_seq_length=512,
        multilingual=False,
        parameter_count="110m",
        prompt_required=False,
        valid_prefixes=None,
        prompt_unsupported=False,
        task_map=None,
    )


def test_add_and_retrieve(patched_store):
    spec = _make_spec()
    add_embedding_spec(spec)
    result = get_embedding_spec_by_name("BAAI/bge-m3")
    assert result.model == "BAAI/bge-m3"
    assert result.embedding_dim == 768


def test_get_missing_raises(patched_store):
    with pytest.raises(ValueError, match="not found"):
        get_embedding_spec_by_name("nonexistent/model")


def test_in_db(patched_store):
    assert not in_db("BAAI/bge-m3")
    add_embedding_spec(_make_spec())
    assert in_db("BAAI/bge-m3")


def test_delete(patched_store):
    add_embedding_spec(_make_spec())
    delete_embedding_spec("BAAI/bge-m3")
    assert not in_db("BAAI/bge-m3")


def test_delete_missing_is_noop(patched_store):
    delete_embedding_spec("nonexistent/model")  # must not raise
```

### Step 4: Run tests to verify they fail

```bash
uv run pytest tests/services/embeddings_service/test_embedding_modelspecs_crud.py -v
```

Expected: `ImportError` — CRUD module does not exist yet

### Step 5: Implement CRUD module

```python
# src/headwater_server/services/embeddings_service/embedding_modelspecs_crud.py
from __future__ import annotations
from pathlib import Path
from tinydb import TinyDB, Query
from headwater_api.classes import EmbeddingModelSpec

_dir = Path(__file__).parent
db = TinyDB(_dir / "embedding_modelspecs.json")


def add_embedding_spec(spec: EmbeddingModelSpec) -> None:
    db.insert(spec.model_dump())


def get_all_embedding_specs() -> list[EmbeddingModelSpec]:
    return [EmbeddingModelSpec(**item) for item in db.all()]


def get_embedding_spec_by_name(model: str) -> EmbeddingModelSpec:
    q = Query()
    results = db.search(q.model == model)
    if not results:
        raise ValueError(f"EmbeddingModelSpec for '{model}' not found.")
    return EmbeddingModelSpec(**results[0])


def get_all_spec_model_names() -> list[str]:
    return [item["model"] for item in db.all()]


def delete_embedding_spec(model: str) -> None:
    q = Query()
    db.remove(q.model == model)


def in_db(model: str) -> bool:
    q = Query()
    return bool(db.search(q.model == model))


def wipe_and_repopulate(specs: list[EmbeddingModelSpec]) -> None:
    db.truncate()
    for spec in specs:
        db.insert(spec.model_dump())
```

### Step 6: Run tests to verify they pass

```bash
uv run pytest tests/services/embeddings_service/test_embedding_modelspecs_crud.py -v
```

Expected: all PASSED

### Step 7: Commit

```bash
git add \
  headwater-server/src/headwater_server/services/embeddings_service/embedding_models.json \
  headwater-server/src/headwater_server/services/embeddings_service/embedding_modelspecs_crud.py \
  headwater-server/tests/services/embeddings_service/conftest.py \
  headwater-server/tests/services/embeddings_service/test_embedding_modelspecs_crud.py
git commit -m "feat: add registry JSON, CRUD layer, and test fixtures for embedding model specs"
```

---

## Task 7: EmbeddingModelStore — models() and list_models() (AC4, AC5)

Each AC gets its own TDD cycle within this task.

**Files:**
- Create: `headwater-server/src/headwater_server/services/embeddings_service/embedding_model_store.py`
- Create: `headwater-server/tests/services/embeddings_service/test_embedding_model_store.py`

### TDD Cycle A — AC4: models() returns provider-keyed dict

**Fulfills:** AC — `EmbeddingModelStore.models()` returns a dict whose keys are exactly the provider strings in `embedding_models.json`.

**Step 1: Write the failing test**

```python
# tests/services/embeddings_service/test_embedding_model_store.py
from __future__ import annotations
from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore


def test_models_returns_provider_keyed_dict(patched_store):
    result = EmbeddingModelStore.models()
    assert set(result.keys()) == {"huggingface", "openai", "cohere", "jina"}
    assert "BAAI/bge-m3" in result["huggingface"]
    assert result["openai"] == []
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_models_returns_provider_keyed_dict -v
```

Expected: `ImportError`

**Step 3: Implement EmbeddingModelStore.models()**

```python
# src/headwater_server/services/embeddings_service/embedding_model_store.py
from __future__ import annotations
import json
import itertools
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).parent / "embedding_models.json"


class EmbeddingModelStore:
    @classmethod
    def models(cls) -> dict[str, list[str]]:
        with open(_REGISTRY_PATH) as f:
            return json.load(f)
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_models_returns_provider_keyed_dict -v
```

Expected: PASSED

---

### TDD Cycle B — AC5: list_models() is flat, no duplicates, empty providers excluded

**Fulfills:** AC — `EmbeddingModelStore.list_models()` returns a flat list with no duplicates and no model IDs from empty provider lists.

**Step 1: Write the failing test**

```python
# append to test_embedding_model_store.py
def test_list_models_flat_no_duplicates(patched_store):
    result = EmbeddingModelStore.list_models()
    assert isinstance(result, list)
    assert len(result) == len(set(result))  # no duplicates
    assert "BAAI/bge-m3" in result
    assert "BAAI/bge-base-en-v1.5" in result
    # empty provider lists contribute nothing
    openai_count = sum(1 for m in result if "openai" in m.lower())
    assert openai_count == 0
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_list_models_flat_no_duplicates -v
```

Expected: `AttributeError` — `list_models` not defined

**Step 3: Implement list_models()**

```python
    @classmethod
    def list_models(cls) -> list[str]:
        return list(itertools.chain.from_iterable(cls.models().values()))
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_list_models_flat_no_duplicates -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add \
  headwater-server/src/headwater_server/services/embeddings_service/embedding_model_store.py \
  headwater-server/tests/services/embeddings_service/test_embedding_model_store.py
git commit -m "feat: add EmbeddingModelStore with models() and list_models()"
```

---

## Task 8: EmbeddingModelStore — identify_provider() (AC6, AC7)

**Files:**
- Modify: `headwater-server/src/headwater_server/services/embeddings_service/embedding_model_store.py`
- Modify: `headwater-server/tests/services/embeddings_service/test_embedding_model_store.py`

### TDD Cycle A — AC6: identify_provider returns correct provider

**Fulfills:** AC — `EmbeddingModelStore.identify_provider("BAAI/bge-m3")` returns `EmbeddingProvider.HUGGINGFACE`.

**Step 1: Write the failing test**

```python
# append to test_embedding_model_store.py
from headwater_api.classes import EmbeddingProvider


def test_identify_provider_found(patched_store):
    result = EmbeddingModelStore.identify_provider("BAAI/bge-m3")
    assert result == EmbeddingProvider.HUGGINGFACE
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_identify_provider_found -v
```

Expected: `AttributeError`

**Step 3: Implement identify_provider()**

```python
    @classmethod
    def identify_provider(cls, model: str) -> EmbeddingProvider:
        from headwater_api.classes import EmbeddingProvider
        matches = [
            provider for provider, model_list in cls.models().items()
            if model in model_list
        ]
        if len(matches) == 0:
            raise ValueError(f"Provider not found for model: '{model}'.")
        if len(matches) > 1:
            raise ValueError(
                f"Model '{model}' found under multiple providers: {matches}. Registry is malformed."
            )
        return EmbeddingProvider(matches[0])
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_identify_provider_found -v
```

Expected: PASSED

---

### TDD Cycle B — AC7: identify_provider raises for unknown model

**Fulfills:** AC — `EmbeddingModelStore.identify_provider("not-a-real-model")` raises `ValueError`.

**Step 1: Write the failing test**

```python
# append to test_embedding_model_store.py
import pytest


def test_identify_provider_not_found_raises(patched_store):
    with pytest.raises(ValueError, match="Provider not found"):
        EmbeddingModelStore.identify_provider("not-a-real-model")
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_identify_provider_not_found_raises -v
```

Expected: FAILED — no ValueError raised (method doesn't exist yet when test is first written; after cycle A it should raise correctly)

**Step 3: Verify implementation from Cycle A already satisfies this**

No new code. Run test.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_identify_provider_not_found_raises -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add \
  headwater-server/src/headwater_server/services/embeddings_service/embedding_model_store.py \
  headwater-server/tests/services/embeddings_service/test_embedding_model_store.py
git commit -m "feat: add EmbeddingModelStore.identify_provider()"
```

---

## Task 9: EmbeddingModelStore — get_spec() (AC8, AC9, AC10)

**Files:**
- Modify: `headwater-server/src/headwater_server/services/embeddings_service/embedding_model_store.py`
- Modify: `headwater-server/tests/services/embeddings_service/test_embedding_model_store.py`

### TDD Cycle A — AC8: get_spec() raises before TinyDB lookup when model not in registry

**Fulfills:** AC — `EmbeddingModelStore.get_spec("not-a-real-model")` raises `ValueError` before performing any TinyDB lookup (verify with a mock that asserts TinyDB is never called).

**Step 1: Write the failing test**

```python
# append to test_embedding_model_store.py
from unittest.mock import patch


def test_get_spec_unregistered_raises_before_db(patched_store):
    with patch(
        "headwater_server.services.embeddings_service.embedding_modelspecs_crud.in_db"
    ) as mock_in_db:
        with pytest.raises(ValueError, match="not in the embedding model registry"):
            EmbeddingModelStore.get_spec("not-a-real-model")
        mock_in_db.assert_not_called()
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_get_spec_unregistered_raises_before_db -v
```

Expected: `AttributeError`

**Step 3: Implement get_spec() with registry-first guard**

```python
    @classmethod
    def is_supported(cls, model: str) -> bool:
        return model in cls.list_models()

    @classmethod
    def get_spec(cls, model: str) -> EmbeddingModelSpec:
        from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
            get_embedding_spec_by_name,
            in_db,
        )
        if not cls.is_supported(model):
            raise ValueError(
                f"Model '{model}' is not in the embedding model registry."
            )
        if not in_db(model):
            raise ValueError(
                f"Model '{model}' has no spec record — run update_embedding_modelstore."
            )
        return get_embedding_spec_by_name(model)
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_get_spec_unregistered_raises_before_db -v
```

Expected: PASSED

---

### TDD Cycle B — AC9: get_spec() raises when model is in registry but TinyDB is empty

**Fulfills:** AC — `EmbeddingModelStore.get_spec("BAAI/bge-m3")` raises `ValueError` when model is in registry but TinyDB is empty.

**Step 1: Write the failing test**

```python
def test_get_spec_registered_but_no_db_record_raises(patched_store):
    with pytest.raises(ValueError, match="run update_embedding_modelstore"):
        EmbeddingModelStore.get_spec("BAAI/bge-m3")
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_get_spec_registered_but_no_db_record_raises -v
```

Expected: FAILED

**Step 3: Already implemented in Cycle A — verify**

No new code needed. Run test.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_get_spec_registered_but_no_db_record_raises -v
```

Expected: PASSED

---

### TDD Cycle C — AC10: get_spec() returns valid spec when TinyDB is populated

**Fulfills:** AC — `EmbeddingModelStore.get_spec("BAAI/bge-m3")` returns a valid `EmbeddingModelSpec` when TinyDB is populated.

**Step 1: Write the failing test**

```python
from headwater_server.services.embeddings_service.embedding_modelspecs_crud import add_embedding_spec
from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider


def _make_spec(model="BAAI/bge-m3") -> EmbeddingModelSpec:
    return EmbeddingModelSpec(
        model=model, provider=EmbeddingProvider.HUGGINGFACE,
        description="A multilingual embedding model.", embedding_dim=1024,
        max_seq_length=8192, multilingual=True, parameter_count="568m",
        prompt_required=False, valid_prefixes=None,
        prompt_unsupported=False, task_map=None,
    )


def test_get_spec_returns_spec_when_populated(patched_store):
    add_embedding_spec(_make_spec())
    result = EmbeddingModelStore.get_spec("BAAI/bge-m3")
    assert isinstance(result, EmbeddingModelSpec)
    assert result.model == "BAAI/bge-m3"
    assert result.embedding_dim == 1024
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_get_spec_returns_spec_when_populated -v
```

Expected: FAILED (DB is empty)

**Step 3: No new code — test verifies existing implementation with populated DB**

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_get_spec_returns_spec_when_populated -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add \
  headwater-server/src/headwater_server/services/embeddings_service/embedding_model_store.py \
  headwater-server/tests/services/embeddings_service/test_embedding_model_store.py
git commit -m "feat: add EmbeddingModelStore.get_spec() with registry-first guard"
```

---

## Task 10: EmbeddingModelStore — get_all_specs() and by_provider() (AC11)

**Fulfills:** AC — `EmbeddingModelStore.by_provider(EmbeddingProvider.OPENAI)` returns `[]` when no OpenAI models are registered.

**Files:**
- Modify: `headwater-server/src/headwater_server/services/embeddings_service/embedding_model_store.py`
- Modify: `headwater-server/tests/services/embeddings_service/test_embedding_model_store.py`

### TDD Cycle — by_provider returns empty list for unpopulated provider

**Step 1: Write the failing test**

```python
def test_by_provider_empty_when_none_registered(patched_store):
    result = EmbeddingModelStore.by_provider(EmbeddingProvider.OPENAI)
    assert result == []
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_by_provider_empty_when_none_registered -v
```

Expected: `AttributeError`

**Step 3: Implement get_all_specs() and by_provider()**

```python
    @classmethod
    def get_all_specs(cls) -> list[EmbeddingModelSpec]:
        from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
            get_all_embedding_specs,
        )
        return get_all_embedding_specs()

    @classmethod
    def by_provider(cls, provider: EmbeddingProvider) -> list[EmbeddingModelSpec]:
        return [s for s in cls.get_all_specs() if s.provider == provider]
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_by_provider_empty_when_none_registered -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add \
  headwater-server/src/headwater_server/services/embeddings_service/embedding_model_store.py \
  headwater-server/tests/services/embeddings_service/test_embedding_model_store.py
git commit -m "feat: add EmbeddingModelStore.get_all_specs() and by_provider()"
```

---

## Task 11: EmbeddingModelStore — _is_consistent() and update() (AC12, AC13, AC14)

**Files:**
- Modify: `headwater-server/src/headwater_server/services/embeddings_service/embedding_model_store.py`
- Modify: `headwater-server/tests/services/embeddings_service/test_embedding_model_store.py`

### TDD Cycle A — AC12: update() adds new model without overwriting existing records

**Fulfills:** AC — `update()` with one new model in the registry (not in TinyDB) adds it without modifying existing records (assert A's record is byte-identical before and after).

**Step 1: Write the failing test**

```python
import json


def test_update_adds_new_model_without_overwriting(patched_store, monkeypatch):
    # Pre-populate A
    add_embedding_spec(_make_spec("BAAI/bge-m3"))
    original_dump = EmbeddingModelStore.get_spec("BAAI/bge-m3").model_dump()

    # Mock research to return a valid spec for the new model
    new_spec = _make_spec("BAAI/bge-base-en-v1.5")
    monkeypatch.setattr(
        "headwater_server.services.embeddings_service.embedding_model_store.create_embedding_spec",
        lambda model, provider: add_embedding_spec(new_spec),
    )

    EmbeddingModelStore.update()

    # A is unchanged
    after_dump = EmbeddingModelStore.get_spec("BAAI/bge-m3").model_dump()
    assert original_dump == after_dump

    # B was added
    result = EmbeddingModelStore.get_spec("BAAI/bge-base-en-v1.5")
    assert result.model == "BAAI/bge-base-en-v1.5"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_update_adds_new_model_without_overwriting -v
```

Expected: `AttributeError` — update not defined

**Step 3: Implement _is_consistent() and update()/_update_models()**

```python
    @classmethod
    def _is_consistent(cls) -> bool:
        from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
            get_all_spec_model_names,
        )
        registry_names = set(cls.list_models())
        db_names = set(get_all_spec_model_names())
        # Check for duplicate model IDs across providers
        all_entries = list(itertools.chain.from_iterable(cls.models().values()))
        if len(all_entries) != len(set(all_entries)):
            logger.warning("Duplicate model IDs detected in registry.")
            return False
        return registry_names == db_names

    @classmethod
    def update(cls) -> None:
        if not cls._is_consistent():
            logger.info("Embedding model specs inconsistent with registry. Updating...")
            cls._update_models()
        else:
            logger.info("Embedding model specs consistent. No update needed.")

    @classmethod
    def _update_models(cls) -> None:
        from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
            get_all_spec_model_names,
            delete_embedding_spec,
        )
        from headwater_server.services.embeddings_service.research_embedding_models import (
            create_embedding_spec,
        )
        registry_names = set(cls.list_models())
        db_names = set(get_all_spec_model_names())

        to_add = registry_names - db_names
        to_delete = db_names - registry_names

        logger.info(f"Models to add: {len(to_add)}, to delete: {len(to_delete)}")

        for model in to_delete:
            delete_embedding_spec(model)
            logger.info(f"Deleted orphaned spec for {model}")

        for model in to_add:
            provider = cls.identify_provider(model)
            create_embedding_spec(model, provider)
            logger.info(f"Created spec for {model} ({provider})")

        if not cls._is_consistent():
            raise ValueError("Specs still inconsistent after update().")
```

**Note:** `research_embedding_models` doesn't exist yet — the test monkeypatches `create_embedding_spec` so this won't fail due to the missing module during testing.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_update_adds_new_model_without_overwriting -v
```

Expected: PASSED

---

### TDD Cycle B — AC13: update() deletes orphaned records

**Fulfills:** AC — `update()` with one model removed from the registry (still in TinyDB) deletes its record.

**Step 1: Write the failing test**

```python
def test_update_deletes_orphaned_spec(patched_store, monkeypatch):
    # Populate both A and B in DB, but registry only has A and B (from conftest)
    # Inject a fake extra record for a model not in registry
    from headwater_server.services.embeddings_service.embedding_modelspecs_crud import add_embedding_spec, in_db
    orphan = _make_spec("orphaned/model-v1")
    # Directly insert without registry check (CRUD doesn't validate)
    add_embedding_spec(orphan)
    assert in_db("orphaned/model-v1")

    monkeypatch.setattr(
        "headwater_server.services.embeddings_service.embedding_model_store.create_embedding_spec",
        lambda model, provider: add_embedding_spec(_make_spec(model)),
    )

    EmbeddingModelStore.update()
    assert not in_db("orphaned/model-v1")
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_update_deletes_orphaned_spec -v
```

Expected: FAILED

**Step 3: Implementation already done in Cycle A — run test**

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_update_deletes_orphaned_spec -v
```

Expected: PASSED

---

### TDD Cycle C — AC14: _is_consistent() returns True after update()

**Fulfills:** AC — After any `update()` call that does not raise, `_is_consistent()` returns `True`.

**Step 1: Write the failing test**

```python
def test_is_consistent_after_update(patched_store, monkeypatch):
    monkeypatch.setattr(
        "headwater_server.services.embeddings_service.embedding_model_store.create_embedding_spec",
        lambda model, provider: add_embedding_spec(_make_spec(model)),
    )
    EmbeddingModelStore.update()
    assert EmbeddingModelStore._is_consistent()
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_is_consistent_after_update -v
```

Expected: FAILED

**Step 3: Implementation already done — run test**

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_store.py::test_is_consistent_after_update -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add \
  headwater-server/src/headwater_server/services/embeddings_service/embedding_model_store.py \
  headwater-server/tests/services/embeddings_service/test_embedding_model_store.py
git commit -m "feat: add EmbeddingModelStore._is_consistent() and update()"
```

---

## Task 12: research_embedding_models.py (AC15)

**Fulfills:** AC — `update()` with Perplexity mocked to raise `ConnectionError` raises and does not write any new TinyDB records.

**Files:**
- Create: `headwater-server/src/headwater_server/services/embeddings_service/research_embedding_models.py`
- Create: `headwater-server/tests/services/embeddings_service/test_research_embedding_models.py`

### TDD Cycle — Perplexity failure halts update() with no partial writes

**Step 1: Write the failing test**

```python
# tests/services/embeddings_service/test_research_embedding_models.py
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from headwater_server.services.embeddings_service.embedding_modelspecs_crud import in_db


def test_perplexity_failure_halts_no_partial_writes(patched_store, monkeypatch):
    # Registry has BAAI/bge-m3 and BAAI/bge-base-en-v1.5; DB is empty
    with patch(
        "headwater_server.services.embeddings_service.research_embedding_models.Conduit"
    ) as mock_conduit_cls:
        mock_conduit_cls.return_value.run.side_effect = ConnectionError("Perplexity unreachable")

        from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore
        with pytest.raises(ConnectionError):
            EmbeddingModelStore.update()

    # No records should have been written
    assert not in_db("BAAI/bge-m3")
    assert not in_db("BAAI/bge-base-en-v1.5")
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_research_embedding_models.py -v
```

Expected: `ImportError` — module doesn't exist

**Step 3: Implement research_embedding_models.py**

```python
# src/headwater_server/services/embeddings_service/research_embedding_models.py
from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from conduit.sync import Conduit, GenerationParams, ConduitOptions, Verbosity
from conduit.core.prompt.prompt import Prompt
from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_RESEARCH_PROMPT = """
You are an assistant providing factual technical specifications for embedding models.

<provider>
{{ provider }}
</provider>

<model>
{{ model }}
</model>

Return an EmbeddingModelSpec object with accurate values for the following informational fields:
- description (50-80 words, factual, no promotional language)
- embedding_dim (integer output vector size, or null if unknown)
- max_seq_length (integer max input tokens, or null if unknown)
- multilingual (true if model supports non-English text)
- parameter_count (string like "110m", "7b", or null if unknown)

Set these fields exactly as follows — do not change them:
- prompt_required: false
- valid_prefixes: null
- prompt_unsupported: false
- task_map: null
- model: {{ model }}
- provider: {{ provider }}
""".strip()


def get_embedding_spec(model: str, provider: EmbeddingProvider) -> EmbeddingModelSpec:
    params = GenerationParams(
        model="sonar-pro",
        response_model=EmbeddingModelSpec,
        output_type="structured_response",
    )
    prompt = Prompt(_RESEARCH_PROMPT)
    options = ConduitOptions(project_name="headwater", verbosity=Verbosity.PROGRESS)
    conduit = Conduit(prompt=prompt, params=params, options=options)
    response = conduit.run(input_variables={"model": model, "provider": provider.value})
    spec: EmbeddingModelSpec = response.last.parsed
    # Always override model field with the requested name — never trust Perplexity's output
    spec = EmbeddingModelSpec(**{**spec.model_dump(), "model": model, "provider": provider})
    return spec


def create_embedding_spec(model: str, provider: EmbeddingProvider) -> None:
    from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
        add_embedding_spec,
        in_db,
    )
    if in_db(model):
        logger.warning(f"Spec for '{model}' already in DB — skipping.")
        return
    logger.info(f"Researching spec for {model} ({provider})...")
    spec = get_embedding_spec(model, provider)
    add_embedding_spec(spec)
    logger.info(f"Spec for {model} written to DB.")
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_research_embedding_models.py -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add \
  headwater-server/src/headwater_server/services/embeddings_service/research_embedding_models.py \
  headwater-server/tests/services/embeddings_service/test_research_embedding_models.py
git commit -m "feat: add research_embedding_models.py with Perplexity-powered spec generation"
```

---

## Task 13: CLI script and pyproject.toml entry

**Files:**
- Create: `headwater-server/src/headwater_server/scripts/update_embedding_modelstore.py`
- Modify: `headwater-server/pyproject.toml`

**Step 1: Create the script**

```python
# src/headwater_server/scripts/update_embedding_modelstore.py
from __future__ import annotations
import sys


def main() -> None:
    from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore
    store = EmbeddingModelStore()
    if not EmbeddingModelStore._is_consistent():
        print("Embedding model specs are not consistent with registry. Updating...")
        try:
            EmbeddingModelStore.update()
            print("Update complete.")
        except Exception as e:
            print(f"Update failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Embedding model specs are consistent. No update needed.")


if __name__ == "__main__":
    main()
```

**Step 2: Register in pyproject.toml**

Add to `[project.scripts]`:

```toml
update-embedding-modelstore = "headwater_server.scripts.update_embedding_modelstore:main"
```

**Step 3: Verify the entrypoint is importable**

```bash
cd headwater-server
uv run python -c "from headwater_server.scripts.update_embedding_modelstore import main; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add \
  headwater-server/src/headwater_server/scripts/update_embedding_modelstore.py \
  headwater-server/pyproject.toml
git commit -m "feat: add update_embedding_modelstore CLI script and pyproject entry"
```

---

## Task 14: Startup consistency check

**Files:**
- Modify: `headwater-server/src/headwater_server/server/headwater.py`

**Step 1: Add consistency check to lifespan**

In `_create_app`, update the lifespan context manager:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Headwater Server starting up...")
    from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore
    if not EmbeddingModelStore._is_consistent():
        logger.warning(
            "Embedding model specs are inconsistent with registry — run update_embedding_modelstore.",
            extra={
                "models_in_registry": len(EmbeddingModelStore.list_models()),
                "models_in_db": len(EmbeddingModelStore.get_all_specs()),
            },
        )
    yield
    # Shutdown
    logger.info("Headwater Server shutting down...")
```

**Step 2: Verify server still starts**

```bash
cd headwater-server
uv run python -c "from headwater_server.server.headwater import app; print('OK')"
```

Expected: `OK` (may log a warning about inconsistency — that is correct behaviour if TinyDB is empty)

**Step 3: Commit**

```bash
git add headwater-server/src/headwater_server/server/headwater.py
git commit -m "feat: add embedding model spec consistency check to server startup"
```

---

## Task 15: Migrate embedding_model.py

**Files:**
- Modify: `headwater-server/src/headwater_server/services/embeddings_service/embedding_model.py`

Replace `load_embedding_models()` with `EmbeddingModelStore.list_models()`.

**Step 1: Edit embedding_model.py**

Replace:
```python
from headwater_api.classes import ChromaBatch, load_embedding_models
```
With:
```python
from headwater_api.classes import ChromaBatch
from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore
```

Replace in `models()`:
```python
return load_embedding_models()
```
With:
```python
return EmbeddingModelStore.list_models()
```

**Step 2: Verify import**

```bash
uv run python -c "from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add headwater-server/src/headwater_server/services/embeddings_service/embedding_model.py
git commit -m "refactor: embedding_model.py uses EmbeddingModelStore.list_models()"
```

---

## Task 16: Migrate generate_embeddings_service.py (AC19)

**Fulfills:** AC — `generate_embeddings_service` calls `EmbeddingModelStore.get_spec()` and not `get_model_prompt_spec()` (verified by mock assertion).

**Files:**
- Modify: `headwater-server/src/headwater_server/services/embeddings_service/generate_embeddings_service.py`
- Modify: `headwater-server/tests/services/embeddings_service/test_embedding_model_prompt.py` (or create a new focused test)

### TDD Cycle — generate_embeddings_service uses EmbeddingModelStore

**Step 1: Write the failing test**

```python
# tests/services/embeddings_service/test_generate_embeddings_service_store.py
from __future__ import annotations
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider, ChromaBatch, EmbeddingsRequest


def test_generate_embeddings_calls_get_spec_not_old_function(patched_store, monkeypatch):
    # Ensure get_model_prompt_spec is not called anywhere in the call chain
    with patch(
        "headwater_server.services.embeddings_service.generate_embeddings_service.EmbeddingModelStore.get_spec"
    ) as mock_get_spec, patch(
        "headwater_server.services.embeddings_service.generate_embeddings_service.EmbeddingModel"
    ) as mock_model_cls:
        mock_spec = MagicMock(spec=EmbeddingModelSpec)
        mock_spec.task_map = {"query": "query: "}
        mock_spec.prompt_unsupported = False
        mock_spec.prompt_required = False
        mock_get_spec.return_value = mock_spec

        mock_instance = MagicMock()
        mock_instance.generate_embeddings.return_value = ChromaBatch(
            ids=["1"], documents=["test"], embeddings=[[0.1, 0.2]]
        )
        mock_model_cls.return_value = mock_instance

        import asyncio
        from headwater_server.services.embeddings_service.generate_embeddings_service import (
            generate_embeddings_service,
        )
        request = EmbeddingsRequest(
            model="nomic-ai/nomic-embed-text-v1.5",
            batch=ChromaBatch(ids=["1"], documents=["hello"]),
            task=None,
            prompt=None,
        )
        asyncio.run(generate_embeddings_service(request))
        mock_get_spec.assert_called_once_with("nomic-ai/nomic-embed-text-v1.5")
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_generate_embeddings_service_store.py -v
```

Expected: FAILED — service imports `get_model_prompt_spec`, not `EmbeddingModelStore`

**Step 3: Update generate_embeddings_service.py**

```python
# src/headwater_server/services/embeddings_service/generate_embeddings_service.py
from __future__ import annotations
import logging
from headwater_api.classes import EmbeddingsRequest, EmbeddingsResponse
from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel
from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore

logger = logging.getLogger(__name__)


async def generate_embeddings_service(request: EmbeddingsRequest) -> EmbeddingsResponse:
    from headwater_api.classes import ChromaBatch

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
        spec = EmbeddingModelStore.get_spec(model)
        prompt = spec.task_map[request.task.value]

    embedding_model = EmbeddingModel(model)
    new_batch: ChromaBatch = embedding_model.generate_embeddings(batch, prompt=prompt)
    return EmbeddingsResponse(embeddings=new_batch.embeddings)
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_generate_embeddings_service_store.py -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add \
  headwater-server/src/headwater_server/services/embeddings_service/generate_embeddings_service.py \
  headwater-server/tests/services/embeddings_service/test_generate_embeddings_service_store.py
git commit -m "refactor: generate_embeddings_service uses EmbeddingModelStore.get_spec()"
```

---

## Task 17: Migrate list_embedding_models_service.py

**Files:**
- Modify: `headwater-server/src/headwater_server/services/embeddings_service/list_embedding_models_service.py`

**Step 1: Update the service**

```python
# src/headwater_server/services/embeddings_service/list_embedding_models_service.py
from __future__ import annotations
import logging
from headwater_api.classes import EmbeddingModelSpec
from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore

logger = logging.getLogger(__name__)


async def list_embedding_models_service() -> list[EmbeddingModelSpec]:
    logger.info("Listing available embedding model specs.")
    return EmbeddingModelStore.get_all_specs()
```

**Step 2: Verify import**

```bash
uv run python -c "from headwater_server.services.embeddings_service.list_embedding_models_service import list_embedding_models_service; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add headwater-server/src/headwater_server/services/embeddings_service/list_embedding_models_service.py
git commit -m "refactor: list_embedding_models_service returns list[EmbeddingModelSpec] from store"
```

---

## Task 18: Migrate requests.py — remove file I/O from validators (AC18)

**Fulfills:** AC — `EmbeddingsRequest` model validator constructs successfully without any filesystem access (verified by patching `builtins.open` and asserting it is not called during validation).

**Files:**
- Modify: `headwater-api/src/headwater_api/classes/embeddings_classes/requests.py`
- Create: `headwater-server/tests/services/embeddings_service/test_request_no_file_io.py`

### TDD Cycle — EmbeddingsRequest validation performs no file I/O

**Step 1: Write the failing test**

```python
# tests/services/embeddings_service/test_request_no_file_io.py
from __future__ import annotations
from unittest.mock import patch, MagicMock
from headwater_api.classes import EmbeddingsRequest, ChromaBatch


def test_embeddings_request_no_file_io():
    mock_open = MagicMock(side_effect=AssertionError("File I/O must not occur during validation"))
    with patch("builtins.open", mock_open):
        # Should construct without touching any file
        req = EmbeddingsRequest(
            model="some-model/v1",
            batch=ChromaBatch(ids=["1"], documents=["hello"]),
            task=None,
            prompt=None,
        )
    assert req.model == "some-model/v1"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_request_no_file_io.py -v
```

Expected: FAILED — `AssertionError: File I/O must not occur during validation`

**Step 3: Strip file I/O from both validators in requests.py**

The `@model_validator` in `EmbeddingsRequest` and `QuickEmbeddingRequest` currently calls `load_embedding_models()` and `get_model_prompt_spec()`. Replace each validator body with only the mutual-exclusion check:

```python
# EmbeddingsRequest._validate_prompt_fields
@model_validator(mode="after")
def _validate_prompt_fields(self) -> EmbeddingsRequest:
    if self.task is not None and self.prompt is not None:
        raise ValueError("Provide 'task' or 'prompt', not both.")
    return self
```

Apply the same reduction to `QuickEmbeddingRequest._validate_prompt_fields`.

Remove the imports of `load_embedding_models` and `get_model_prompt_spec` from the file entirely.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_request_no_file_io.py -v
```

Expected: PASSED

**Step 5: Run the full embeddings test suite to check for regressions**

```bash
uv run pytest tests/services/embeddings_service/ -v
```

Expected: all PASSED (existing prompt validation tests that relied on the old file-backed validator may now fail — delete or rewrite any that tested file-backed behaviour)

**Step 6: Commit**

```bash
git add \
  headwater-api/src/headwater_api/classes/embeddings_classes/requests.py \
  headwater-server/tests/services/embeddings_service/test_request_no_file_io.py
git commit -m "refactor: remove file I/O from EmbeddingsRequest and QuickEmbeddingRequest validators"
```

---

## Task 19: Update API endpoint (AC16, AC17)

Each AC gets its own TDD cycle.

**Files:**
- Modify: `headwater-server/src/headwater_server/api/embeddings_server_api.py`

### TDD Cycle A — AC16: GET /conduit/embeddings/models returns HTTP 200

**Fulfills:** AC — `GET /conduit/embeddings/models` returns HTTP 200 with a JSON array.

**Step 1: Write the failing test**

```python
# tests/api/test_embedding_models_endpoint.py
from __future__ import annotations
from unittest.mock import patch
from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider


def _sample_spec() -> EmbeddingModelSpec:
    return EmbeddingModelSpec(
        model="BAAI/bge-m3", provider=EmbeddingProvider.HUGGINGFACE,
        description="Test.", embedding_dim=1024, max_seq_length=8192,
        multilingual=True, parameter_count="568m",
        prompt_required=False, valid_prefixes=None,
        prompt_unsupported=False, task_map=None,
    )


def test_list_embedding_models_returns_200(client):
    with patch(
        "headwater_server.services.embeddings_service.list_embedding_models_service.EmbeddingModelStore.get_all_specs",
        return_value=[_sample_spec()],
    ):
        response = client.get("/conduit/embeddings/models")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/api/test_embedding_models_endpoint.py::test_list_embedding_models_returns_200 -v
```

Expected: FAILED — response model mismatch (endpoint returns `list[str]`, service now returns `list[EmbeddingModelSpec]`)

**Step 3: Update embeddings_server_api.py response model**

```python
# in embeddings_server_api.py, update the GET /conduit/embeddings/models route:
from headwater_api.classes import EmbeddingModelSpec

@self.app.get("/conduit/embeddings/models", response_model=list[EmbeddingModelSpec])
async def list_embedding_models() -> list[EmbeddingModelSpec]:
    from headwater_server.services.embeddings_service.list_embedding_models_service import (
        list_embedding_models_service,
    )
    return await list_embedding_models_service()
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/api/test_embedding_models_endpoint.py::test_list_embedding_models_returns_200 -v
```

Expected: PASSED

---

### TDD Cycle B — AC17: each element deserializes into valid EmbeddingModelSpec

**Fulfills:** AC — Each element of the array deserializes into a valid `EmbeddingModelSpec` with all fields present including `None`-valued optionals.

**Step 1: Write the failing test**

```python
# append to tests/api/test_embedding_models_endpoint.py
def test_list_embedding_models_elements_are_valid_specs(client):
    with patch(
        "headwater_server.services.embeddings_service.list_embedding_models_service.EmbeddingModelStore.get_all_specs",
        return_value=[_sample_spec()],
    ):
        response = client.get("/conduit/embeddings/models")
    data = response.json()
    assert len(data) == 1
    spec = EmbeddingModelSpec.model_validate(data[0])
    assert spec.model == "BAAI/bge-m3"
    assert spec.embedding_dim == 1024
    # Verify None-valued optionals are present in response body
    assert "description" in data[0]
    assert "task_map" in data[0]
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/api/test_embedding_models_endpoint.py::test_list_embedding_models_elements_are_valid_specs -v
```

Expected: FAILED

**Step 3: No new code — this tests existing implementation**

If the test fails due to None fields being excluded from the response, add to `EmbeddingModelSpec`:

```python
model_config = {"populate_by_name": True}
```

And ensure the FastAPI route does not use `response_model_exclude_none=True`.

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/api/test_embedding_models_endpoint.py -v
```

Expected: all PASSED

**Step 5: Commit**

```bash
git add \
  headwater-server/src/headwater_server/api/embeddings_server_api.py \
  headwater-server/tests/api/test_embedding_models_endpoint.py
git commit -m "feat: update /conduit/embeddings/models to return list[EmbeddingModelSpec]"
```

---

## Task 20: Delete old files and verify migration (AC20)

**Fulfills:** AC — `ModelPromptSpec`, `load_embedding_models()`, `get_model_prompt_spec()` do not appear anywhere in the codebase (verified by `grep`).

**Files:**
- Delete: `headwater-api/src/headwater_api/classes/embeddings_classes/embedding_models.py`
- Delete: `headwater-api/src/headwater_api/classes/embeddings_classes/embedding_models.json`

### TDD Cycle — deleted symbols are absent from codebase

**Step 1: Write the "test" — a grep assertion**

```bash
# This is the test. Run it and expect zero results.
grep -r "ModelPromptSpec\|load_embedding_models\|get_model_prompt_spec" \
  headwater-api/src headwater-server/src headwater-server/tests \
  --include="*.py"
```

**Step 2: Run to verify it currently fails (symbols still exist)**

```bash
grep -r "ModelPromptSpec\|load_embedding_models\|get_model_prompt_spec" \
  headwater-api/src headwater-server/src headwater-server/tests \
  --include="*.py"
```

Expected: several matches in `embedding_models.py` and `__init__.py`

**Step 3: Delete the old files**

```bash
rm headwater-api/src/headwater_api/classes/embeddings_classes/embedding_models.py
rm headwater-api/src/headwater_api/classes/embeddings_classes/embedding_models.json
```

Also delete any existing test files that tested the old `ModelPromptSpec` directly (they are now invalid):

```bash
# Identify then delete
grep -rl "ModelPromptSpec\|load_embedding_models\|get_model_prompt_spec" \
  headwater-server/tests --include="*.py"
# Review the list, then delete each file found
```

**Step 4: Re-run grep to verify symbols are gone**

```bash
grep -r "ModelPromptSpec\|load_embedding_models\|get_model_prompt_spec" \
  headwater-api/src headwater-server/src headwater-server/tests \
  --include="*.py"
```

Expected: zero output

**Step 5: Run full test suite**

```bash
cd headwater-server
uv run pytest tests/ -v
```

Expected: all PASSED with no import errors

**Step 6: Commit**

```bash
git add -A
git commit -m "chore: delete ModelPromptSpec, load_embedding_models, get_model_prompt_spec — migration complete"
```

---

## Final verification

Run the complete test suite one more time:

```bash
cd headwater-server
uv run pytest tests/ -v --tb=short
```

Confirm:
- All tests pass
- No references to `ModelPromptSpec`, `load_embedding_models`, or `get_model_prompt_spec` remain
- Server starts: `uv run python -c "from headwater_server.server.headwater import app; print('OK')"`
