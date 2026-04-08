# Headwater Observability

**Date:** 2026-04-06
**Status:** Draft

---

## 1. Goal

Close the feedback loop for client/server development by giving HeadwaterRouter parity with HeadwaterServer on observability endpoints, adding a `/routes/` endpoint that exposes the live routing config, ensuring the router logs upstream response codes, and surfacing all observability endpoints as typed methods on HeadwaterClient.

The regression loop this enables:

```
client failure
  → router /logs/last   (routing error? backend unreachable? timeout?)
    → subserver /logs/last  (service error? bad model? validation?)
```

**Implementation status:** All five server-side and client-side features are already implemented. The remaining work is tests — `test_router.py` has no coverage for the new router endpoints or the proxy response log.

### Log record shape

Each entry in `LogsLastResponse.entries` is a `dict` with these keys (used in all test assertions):

| field | type | notes |
|---|---|---|
| `level` | `str` | e.g. `"DEBUG"`, `"INFO"`, `"WARNING"` |
| `message` | `str` | the log message string |
| `extra` | `dict` | arbitrary key/value attached at log-call site |
| `timestamp` | `str` | ISO-8601 string, set by the ring buffer handler |

`LogsLastResponse` fields: `entries: list[dict]`, `total_buffered: int`, `capacity: int`.

---

## 2. Constraints and Non-Goals

### Constraints
- Router observability endpoints must be registered before the catch-all proxy route, or FastAPI will swallow them
- `/logs/last` on the router reuses the existing `ring_buffer` from `logging_config` — no new handler needed; `n` is capped at `le=500` (ring buffer capacity) to prevent oversized queries
- `/routes/` returns a hand-built `dict` from `RouterConfig` dataclass fields (`backends`, `routes`, `heavy_models`, `config_path`) — not a Pydantic model, so `.model_dump()` does not apply
- The router's `/routes/` (trailing slash) and the subserver's `/routes` (no trailing slash) are different endpoints on different servers. FastAPI's `redirect_slashes=True` means `/routes` → 307 → `/routes/` on the router, but on subservers `/routes` is the canonical endpoint. `get_routes()` calls `/routes/` and is router-specific; `list_routes()` calls `/routes` and is subserver-specific
- `startup_time` must be an instance attribute (`self._startup_time`), not a module-level variable — module import time ≠ router startup time, and module-level breaks test isolation
- All new client methods are added to both the sync (`HeadwaterClient`) and async (`HeadwaterAsyncClient`) variants
- No new Pydantic models in `headwater-api` unless strictly required — prefer `dict` returns for router-only endpoints
- Observability endpoints carry no authentication — this is intentional. Do not add auth middleware to these endpoints

### Non-Goals
- Centralized log aggregation across all subservers
- Log streaming / SSE
- Metrics (Prometheus, etc.)
- Backend health polling from the router (tracked separately in backlog)
- Rate limiting on `/logs/last`
- Upper-bounding `n` dynamically based on ring buffer fill level (static `le=500` is sufficient)
- Request correlation IDs or trace propagation — do not add these to proxy log records
- Retry logic or response caching in client methods — thin wrappers only
- Changing `proxy_request` / `proxy_response` log level from DEBUG to INFO — the DEBUG level is intentional
- Modifying or deleting any existing tests in `test_router.py`
- Testing only the sync client variant — both `HeadwaterClient` and `HeadwaterAsyncClient` are required (see AC-5)

---

## 3. Acceptance Criteria

- **AC-1:** `GET /logs/last?n=N` on HeadwaterRouter returns the last N log records from the router's ring buffer (N bounded: `ge=1, le=500`), with identical `LogsLastResponse` shape to the existing headwater-server endpoint
- **AC-2:** `GET /status` on HeadwaterRouter returns server name, uptime, and version using the same `StatusResponse` model as headwater-server; uptime reflects router instance creation time, not module import time
- **AC-3:** `GET /routes/` on HeadwaterRouter returns a JSON object with keys `backends`, `routes`, `heavy_models`, and `config_path` populated from the live `RouterConfig`
- **AC-4:** The router proxy handler emits both a `proxy_request` log record (before forwarding) and a `proxy_response` log record (after receiving the upstream response) at DEBUG level. "After receiving the upstream response" means any completed HTTP exchange — any status code including 4xx/5xx from the upstream counts. The `proxy_response` record's `extra` dict must contain `upstream_status` (int). Connection errors and timeouts that prevent a response do NOT guarantee a `proxy_response` record. Tests must assert `record["level"] == "DEBUG"` and must make at least 2 proxied requests to verify the log fires on each one, not just once.
- **AC-5:** Both `HeadwaterClient` (sync) and `HeadwaterAsyncClient` (async) expose `.get_logs_last(n=50)`, `.get_status()`, and `.get_routes()` methods that call the corresponding endpoints. Both variants must be tested.
- **AC-6:** `get_routes()` returns `dict` when called against the router (yaml routing config) and `list[dict]` when called against a subserver (FastAPI route list). These are different types. Callers can distinguish with `isinstance(result, dict)`. The AC is NOT that the return type is the same — it is explicitly different by design

---

## 4. Implementation Notes

> All server-side and client-side code is already written. Tasks below are test-writing only.

### Existing implementations

Line numbers are approximate and may drift — navigate by function name, not line number.

**Router endpoints** (`headwater-server/src/headwater_server/server/router.py`):
- `GET /logs/last` — ~line 69
- `GET /status` — ~line 74
- `GET /routes/` — ~line 79
- `proxy_request` log — emitted before forwarding, ~line 205
- `proxy_response` log with `upstream_status` — emitted after upstream response, ~line 209

**Client methods** (`headwater-client/src/headwater_client/client/headwater_client.py`):
- `get_logs_last()` — ~line 53
- `get_status()` — ~line 41
- `get_routes()` — ~line 49

**Transport** (`headwater-client/src/headwater_client/transport/headwater_transport.py`):
- `get_logs_last()` — ~line 255
- `get_status()` — ~line 213
- `get_routes()` — ~line 244 (calls `/routes/`)
- `list_routes()` — ~line 229 (calls `/routes`, subserver-only)

---

## 5. Test Plan

> Each task maps to exactly one AC. Follow strict Red-Green-Refactor per task.
> Target file: `headwater-server/tests/server/test_router.py`

### Task 1 — Test router `/logs/last` *(AC-1)*

Spin up `HeadwaterRouter` via `TestClient`. Assert the following cases:

**Empty buffer:** call `/logs/last?n=10` before emitting any logs. Assert:
- Response is 200
- `entries == []`, `total_buffered == 0`, `capacity == 500`

**Non-empty buffer:** emit a known log record (unique message string). Call `/logs/last?n=500` (large enough to guarantee the record is present regardless of other logs). Assert:
- Response is 200
- `LogsLastResponse` shape is valid (has `entries`, `total_buffered`, `capacity`)
- The emitted record appears in `entries` (match on `message` field)
- Each entry has fields: `level`, `message`, `extra`, `timestamp`

**Boundary on n:** emit several records, then call with `n=1`. Assert `len(entries) == 1` (the most recent record). Assert `n=0` returns 422 and `n=501` returns 422.

### Task 2 — Test router `/status` *(AC-2)*

Assert:
- Response is 200 and validates against `StatusResponse`
- `server_name` matches the name passed to `HeadwaterRouter(name=...)`
- `uptime` proves instance-creation time, not module import time: record `t_before = time.monotonic()`, construct the router, record `t_after = time.monotonic()`, then call `/status` and assert `0 < uptime < (t_after - t_before + some_epsilon)`. A test that only checks `uptime > 0` does NOT satisfy this AC.

### Task 3 — Test router `/routes/` *(AC-3)*

Create a temp `routes.yaml` fixture and pass its path to `HeadwaterRouter(config_path=...)`. Assert:
- Response is 200
- Response JSON has keys `backends`, `routes`, `heavy_models`, `config_path`
- Values match the fixture YAML (spot-check one backend URL)
- `config_path` is a string (not a `Path` object — JSON serialization must have converted it)

### Task 4 — Test proxy logs upstream status *(AC-4)*

Mock `httpx.AsyncClient.request` to return a synthetic response. Assert all of the following:

**proxy_request log:** make one proxied request. Assert a record with `message == "proxy_request"` appears in the ring buffer at `level == "DEBUG"`.

**proxy_response log — fires on every request:** mock two requests (e.g., first returns 201, second returns 404). Assert two `proxy_response` records appear (one per request), proving the log fires on every completed HTTP exchange not just the first.

**proxy_response content:** for each record assert:
- `message == "proxy_response"`
- `extra["upstream_status"]` matches the mocked status code
- `level == "DEBUG"`

**non-2xx upstream still logs:** the 404 case above proves this — include it explicitly in the assertion narrative.

### Task 5 — Test client observability methods *(AC-5 + AC-6)*

Target file: `headwater-client/tests/client/test_observability.py` (create if it doesn't exist; do NOT add to `test_transport.py`).

Test both `HeadwaterClient` (sync) and `HeadwaterAsyncClient` (async) — both variants are required.

Mock the transport's HTTP session. Assert for each variant:
- `get_logs_last(n=10)` calls `GET /logs/last` with `?n=10` and returns a `LogsLastResponse`
- `get_status()` calls `GET /status` and returns a `StatusResponse`
- `get_routes()` calls `GET /routes/` (trailing slash — this is router-specific; note the contrast with `list_routes()` which calls `/routes` on subservers)
- When the mocked response body is a `dict`, `get_routes()` returns a `dict` (router case)
- When the mocked response body is a `list`, `get_routes()` returns a `list` (subserver case)

For the async variant, use `pytest.mark.asyncio` and `AsyncMock`.

---

## 6. Production Observability

The observability features are self-referential — the router can observe itself. In production:

- `proxy_request` and `proxy_response` logs are at DEBUG. They are invisible on the console at default `PYTHON_LOG_LEVEL=2` (INFO) but are captured by the ring buffer (which has no level gate). **`GET /logs/last` is the only way to see per-request routing decisions in production without changing the log level.**
- Ring buffer capacity is 500 records. The ring buffer is circular: once full, the oldest records are dropped as new ones arrive. On a busy router this means `/logs/last?n=500` covers only the most recent burst — not all-time history.
- If `/logs/last` returns `entries == []` and `total_buffered == 0`: the ring buffer was never populated. Likely causes: startup failure, import error before logging configured, or no requests have reached the router yet.
- If `/logs/last` returns `entries == []` but `total_buffered > 0`: the ring buffer wrapped and all retained records were below the requested `n`. Increase `n` toward 500.
- Diagnosing upstream errors: scan entries for `proxy_response` records where `extra["upstream_status"] >= 500`. A cluster of these indicates the upstream backend is returning errors. Cross-reference with `proxy_request` records (same timestamp window) to identify which route is failing.

---

## 7. Open Questions

- Should `/routes/` on the router also ping each backend and include reachability status? Deferred — tracked in backlog as "router backend health check".
- Should the ring buffer capacity (500) be configurable via env var? Currently hardcoded. Deferred.
