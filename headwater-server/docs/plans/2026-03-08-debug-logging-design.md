# Design: Debug Logging & `/logs/last` Endpoint

**Date:** 2026-03-08
**Status:** Spec

---

## Motivation

Smoke testing and client-side debugging currently surface only a condensed error message from `HeadwaterServerException`. The full server-side traceback exists in `HeadwaterServerError.traceback` but is silently dropped. Additionally, the log file has grown to 300MB with no rotation or retention policy.

Two targeted fixes address this:

1. **Surface tracebacks on the client** — no new infrastructure required
2. **`GET /logs/last`** — in-memory ring buffer served as a first-class API endpoint

---

## Fix 1: Expose `traceback` in `HeadwaterServerException`

### Problem
`HeadwaterServerError.traceback` is already populated by `from_general_exception(..., include_traceback=True)` and transmitted in the JSON error response. The client deserializes it correctly into `HeadwaterServerError`. But `HeadwaterServerException.__str__` only prints `message`, discarding the traceback.

### Change
**`headwater-api` — `server_classes/exceptions.py`**

Update `HeadwaterServerException.__str__` to append the traceback when present:

```python
def __str__(self):
    base = f"HeadwaterServer {self.server_error.error_type}: {self.server_error.message}"
    if self.server_error.traceback:
        return f"{base}\n\nServer traceback:\n{self.server_error.traceback}"
    return base
```

No schema changes. No new fields. No client or server changes beyond this one method.

---

## Fix 2: `GET /logs/last`

### Architecture

A `RingBufferHandler` is added to the root logger alongside the existing Rich and file handlers. It holds the last N log records in a `collections.deque`. The `/logs/last` endpoint reads directly from this deque — no file I/O, no tail parsing.

### Changes by package

#### `headwater-server` — `logging_config.py`

- Replace `logging.FileHandler` with `logging.handlers.TimedRotatingFileHandler`:
  - `when='midnight'`, `backupCount=30` (30-day retention, auto-culled)
  - Same formatter as current file handler
- Add `RingBufferHandler(capacity=500)`:
  - Subclass of `logging.Handler`
  - Stores `LogRecord`s in a `deque(maxlen=capacity)`
  - Exposes `get_records(n: int) -> list[LogRecord]`
- Export `ring_buffer` as a module-level singleton

#### `headwater-api` — new response class

Add `LogEntry` and `LogsLastResponse` to `server_classes/`:

```python
class LogEntry(BaseModel):
    timestamp: float
    level: str       # "INFO", "WARNING", "ERROR", "DEBUG"
    logger: str      # record.name
    message: str
    pathname: str    # filename:lineno for display

class LogsLastResponse(BaseModel):
    entries: list[LogEntry]
    total_buffered: int
    capacity: int
```

Export from `headwater_api.classes`.

#### `headwater-server` — `headwater_api.py`

Add `GET /logs/last` to `HeadwaterServerAPI.register_routes()`:

```python
@self.app.get("/logs/last", response_model=LogsLastResponse)
def logs_last(n: int = 50):
    from headwater_server.server.logging_config import ring_buffer
    return ring_buffer.get_response(n)
```

`n` is a query param, capped at `capacity` server-side.

#### `headwater-client` — `headwater_api.py` (transport) + `HeadwaterClient`

Add `get_logs_last(n: int = 50) -> LogsLastResponse` to `HeadwaterTransport` and expose it on `HeadwaterClient` directly (not under a sub-API, since it's a server-level concern like `ping` and `get_status`).

---

## Log Rotation Policy

| Setting | Value | Rationale |
|---|---|---|
| Rotation | Daily at midnight | One file per day, easy to navigate |
| Retention | 30 days (`backupCount=30`) | Covers a month of troubleshooting history |
| File naming | `server.log.YYYY-MM-DD` | stdlib default for `TimedRotatingFileHandler` |
| Existing file | Manually deleted before first run | Won't be auto-culled by the new handler |

---

## Files Changed

| Package | File | Change |
|---|---|---|
| `headwater-api` | `server_classes/exceptions.py` | `__str__` exposes traceback |
| `headwater-api` | `server_classes/logs.py` (new) | `LogEntry`, `LogsLastResponse` |
| `headwater-api` | `server_classes/__init__.py` | Export new classes |
| `headwater-api` | `classes/__init__.py` | Re-export new classes |
| `headwater-server` | `server/logging_config.py` | Add `RingBufferHandler`, swap to `TimedRotatingFileHandler`, export `ring_buffer` |
| `headwater-server` | `api/headwater_api.py` | Add `GET /logs/last` route |
| `headwater-client` | `transport/headwater_transport.py` | Add `get_logs_last()` |
| `headwater-client` | `client/headwater_client.py` | Expose `get_logs_last()` |

---

## Non-Goals

- No authentication on `/logs/last` (private server, local network only)
- No SSE / streaming endpoint (ring buffer + polling is sufficient for the debugging use case)
- No log filtering by level or logger name in v1
