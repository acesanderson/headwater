# EmbeddingModelSpec Design

## 1. Goal

Replace the ad-hoc `ModelPromptSpec` dataclass and merged `embedding_models.json` with a structured `EmbeddingModelSpec` (Pydantic) + `EmbeddingModelStore` pattern that mirrors conduit's `ModelSpec`/`ModelStore`. The model registry and spec store live in headwater-server; `EmbeddingModelSpec` and `EmbeddingProvider` live in headwater-api as shared data contracts. Clients access model information via API, not local file I/O.

---

## 2. Constraints and Non-Goals

**In scope:**
- Define `EmbeddingProvider` (str enum) in headwater-api
- Define `EmbeddingModelSpec` (Pydantic) in headwater-api, replacing `ModelPromptSpec` (dataclass)
- Move `embedding_models.json` (provider-keyed registry, model names only) to headwater-server
- Add `embedding_modelspecs.json` (TinyDB) to headwater-server for persisted specs
- Implement `EmbeddingModelStore` in headwater-server (classmethod manager)
- Implement `research_embedding_models.py` in headwater-server (Perplexity populates informational fields only; prompt behavioral fields stubbed to safe defaults)
- Add `update_embedding_modelstore.py` CLI script in headwater-server
- Update headwater-server's embeddings service to read from `EmbeddingModelStore`
- Update `/conduit/embeddings/models` to return `list[EmbeddingModelSpec]`

**Explicitly not in scope — do not implement these:**
- Reranker models (separate concern, separate store)
- Aliases (embedding models have no alias system)
- Client-side caching of model specs
- Automatic polling or background sync of the registry
- Wiring `EmbeddingModelStore.update()` into FastAPI lifespan or startup — `update()` is CLI-only
- Auto-migrating prompt behavioral field data from the old `embedding_models.json` — start fresh, hand-author those fields
- Pagination on `/conduit/embeddings/models`
- Authentication or authorization on the models endpoint
- A CLI command for patching individual specs — corrections are made by re-running the update script and hand-editing via a `patch_spec` helper that is out of scope for this implementation
- Modifying how `SentenceTransformer` loads models
- Hot-reload of the TinyDB without a server restart
- Perplexity auto-generating prompt behavioral fields (`prompt_required`, `valid_prefixes`, `prompt_unsupported`, `task_map`) — these are always stubbed to safe defaults and require human correction

---

## 3. Interface Contracts

### 3a. `EmbeddingProvider` — headwater-api

**Location:** `headwater-api/src/headwater_api/classes/embeddings_classes/embedding_provider.py`

```python
class EmbeddingProvider(str, Enum):
    HUGGINGFACE = "huggingface"
    OPENAI = "openai"
    COHERE = "cohere"
    JINA = "jina"
```

Adding a new provider in future requires only: adding a value here, adding a key to `embedding_models.json`, and ensuring the embedding service can load models from that provider. No other structural changes.

---

### 3b. `EmbeddingModelSpec` — headwater-api

**Location:** `headwater-api/src/headwater_api/classes/embeddings_classes/embedding_model_spec.py`

```python
class EmbeddingModelSpec(BaseModel):
    model: str
    # The model identifier. For HuggingFace this is "org/model-name" (e.g. "BAAI/bge-m3").
    # For OpenAI this is the model slug (e.g. "text-embedding-3-small").
    # For Cohere this is the model name (e.g. "embed-english-v3.0").
    # No provider prefix is added — the provider field carries that information.

    provider: EmbeddingProvider

    # Informational fields — populated by Perplexity, may need human correction
    description: str | None
    embedding_dim: int | None       # None if Perplexity cannot determine
    max_seq_length: int | None      # None if Perplexity cannot determine
    multilingual: bool
    parameter_count: str | None     # e.g. "300m", "7b"; None if unknown

    # Prompt behavioral fields — always stubbed to safe defaults by research script;
    # must be hand-corrected after update() runs for any model that uses prompts.
    prompt_required: bool           # Default: False
    valid_prefixes: list[str] | None  # Default: None
    prompt_unsupported: bool        # Default: False
    task_map: dict[str, str] | None   # Default: None

    @model_validator(mode="after")
    def _prompt_flags_not_contradictory(self) -> EmbeddingModelSpec:
        if self.prompt_required and self.prompt_unsupported:
            raise ValueError("prompt_required and prompt_unsupported cannot both be True.")
        return self
```

`EmbeddingModelSpec` replaces `ModelPromptSpec` everywhere. `ModelPromptSpec` is deleted.

`load_embedding_models()` and `get_model_prompt_spec()` are deleted. `embedding_models.py` is deleted from headwater-api. The `embedding_models.json` in headwater-api is deleted.

**Exported from `headwater_api.classes`** alongside existing classes.

---

### 3c. `embedding_models.json` — headwater-server

**Location:** `headwater-server/src/headwater_server/services/embeddings_service/embedding_models.json`

Provider-keyed registry. Values are lists of model ID strings. Empty lists are valid (provider supported but no models registered yet).

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

**Invariants:** No model ID may appear more than once across the entire file (across all providers). A model ID appearing under two providers is a malformed registry. The `_is_consistent()` check must detect and surface this.

**Workflow for adding a model:** Add its ID under the correct provider key, then run `update_embedding_modelstore`. Perplexity will populate informational fields. Prompt behavioral fields will be stubbed to safe defaults and must be hand-corrected via direct TinyDB edit using the `EmbeddingModelStore.patch_spec()` helper (out of scope for this implementation — use TinyDB directly in the interim).

---

### 3d. `embedding_modelspecs.json` — headwater-server

**Location:** `headwater-server/src/headwater_server/services/embeddings_service/embedding_modelspecs.json`

TinyDB file. Each record is a serialized `EmbeddingModelSpec`. Managed exclusively by `EmbeddingModelStore` and CRUD functions.

**Do not hand-edit this file directly.** TinyDB's internal format (numeric doc IDs, `_default` table key) makes hand-editing error-prone. To correct prompt behavioral fields after `update()`, use direct CRUD calls from a Python REPL until a `patch_spec` helper is implemented.

---

### 3e. CRUD functions — headwater-server

**Location:** `headwater-server/src/headwater_server/services/embeddings_service/embedding_modelspecs_crud.py`

```python
def add_embedding_spec(spec: EmbeddingModelSpec) -> None: ...
# Raises ValueError if spec.model is not in the registry (enforced at CRUD layer)

def get_all_embedding_specs() -> list[EmbeddingModelSpec]: ...

def get_embedding_spec_by_name(model: str) -> EmbeddingModelSpec: ...
# Raises ValueError (not KeyError) if not found

def get_all_spec_model_names() -> list[str]: ...

def delete_embedding_spec(model: str) -> None: ...
# No-op if model not in DB (does not raise)

def in_db(model: str) -> bool: ...

def wipe_and_repopulate(specs: list[EmbeddingModelSpec]) -> None: ...
# Drops all records and inserts the provided list.
# Must not be called from update() — only from explicit scripts.
```

All functions raise `ValueError` (never `KeyError`) so callers have a single exception type to handle.

---

### 3f. `EmbeddingModelStore` — headwater-server

**Location:** `headwater-server/src/headwater_server/services/embeddings_service/embedding_model_store.py`

```python
class EmbeddingModelStore:
    @classmethod
    def models(cls) -> dict[str, list[str]]: ...
    # Returns contents of embedding_models.json.
    # Raises FileNotFoundError if registry is missing.

    @classmethod
    def list_models(cls) -> list[str]: ...
    # Flat list of all model IDs across all providers. Empty provider lists contribute nothing.

    @classmethod
    def list_providers(cls) -> list[EmbeddingProvider]: ...

    @classmethod
    def identify_provider(cls, model: str) -> EmbeddingProvider: ...
    # Raises ValueError if model not found in any provider list.
    # Raises ValueError (with detail) if model appears under more than one provider.

    @classmethod
    def is_supported(cls, model: str) -> bool: ...

    @classmethod
    def get_spec(cls, model: str) -> EmbeddingModelSpec: ...
    # Raises ValueError if model not in registry (checked first, before TinyDB lookup).
    # Raises ValueError if model is in registry but not in TinyDB (un-populated spec).

    @classmethod
    def get_all_specs(cls) -> list[EmbeddingModelSpec]: ...

    @classmethod
    def by_provider(cls, provider: EmbeddingProvider) -> list[EmbeddingModelSpec]: ...

    @classmethod
    def update(cls) -> None: ...
    # Syncs TinyDB with registry. Never overwrites existing TinyDB records.
    # Deletes records whose model IDs are not in the registry.
    # Calls create_embedding_spec() only for models missing from TinyDB.
    # Raises and halts (does not continue to next model) if Perplexity fails for any model.
    # Prints progress to stdout. Logs INFO on success, ERROR on failure.

    @classmethod
    def _is_consistent(cls) -> bool: ...
    # Returns False if: any model in registry has no TinyDB record,
    # any TinyDB record has no corresponding registry entry,
    # or any model ID appears under more than one provider in the registry.

    @classmethod
    def _update_models(cls) -> None: ...
    # Internal. Called only by update(). Performs the incremental sync.
```

---

### 3g. `research_embedding_models.py` — headwater-server

**Location:** `headwater-server/src/headwater_server/services/embeddings_service/research_embedding_models.py`

```python
def get_embedding_spec(model: str, provider: EmbeddingProvider) -> EmbeddingModelSpec: ...
# Calls Perplexity (sonar-pro) for informational fields only.
# Always sets model field to the `model` argument — never trusts the model name
# returned by Perplexity (mirrors conduit's model_spec.model = model pattern).
# Prompt behavioral fields are always: prompt_required=False, valid_prefixes=None,
# prompt_unsupported=False, task_map=None.
# Raises ValidationError if Perplexity response cannot be coerced to EmbeddingModelSpec.
# Raises on network timeout or Perplexity API error — does not retry.

def create_embedding_spec(model: str, provider: EmbeddingProvider) -> None: ...
# Calls get_embedding_spec. Writes to TinyDB only if model is not already in DB.
# If model is already in DB, logs a warning and returns without overwriting.
# Raises ValueError if model is not in the registry.
```

---

### 3h. `update_embedding_modelstore.py` CLI script — headwater-server

**Location:** `headwater-server/src/headwater_server/scripts/update_embedding_modelstore.py`

```python
def main() -> None:
    store = EmbeddingModelStore()
    if not store._is_consistent():
        print("Embedding model specs are not consistent with registry. Updating...")
        store.update()
        print("Update complete.")
    else:
        print("Embedding model specs are consistent. No update needed.")
```

Registered as a script entrypoint in `pyproject.toml`. Exits with code 0 on success, non-zero on error.

---

### 3i. API endpoint change

`GET /conduit/embeddings/models` changes response model from `list[str]` to `list[EmbeddingModelSpec]`.

`list_embedding_models_service.py` is updated to call `EmbeddingModelStore.get_all_specs()`.

The response includes all fields of `EmbeddingModelSpec` including `None`-valued optional fields. No fields are suppressed in the serialization.

---

## 4. Acceptance Criteria

Each criterion is written as a directly executable test assertion.

**EmbeddingModelSpec:**
- `EmbeddingModelSpec(prompt_required=True, prompt_unsupported=True, ...)` raises `ValidationError`.
- `EmbeddingModelSpec(prompt_required=False, prompt_unsupported=False, embedding_dim=None, ...)` constructs without error.
- `EmbeddingModelSpec.model_validate(spec.model_dump())` round-trips without data loss for all field combinations.

**EmbeddingModelStore:**
- `EmbeddingModelStore.models()` returns a dict whose keys are exactly the provider strings in `embedding_models.json`.
- `EmbeddingModelStore.list_models()` returns a flat list with no duplicates and no model IDs from empty provider lists.
- `EmbeddingModelStore.identify_provider("BAAI/bge-m3")` returns `EmbeddingProvider.HUGGINGFACE`.
- `EmbeddingModelStore.identify_provider("not-a-real-model")` raises `ValueError`.
- `EmbeddingModelStore.get_spec("not-a-real-model")` raises `ValueError` before performing any TinyDB lookup (verify with a mock that asserts TinyDB is never called).
- `EmbeddingModelStore.get_spec("BAAI/bge-m3")` raises `ValueError` when model is in registry but TinyDB is empty.
- `EmbeddingModelStore.get_spec("BAAI/bge-m3")` returns a valid `EmbeddingModelSpec` when TinyDB is populated.
- `EmbeddingModelStore.by_provider(EmbeddingProvider.OPENAI)` returns `[]` when no OpenAI models are registered.

**update() behavior:**
- Given registry with models [A, B] and TinyDB with [A]: `update()` adds B, leaves A's record unchanged (assert A's record is byte-identical before and after).
- Given registry with models [A] and TinyDB with [A, B]: `update()` deletes B, leaves A unchanged.
- After any `update()` call that does not raise, `_is_consistent()` returns `True`.
- `update()` with Perplexity mocked to raise `ConnectionError` raises and does not write any new TinyDB records.

**API:**
- `GET /conduit/embeddings/models` returns HTTP 200 with a JSON array.
- Each element of the array deserializes into a valid `EmbeddingModelSpec` with all fields present (including `None`-valued optionals).

**Migration:**
- `EmbeddingsRequest` model validator constructs successfully without any filesystem access (verified by patching `builtins.open` and asserting it is not called during validation).
- `generate_embeddings_service` calls `EmbeddingModelStore.get_spec()` and not `get_model_prompt_spec()` (verified by import analysis or mock assertion).
- `ModelPromptSpec`, `load_embedding_models()`, `get_model_prompt_spec()` do not appear anywhere in the codebase (verified by `grep`).

---

## 5. Error Handling / Failure Modes

| Failure | Behavior |
|---|---|
| `embedding_models.json` missing | `EmbeddingModelStore.models()` raises `FileNotFoundError` immediately |
| `embedding_modelspecs.json` missing at startup | TinyDB creates empty file; `_is_consistent()` returns `False`; log WARNING at server startup |
| Server starts with inconsistent TinyDB | Log WARNING: "Embedding model specs are inconsistent — run update_embedding_modelstore"; do not block startup |
| Model in registry but not in TinyDB | `get_spec()` raises `ValueError("Model '{model}' has no spec record — run update_embedding_modelstore")`; upstream returns HTTP 500 |
| Model in TinyDB but not in registry | `_is_consistent()` returns `False`; orphan is deleted on next `update()` |
| Perplexity returns malformed/uncoerceable response | `get_embedding_spec()` raises `ValidationError`; `update()` logs `ERROR` with model name and halts; TinyDB is left in partial state; already-written records for other models in the same run are retained |
| Perplexity network timeout or API error | `get_embedding_spec()` raises; `update()` propagates and halts; same partial-state behavior as above |
| Duplicate model ID within one provider in registry | `_is_consistent()` returns `False`; `identify_provider()` returns the first match and logs `WARNING`; registry must be corrected manually |
| Duplicate model ID across two providers in registry | `identify_provider()` raises `ValueError` with both provider names listed |
| `update()` called concurrently by two processes | TinyDB file locking applies; no additional handling — document this as an operational constraint |
| `wipe_and_repopulate()` called from `update()` | Must not happen — `update()` must never call `wipe_and_repopulate()` |
| Perplexity returns spec with wrong `model` field | `create_embedding_spec()` overwrites `spec.model` with the requested model name before writing to TinyDB |

---

## 6. Observability

### Logging contract

All log calls use `logger = logging.getLogger(__name__)`.

| Event | Level | Required fields |
|---|---|---|
| Server starts with inconsistent TinyDB | WARNING | `models_in_registry`, `models_in_db` |
| `update()` begins | INFO | `models_to_add` (count), `models_to_delete` (count) |
| Spec created for new model | INFO | `model`, `provider` |
| Spec deleted for removed model | INFO | `model` |
| `update()` completes successfully | INFO | `added` (count), `deleted` (count) |
| `update()` fails for a model | ERROR | `model`, `provider`, `error` |
| `get_spec()` called for unsupported model | WARNING | `model` |
| Duplicate model ID detected in registry | WARNING | `model`, `providers` |

### Console output (update script only)

The update script prints human-readable progress to stdout following the conduit pattern:
```
Embedding model specs are not consistent with registry. Updating...
  Adding spec for BAAI/bge-m3 (huggingface)...
  Deleting orphaned spec for old-model/removed...
Update complete. Added: 1, Deleted: 1.
```

### Startup check

At server startup (FastAPI lifespan or equivalent), call `EmbeddingModelStore._is_consistent()`. If `False`, log a WARNING. Do not block startup. Do not call `update()` automatically.

---

## 7. Code Example

```python
# embedding_model_store.py
from __future__ import annotations

import json
import logging
import itertools
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider

logger = logging.getLogger(__name__)

_DIR = Path(__file__).parent
_REGISTRY_PATH = _DIR / "embedding_models.json"


class EmbeddingModelStore:
    @classmethod
    def models(cls) -> dict[str, list[str]]:
        with open(_REGISTRY_PATH) as f:
            return json.load(f)

    @classmethod
    def list_models(cls) -> list[str]:
        return list(itertools.chain.from_iterable(cls.models().values()))

    @classmethod
    def identify_provider(cls, model: str) -> EmbeddingProvider:
        from headwater_api.classes import EmbeddingProvider
        matches = [
            provider for provider, model_list in cls.models().items()
            if model in model_list
        ]
        if len(matches) == 0:
            raise ValueError(f"Provider not found for model: {model}")
        if len(matches) > 1:
            raise ValueError(
                f"Model '{model}' found under multiple providers: {matches}. Registry is malformed."
            )
        return EmbeddingProvider(matches[0])

    @classmethod
    def get_spec(cls, model: str) -> EmbeddingModelSpec:
        from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
            get_embedding_spec_by_name,
            in_db,
        )
        if not cls.is_supported(model):
            raise ValueError(f"Model '{model}' is not in the embedding model registry.")
        if not in_db(model):
            raise ValueError(
                f"Model '{model}' has no spec record — run update_embedding_modelstore."
            )
        return get_embedding_spec_by_name(model)
```

---

## 8. Domain Language

| Term | Definition |
|---|---|
| **registry** | `embedding_models.json` — provider-keyed authoritative list of supported embedding model IDs; the only file that is hand-edited to add/remove models |
| **spec store** | `embedding_modelspecs.json` — TinyDB holding persisted `EmbeddingModelSpec` records; never hand-edited directly |
| **EmbeddingModelSpec** | Pydantic model capturing both operational prompt config and informational metadata for one embedding model |
| **EmbeddingProvider** | Str enum identifying the origin provider of an embedding model (huggingface, openai, cohere, jina) |
| **model ID** | The string identifying a model, scoped to its provider's convention (e.g. `"BAAI/bge-m3"` for HuggingFace, `"text-embedding-3-small"` for OpenAI) |
| **informational fields** | Fields populated by Perplexity: `description`, `embedding_dim`, `max_seq_length`, `multilingual`, `parameter_count` |
| **prompt behavioral fields** | Fields requiring human authorship: `prompt_required`, `valid_prefixes`, `prompt_unsupported`, `task_map`; always stubbed to safe defaults by the research script |
| **safe defaults** | The stub values for prompt behavioral fields when auto-generated: `prompt_required=False`, `valid_prefixes=None`, `prompt_unsupported=False`, `task_map=None` |
| **consistent** | State where every model ID in the registry has exactly one record in the spec store, every record in the spec store has a corresponding registry entry, and no model ID appears under more than one provider in the registry |
| **update** | The incremental sync operation: adds specs for models in registry but not in TinyDB; deletes specs for models in TinyDB but not in registry; never overwrites existing records |

---

## 9. Invalid State Transitions

- `EmbeddingModelStore.get_spec(model)` must raise `ValueError` before performing any TinyDB lookup if `model` is not in the registry.
- `create_embedding_spec(model)` must raise `ValueError` if `model` is not in the registry — a spec must never be written for an unregistered model.
- `update()` must never call `wipe_and_repopulate()` — incremental sync only.
- `update()` must never overwrite an existing TinyDB record — `create_embedding_spec()` checks `in_db()` and skips if already present.
- `prompt_required=True` and `prompt_unsupported=True` on the same spec must raise `ValidationError` at construction — this is caught before any TinyDB write.
- A model ID must not appear under more than one provider key in the registry — `identify_provider()` raises `ValueError` if this is detected.

---

## Migration Notes

Existing files that must be modified (not created) as part of this implementation:

- `embedding_model.py` — replace `load_embedding_models()` with `EmbeddingModelStore.list_models()`
- `list_embedding_models_service.py` — replace `load_embedding_models()` with `EmbeddingModelStore.get_all_specs()`
- `generate_embeddings_service.py` — replace `get_model_prompt_spec()` with `EmbeddingModelStore.get_spec()`
- `headwater-api/classes/embeddings_classes/requests.py` — remove all calls to `load_embedding_models()` and `get_model_prompt_spec()` from model validators; prompt validation becomes server-side only (behavioral change: client no longer catches bad task/prompt combos before network call)
- `embeddings_server_api.py` — update response model on `GET /conduit/embeddings/models` from `list[str]` to `list[EmbeddingModelSpec]`
- `headwater-api/classes/__init__.py` — export `EmbeddingModelSpec` and `EmbeddingProvider`; remove `ModelPromptSpec` export
