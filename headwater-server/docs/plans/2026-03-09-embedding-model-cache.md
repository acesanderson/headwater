# Embedding Model Cache Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate per-request `SentenceTransformer` instantiation and event-loop blocking in the embeddings service by adding a cached `EmbeddingModel.get()` classmethod and offloading inference to a thread via `run_in_executor`.

**Architecture:** A module-level dict cache with double-checked locking (mirroring the existing reranker pattern) lives inside `embedding_model.py`. `generate_embeddings_service` calls `EmbeddingModel.get(model)` instead of `EmbeddingModel(model)` and wraps the blocking `.generate_embeddings()` call in `run_in_executor(None, ...)`. No new files. No changes to public `EmbeddingModel.__init__` signature. No inference-level lock. No bounded executor.

**Tech Stack:** Python `threading.Lock`, `asyncio.get_running_loop().run_in_executor`, `unittest.mock.patch`

---

## Acceptance Criteria (reference key)

- **AC1** — `EmbeddingModel.get(name)` called twice returns the same object instance.
- **AC2** — Two concurrent threads calling `EmbeddingModel.get(name)` result in exactly one `SentenceTransformer` construction.
- **AC3** — A fast coroutine completes while inference is blocked in a thread (event loop stays responsive).
- **AC4** — A failed `SentenceTransformer` construction does not poison the cache; the next call retries.
- **AC5** — A `RuntimeError` raised inside the executor thread surfaces as an exception at the `await` site in the service.

---

## Task 1: Add `EmbeddingModel.get()` classmethod with cache

**Files:**
- Modify: `src/headwater_server/services/embeddings_service/embedding_model.py`
- Test: `tests/services/embeddings_service/test_embedding_model_cache.py` (new file)

---

### TDD Cycle 1 — AC1: same instance returned on repeated calls

**Step 1: Write the failing test**

Create `tests/services/embeddings_service/test_embedding_model_cache.py`:

```python
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def clear_cache():
    from headwater_server.services.embeddings_service.embedding_model import _model_cache
    _model_cache.clear()
    yield
    _model_cache.clear()


def test_get_returns_same_instance():
    """AC1: calling get() twice with same name returns identical object."""
    mock_st = MagicMock()
    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        return_value=mock_st,
    ), patch(
        "headwater_server.services.embeddings_service.embedding_model.EmbeddingModelStore.list_models",
        return_value=["BAAI/bge-m3"],
    ):
        from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

        r1 = EmbeddingModel.get("BAAI/bge-m3")
        r2 = EmbeddingModel.get("BAAI/bge-m3")

        assert r1 is r2
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/services/embeddings_service/test_embedding_model_cache.py::test_get_returns_same_instance -v
```

Expected: `FAILED` — `AttributeError: type object 'EmbeddingModel' has no attribute 'get'`

**Step 3: Implement minimal code (AC1 only)**

In `embedding_model.py`, add after the existing imports:

```python
import threading
```

Add after the module-level `_DEVICE_CACHE = None` line:

```python
_model_cache: dict[str, EmbeddingModel] = {}
_cache_lock = threading.Lock()
```

Add this classmethod to `EmbeddingModel`, after the `device()` classmethod:

```python
@classmethod
def get(cls, model_name: str) -> EmbeddingModel:
    if model_name not in _model_cache:
        with _cache_lock:
            if model_name not in _model_cache:
                logger.info("embedding model loading: %s", model_name)
                _model_cache[model_name] = cls(model_name)
                logger.info("embedding model cached: %s", model_name)
    else:
        logger.info("embedding model cache hit: %s", model_name)
    return _model_cache[model_name]
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_cache.py::test_get_returns_same_instance -v
```

Expected: `PASSED`

---

### TDD Cycle 2 — AC2: concurrent calls instantiate exactly once

**Step 5: Write the failing test**

Append to `tests/services/embeddings_service/test_embedding_model_cache.py`:

```python
def test_concurrent_get_instantiates_once():
    """AC2: two threads racing to get() the same uncached model → one SentenceTransformer construction."""
    import threading

    construct_count = 0
    first_started = threading.Event()
    first_can_finish = threading.Event()

    def controlled_st(*args, **kwargs):
        nonlocal construct_count
        construct_count += 1
        first_started.set()
        first_can_finish.wait(timeout=2)
        return MagicMock()

    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        side_effect=controlled_st,
    ), patch(
        "headwater_server.services.embeddings_service.embedding_model.EmbeddingModelStore.list_models",
        return_value=["BAAI/bge-m3"],
    ):
        from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

        results = []

        def call_get():
            results.append(EmbeddingModel.get("BAAI/bge-m3"))

        t1 = threading.Thread(target=call_get)
        t2 = threading.Thread(target=call_get)

        t1.start()
        first_started.wait(timeout=2)  # t1 is inside the constructor
        t2.start()                     # t2 will hit the outer check, then block on _cache_lock
        first_can_finish.set()         # let t1 finish construction
        t1.join(timeout=2)
        t2.join(timeout=2)

        assert construct_count == 1
        assert results[0] is results[1]
```

**Step 6: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_cache.py::test_concurrent_get_instantiates_once -v
```

Expected: `FAILED` (the `get` classmethod doesn't exist yet in the test file's imported state if cache was cleared; or passes trivially if AC1 step already added it — in that case, skip to step 8 to confirm it passes).

**Step 7: Verify the implementation already satisfies this**

The double-checked locking pattern added in Cycle 1 already handles this. No new code needed.

**Step 8: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_cache.py::test_concurrent_get_instantiates_once -v
```

Expected: `PASSED`

---

### TDD Cycle 3 — AC4: failed instantiation does not poison cache

**Step 9: Write the failing test**

Append to `tests/services/embeddings_service/test_embedding_model_cache.py`:

```python
def test_failed_instantiation_does_not_poison_cache():
    """AC4: if SentenceTransformer() raises, the next get() retries rather than returning a cached failure."""
    call_count = 0

    def sometimes_fails(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated CUDA OOM on first load")
        return MagicMock()

    with patch(
        "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer",
        side_effect=sometimes_fails,
    ), patch(
        "headwater_server.services.embeddings_service.embedding_model.EmbeddingModelStore.list_models",
        return_value=["BAAI/bge-m3"],
    ):
        from headwater_server.services.embeddings_service.embedding_model import EmbeddingModel

        with pytest.raises(RuntimeError, match="simulated CUDA OOM"):
            EmbeddingModel.get("BAAI/bge-m3")

        # Second call must retry, not return a cached None or re-raise a stale exception
        result = EmbeddingModel.get("BAAI/bge-m3")

        assert result is not None
        assert call_count == 2
```

**Step 10: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_cache.py::test_failed_instantiation_does_not_poison_cache -v
```

Expected: `FAILED` — second `get()` call likely raises again or returns wrong value before implementation is confirmed correct.

**Step 11: Verify the implementation already satisfies this**

The `_model_cache[model_name] = cls(model_name)` assignment only executes if `cls(model_name)` succeeds. A raised exception unwinds the stack without writing to the cache. No new code needed.

**Step 12: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_cache.py::test_failed_instantiation_does_not_poison_cache -v
```

Expected: `PASSED`

**Step 13: Run full cache test file**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_cache.py -v
```

Expected: all 3 tests `PASSED`

**Step 14: Commit**

```bash
git add src/headwater_server/services/embeddings_service/embedding_model.py \
        tests/services/embeddings_service/test_embedding_model_cache.py
git commit -m "feat: add EmbeddingModel.get() classmethod with module-level cache

Mirrors reranker model_cache pattern. Double-checked locking prevents
duplicate instantiation under concurrent access. Failed loads do not
poison the cache. Covers AC1, AC2, AC4.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Offload inference to thread pool and use cache in service

**Files:**
- Modify: `src/headwater_server/services/embeddings_service/generate_embeddings_service.py`
- Modify (existing test): `tests/services/embeddings_service/test_generate_embeddings_service_store.py`
- Test: `tests/services/embeddings_service/test_generate_embeddings_service_concurrency.py` (new file)

---

### TDD Cycle 4 — AC3: event loop remains responsive during inference

**Step 1: Write the failing test**

Create `tests/services/embeddings_service/test_generate_embeddings_service_concurrency.py`:

```python
from __future__ import annotations
import asyncio
import time
from unittest.mock import MagicMock, patch
import pytest
from headwater_api.classes import ChromaBatch, EmbeddingsRequest


def _make_request() -> EmbeddingsRequest:
    return EmbeddingsRequest(
        model="BAAI/bge-m3",
        batch=ChromaBatch(ids=["1"], documents=["hello"]),
        task=None,
        prompt=None,
    )


def test_event_loop_not_blocked_during_inference():
    """AC3: a fast coroutine completes before slow inference finishes, proving the event loop is not blocked."""
    completion_order: list[str] = []

    def slow_inference(batch, prompt=None):
        time.sleep(0.15)
        completion_order.append("inference")
        return MagicMock(embeddings=[[0.1, 0.2]])

    mock_model = MagicMock()
    mock_model.generate_embeddings.side_effect = slow_inference

    async def fast_task():
        await asyncio.sleep(0.05)
        completion_order.append("fast")

    async def run():
        from headwater_server.services.embeddings_service.generate_embeddings_service import (
            generate_embeddings_service,
        )
        with patch(
            "headwater_server.services.embeddings_service.generate_embeddings_service.EmbeddingModel.get",
            return_value=mock_model,
        ):
            await asyncio.gather(
                asyncio.create_task(generate_embeddings_service(_make_request())),
                asyncio.create_task(fast_task()),
            )

    asyncio.run(run())

    # fast_task sleeps 50ms, inference takes 150ms.
    # If event loop was blocked: fast_task couldn't run until inference finished → order is ["inference", "fast"].
    # If event loop is not blocked: fast_task completes at ~50ms → order is ["fast", "inference"].
    assert completion_order == ["fast", "inference"], (
        f"Expected fast task to complete before inference. Got order: {completion_order}. "
        "This means the event loop was blocked during inference."
    )
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_generate_embeddings_service_concurrency.py::test_event_loop_not_blocked_during_inference -v
```

Expected: `FAILED` — order will be `["inference", "fast"]` because the current service blocks the event loop.

**Step 3: Implement the fix in `generate_embeddings_service.py`**

Replace the full contents of `generate_embeddings_service.py`:

```python
from __future__ import annotations
import asyncio
import logging
import time

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

    embedding_model = EmbeddingModel.get(model)

    start = time.monotonic()
    loop = asyncio.get_running_loop()
    new_batch: ChromaBatch = await loop.run_in_executor(
        None, lambda: embedding_model.generate_embeddings(batch, prompt=prompt)
    )
    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "embeddings generated: model=%s batch_size=%d duration_ms=%.1f",
        model,
        len(batch.documents),
        elapsed_ms,
    )

    return EmbeddingsResponse(embeddings=new_batch.embeddings)
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_generate_embeddings_service_concurrency.py::test_event_loop_not_blocked_during_inference -v
```

Expected: `PASSED`

---

### TDD Cycle 5 — AC5: inference exceptions propagate through the executor

**Step 5: Write the failing test**

Append to `tests/services/embeddings_service/test_generate_embeddings_service_concurrency.py`:

```python
def test_inference_exception_propagates():
    """AC5: a RuntimeError raised inside run_in_executor surfaces at the await site, not swallowed."""
    def exploding_inference(batch, prompt=None):
        raise RuntimeError("CUDA out of memory")

    mock_model = MagicMock()
    mock_model.generate_embeddings.side_effect = exploding_inference

    async def run():
        from headwater_server.services.embeddings_service.generate_embeddings_service import (
            generate_embeddings_service,
        )
        with patch(
            "headwater_server.services.embeddings_service.generate_embeddings_service.EmbeddingModel.get",
            return_value=mock_model,
        ):
            with pytest.raises(RuntimeError, match="CUDA out of memory"):
                await generate_embeddings_service(_make_request())

    import pytest
    asyncio.run(run())
```

**Step 6: Run test to verify it fails**

```bash
uv run pytest tests/services/embeddings_service/test_generate_embeddings_service_concurrency.py::test_inference_exception_propagates -v
```

Expected: `FAILED` — before the fix, the blocking call raised synchronously; after the fix with `run_in_executor`, the exception should propagate through the `Future`. If the implementation from Cycle 4 is already in place, this may pass immediately — proceed to step 8.

**Step 7: Verify implementation already satisfies this**

`run_in_executor` re-raises exceptions from the thread at the `await` site automatically. No additional code needed.

**Step 8: Run test to verify it passes**

```bash
uv run pytest tests/services/embeddings_service/test_generate_embeddings_service_concurrency.py::test_inference_exception_propagates -v
```

Expected: `PASSED`

---

### Step 9: Update the existing service test to patch `.get` instead of the constructor

`test_generate_embeddings_service_store.py` currently patches `EmbeddingModel` as a constructor (`mock_model_cls.return_value = mock_instance`). The service now calls `EmbeddingModel.get(model)`, so update the patch target and return value:

In `tests/services/embeddings_service/test_generate_embeddings_service_store.py`, change:

```python
# OLD
with patch(
    "headwater_server.services.embeddings_service.generate_embeddings_service.EmbeddingModel"
) as mock_model_cls:
    ...
    mock_model_cls.return_value = mock_instance
```

to:

```python
# NEW
with patch(
    "headwater_server.services.embeddings_service.generate_embeddings_service.EmbeddingModel.get",
    return_value=mock_instance,
):
```

**Step 10: Run the updated existing test**

```bash
uv run pytest tests/services/embeddings_service/test_generate_embeddings_service_store.py -v
```

Expected: `PASSED`

---

### Step 11: Run the full test suite for affected modules

```bash
uv run pytest tests/services/embeddings_service/ -v
```

Expected: all tests pass. Confirm log output includes `"embedding model loading"`, `"embedding model cached"`, and `"embeddings generated: model=... duration_ms=..."` lines in the captured output.

**Step 12: Commit**

```bash
git add src/headwater_server/services/embeddings_service/generate_embeddings_service.py \
        tests/services/embeddings_service/test_generate_embeddings_service_concurrency.py \
        tests/services/embeddings_service/test_generate_embeddings_service_store.py
git commit -m "feat: offload embedding inference to thread pool, use model cache

Replaces per-request EmbeddingModel() instantiation with EmbeddingModel.get().
Wraps generate_embeddings() in run_in_executor(None, ...) so the asyncio event
loop is not blocked during GPU inference. Adds duration_ms logging to match
reranker observability. Covers AC3, AC5.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```
