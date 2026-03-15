# Headwater Server Logging Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement request-correlated, noise-suppressed server logging with LLM call observability, replacing conduit's silenced Rich progress display.

**Architecture:** A `server/context.py` module owns a `ContextVar[str]` defaulting to `"system"`. A `RequestIdFilter` on the root logger auto-injects the current value into every `LogRecord`. Correlation middleware in `headwater.py` mints or validates a UUID per request, sets the `ContextVar`, and emits structured `request_started`/`request_finished` events. Service files emit LLM call events by reading the `ContextVar`. Third-party loggers are silenced at `WARNING` in `logging_config.py`. `LogEntry` in `headwater_api` gains a `request_id` field for ring buffer tracing.

**Tech Stack:** Python stdlib `logging` + `contextvars`, FastAPI middleware, `pytest`, `pytest-asyncio`, `unittest.mock`

**Design doc:** `docs/plans/2026-03-13-logging-design.md`

**Run all tests from:** `headwater-server/` directory using `uv run pytest`

**Note on `--pdb`:** `pyproject.toml` sets `addopts = "... --pdb"`. On verify-fail steps, use `-p no:pdb` to prevent the debugger opening when the test fails as expected.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/headwater_server/server/context.py` | **Create** | `request_id_var` ContextVar; single source of truth |
| `src/headwater_server/server/logging_config.py` | **Modify** | Fix RichHandler format; add `RequestIdFilter`; silence third parties |
| `src/headwater_server/server/headwater.py` | **Modify** | Correlation middleware |
| `src/headwater_server/services/conduit_service/conduit_generate_service.py` | **Modify** | LLM call log events |
| `src/headwater_server/services/conduit_service/conduit_batch_service.py` | **Modify** | Batch log events |
| `src/headwater_server/services/embeddings_service/embedding_model.py` | **Modify** | Cache hit → DEBUG; eviction → WARNING |
| `src/headwater_server/services/embeddings_service/generate_embeddings_service.py` | **Modify** | Demote "started" event to DEBUG |
| `../../headwater-api/src/headwater_api/classes/server_classes/logs.py` | **Modify** | Add `request_id: str \| None = None` to `LogEntry` |
| `src/headwater_server/server/logging_config.py` | **Modify** | `RingBufferHandler.get_records()` populates `request_id` |
| `tests/server/test_logging_config.py` | **Create** | Tasks 1, 2, 3 |
| `tests/server/test_middleware.py` | **Create** | Tasks 4, 5, 6, 7 |
| `tests/conduit_service/test_conduit_generate_logging.py` | **Create** | Tasks 8, 9, 10 |
| `tests/conduit_service/test_conduit_batch_logging.py` | **Create** | Task 11 |
| `tests/services/embeddings_service/test_embedding_model_logging.py` | **Create** | Task 12 |
| `tests/api/test_logs_endpoint.py` | **Create** | Task 13 |

---

## Chunk 1: Logging Configuration Foundation

### Task 1: Fix RichHandler double-INFO format *(AC-1)*

The current `RichHandler` has no explicit formatter, causing Python's default format string
(`%(levelname)s:%(name)s:%(message)s`) to embed the level in the message body while Rich also
renders its own level column. Set `format="%(message)s"` to let Rich own the level display.

**Files:**
- Modify: `src/headwater_server/server/logging_config.py`
- Create: `tests/server/test_logging_config.py`

- [ ] **Step 1 *(AC-1)*: Write the failing test**

```python
# tests/server/test_logging_config.py
from __future__ import annotations
import logging
from rich.logging import RichHandler


def test_rich_handler_format_is_message_only():
    """AC-1: RichHandler must use '%(message)s' only — no level embedded in message body."""
    import headwater_server.server.logging_config  # ensure side effects run
    root = logging.getLogger()
    rich_handlers = [h for h in root.handlers if isinstance(h, RichHandler)]
    assert rich_handlers, "No RichHandler found on root logger"
    handler = rich_handlers[0]
    assert handler.formatter is not None, "RichHandler has no formatter set"
    assert handler.formatter._fmt == "%(message)s", (
        f"Expected '%(message)s', got '{handler.formatter._fmt}'"
    )
```

- [ ] **Step 2 *(AC-1)*: Verify test fails**

```bash
uv run pytest tests/server/test_logging_config.py::test_rich_handler_format_is_message_only -v -p no:pdb
```

Expected: `FAILED` — `AssertionError: RichHandler has no formatter set` (or similar)

- [ ] **Step 3 *(AC-1)*: Implement**

In `logging_config.py`, update the `RichHandler` construction:

```python
rich_handler = RichHandler(
    rich_tracebacks=True,
    markup=True,
    console=console,
)
rich_handler.setFormatter(logging.Formatter("%(message)s"))  # add this line
rich_handler.addFilter(PackagePathFilter())
rich_handler.setLevel(root_level)
```

- [ ] **Step 4 *(AC-1)*: Verify test passes**

```bash
uv run pytest tests/server/test_logging_config.py::test_rich_handler_format_is_message_only -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/headwater_server/server/logging_config.py tests/server/test_logging_config.py
git commit -m "fix: set RichHandler formatter to message-only to eliminate double INFO prefix"
```

---

### Task 2: Create `server/context.py` and `RequestIdFilter` *(AC-5)*

`request_id_var` defaults to `"system"`. A `RequestIdFilter` on the root logger auto-injects
the current contextvar value into every `LogRecord` as `record.request_id`. This means all log
calls — including those that don't explicitly set `extra={"request_id": ...}` — carry the field.

**Files:**
- Create: `src/headwater_server/server/context.py`
- Modify: `src/headwater_server/server/logging_config.py`
- Modify: `tests/server/test_logging_config.py`

- [ ] **Step 1 *(AC-5)*: Write the failing tests**

```python
# Append to tests/server/test_logging_config.py


def test_request_id_var_default_is_system():
    """AC-5: Outside any request context, request_id_var defaults to 'system'."""
    from headwater_server.server.context import request_id_var
    assert request_id_var.get() == "system"


def test_request_id_filter_injects_into_log_record(caplog):
    """AC-5: Every log record carries request_id='system' outside a request context."""
    import logging
    import headwater_server.server.logging_config  # ensure filter is registered

    with caplog.at_level(logging.INFO, logger="test.sentinel"):
        logging.getLogger("test.sentinel").info("startup event")

    assert caplog.records, "No log records captured"
    record = caplog.records[-1]
    assert hasattr(record, "request_id"), "request_id not injected into LogRecord"
    assert record.request_id == "system"
```

- [ ] **Step 2 *(AC-5)*: Verify tests fail**

```bash
uv run pytest tests/server/test_logging_config.py::test_request_id_var_default_is_system tests/server/test_logging_config.py::test_request_id_filter_injects_into_log_record -v -p no:pdb
```

Expected: `FAILED` — `ModuleNotFoundError: headwater_server.server.context` or `AttributeError`

- [ ] **Step 3 *(AC-5)*: Create `server/context.py`**

```python
# src/headwater_server/server/context.py
from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="system")
```

- [ ] **Step 4 *(AC-5)*: Add `RequestIdFilter` to `logging_config.py`**

Add after the `PackagePathFilter` class definition:

```python
class RequestIdFilter(logging.Filter):
    """Injects the current request_id from context into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        from headwater_server.server.context import request_id_var
        record.request_id = request_id_var.get()
        return True
```

Then register it on the root logger immediately after `basicConfig`:

```python
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[rich_handler, file_handler, ring_buffer],
)

# Inject request_id into every record
logging.getLogger().addFilter(RequestIdFilter())
```

- [ ] **Step 5 *(AC-5)*: Verify tests pass**

```bash
uv run pytest tests/server/test_logging_config.py::test_request_id_var_default_is_system tests/server/test_logging_config.py::test_request_id_filter_injects_into_log_record -v
```

Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add src/headwater_server/server/context.py src/headwater_server/server/logging_config.py tests/server/test_logging_config.py
git commit -m "feat: add request_id ContextVar and RequestIdFilter for automatic log record injection"
```

---

### Task 3: Suppress third-party loggers *(AC-9)*

**Files:**
- Modify: `src/headwater_server/server/logging_config.py`
- Modify: `tests/server/test_logging_config.py`

- [ ] **Step 1 *(AC-9)*: Write the failing test**

```python
# Append to tests/server/test_logging_config.py


def test_third_party_loggers_suppressed_at_warning():
    """AC-9: Noisy third-party loggers are set to WARNING; uvicorn.error is untouched."""
    import logging
    import headwater_server.server.logging_config

    suppressed = ["httpx", "httpcore", "sentence_transformers", "conduit", "uvicorn.access"]
    for name in suppressed:
        level = logging.getLogger(name).level
        assert level == logging.WARNING, (
            f"Logger '{name}' has level {logging.getLevelName(level)}, expected WARNING"
        )

    # uvicorn.error must NOT be suppressed
    uvicorn_error_level = logging.getLogger("uvicorn.error").level
    assert uvicorn_error_level != logging.WARNING, (
        "uvicorn.error must not be suppressed — it reports worker crashes"
    )
```

- [ ] **Step 2 *(AC-9)*: Verify test fails**

```bash
uv run pytest tests/server/test_logging_config.py::test_third_party_loggers_suppressed_at_warning -v -p no:pdb
```

Expected: `FAILED` — `AssertionError: Logger 'httpx' has level NOTSET, expected WARNING`

- [ ] **Step 3 *(AC-9)*: Implement**

Add immediately after the `logging.getLogger().addFilter(RequestIdFilter())` line in `logging_config.py`:

```python
# Silence third-party loggers. Hardcoded — not configurable.
# uvicorn.error is intentionally excluded: it reports worker crashes.
SUPPRESSED_LOGGERS = [
    "httpx",
    "httpcore",
    "sentence_transformers",
    "conduit",
    "uvicorn.access",
]
for _name in SUPPRESSED_LOGGERS:
    logging.getLogger(_name).setLevel(logging.WARNING)
```

- [ ] **Step 4 *(AC-9)*: Verify test passes**

```bash
uv run pytest tests/server/test_logging_config.py::test_third_party_loggers_suppressed_at_warning -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/headwater_server/server/logging_config.py tests/server/test_logging_config.py
git commit -m "feat: suppress httpx, httpcore, sentence_transformers, conduit, uvicorn.access at WARNING"
```

---

## Chunk 2: Request Correlation Middleware

### Task 4: Middleware — valid `X-Request-ID` echo *(AC-3)*

**Files:**
- Modify: `src/headwater_server/server/headwater.py`
- Create: `tests/server/test_middleware.py`

- [ ] **Step 1 *(AC-3)*: Write the failing test**

```python
# tests/server/test_middleware.py
from __future__ import annotations

import uuid
from fastapi.testclient import TestClient


def _make_client():
    from headwater_server.server.headwater import HeadwaterServer
    return TestClient(HeadwaterServer().app)


def test_valid_request_id_is_echoed_in_response_header():
    """AC-3: A valid UUID4 X-Request-ID header is echoed back unchanged."""
    client = _make_client()
    supplied_id = str(uuid.uuid4())
    response = client.get("/ping", headers={"X-Request-ID": supplied_id})
    assert response.headers.get("X-Request-ID") == supplied_id


def test_no_request_id_header_generates_uuid4():
    """AC-3: When no header is supplied, a UUID4 is generated and returned."""
    client = _make_client()
    response = client.get("/ping")
    returned_id = response.headers.get("X-Request-ID")
    assert returned_id is not None
    parsed = uuid.UUID(returned_id)
    assert parsed.version == 4
```

- [ ] **Step 2 *(AC-3)*: Verify tests fail**

```bash
uv run pytest tests/server/test_middleware.py::test_valid_request_id_is_echoed_in_response_header tests/server/test_middleware.py::test_no_request_id_header_generates_uuid4 -v -p no:pdb
```

Expected: `FAILED` — `AssertionError: None != <uuid>`

- [ ] **Step 3 *(AC-3)*: Implement correlation middleware in `headwater.py`**

Add imports at top of file:

```python
import time
import uuid
from contextvars import copy_context
from fastapi import Request, Response
from collections.abc import Callable
```

Add the middleware method to `HeadwaterServer._register_middleware()`, before CORSMiddleware:

```python
def _register_middleware(self):
    from fastapi.middleware.cors import CORSMiddleware
    from headwater_server.server.context import request_id_var

    @self.app.middleware("http")
    async def correlation_middleware(request: Request, call_next: Callable) -> Response:
        # Resolve request_id from header or generate new
        header_value = request.headers.get("X-Request-ID", "")
        request_id: str
        try:
            parsed = uuid.UUID(header_value)
            assert parsed.version == 4
            request_id = header_value
        except (ValueError, AttributeError, AssertionError):
            request_id = str(uuid.uuid4())

        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        start = time.monotonic()
        status_code = 500

        logger.info(
            "request_started",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
            },
        )

        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            logger.info(
                "request_finished",
                extra={
                    "request_id": request_id,
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response

    self.app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

- [ ] **Step 4 *(AC-3)*: Verify tests pass**

```bash
uv run pytest tests/server/test_middleware.py::test_valid_request_id_is_echoed_in_response_header tests/server/test_middleware.py::test_no_request_id_header_generates_uuid4 -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/headwater_server/server/headwater.py tests/server/test_middleware.py
git commit -m "feat: add correlation middleware — mint/validate request_id, emit request_started/finished"
```

---

### Task 5: Middleware — invalid `X-Request-ID` fallback *(AC-4)*

**Files:**
- Modify: `tests/server/test_middleware.py` (append)

- [ ] **Step 1 *(AC-4)*: Write the failing test**

```python
# Append to tests/server/test_middleware.py

import pytest

@pytest.mark.parametrize("bad_value", [
    "not-a-uuid",
    "",
    "12345",
    "550e8400-e29b-11d4-a716-446655440000",  # UUID v1 — invalid for our purposes
])
def test_invalid_request_id_falls_back_to_generated_uuid4(bad_value):
    """AC-4: Invalid X-Request-ID values produce a server-generated UUID4; no error raised."""
    client = _make_client()
    response = client.get("/ping", headers={"X-Request-ID": bad_value})
    assert response.status_code == 200
    returned_id = response.headers.get("X-Request-ID")
    assert returned_id is not None
    assert returned_id != bad_value or bad_value == ""  # always replaced
    parsed = uuid.UUID(returned_id)
    assert parsed.version == 4
```

- [ ] **Step 2 *(AC-4)*: Verify test fails**

```bash
uv run pytest tests/server/test_middleware.py::test_invalid_request_id_falls_back_to_generated_uuid4 -v -p no:pdb
```

Expected: `FAILED` on the UUID v1 case (middleware as written rejects non-v4 via `assert parsed.version == 4`). The other cases should already pass.

- [ ] **Step 3 *(AC-4)*: Verify implementation is correct**

The middleware from Task 4 already handles all these cases via the `try/except (ValueError, AttributeError, AssertionError)` block. No code change needed — this task confirms the implementation is complete.

- [ ] **Step 4 *(AC-4)*: Verify test passes**

```bash
uv run pytest tests/server/test_middleware.py::test_invalid_request_id_falls_back_to_generated_uuid4 -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add tests/server/test_middleware.py
git commit -m "test: verify invalid X-Request-ID header fallback behavior (AC-4)"
```

---

### Task 6: Middleware — concurrent requests carry distinct `request_id` *(AC-2)*

**Files:**
- Modify: `tests/server/test_middleware.py` (append)

- [ ] **Step 1 *(AC-2)*: Write the failing test**

```python
# Append to tests/server/test_middleware.py


def test_two_requests_carry_distinct_request_ids(caplog):
    """AC-2: Two requests produce distinct request_ids; filtering by either yields its own events."""
    import logging
    client = _make_client()

    with caplog.at_level(logging.INFO):
        r1 = client.get("/ping")
        r2 = client.get("/ping")

    id1 = r1.headers["X-Request-ID"]
    id2 = r2.headers["X-Request-ID"]
    assert id1 != id2, "Two sequential requests must have distinct request_ids"

    r1_records = [r for r in caplog.records if getattr(r, "request_id", None) == id1]
    r2_records = [r for r in caplog.records if getattr(r, "request_id", None) == id2]

    assert len(r1_records) >= 2, f"Expected at least request_started+request_finished for id1, got {len(r1_records)}"
    assert len(r2_records) >= 2, f"Expected at least request_started+request_finished for id2, got {len(r2_records)}"

    r1_messages = [r.message for r in r1_records]
    assert "request_started" in r1_messages
    assert "request_finished" in r1_messages

    r2_messages = [r.message for r in r2_records]
    assert "request_started" in r2_messages
    assert "request_finished" in r2_messages
```

- [ ] **Step 2 *(AC-2)*: Verify test fails**

```bash
uv run pytest tests/server/test_middleware.py::test_two_requests_carry_distinct_request_ids -v -p no:pdb
```

Expected: `FAILED` — no `request_id` attribute on records yet (middleware not wired), or `request_started` not found.

If middleware from Task 4 is already working, this may pass. If it does, note "already passing" and commit.

- [ ] **Step 3 *(AC-2)*: Verify test passes**

```bash
uv run pytest tests/server/test_middleware.py::test_two_requests_carry_distinct_request_ids -v
```

Expected: `PASSED`

- [ ] **Step 4: Commit**

```bash
git add tests/server/test_middleware.py
git commit -m "test: verify concurrent request isolation via distinct request_id values (AC-2)"
```

---

### Task 7: `request_id` in 500 error response body *(AC-10)*

**Files:**
- Modify: `src/headwater_server/server/error_handlers.py`
- Modify: `tests/server/test_middleware.py` (append)

- [ ] **Step 1 *(AC-10)*: Write the failing test**

```python
# Append to tests/server/test_middleware.py
from unittest.mock import patch, AsyncMock


def test_request_id_matches_in_500_error_body_and_header():
    """AC-10: On 500, X-Request-ID response header matches request_id in HeadwaterServerError body."""
    from headwater_server.server.headwater import HeadwaterServer

    server = HeadwaterServer()

    @server.app.get("/force-500")
    async def boom():
        raise RuntimeError("deliberate failure")

    client = TestClient(server.app, raise_server_exceptions=False)
    response = client.get("/force-500")

    assert response.status_code == 500
    header_id = response.headers.get("X-Request-ID")
    assert header_id is not None

    body = response.json()
    body_request_id = body.get("request_id")
    assert body_request_id == header_id, (
        f"Header request_id '{header_id}' != body request_id '{body_request_id}'"
    )
```

- [ ] **Step 2 *(AC-10)*: Verify test fails**

```bash
uv run pytest tests/server/test_middleware.py::test_request_id_matches_in_500_error_body_and_header -v -p no:pdb
```

Expected: `FAILED` — `body_request_id` is None (error handler doesn't populate it yet)

- [ ] **Step 3 *(AC-10)*: Update `error_handlers.py` general exception handler**

In `general_exception_handler`, the `request_id` is already read from `request.state`. Verify that the middleware (Task 4) populates `request.state.request_id` before the exception handler runs. If it does, `getattr(request.state, "request_id", None)` already returns the correct value.

Check `HeadwaterServerError.from_general_exception` — confirm it passes `request_id` through to the serialized body. If `HeadwaterServerError` has a `request_id` field, no code change is needed here. If it doesn't, add the field.

Inspect `headwater_api.classes.HeadwaterServerError` to confirm the field exists, then trace that `from_general_exception` calls it:

```python
# In error_handlers.py, general_exception_handler already does:
error = HeadwaterServerError.from_general_exception(
    exc, request, status_code=500, include_traceback=True
)
# request.state.request_id is set by middleware — HeadwaterServerError must read it
```

If `HeadwaterServerError` does not serialize `request_id` in its output, add it:

```python
# In from_general_exception (or the model), ensure:
# request_id=getattr(request.state, "request_id", None)
```

- [ ] **Step 4 *(AC-10)*: Verify test passes**

```bash
uv run pytest tests/server/test_middleware.py::test_request_id_matches_in_500_error_body_and_header -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/headwater_server/server/error_handlers.py tests/server/test_middleware.py
git commit -m "feat: ensure request_id flows from middleware through error handler to response body (AC-10)"
```

---

## Chunk 3: LLM Call Observability

### Task 8: `conduit_generate_service` — happy path log events *(AC-1)*

Replaces the silenced conduit Rich progress display. Emits `llm_call_started` and `llm_call_completed` (or `llm_call_length_truncated` when `stop_reason == LENGTH`).

**Files:**
- Modify: `src/headwater_server/services/conduit_service/conduit_generate_service.py`
- Create: `tests/conduit_service/test_conduit_generate_logging.py`

- [ ] **Step 1 *(AC-1)*: Write the failing test**

```python
# tests/conduit_service/test_conduit_generate_logging.py
from __future__ import annotations

import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_mock_request(model: str = "test-model", content: str = "hello world") -> MagicMock:
    req = MagicMock()
    req.params.model = model
    req.messages = [MagicMock(content=content)]
    req.options.project_name = "test"
    req.use_cache = False
    req.include_history = False
    req.verbosity_override = None
    return req


def _make_mock_response(stop_reason=None) -> MagicMock:
    from conduit.domain.result.response_metadata import StopReason
    meta = MagicMock()
    meta.model_slug = "test-model"
    meta.duration = 1234.5
    meta.input_tokens = 10
    meta.output_tokens = 5
    meta.stop_reason = stop_reason or StopReason.STOP
    meta.cache_hit = False
    resp = MagicMock()
    resp.metadata = meta
    return resp


@pytest.mark.asyncio
async def test_llm_call_started_and_completed_logged(caplog):
    """AC-1: Happy path emits llm_call_started and llm_call_completed at INFO."""
    from headwater_server.services.conduit_service.conduit_generate_service import (
        conduit_generate_service,
    )

    mock_response = _make_mock_response()

    with patch("conduit.core.model.model_async.ModelAsync") as mock_cls, \
         patch("conduit.config.settings") as mock_settings, \
         patch("headwater_server.services.conduit_service.conduit_generate_service.GenerationRequest") as mock_gen_req:

        mock_settings.default_cache.return_value = MagicMock()
        mock_settings.default_repository.return_value = MagicMock()
        mock_gen_req.return_value = MagicMock()
        instance = AsyncMock()
        mock_cls.return_value = instance
        instance.query.return_value = mock_response

        with caplog.at_level(logging.INFO):
            await conduit_generate_service(_make_mock_request())

    messages = [r.message for r in caplog.records]
    assert "llm_call_started" in messages, f"llm_call_started not found in {messages}"
    assert "llm_call_completed" in messages, f"llm_call_completed not found in {messages}"


@pytest.mark.asyncio
async def test_llm_call_completed_carries_metadata_fields(caplog):
    """AC-1: llm_call_completed record contains model, duration_ms, tokens, stop_reason, cache_hit."""
    from headwater_server.services.conduit_service.conduit_generate_service import (
        conduit_generate_service,
    )

    mock_response = _make_mock_response()

    with patch("conduit.core.model.model_async.ModelAsync") as mock_cls, \
         patch("conduit.config.settings") as mock_settings, \
         patch("headwater_server.services.conduit_service.conduit_generate_service.GenerationRequest") as mock_gen_req:

        mock_settings.default_cache.return_value = MagicMock()
        mock_settings.default_repository.return_value = MagicMock()
        mock_gen_req.return_value = MagicMock()
        instance = AsyncMock()
        mock_cls.return_value = instance
        instance.query.return_value = mock_response

        with caplog.at_level(logging.INFO):
            await conduit_generate_service(_make_mock_request())

    completed = next(r for r in caplog.records if r.message == "llm_call_completed")
    assert completed.model == "test-model"
    assert completed.duration_ms == round(1234.5, 1)
    assert completed.input_tokens == 10
    assert completed.output_tokens == 5
    assert completed.cache_hit is False
```

- [ ] **Step 2 *(AC-1)*: Verify tests fail**

```bash
uv run pytest tests/conduit_service/test_conduit_generate_logging.py::test_llm_call_started_and_completed_logged tests/conduit_service/test_conduit_generate_logging.py::test_llm_call_completed_carries_metadata_fields -v -p no:pdb
```

Expected: `FAILED` — `llm_call_started not found`

- [ ] **Step 3 *(AC-1)*: Implement**

Replace `conduit_generate_service.py` with the full implementation from the design doc's conventions example (section 6), plus the existing options-reconstruction logic. The key additions:

```python
from __future__ import annotations
import logging
import time
from headwater_api.classes import GenerationRequest, GenerationResponse
from headwater_server.server.context import request_id_var

logger = logging.getLogger(__name__)


async def conduit_generate_service(request: GenerationRequest) -> GenerationResponse:
    from conduit.core.model.model_async import ModelAsync
    from conduit.utils.progress.verbosity import Verbosity
    from conduit.config import settings
    from rich.console import Console
    from conduit.domain.result.response_metadata import StopReason

    messages = request.messages
    params = request.params
    options = request.options

    project_name = options.project_name
    cache = settings.default_cache(project_name)
    repository = settings.default_repository(project_name)
    console = Console()
    options = options.model_copy(
        update={
            "cache": cache,
            "repository": repository,
            "console": console,
            "verbosity": Verbosity.SILENT,
        }
    )
    request = GenerationRequest(
        messages=messages,
        params=params,
        options=options,
        use_cache=request.use_cache,
        include_history=request.include_history,
        verbosity_override=request.verbosity_override,
    )

    model = params.model
    preview_content = messages[0].content if messages else ""
    prompt_preview = (preview_content or "")[:80] + "..."

    logger.info(
        "llm_call_started",
        extra={
            "model": model,
            "prompt_preview": prompt_preview,
            "request_id": request_id_var.get(),
        },
    )

    start = time.monotonic()
    try:
        response = await ModelAsync(model).query(request)
    except Exception as exc:
        logger.error(
            "llm_call_failed",
            extra={
                "model": model,
                "duration_ms": round((time.monotonic() - start) * 1000, 1),
                "error_type": type(exc).__name__,
                "request_id": request_id_var.get(),
            },
            exc_info=True,
        )
        raise

    if response.metadata is None:
        logger.error(
            "llm_call_failed",
            extra={
                "model": model,
                "duration_ms": round((time.monotonic() - start) * 1000, 1),
                "error_type": "MissingMetadata",
                "request_id": request_id_var.get(),
            },
        )
        raise RuntimeError("ResponseMetadata missing from conduit response")

    meta = response.metadata

    if meta.stop_reason == StopReason.LENGTH:
        logger.warning(
            "llm_call_length_truncated",
            extra={
                "model": meta.model_slug,
                "duration_ms": round(meta.duration, 1),
                "input_tokens": meta.input_tokens,
                "output_tokens": meta.output_tokens,
                "cache_hit": meta.cache_hit,
                "request_id": request_id_var.get(),
            },
        )
    else:
        logger.info(
            "llm_call_completed",
            extra={
                "model": meta.model_slug,
                "duration_ms": round(meta.duration, 1),
                "input_tokens": meta.input_tokens,
                "output_tokens": meta.output_tokens,
                "stop_reason": str(meta.stop_reason),
                "cache_hit": meta.cache_hit,
                "request_id": request_id_var.get(),
            },
        )

    return response
```

- [ ] **Step 4 *(AC-1)*: Verify tests pass**

```bash
uv run pytest tests/conduit_service/test_conduit_generate_logging.py::test_llm_call_started_and_completed_logged tests/conduit_service/test_conduit_generate_logging.py::test_llm_call_completed_carries_metadata_fields -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/headwater_server/services/conduit_service/conduit_generate_service.py tests/conduit_service/test_conduit_generate_logging.py
git commit -m "feat: replace conduit progress display with structured llm_call_started/completed log events"
```

---

### Task 9: `conduit_generate_service` — failure path *(AC-11)*

**Files:**
- Modify: `tests/conduit_service/test_conduit_generate_logging.py` (append)

- [ ] **Step 1 *(AC-11)*: Write the failing test**

```python
# Append to tests/conduit_service/test_conduit_generate_logging.py


@pytest.mark.asyncio
async def test_llm_call_failed_logged_on_exception(caplog):
    """AC-11: When model.query() raises, llm_call_failed is emitted; llm_call_completed is NOT."""
    from headwater_server.services.conduit_service.conduit_generate_service import (
        conduit_generate_service,
    )

    with patch("conduit.core.model.model_async.ModelAsync") as mock_cls, \
         patch("conduit.config.settings") as mock_settings, \
         patch("headwater_server.services.conduit_service.conduit_generate_service.GenerationRequest") as mock_gen_req:

        mock_settings.default_cache.return_value = MagicMock()
        mock_settings.default_repository.return_value = MagicMock()
        mock_gen_req.return_value = MagicMock()
        instance = AsyncMock()
        mock_cls.return_value = instance
        instance.query.side_effect = RuntimeError("model exploded")

        with caplog.at_level(logging.INFO):
            with pytest.raises(RuntimeError, match="model exploded"):
                await conduit_generate_service(_make_mock_request())

    messages = [r.message for r in caplog.records]
    assert "llm_call_failed" in messages, f"llm_call_failed not found in {messages}"
    assert "llm_call_completed" not in messages, "llm_call_completed must not be emitted on failure"

    failed_record = next(r for r in caplog.records if r.message == "llm_call_failed")
    assert failed_record.levelno == logging.ERROR
    assert failed_record.error_type == "RuntimeError"
    assert failed_record.duration_ms > 0
    assert failed_record.exc_info is not None
```

- [ ] **Step 2 *(AC-11)*: Verify test fails**

```bash
uv run pytest tests/conduit_service/test_conduit_generate_logging.py::test_llm_call_failed_logged_on_exception -v -p no:pdb
```

Expected: `FAILED` — `llm_call_failed not found`

- [ ] **Step 3 *(AC-11)*: Verify implementation already covers this**

The failure path was implemented in Task 8's Step 3. Run the test — it should pass without additional changes.

- [ ] **Step 4 *(AC-11)*: Verify test passes**

```bash
uv run pytest tests/conduit_service/test_conduit_generate_logging.py::test_llm_call_failed_logged_on_exception -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add tests/conduit_service/test_conduit_generate_logging.py
git commit -m "test: verify llm_call_failed on exception and absence of llm_call_completed (AC-11)"
```

---

### Task 10: `conduit_generate_service` — LENGTH truncation warning *(AC-12)*

**Files:**
- Modify: `tests/conduit_service/test_conduit_generate_logging.py` (append)

- [ ] **Step 1 *(AC-12)*: Write the failing test**

```python
# Append to tests/conduit_service/test_conduit_generate_logging.py


@pytest.mark.asyncio
async def test_length_truncation_emits_warning_not_completed(caplog):
    """AC-12: stop_reason=LENGTH emits llm_call_length_truncated at WARNING; llm_call_completed NOT emitted."""
    from conduit.domain.result.response_metadata import StopReason
    from headwater_server.services.conduit_service.conduit_generate_service import (
        conduit_generate_service,
    )

    mock_response = _make_mock_response(stop_reason=StopReason.LENGTH)

    with patch("conduit.core.model.model_async.ModelAsync") as mock_cls, \
         patch("conduit.config.settings") as mock_settings, \
         patch("headwater_server.services.conduit_service.conduit_generate_service.GenerationRequest") as mock_gen_req:

        mock_settings.default_cache.return_value = MagicMock()
        mock_settings.default_repository.return_value = MagicMock()
        mock_gen_req.return_value = MagicMock()
        instance = AsyncMock()
        mock_cls.return_value = instance
        instance.query.return_value = mock_response

        with caplog.at_level(logging.DEBUG):
            await conduit_generate_service(_make_mock_request())

    messages = [r.message for r in caplog.records]
    assert "llm_call_length_truncated" in messages, f"llm_call_length_truncated not found in {messages}"
    assert "llm_call_completed" not in messages, "llm_call_completed must not be emitted when stop_reason=LENGTH"

    trunc_record = next(r for r in caplog.records if r.message == "llm_call_length_truncated")
    assert trunc_record.levelno == logging.WARNING
```

- [ ] **Step 2 *(AC-12)*: Verify test fails**

```bash
uv run pytest tests/conduit_service/test_conduit_generate_logging.py::test_length_truncation_emits_warning_not_completed -v -p no:pdb
```

Expected: `FAILED` — `llm_call_length_truncated not found`

- [ ] **Step 3 *(AC-12)*: Verify implementation already covers this**

Task 8's implementation handles this branch. If the test fails, check that the `StopReason.LENGTH` comparison in the service uses the same import as the test (`conduit.domain.result.response_metadata.StopReason`).

- [ ] **Step 4 *(AC-12)*: Verify test passes**

```bash
uv run pytest tests/conduit_service/test_conduit_generate_logging.py::test_length_truncation_emits_warning_not_completed -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add tests/conduit_service/test_conduit_generate_logging.py
git commit -m "test: verify stop_reason=LENGTH triggers WARNING not INFO (AC-12)"
```

---

### Task 11: `conduit_batch_service` — batch events with partial failure *(AC-6)*

**Files:**
- Modify: `src/headwater_server/services/conduit_service/conduit_batch_service.py`
- Create: `tests/conduit_service/test_conduit_batch_logging.py`

- [ ] **Step 1 *(AC-6)*: Write the failing test**

```python
# tests/conduit_service/test_conduit_batch_logging.py
from __future__ import annotations

import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_batch_started_and_completed_logged(caplog):
    """AC-6: batch_started (n=N) and batch_completed (succeeded+failed==N) are emitted."""
    from headwater_server.services.conduit_service.conduit_batch_service import (
        conduit_batch_service,
    )
    from headwater_api.classes import BatchRequest

    mock_batch = MagicMock(spec=BatchRequest)
    mock_batch.prompt_strings_list = ["prompt one", "prompt two", "prompt three"]
    mock_batch.prompt_str = None
    mock_batch.input_variables_list = None
    mock_batch.params.model = "test-model"
    mock_batch.options = MagicMock()
    mock_batch.max_concurrent = 2

    mock_results = [MagicMock(), MagicMock(), MagicMock()]

    with patch(
        "headwater_server.services.conduit_service.conduit_batch_service.ConduitBatchAsync"
    ) as mock_batch_cls:
        mock_instance = AsyncMock()
        mock_batch_cls.return_value = mock_instance
        mock_instance.run.return_value = mock_results

        with caplog.at_level(logging.INFO):
            await conduit_batch_service(mock_batch)

    messages = [r.message for r in caplog.records]
    assert "batch_started" in messages, f"batch_started not found in {messages}"
    assert "batch_completed" in messages, f"batch_completed not found in {messages}"

    started = next(r for r in caplog.records if r.message == "batch_started")
    assert started.n == 3
    assert started.max_concurrent == 2

    completed = next(r for r in caplog.records if r.message == "batch_completed")
    assert completed.succeeded + completed.failed == 3


@pytest.mark.asyncio
async def test_batch_partial_failure_logs_item_failed_and_still_completes(caplog):
    """AC-6: If one item raises, batch_item_failed is emitted and batch_completed still fires."""
    from headwater_server.services.conduit_service.conduit_batch_service import (
        conduit_batch_service,
    )
    from headwater_api.classes import BatchRequest

    mock_batch = MagicMock(spec=BatchRequest)
    mock_batch.prompt_strings_list = ["p1", "p2"]
    mock_batch.prompt_str = None
    mock_batch.input_variables_list = None
    mock_batch.params.model = "test-model"
    mock_batch.options = MagicMock()
    mock_batch.max_concurrent = 2

    error = RuntimeError("item failed")

    with patch(
        "headwater_server.services.conduit_service.conduit_batch_service.ConduitBatchAsync"
    ) as mock_batch_cls:
        mock_instance = AsyncMock()
        mock_batch_cls.return_value = mock_instance
        # Simulate return_exceptions=True — run() returns mix of result and exception
        mock_instance.run.return_value = [MagicMock(), error]

        with caplog.at_level(logging.INFO):
            await conduit_batch_service(mock_batch)

    messages = [r.message for r in caplog.records]
    assert "batch_item_failed" in messages
    assert "batch_completed" in messages

    completed = next(r for r in caplog.records if r.message == "batch_completed")
    assert completed.succeeded == 1
    assert completed.failed == 1

    item_failed = next(r for r in caplog.records if r.message == "batch_item_failed")
    assert item_failed.levelno == logging.ERROR
    assert item_failed.index == 1
    assert item_failed.exc_info is not None
```

- [ ] **Step 2 *(AC-6)*: Verify tests fail**

```bash
uv run pytest tests/conduit_service/test_conduit_batch_logging.py -v -p no:pdb
```

Expected: `FAILED` — `batch_started not found`

- [ ] **Step 3 *(AC-6)*: Implement**

Replace `conduit_batch_service.py`:

```python
from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from headwater_api.classes import BatchRequest, BatchResponse

if TYPE_CHECKING:
    from conduit.domain.conversation.conversation import Conversation

from headwater_server.server.context import request_id_var

logger = logging.getLogger(__name__)


async def conduit_batch_service(batch: BatchRequest) -> BatchResponse:
    from conduit.core.conduit.batch.conduit_batch_async import ConduitBatchAsync
    from conduit.core.prompt.prompt import Prompt

    model = batch.params.model
    n = len(batch.prompt_strings_list or batch.input_variables_list or [])
    request_id = request_id_var.get()

    logger.info(
        "batch_started",
        extra={
            "model": model,
            "n": n,
            "max_concurrent": batch.max_concurrent,
            "request_id": request_id,
        },
    )

    conduit = ConduitBatchAsync(
        prompt=Prompt(batch.prompt_str) if batch.prompt_str else None,
    )

    start = time.monotonic()

    if batch.input_variables_list:
        raw_results = await conduit.run(
            input_variables_list=batch.input_variables_list,
            prompt_strings_list=None,
            params=batch.params,
            options=batch.options,
            max_concurrent=batch.max_concurrent,
        )
    else:
        raw_results = await conduit.run(
            prompt_strings_list=batch.prompt_strings_list,
            input_variables_list=None,
            params=batch.params,
            options=batch.options,
            max_concurrent=batch.max_concurrent,
        )

    duration_ms = round((time.monotonic() - start) * 1000, 1)
    succeeded = 0
    failed = 0
    clean_results: list = []

    for i, result in enumerate(raw_results):
        if isinstance(result, Exception):
            failed += 1
            logger.error(
                "batch_item_failed",
                extra={
                    "model": model,
                    "index": i,
                    "error_type": type(result).__name__,
                    "request_id": request_id,
                },
                exc_info=result,
            )
            clean_results.append(None)
        else:
            succeeded += 1
            clean_results.append(result)

    logger.info(
        "batch_completed",
        extra={
            "model": model,
            "n": n,
            "succeeded": succeeded,
            "failed": failed,
            "duration_ms": duration_ms,
            "request_id": request_id,
        },
    )

    return BatchResponse(results=clean_results)
```

**Note:** `ConduitBatchAsync.run()` currently does NOT use `return_exceptions=True` — it returns a list of `Conversation` objects or raises. The test above assumes it may return exception instances (matching the design spec). If `run()` does not support `return_exceptions`, you may need to wrap each call individually. Verify the actual `ConduitBatchAsync.run()` signature before finalizing.

- [ ] **Step 4 *(AC-6)*: Verify tests pass**

```bash
uv run pytest tests/conduit_service/test_conduit_batch_logging.py -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/headwater_server/services/conduit_service/conduit_batch_service.py tests/conduit_service/test_conduit_batch_logging.py
git commit -m "feat: add batch_started/completed/item_failed log events to conduit_batch_service (AC-6)"
```

---

## Chunk 4: Embeddings + API Schema

### Task 12: `embedding_model.py` — cache hit → DEBUG, eviction → WARNING *(AC-8)*

**Files:**
- Modify: `src/headwater_server/services/embeddings_service/embedding_model.py`
- Create: `tests/services/embeddings_service/test_embedding_model_logging.py`

- [ ] **Step 1 *(AC-8)*: Write the failing tests**

```python
# tests/services/embeddings_service/test_embedding_model_logging.py
from __future__ import annotations

import logging
import threading
from unittest.mock import MagicMock, patch


def _patch_embedding_model_for_logging():
    """Return context managers that prevent real model loading during logging tests."""
    return [
        patch(
            "headwater_server.services.embeddings_service.embedding_model.SentenceTransformer"
        ),
        patch(
            "headwater_server.services.embeddings_service.embedding_model.EmbeddingModelStore.list_models",
            return_value=["test-model"],
        ),
        patch(
            "headwater_server.services.embeddings_service.embedding_model.EmbeddingModelStore.get_spec",
            return_value=MagicMock(),
        ),
    ]


def test_cache_hit_logged_at_debug_not_info(caplog):
    """AC-8: Cache hits on EmbeddingModel.get() are logged at DEBUG, not INFO."""
    from headwater_server.services.embeddings_service.embedding_model import (
        EmbeddingModel,
        _model_cache,
    )

    fake_model = MagicMock(spec=EmbeddingModel)
    _model_cache["test-model"] = fake_model

    try:
        with caplog.at_level(logging.DEBUG):
            EmbeddingModel.get("test-model")

        cache_hit_records = [
            r for r in caplog.records
            if "cache hit" in r.message and r.name.endswith("embedding_model")
        ]
        assert cache_hit_records, "No cache hit record found"
        for r in cache_hit_records:
            assert r.levelno == logging.DEBUG, (
                f"Cache hit logged at {logging.getLevelName(r.levelno)}, expected DEBUG"
            )

        # Confirm nothing appears at INFO
        with caplog.at_level(logging.INFO):
            caplog.clear()
            EmbeddingModel.get("test-model")
        info_cache_hits = [
            r for r in caplog.records
            if "cache hit" in r.message and r.levelno == logging.INFO
        ]
        assert not info_cache_hits, "Cache hit must not appear at INFO level"
    finally:
        _model_cache.pop("test-model", None)


def test_eviction_logged_at_warning(caplog):
    """AC-8: Model eviction from GPU cache is logged at WARNING."""
    import torch
    from headwater_server.services.embeddings_service.embedding_model import (
        EmbeddingModel,
        _model_cache,
    )

    fake_old_model = MagicMock(spec=EmbeddingModel)
    _model_cache["old-model"] = fake_old_model

    patches = _patch_embedding_model_for_logging()
    with patches[0] as mock_st, patches[1], patches[2]:
        mock_st.return_value = MagicMock()
        with patch("torch.cuda.is_available", return_value=False), \
             patch("torch.cuda.empty_cache"), \
             caplog.at_level(logging.DEBUG):
            try:
                EmbeddingModel.get("test-model")
            except Exception:
                pass  # model construction may fail in test — we only care about eviction log

    eviction_records = [
        r for r in caplog.records
        if "evict" in r.message.lower() and r.name.endswith("embedding_model")
    ]
    assert eviction_records, "No eviction log record found"
    for r in eviction_records:
        assert r.levelno == logging.WARNING, (
            f"Eviction logged at {logging.getLevelName(r.levelno)}, expected WARNING"
        )
    _model_cache.pop("test-model", None)
    _model_cache.pop("old-model", None)
```

- [ ] **Step 2 *(AC-8)*: Verify tests fail**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_logging.py -v -p no:pdb
```

Expected: `FAILED` — cache hit at INFO, not DEBUG

- [ ] **Step 3 *(AC-8)*: Implement — update log levels in `embedding_model.py`**

In `EmbeddingModel.get()`, change:

```python
# BEFORE
logger.info("embedding model cache hit: %s", model_name)  # both occurrences
logger.info("evicting model from GPU: %s", name)

# AFTER
logger.debug("embedding model cache hit: %s", model_name)  # both occurrences
logger.warning("evicting model from GPU: %s", name)
```

The two `logger.info("embedding model cache hit: ...")` lines are at lines 160 and 162. Change both to `logger.debug(...)`. The `logger.info("evicting model from GPU: ...")` at line 148 changes to `logger.warning(...)`.

- [ ] **Step 4 *(AC-8)*: Verify tests pass**

```bash
uv run pytest tests/services/embeddings_service/test_embedding_model_logging.py -v
```

Expected: `PASSED`

- [ ] **Step 5 *(AC-8)*: Also demote "Generating embeddings" in `generate_embeddings_service.py`**

In `generate_embeddings_service.py`, change the first log call:

```python
# BEFORE
logger.info("Generating embeddings", extra={...})

# AFTER
logger.debug("Generating embeddings", extra={...})
```

The "embeddings generated" completion event stays at INFO.

- [ ] **Step 6: Commit**

```bash
git add src/headwater_server/services/embeddings_service/embedding_model.py \
        src/headwater_server/services/embeddings_service/generate_embeddings_service.py \
        tests/services/embeddings_service/test_embedding_model_logging.py
git commit -m "fix: cache hits to DEBUG, eviction to WARNING, embedding started to DEBUG (AC-8)"
```

---

### Task 13: `LogEntry` schema and ring buffer `request_id` population *(AC-7)*

**Files:**
- Modify: `../../headwater-api/src/headwater_api/classes/server_classes/logs.py`
- Modify: `src/headwater_server/server/logging_config.py`
- Create: `tests/api/test_logs_endpoint.py`

- [ ] **Step 1 *(AC-7)*: Write the failing test**

```python
# tests/api/test_logs_endpoint.py
from __future__ import annotations

import logging
from fastapi.testclient import TestClient


def test_logs_last_entries_have_request_id_field():
    """AC-7: Every LogEntry in /logs/last response contains a request_id key."""
    from headwater_server.server.headwater import HeadwaterServer

    server = HeadwaterServer()
    client = TestClient(server.app)

    # Generate some log traffic
    client.get("/ping")
    client.get("/ping")

    response = client.get("/logs/last?n=10")
    assert response.status_code == 200

    data = response.json()
    entries = data.get("entries", [])
    assert entries, "No log entries returned — ring buffer may be empty"

    for entry in entries:
        assert "request_id" in entry, (
            f"LogEntry missing request_id field: {entry}"
        )


def test_logs_last_request_scoped_entries_carry_uuid(caplog):
    """AC-7: Entries from request-scoped events carry a UUID4 string as request_id."""
    from headwater_server.server.headwater import HeadwaterServer
    import uuid

    server = HeadwaterServer()
    client = TestClient(server.app)
    client.get("/ping")

    response = client.get("/logs/last?n=20")
    data = response.json()

    request_scoped = [
        e for e in data["entries"]
        if e.get("request_id") not in (None, "system")
    ]
    assert request_scoped, "No request-scoped entries found"

    for entry in request_scoped:
        rid = entry["request_id"]
        try:
            parsed = uuid.UUID(rid)
            assert parsed.version == 4
        except (ValueError, AssertionError):
            raise AssertionError(f"request_id '{rid}' is not a valid UUID4")
```

- [ ] **Step 2 *(AC-7)*: Verify tests fail**

```bash
uv run pytest tests/api/test_logs_endpoint.py -v -p no:pdb
```

Expected: `FAILED` — `LogEntry missing request_id field`

- [ ] **Step 3 *(AC-7)*: Add `request_id` to `LogEntry`**

```python
# headwater-api/src/headwater_api/classes/server_classes/logs.py
from __future__ import annotations
from pydantic import BaseModel


class LogEntry(BaseModel):
    timestamp: float
    level: str
    logger: str
    message: str
    pathname: str
    request_id: str | None = None  # add this field


class LogsLastResponse(BaseModel):
    entries: list[LogEntry]
    total_buffered: int
    capacity: int
```

- [ ] **Step 4 *(AC-7)*: Update `RingBufferHandler.get_records()` in `logging_config.py`**

```python
def get_records(self, n: int) -> list[dict]:
    if n <= 0:
        return []
    records = list(self._buffer)
    return [
        {
            "timestamp": r.created,
            "level": r.levelname,
            "logger": r.name,
            "message": r.getMessage(),
            "pathname": r.pathname,
            "request_id": r.__dict__.get("request_id", None),  # add this line
        }
        for r in records[-n:]
    ]
```

- [ ] **Step 5 *(AC-7)*: Verify tests pass**

```bash
uv run pytest tests/api/test_logs_endpoint.py -v
```

Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add ../../headwater-api/src/headwater_api/classes/server_classes/logs.py \
        src/headwater_server/server/logging_config.py \
        tests/api/test_logs_endpoint.py
git commit -m "feat: add request_id field to LogEntry schema and ring buffer serialization (AC-7)"
```

---

## Final Verification

Run the full test suite to confirm no regressions:

```bash
uv run pytest tests/ -v --ignore=tests/services/test_embeddings_full.py
```

(`test_embeddings_full.py` requires GPU/model weights — skip in CI unless on AlphaBlue.)

Expected: all 13 new tests pass alongside existing tests.

---

## Known Gaps (do not implement)

- **Per-item batch logging** — requires `ConduitBatchAsync` refactor in conduit library. Tracked as follow-on.
- **tqdm stdout suppression** — sentence_transformers tqdm writes directly to stdout, bypassing logging. Out of scope.
- **Bywater** — this plan only covers `headwater.py`. Apply to `bywater_main.py` in a follow-on.
