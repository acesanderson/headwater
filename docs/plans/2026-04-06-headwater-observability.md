# Headwater Observability

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan.

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

---

## 2. Constraints and Non-Goals

### Constraints
- Router observability endpoints must be registered before the catch-all proxy route, or FastAPI will swallow them
- `/logs/last` on the router reuses the existing `ring_buffer` from `logging_config` — no new handler needed
- `/routes/` returns the parsed `RouterConfig` as JSON, not the raw YAML
- All new client methods are added to both the sync (`HeadwaterClient`) and async (`HeadwaterAsyncClient`) variants
- No new Pydantic models in `headwater-api` unless strictly required — prefer `dict` returns for router-only endpoints

### Non-Goals
- Centralized log aggregation across all subservers
- Log streaming / SSE
- Metrics (Prometheus, etc.)
- Backend health polling from the router (tracked separately in backlog)

---

## 3. Acceptance Criteria

- **AC-1:** `GET /logs/last?n=N` on HeadwaterRouter returns the last N log records from the router's ring buffer, identical shape to the existing headwater-server endpoint
- **AC-2:** `GET /status` on HeadwaterRouter returns server name, uptime, and version — same `StatusResponse` model used by headwater-server
- **AC-3:** `GET /routes/` on HeadwaterRouter returns the full parsed routing config as JSON: `backends`, `routes`, `heavy_models`, and `config_path`
- **AC-4:** The router proxy handler logs the upstream HTTP status code after every proxied request (at DEBUG level)
- **AC-5:** `HeadwaterClient` and `HeadwaterAsyncClient` expose `.get_logs(n=50)`, `.get_status()`, and `.get_routes()` methods that call the corresponding endpoints
- **AC-6:** `.get_routes()` on a client pointed at a subserver (not the router) returns the registered FastAPI routes list (the existing `/routes` endpoint), not the yaml config — the return type is the same `list[dict]` in both cases; callers distinguish by host

---

## 4. Implementation Plan

> Each task maps to exactly one AC. Follow strict Red-Green-Refactor per task.

### Task 1 — Router `/logs/last` *(AC-1)*

**File:** `headwater-server/src/headwater_server/server/router.py`

Register before the catch-all `/{path:path}` route:

```python
@self.app.get("/logs/last")
def logs_last(n: int = Query(default=50, ge=1)):
    from headwater_server.server.logging_config import ring_buffer
    return ring_buffer.get_response(n)
```

Import `Query` from `fastapi`. No new model needed — `ring_buffer.get_response()` already returns a `LogsLastResponse`.

---

### Task 2 — Router `/status` *(AC-2)*

**File:** `headwater-server/src/headwater_server/server/router.py`

Add a `startup_time = time.time()` at module level (mirror of `headwater_api.py`). Register:

```python
@self.app.get("/status", response_model=StatusResponse)
async def status():
    from headwater_server.services.status_service.get_status import get_status_service
    return await get_status_service(startup_time, server_name=self._name)
```

Import `StatusResponse` from `headwater_api.classes`.

---

### Task 3 — Router `/routes/` *(AC-3)*

**File:** `headwater-server/src/headwater_server/server/router.py`

```python
@self.app.get("/routes/")
def routes_config():
    return {
        "backends": self._config.backends,
        "routes": self._config.routes,
        "heavy_models": self._config.heavy_models,
        "config_path": str(ROUTES_YAML_PATH),
    }
```

Note: the existing `/routes` endpoint (no trailing slash) on headwater-server returns the FastAPI route list. The router's `/routes/` (with trailing slash) returns the yaml routing config. These are different endpoints on different servers — no collision.

---

### Task 4 — Log upstream status code in proxy *(AC-4)*

**File:** `headwater-server/src/headwater_server/server/router.py`

After the `upstream = await client.request(...)` call, add a debug log before the return:

```python
logger.debug(
    "proxy_response",
    extra={
        "service": service,
        "backend": backend_url,
        "path": path,
        "upstream_status": upstream.status_code,
        "req_id": request.state.request_id,
    },
)
```

This makes the router logs self-sufficient for triage without needing to query subserver logs for the common case.

---

### Task 5 — Client observability methods *(AC-5 + AC-6)*

**Files:**
- `headwater-client/src/headwater_client/client/headwater_client.py`
- `headwater-client/src/headwater_client/client/headwater_client_async.py`

Add to both client classes:

```python
def get_logs(self, n: int = 50) -> dict:
    return self._transport.get("/logs/last", params={"n": n})

def get_status(self) -> dict:
    return self._transport.get("/status")

def get_routes(self) -> dict | list:
    # Router returns dict (yaml config), subserver returns list (FastAPI routes)
    return self._transport.get("/routes/")
```

Async variant uses `await self._transport.get(...)`.

Return type is `dict | list` for `get_routes()` because the shape differs by server. Document this in the docstring.

---

## 5. Testing Notes

- Router endpoint tests: spin up `HeadwaterRouter` via `TestClient` from `starlette.testclient`, no live server needed
- For `/logs/last`: emit a log record before calling the endpoint and assert it appears in the response
- For `/routes/`: create a temp `routes.yaml` fixture and pass its path to `HeadwaterRouter(config_path=...)`
- For upstream status logging (AC-4): mock `httpx.AsyncClient.request` to return a synthetic response and assert the log record contains `upstream_status`
- Client method tests: mock the transport layer, assert correct path and params are passed

---

## 6. Open Questions

- Should `/routes/` on the router also ping each backend and include reachability status? Deferred — tracked in backlog as "router backend health check".
- Should `LogsLastResponse` be reused for the router `/logs/last` response, or should router logs have a different shape (e.g. include `service` and `backend` fields that subserver logs lack)? Current decision: reuse `LogsLastResponse` for simplicity.
