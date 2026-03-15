# Logging Design — Headwater Server

## 1. Goal

Replace headwater-server's current ad-hoc logging with a disciplined, request-correlated log system. Every log event must be attributable to a request or marked as a system event, third-party noise must be suppressed, and LLM call outcomes must be observable where conduit's progress display previously provided that signal.

## 2. Constraints and Non-Goals

**In scope:**
- `logging_config.py` — fix double-INFO format, suppress third-party loggers
- `server/context.py` — new module; owns `request_id` `ContextVar`
- `server/headwater.py` — request correlation middleware replacing `uvicorn.access`
- `conduit_generate_service.py` — LLM call start/completion logging
- `conduit_batch_service.py` — batch start/completion logging
- `embedding_model.py` — log level corrections (cache hits, evictions)
- `generate_embeddings_service.py` — demote "started" event to DEBUG
- `LogEntry` schema in `headwater_api` — add `request_id` field (nullable, backward compatible)

**Not in scope — do not implement:**
- Per-item logging within `conduit_batch_service.py` — requires conduit library refactor. Acknowledged gap; do not invent a partial implementation.
- Changes to the conduit library itself
- Structured logging libraries (structlog) — stdlib + contextvars is sufficient; do not add this dependency
- Log aggregation, shipping, or external observability tooling
- Authentication or authorization on `/logs/last`
- Changing the ring buffer capacity or rotation policy
- Adding new API endpoints
- Making `SUPPRESSED_LOGGERS` env-configurable — it is hardcoded; do not add configuration
- Suppressing tqdm progress bars from sentence_transformers — tqdm writes directly to stdout, bypassing the logging system; this is a separate concern not addressed here
- Applying this design to `bywater_main.py` — Bywater is out of scope; only `headwater.py` receives the correlation middleware
- Adding `request_id` to the file handler format string — only the ring buffer `LogEntry` schema is updated

## 3. Interface Contracts

### `server/context.py`

```python
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="system")
```

Single public name. No functions. Imported by middleware (to set) and by services (to read). The default `"system"` is used for all events outside a request lifecycle.

---

### Correlation middleware

Added to `HeadwaterServer._register_middleware()` in `headwater.py`. Registered before `CORSMiddleware`.

```python
@app.middleware("http")
async def correlation_middleware(request: Request, call_next: Callable) -> Response:
    ...
```

**Behavior:**
1. Read `X-Request-ID` header. Validate with `uuid.UUID(value)` and check `.version == 4`. On any `ValueError` or missing header, generate `str(uuid.uuid4())`.
2. Store on `request.state.request_id`.
3. `token = request_id_var.set(request_id)` — capture token before try block.
4. Emit `request_started` at INFO (fields: `request_id`, `path`, `method`).
5. Record `start = time.monotonic()`.
6. In `try`: `response = await call_next(request)`. On exception, set `status_code = 500`.
7. In `finally`: emit `request_finished` at INFO (fields: `request_id`, `path`, `method`, `status_code`, `duration_ms`). Call `request_id_var.reset(token)`. Set `X-Request-ID` header on response if response exists.

`request_id_var.reset(token)` MUST be called in `finally`. The `token` variable MUST be assigned before the `try` block to guarantee it is defined when `finally` executes.

---

### Log event field specs

All events use the pattern: snake_case message string, all variable data in `extra={}`. `request_id` is always the last field. `duration_ms` is always a float rounded to 1 decimal place.

#### Correlation middleware events

```
INFO  request_started
  request_id: str
  path: str        # request.url.path
  method: str      # request.method

INFO  request_finished
  request_id: str
  path: str
  method: str
  status_code: int
  duration_ms: float
```

#### LLM call events (`conduit_generate_service.py`)

```
INFO  llm_call_started
  model: str
  prompt_preview: str    # see prompt_preview definition in section 7
  request_id: str

INFO  llm_call_completed
  model: str             # from ResponseMetadata.model_slug
  duration_ms: float     # from ResponseMetadata.duration, rounded to 1dp
  input_tokens: int
  output_tokens: int
  stop_reason: str       # StopReason enum value
  cache_hit: bool
  request_id: str

WARNING  llm_call_length_truncated   # emitted INSTEAD of llm_call_completed when stop_reason == StopReason.LENGTH
  model: str
  duration_ms: float
  input_tokens: int
  output_tokens: int
  cache_hit: bool
  request_id: str

ERROR  llm_call_failed
  model: str
  duration_ms: float     # time.monotonic() delta from call start, rounded to 1dp
  error_type: str        # type(exc).__name__
  request_id: str
  # exc_info=True passed as kwarg to logger.error(), not in extra
```

#### Batch events (`conduit_batch_service.py`)

```
INFO  batch_started
  model: str
  n: int             # total number of prompts submitted
  max_concurrent: int
  request_id: str

INFO  batch_completed
  model: str
  n: int
  succeeded: int
  failed: int
  duration_ms: float
  request_id: str

ERROR  batch_item_failed    # once per failed item; emitted before batch_completed
  model: str
  index: int          # position in the original input list (0-based), same as gather result index
  error_type: str     # type(exc).__name__
  request_id: str
  # exc_info=<exception instance> passed as kwarg to logger.error(), not in extra
```

---

### Third-party logger suppression (`logging_config.py`)

Applied immediately after `basicConfig`. Hardcoded. Not configurable.

```python
SUPPRESSED_LOGGERS = [
    "httpx",
    "httpcore",
    "sentence_transformers",
    "conduit",
    "uvicorn.access",
]

for name in SUPPRESSED_LOGGERS:
    logging.getLogger(name).setLevel(logging.WARNING)
```

`uvicorn.error` is NOT in this list and MUST NOT be added. It handles worker crash and socket error reporting.

---

### RichHandler format string

`RichHandler` must be configured with `format="%(message)s"` to prevent the log level from being embedded in the message string (which causes the double-INFO display). Rich renders the level in its own column.

---

### `LogEntry` schema (`headwater_api`)

Add field:

```python
request_id: str | None = None
```

`RingBufferHandler.get_records()` populates `request_id` from `record.__dict__.get("request_id", None)`. This returns `None` for any log record that did not include `request_id` in `extra={}` — acceptable for third-party library records that pass through at WARNING+.

---

## 4. Acceptance Criteria

- **AC-1:** A single `POST /conduit/generate` request produces exactly 4 INFO-or-above log lines: `request_started`, `llm_call_started`, `llm_call_completed` (or `llm_call_length_truncated`), `request_finished`. No lines from `httpx`, `httpcore`, `conduit`, or `sentence_transformers` loggers appear at INFO.

- **AC-2:** Two concurrent `POST /conduit/generate` requests produce interleaved log lines. Each line carries a `request_id`. The two `request_id` values are distinct. Filtering log lines by either ID yields exactly 4 lines belonging to that request.

- **AC-3:** A client supplying `X-Request-ID: <valid-uuid4>` receives that exact UUID echoed in the `X-Request-ID` response header and present in all 4 log lines for that request.

- **AC-4:** A client supplying an invalid `X-Request-ID` value (non-UUID, empty string, UUID version 1) receives a server-generated UUID4 in the response header. No 400 is returned. No exception is raised.

- **AC-5:** Log lines emitted during server startup (the lifespan `startup` block) carry `request_id="system"`. Verified by checking the `request_id` field in ring buffer entries captured during startup.

- **AC-6:** A `POST /conduit/batch` with N prompts produces a `batch_started` event with `n=N` and a `batch_completed` event with `succeeded + failed == N`. If one item raises, `batch_item_failed` is emitted with `exc_info` populated and `batch_completed` is still emitted.

- **AC-7:** `GET /logs/last?n=10` returns `LogEntry` objects. Every entry has a `request_id` key in its JSON. Entries originating from request-scoped events carry a UUID4 string. Entries from system events carry `"system"`. No entry is missing the key.

- **AC-8:** With log level set to INFO, `embedding_model.py` cache-hit events do not appear in the captured log output. With log level set to DEBUG, they appear at DEBUG. Eviction events appear at WARNING regardless of log level.

- **AC-9:** `uvicorn.access` emits no log lines at any level during a successful `POST /conduit/generate`. `uvicorn.error` remains at its default level and is not suppressed.

- **AC-10:** When a request results in a 500 response, the `request_id` in the `HeadwaterServerError` response body matches the `X-Request-ID` response header and the `request_id` on the `request_finished` log event.

- **AC-11:** `llm_call_completed` is never emitted when `model.query()` raises. `llm_call_failed` is emitted instead, with a non-zero `duration_ms` and `exc_info` populated.

- **AC-12:** When `ResponseMetadata.stop_reason == StopReason.LENGTH`, `llm_call_length_truncated` is emitted at WARNING. `llm_call_completed` is NOT emitted for that call.

---

## 5. Error Handling / Failure Modes

**Middleware exception before `call_next`:** The `token` variable is assigned before the `try` block. If any code between `token` assignment and `call_next` raises, `finally` still resets the ContextVar.

**`call_next` raises:** `status_code` defaults to `500` before the try block. `request_finished` is emitted in `finally` with that status code.

**`response.metadata` is None:** `conduit_generate_service.py` must guard against this. If `response.metadata is None`, log `llm_call_failed` with `error_type="MissingMetadata"` and raise `RuntimeError("ResponseMetadata missing from conduit response")`.

**`request.messages` is empty:** `prompt_preview` construction must guard against empty `messages` list. Use `messages[0].content if messages else ""` before slicing.

**LLM call exception:** `llm_call_failed` is logged with `exc_info=True`, then the original exception is re-raised unmodified. The service does not swallow exceptions.

**Batch partial failure:** `conduit_batch_service.py` uses `asyncio.gather(*coros, return_exceptions=True)`. Results are inspected with `isinstance(result, Exception)`. For each exception: emit `batch_item_failed`. `batch_completed` is emitted after all results are inspected, with accurate counts. `BatchResponse` handling of failed slots is governed by the existing schema — not this spec.

**Invalid client `X-Request-ID`:** Validated with `try: uid = uuid.UUID(header_value); assert uid.version == 4`. On any failure, fall back to `str(uuid.uuid4())`. Silent fallback — no error response, no warning log.

**`run_in_executor` context loss:** `ContextVar` does not propagate into thread pool executor threads. Log lines emitted from within the executor lambda in `generate_embeddings_service.py` will carry whatever the thread's default context provides — not the request's `request_id`. This is a known limitation. Do not attempt to work around it.

---

## 6. Conventions Example

```python
from __future__ import annotations

import logging
import time

from headwater_server.server.context import request_id_var

logger = logging.getLogger(__name__)


async def conduit_generate_service(request: GenerationRequest) -> GenerationResponse:
    from conduit.core.model.model_async import ModelAsync
    from conduit.domain.request.generation_params import StopReason

    model = request.params.model
    messages = request.messages
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
                "stop_reason": meta.stop_reason,
                "cache_hit": meta.cache_hit,
                "request_id": request_id_var.get(),
            },
        )

    return response
```

---

## 7. Domain Language

- **request_id** — a UUID4 string identifying a single HTTP request lifecycle. Value is `"system"` for events outside a request context. Never `None` in log events owned by this spec.
- **system event** — any log event emitted outside a request lifecycle (startup, shutdown, background work). Carries `request_id="system"`.
- **prompt_preview** — the first 80 characters of `messages[0].content`, suffixed with `"..."`. Empty string `""` if `messages` is empty. Never the full prompt. Maximum length: 83 characters (80 + `"..."`).
- **llm_call** — a single invocation of `ModelAsync.query()` within `conduit_generate_service`.
- **batch** — a single invocation of `ConduitBatchAsync.run()` within `conduit_batch_service`. Contains N items.
- **batch_item** — one prompt/response pair within a batch. Per-item success logging is a known gap; do not invent a partial implementation.
- **suppressed logger** — a third-party logger set to WARNING in `logging_config.py`. Not disabled — WARNING and above still surface.
- **correlation middleware** — the FastAPI HTTP middleware that mints or validates `request_id`, sets the `ContextVar`, and emits `request_started`/`request_finished`.
- **duration_ms** — elapsed wall-clock time in milliseconds, always a float, always rounded to 1 decimal place. For LLM calls on success, sourced from `ResponseMetadata.duration`. For LLM calls on failure, computed from `time.monotonic()` delta.

---

## 8. Invalid State Transitions

- `request_id_var` MUST NOT be set outside of `correlation_middleware`. Services only read it.
- `request_id_var` MUST be reset via `request_id_var.reset(token)` in a `finally` block. The token MUST be captured before the `try` block.
- `llm_call_completed` MUST NOT be emitted if `model.query()` raised. Only `llm_call_failed` is permitted in the exception path.
- `llm_call_completed` and `llm_call_length_truncated` are mutually exclusive for a given call. Exactly one is emitted on success.
- `batch_completed` MUST NOT be emitted before all gather results have been inspected. It MUST always be emitted — even if all items failed.
- `uvicorn.error` MUST NOT be added to `SUPPRESSED_LOGGERS`. Only `uvicorn.access` is suppressed.
- `prompt_preview` MUST NOT exceed 83 characters. Do not log full prompt text at any level through this interface.
- `request_id_var.set()` MUST NOT be called more than once per request. Middleware is the sole writer.

---

## Known Gaps

**Per-item batch logging** is not implemented. `conduit_batch_service.py` cannot observe individual item outcomes without changes to `ConduitBatchAsync` in the conduit library. The `BatchReporter` design in conduit's spec describes the intended hook mechanism. This is tracked as a follow-on. The `batch_item_failed` event (on exception) is the only per-item visibility available in this spec.

**tqdm stdout** is not addressed. `sentence_transformers` uses tqdm which writes progress bars directly to stdout, bypassing the logging system. Setting the `sentence_transformers` logger to WARNING does not suppress tqdm output. This requires a separate intervention (`tqdm.disable` or environment variable) and is out of scope.

**Bywater** (`bywater_main.py`) does not receive correlation middleware in this spec. It is a separate server instance with its own entry point; apply this design there in a follow-on.
