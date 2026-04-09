# Headwater TUI Monitor — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two standalone TUI scripts (`hw-log` and `hw-vitals`) that display live Headwater request and hardware metrics on two 7" screens connected to Lasker.

**Architecture:** Two independent Python scripts using Rich `Live` for rendering. `hw-log` polls the router ring buffer every 1s and displays a scrolling request log. `hw-vitals` polls subserver `/gpu` and `/sysinfo` endpoints every 2s and displays GPU/CPU/RAM/Ollama metrics. Both use raw `httpx` (no HeadwaterClient) for Lasker portability. Server-side changes: extend `LogEntry` with an `extra` field, add `route` to `proxy_request` log records, and add a `/sysinfo` endpoint to each subserver.

**Tech Stack:** Python 3.12, `rich>=13`, `httpx>=0.27`, `psutil` (server-side only), `uv run` with inline script metadata for TUI scripts, pytest for all tests.

---

## File Map

**New files:**
- `headwater-server/src/headwater_server/services/status_service/sysinfo_service.py` — psutil CPU/RAM response
- `scripts/tui/hw_log.py` — left-screen TUI script
- `scripts/tui/hw_vitals.py` — right-screen TUI script
- `scripts/tui/tests/__init__.py` — empty
- `scripts/tui/tests/conftest.py` — sys.path bootstrap for test imports
- `scripts/tui/tests/test_hw_log_assembly.py` — row assembly logic tests
- `scripts/tui/tests/test_hw_log_colors.py` — color function tests
- `scripts/tui/tests/test_hw_log_resize.py` — row cap tests
- `scripts/tui/tests/test_hw_vitals_helpers.py` — hw_vitals pure function tests
- `headwater-server/tests/services/test_sysinfo_service.py` — sysinfo service tests
- `headwater-server/tests/api/test_sysinfo_endpoint.py` — /sysinfo endpoint tests

**Modified files:**
- `headwater-api/src/headwater_api/classes/server_classes/logs.py` — add `extra` field to `LogEntry`
- `headwater-server/src/headwater_server/server/logging_config.py` — serialize extra attrs in `get_records()`
- `headwater-server/src/headwater_server/server/routing_config.py` — `resolve_backend()` returns `tuple[str, str]`
- `headwater-server/src/headwater_server/server/router.py` — unpack tuple, log `route` field
- `headwater-server/src/headwater_server/api/headwater_api.py` — wire `/sysinfo` endpoint
- `headwater-server/pyproject.toml` — add `psutil` dependency

---

## Task 1: Extend `LogEntry` with `extra` field and serialize non-standard log attrs *(AC-2, AC-4 prerequisite)*

**Files:**
- Modify: `headwater-api/src/headwater_api/classes/server_classes/logs.py`
- Modify: `headwater-server/src/headwater_server/server/logging_config.py`
- Test: `headwater-server/tests/server/test_logging_config.py`

- [ ] **Step 1: Write the failing tests**

Add to `headwater-server/tests/server/test_logging_config.py`:

```python
def test_log_entry_has_extra_field():
    """LogEntry accepts extra dict with primitive values."""
    from headwater_api.classes.server_classes.logs import LogEntry
    entry = LogEntry(
        timestamp=1.0, level="DEBUG", logger="test", message="msg",
        pathname="/x.py", request_id="abc",
        extra={"service": "conduit", "upstream_status": 200, "model": None},
    )
    assert entry.extra == {"service": "conduit", "upstream_status": 200, "model": None}


def test_log_entry_extra_defaults_to_none():
    """LogEntry.extra is None when not provided (backward compat)."""
    from headwater_api.classes.server_classes.logs import LogEntry
    entry = LogEntry(timestamp=1.0, level="DEBUG", logger="t", message="m", pathname="/p")
    assert entry.extra is None


def test_ring_buffer_extra_serializes_service_field(caplog):
    """Ring buffer get_records() includes 'service' from logger.extra in the LogEntry.extra dict."""
    import logging
    import headwater_server.server.logging_config  # ensure record factory registered
    from headwater_server.server.logging_config import ring_buffer

    before = len(list(ring_buffer._buffer))
    logging.getLogger("test.extra").debug("proxy_request", extra={"service": "conduit", "backend": "http://x:8080"})

    records = ring_buffer.get_records(500)
    new = [r for r in records[before:] if r["message"] == "proxy_request"]
    assert new, "proxy_request record not found in ring buffer"
    assert new[-1].get("extra", {}).get("service") == "conduit"
    assert new[-1].get("extra", {}).get("backend") == "http://x:8080"


def test_ring_buffer_extra_excludes_standard_log_attrs(caplog):
    """Standard LogRecord attributes are not duplicated in extra."""
    import logging
    import headwater_server.server.logging_config
    from headwater_server.server.logging_config import ring_buffer

    before = len(list(ring_buffer._buffer))
    logging.getLogger("test.nodup").debug("sentinel_noduplicate", extra={"my_field": "value"})

    records = ring_buffer.get_records(500)
    new = [r for r in records[before:] if r["message"] == "sentinel_noduplicate"]
    assert new, "record not found"
    extra = new[-1].get("extra") or {}
    # Standard attrs must not appear in extra
    for banned in ("name", "levelname", "pathname", "filename", "lineno", "funcName"):
        assert banned not in extra, f"standard attr '{banned}' leaked into extra"
    assert extra.get("my_field") == "value"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd headwater-server && uv run pytest tests/server/test_logging_config.py::test_log_entry_has_extra_field tests/server/test_logging_config.py::test_log_entry_extra_defaults_to_none tests/server/test_logging_config.py::test_ring_buffer_extra_serializes_service_field tests/server/test_logging_config.py::test_ring_buffer_extra_excludes_standard_log_attrs -v
```

Expected: FAIL — `LogEntry` has no `extra` field.

- [ ] **Step 3: Extend `LogEntry`**

Replace `headwater-api/src/headwater_api/classes/server_classes/logs.py`:

```python
from __future__ import annotations
from pydantic import BaseModel


class LogEntry(BaseModel):
    timestamp: float
    level: str
    logger: str
    message: str
    pathname: str
    request_id: str | None = None
    extra: dict[str, str | int | float | bool | None] | None = None


class LogsLastResponse(BaseModel):
    entries: list[LogEntry]
    total_buffered: int
    capacity: int
```

- [ ] **Step 4: Update `RingBufferHandler.get_records()` to serialize extra attrs**

In `headwater-server/src/headwater_server/server/logging_config.py`, add the constant and update the method. Add the set after the imports, before the `PackagePathFilter` class:

```python
_STANDARD_LOG_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName", "request_id",
    "root_package",  # added by PackagePathFilter
})
```

Replace the `get_records` method in `RingBufferHandler`:

```python
def get_records(self, n: int) -> list[dict]:
    if n <= 0:
        return []
    records = list(self._buffer)
    result = []
    for r in records[-n:]:
        extra = {
            k: v for k, v in r.__dict__.items()
            if k not in _STANDARD_LOG_ATTRS
            and isinstance(v, (str, int, float, bool, type(None)))
        }
        result.append({
            "timestamp": r.created,
            "level": r.levelname,
            "logger": r.name,
            "message": r.getMessage(),
            "pathname": r.pathname,
            "request_id": r.__dict__.get("request_id", None),
            "extra": extra if extra else None,
        })
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd headwater-server && uv run pytest tests/server/test_logging_config.py::test_log_entry_has_extra_field tests/server/test_logging_config.py::test_log_entry_extra_defaults_to_none tests/server/test_logging_config.py::test_ring_buffer_extra_serializes_service_field tests/server/test_logging_config.py::test_ring_buffer_extra_excludes_standard_log_attrs -v
```

Expected: PASS for all four.

- [ ] **Step 6: Verify existing tests still pass**

```bash
cd headwater-server && uv run pytest tests/server/test_logging_config.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add headwater-api/src/headwater_api/classes/server_classes/logs.py \
        headwater-server/src/headwater_server/server/logging_config.py \
        headwater-server/tests/server/test_logging_config.py
git commit -m "feat: extend LogEntry with extra field; serialize non-standard log attrs in ring buffer"
```

---

## Task 2: `resolve_backend()` returns `tuple[str, str]` *(AC-2 prerequisite)*

**Files:**
- Modify: `headwater-server/src/headwater_server/server/routing_config.py`
- Test: `headwater-server/tests/server/test_routing_config.py`

- [ ] **Step 1: Write the failing tests**

Add to `headwater-server/tests/server/test_routing_config.py`:

```python
def test_resolve_backend_returns_tuple_for_conduit(config: RouterConfig):
    """resolve_backend returns (url, route_key) tuple for standard conduit route."""
    result = resolve_backend("conduit", None, config)
    assert isinstance(result, tuple), "Expected tuple, got non-tuple"
    assert len(result) == 2
    url, route_key = result
    assert url == "http://172.16.0.4:8080"
    assert route_key == "conduit"


def test_resolve_backend_returns_tuple_for_heavy_conduit(config: RouterConfig):
    """conduit + heavy model → heavy_inference route key."""
    url, route_key = resolve_backend("conduit", "qwq:latest", config)
    assert url == "http://172.16.0.2:8080"
    assert route_key == "heavy_inference"


def test_resolve_backend_returns_tuple_for_reranker_light(config: RouterConfig):
    """reranker + non-heavy model → reranker_light route key."""
    url, route_key = resolve_backend("reranker", "small-model", config)
    assert route_key == "reranker_light"


def test_resolve_backend_returns_tuple_for_reranker_heavy(config: RouterConfig):
    """reranker + heavy model → reranker_heavy route key."""
    url, route_key = resolve_backend("reranker", "qwq:latest", config)
    assert route_key == "reranker_heavy"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py::test_resolve_backend_returns_tuple_for_conduit tests/server/test_routing_config.py::test_resolve_backend_returns_tuple_for_heavy_conduit tests/server/test_routing_config.py::test_resolve_backend_returns_tuple_for_reranker_light tests/server/test_routing_config.py::test_resolve_backend_returns_tuple_for_reranker_heavy -v
```

Expected: FAIL — current `resolve_backend` returns `str`.

- [ ] **Step 3: Update `resolve_backend` signature and return values**

Replace the `resolve_backend` function in `headwater-server/src/headwater_server/server/routing_config.py`:

```python
def resolve_backend(service: str, model: str | None, config: RouterConfig) -> tuple[str, str]:
    """
    Return (backend_base_url, route_key) for the given service and model.

    Resolution order:
    1. conduit + heavy model → heavy_inference backend
    2. reranker + heavy model → reranker_heavy backend
    3. reranker + light/unknown model → reranker_light backend
    4. all other services → config.routes[service]

    Raises:
        RoutingError: if service has no entry in config.routes.
    """
    is_heavy = model is not None and model in config.heavy_models

    if service == "conduit" and is_heavy:
        route_key = "heavy_inference"
        backend_name = config.routes[route_key]
        return config.backends[backend_name], route_key

    if service == "reranker":
        route_key = "reranker_heavy" if is_heavy else "reranker_light"
        backend_name = config.routes[route_key]
        return config.backends[backend_name], route_key

    if service not in config.routes:
        raise RoutingError(
            f"Unknown service '{service}'. Known services: {sorted(config.routes.keys())}"
        )

    route_key = service
    backend_name = config.routes[service]
    return config.backends[backend_name], route_key
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py::test_resolve_backend_returns_tuple_for_conduit tests/server/test_routing_config.py::test_resolve_backend_returns_tuple_for_heavy_conduit tests/server/test_routing_config.py::test_resolve_backend_returns_tuple_for_reranker_light tests/server/test_routing_config.py::test_resolve_backend_returns_tuple_for_reranker_heavy -v
```

Expected: PASS for all four.

- [ ] **Step 5: Run the full routing_config test suite**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py -v
```

Expected: all pass. Note: existing tests that call `resolve_backend` and compare to a string will break here — fix them by unpacking: `url, _ = resolve_backend(...)`.

- [ ] **Step 6: Commit**

```bash
git add headwater-server/src/headwater_server/server/routing_config.py \
        headwater-server/tests/server/test_routing_config.py
git commit -m "feat: resolve_backend returns (url, route_key) tuple"
```

---

## Task 3: Router logs `route` field in `proxy_request` *(AC-2)*

**Files:**
- Modify: `headwater-server/src/headwater_server/server/router.py`
- Test: `headwater-server/tests/server/test_router.py`

- [ ] **Step 1: Write the failing test**

Add to `headwater-server/tests/server/test_router.py`:

```python
def test_proxy_request_log_includes_route_field(router_client: TestClient):
    """AC-2: proxy_request log record extra dict contains 'route' field with resolved route key."""
    from headwater_server.server.logging_config import ring_buffer
    import logging

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.content = b'{"result": "ok"}'
    mock_response.headers = {}

    before_count = len(list(ring_buffer._buffer))

    with patch("headwater_server.server.router.httpx") as mock_httpx:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.request = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value = mock_async_client

        router_client.post("/conduit/generate", json={"prompt": "hello"})

    records = ring_buffer.get_records(500)
    new_records = records[before_count:]
    proxy_req_records = [r for r in new_records if r["message"] == "proxy_request"]
    assert proxy_req_records, "No proxy_request record found"
    extra = proxy_req_records[-1].get("extra") or {}
    assert "route" in extra, f"'route' missing from proxy_request extra: {extra}"
    assert extra["route"] == "conduit"


def test_proxy_request_log_route_is_heavy_inference_for_heavy_model(router_client: TestClient):
    """AC-2: heavy model routes to heavy_inference; route field reflects this."""
    from headwater_server.server.logging_config import ring_buffer

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.content = b'{}'
    mock_response.headers = {}

    before_count = len(list(ring_buffer._buffer))

    with patch("headwater_server.server.router.httpx") as mock_httpx:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.request = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value = mock_async_client

        router_client.post("/conduit/generate", json={"model": "qwq:latest", "prompt": "think"})

    records = ring_buffer.get_records(500)
    new_records = records[before_count:]
    proxy_req_records = [r for r in new_records if r["message"] == "proxy_request"]
    assert proxy_req_records
    extra = proxy_req_records[-1].get("extra") or {}
    assert extra.get("route") == "heavy_inference"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py::test_proxy_request_log_includes_route_field tests/server/test_router.py::test_proxy_request_log_route_is_heavy_inference_for_heavy_model -v
```

Expected: FAIL — `route` not in extra.

- [ ] **Step 3: Update router.py to unpack tuple and log `route`**

In `headwater-server/src/headwater_server/server/router.py`, in the `proxy` handler, replace the `resolve_backend` call and the `proxy_request` log:

```python
try:
    from headwater_server.server.routing_config import resolve_backend
    backend_url, route_key = resolve_backend(service, model, config)
except RoutingError as exc:
    error = HeadwaterServerError(
        error_type=ErrorType.ROUTING_ERROR,
        message=str(exc),
        status_code=400,
        path=request.url.path,
        method=request.method,
        request_id=request.state.request_id,
    )
    return JSONResponse(status_code=400, content=error.model_dump(mode="json"))
```

And update the `proxy_request` logger.debug call:

```python
logger.debug(
    "proxy_request",
    extra={
        "service": service,
        "backend": backend_url,
        "model": model,
        "path": path,
        "route": route_key,
    },
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py::test_proxy_request_log_includes_route_field tests/server/test_router.py::test_proxy_request_log_route_is_heavy_inference_for_heavy_model -v
```

Expected: PASS.

- [ ] **Step 5: Run the full router test suite**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add headwater-server/src/headwater_server/server/router.py \
        headwater-server/tests/server/test_router.py
git commit -m "feat(AC-2): add route field to proxy_request log records"
```

---

## Task 4: `/sysinfo` endpoint — service and wire-up *(AC-1)*

**Files:**
- Create: `headwater-server/src/headwater_server/services/status_service/sysinfo_service.py`
- Modify: `headwater-server/src/headwater_server/api/headwater_api.py`
- Modify: `headwater-server/pyproject.toml` (add `psutil`)
- Test: `headwater-server/tests/services/test_sysinfo_service.py`
- Test: `headwater-server/tests/api/test_sysinfo_endpoint.py`

- [ ] **Step 1: Add `psutil` to server dependencies**

In `headwater-server/pyproject.toml`, add to the `dependencies` list:

```toml
"psutil>=5.9",
```

Then sync:

```bash
cd headwater-server && uv sync
```

- [ ] **Step 2: Write the failing service test**

Create `headwater-server/tests/services/test_sysinfo_service.py`:

```python
from __future__ import annotations
import pytest


@pytest.mark.asyncio
async def test_sysinfo_returns_required_keys():
    """AC-1: get_sysinfo_service() returns cpu_percent, ram_used_bytes, ram_total_bytes."""
    from headwater_server.services.status_service.sysinfo_service import get_sysinfo_service
    result = await get_sysinfo_service()
    assert "cpu_percent" in result
    assert "ram_used_bytes" in result
    assert "ram_total_bytes" in result


@pytest.mark.asyncio
async def test_sysinfo_cpu_percent_is_float():
    """AC-1: cpu_percent is a float in range [0.0, 100.0]."""
    from headwater_server.services.status_service.sysinfo_service import get_sysinfo_service
    result = await get_sysinfo_service()
    assert isinstance(result["cpu_percent"], float)
    assert 0.0 <= result["cpu_percent"] <= 100.0


@pytest.mark.asyncio
async def test_sysinfo_ram_values_are_positive_ints():
    """AC-1: ram_used_bytes and ram_total_bytes are positive integers."""
    from headwater_server.services.status_service.sysinfo_service import get_sysinfo_service
    result = await get_sysinfo_service()
    assert isinstance(result["ram_used_bytes"], int)
    assert isinstance(result["ram_total_bytes"], int)
    assert result["ram_used_bytes"] > 0
    assert result["ram_total_bytes"] >= result["ram_used_bytes"]
```

- [ ] **Step 3: Run service tests to verify they fail**

```bash
cd headwater-server && uv run pytest tests/services/test_sysinfo_service.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 4: Write the failing endpoint test**

Create `headwater-server/tests/api/test_sysinfo_endpoint.py`:

```python
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


@pytest.fixture
def bywater_client():
    from headwater_server.server.headwater import app
    return TestClient(app)


def test_sysinfo_endpoint_returns_200(bywater_client: TestClient):
    """AC-1: GET /sysinfo returns 200 with required fields."""
    mock_data = {"cpu_percent": 12.4, "ram_used_bytes": 4_000_000_000, "ram_total_bytes": 16_000_000_000}
    with patch(
        "headwater_server.services.status_service.sysinfo_service.get_sysinfo_service",
        new=AsyncMock(return_value=mock_data),
    ):
        resp = bywater_client.get("/sysinfo")
    assert resp.status_code == 200
    body = resp.json()
    assert "cpu_percent" in body
    assert "ram_used_bytes" in body
    assert "ram_total_bytes" in body


def test_sysinfo_endpoint_before_catch_all(bywater_client: TestClient):
    """AC-1: /sysinfo is reachable (not swallowed by any catch-all route)."""
    resp = bywater_client.get("/sysinfo")
    # Any response other than 404/405 is acceptable here
    assert resp.status_code != 404
```

- [ ] **Step 5: Run endpoint tests to verify they fail**

```bash
cd headwater-server && uv run pytest tests/api/test_sysinfo_endpoint.py -v
```

Expected: FAIL — `/sysinfo` returns 404.

- [ ] **Step 6: Create `sysinfo_service.py`**

Create `headwater-server/src/headwater_server/services/status_service/sysinfo_service.py`:

```python
from __future__ import annotations
import logging
import psutil

logger = logging.getLogger(__name__)


async def get_sysinfo_service() -> dict:
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    logger.debug(
        "sysinfo",
        extra={"cpu_percent": cpu_percent, "ram_used_bytes": ram.used},
    )
    return {
        "cpu_percent": float(cpu_percent),
        "ram_used_bytes": int(ram.used),
        "ram_total_bytes": int(ram.total),
    }
```

- [ ] **Step 7: Wire `/sysinfo` into `headwater_api.py`**

In `headwater-server/src/headwater_server/api/headwater_api.py`, add the `/sysinfo` route inside `register_routes()` before the `/gpu` route:

```python
        @self.app.get("/sysinfo")
        async def sysinfo():
            from headwater_server.services.status_service.sysinfo_service import get_sysinfo_service
            return await get_sysinfo_service()
```

- [ ] **Step 8: Run all tests**

```bash
cd headwater-server && uv run pytest tests/services/test_sysinfo_service.py tests/api/test_sysinfo_endpoint.py -v
```

Expected: PASS for all.

- [ ] **Step 9: Commit**

```bash
git add headwater-server/pyproject.toml \
        headwater-server/src/headwater_server/services/status_service/sysinfo_service.py \
        headwater-server/src/headwater_server/api/headwater_api.py \
        headwater-server/tests/services/test_sysinfo_service.py \
        headwater-server/tests/api/test_sysinfo_endpoint.py
git commit -m "feat(AC-1): add /sysinfo endpoint returning cpu_percent, ram_used_bytes, ram_total_bytes"
```

---

## HITL Gate 1 — Deploy server-side changes and verify endpoints

**Deploy:**
```bash
bash scripts/deploy.sh --sync-deps
```

**Verify from caruana:**
```python
from headwater_client.client.headwater_client import HeadwaterClient
bw = HeadwaterClient(host_alias="bywater")
import httpx
resp = httpx.get("http://172.16.0.4:8080/sysinfo", timeout=5)
print(resp.json())   # expect: {"cpu_percent": ..., "ram_used_bytes": ..., "ram_total_bytes": ...}

resp2 = httpx.get("http://172.16.0.2:8080/sysinfo", timeout=5)
print(resp2.json())  # same shape for deepwater

# Trigger a proxied request and inspect ring buffer
router = HeadwaterClient(host_alias="headwater")
router.ping()
logs = router.get_logs_last(n=20)
proxy_req = [e for e in logs.entries if e.message == "proxy_request"]
print(proxy_req[-1].extra)  # expect: {"service": ..., "backend": ..., "route": ..., ...}
```

**Gate passes when:**
- `/sysinfo` returns 200 with all three fields on both bywater and deepwater
- `proxy_request` log entries have `extra.route` populated

**Do not proceed to Task 5 until this gate passes.**

---

## Task 5: `hw_log.py` — logo header and status line *(AC-3)*

**Files:**
- Create: `scripts/tui/hw_log.py`

- [ ] **Step 1: Create `scripts/tui/` directory and the script skeleton**

Create `scripts/tui/hw_log.py`:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["rich>=13", "httpx>=0.27"]
# ///
from __future__ import annotations

import time
from datetime import datetime

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.columns import Columns

# ── Constants ─────────────────────────────────────────────────────────────────

ROUTER_URL = "http://172.16.0.4:8081"
POLL_INTERVAL = 1.0
HEADER_HEIGHT = 9  # 6 logo lines + 1 status + 1 col header + 1 panel border
MAX_PENDING_CYCLES = 3

INTERNAL_PREFIXES = frozenset([
    "/ping", "/status", "/metrics", "/logs/last", "/routes", "/gpu", "/sysinfo",
])
SPECIAL_ROUTES = frozenset(["heavy_inference", "ambient_inference", "reranker_heavy"])

GREEN  = "#4ec9b0"
AMBER  = "#e8c07d"
RED    = "#f44747"
PURPLE = "#c586c0"
BLUE   = "#6a9fb5"
ORANGE = "#ce9178"
YELLOW = "#dcdcaa"
MUTED  = "#333333"

LOGO_LINES = [
    "    ██╗  ██╗███████╗ █████╗ ██████╗ ██╗    ██╗ █████╗ ████████╗███████╗██████╗ ",
    "    ██║  ██║██╔════╝██╔══██╗██╔══██╗██║    ██║██╔══██╗╚══██╔══╝██╔════╝██╔══██╗",
    "    ███████║█████╗  ███████║██║  ██║██║ █╗ ██║███████║   ██║   █████╗  ██████╔╝",
    "    ██╔══██║██╔══╝  ██╔══██║██║  ██║██║███╗██║██╔══██║   ██║   ██╔══╝  ██╔══██╗",
    "    ██║  ██║███████╗██║  ██║██████╔╝╚███╔███╔╝██║  ██║   ██║   ███████╗██║  ██║",
    "    ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝",
]

COL_WIDTHS = {"TIME": 8, "METH": 5, "PATH": 28, "ROUTE": 18, "BACKEND": 12, "MODEL": 16, "ST": 4, "DUR": 7}

# ── Pure helpers ───────────────────────────────────────────────────────────────

def truncate(s: str, width: int) -> str:
    if len(s) <= width:
        return s
    return s[:width - 1] + "…"


def is_internal_path(path: str) -> bool:
    normalized = "/" + path.lstrip("/")
    return any(normalized == p or normalized.startswith(p + "/") for p in INTERNAL_PREFIXES)


def status_color(code: int | None) -> str:
    if code is None:
        return MUTED
    if 200 <= code < 300:
        return GREEN
    if 400 <= code < 500:
        return AMBER
    if 500 <= code < 600:
        return RED
    return "#888888"


def route_color(route_key: str | None) -> str:
    if route_key in SPECIAL_ROUTES:
        return AMBER
    return PURPLE


def compute_row_cap(term_height: int, header_height: int) -> int:
    return max(1, term_height - header_height - 2)


def format_duration(ms: float | None) -> str:
    if ms is None:
        return "—"
    return f"{int(ms)}ms"

# ── Header rendering ───────────────────────────────────────────────────────────

def build_header(console: Console, router_status: str, backend_count: int, last_poll_s: float | None) -> Panel:
    logo_text = Text()
    for i, line in enumerate(LOGO_LINES):
        logo_text.append(line, style=f"bold {GREEN}")
        if i < len(LOGO_LINES) - 1:
            logo_text.append("\n")

    if console.size.width < 76:
        logo_text = Text("HEADWATER", style=f"bold {GREEN}")

    # Status subtitle
    if last_poll_s is None:
        staleness = "connecting…"
        staleness_style = MUTED
    else:
        age = int(time.time() - last_poll_s)
        staleness = f"last poll {age}s ago"
        staleness_style = AMBER if age > 5 else MUTED

    status_color_str = GREEN if router_status == "up" else RED
    status_line = Text()
    status_line.append("router · caruana:8081 · ", style=MUTED)
    status_line.append(router_status, style=status_color_str)
    status_line.append(f" · {backend_count} backends healthy · ", style=MUTED)
    status_line.append(staleness, style=staleness_style)

    combined = Text()
    combined.append_text(logo_text)
    combined.append("\n")
    combined.append_text(status_line)

    return Panel(combined, style="on #0a0a0a", border_style="#1a1a1a")


def main() -> None:
    console = Console()
    router_status = "connecting…"
    backend_count = 0
    last_successful_poll: float | None = None

    with Live(console=console, refresh_per_second=2, screen=False) as live:
        while True:
            header = build_header(console, router_status, backend_count, last_successful_poll)
            live.update(header)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script locally to confirm it renders**

```bash
uv run scripts/tui/hw_log.py
```

Expected: HEADWATER logo in green with status line below, refreshing every second. Press Ctrl-C to exit.

- [ ] **Step 3: Commit**

```bash
git add scripts/tui/hw_log.py
git commit -m "feat(AC-3): hw_log.py skeleton with HEADWATER logo header and status line"
```

---

## HITL Gate 2 — Header-only visual review on Lasker

**Deploy to Lasker:**
```bash
scp scripts/tui/hw_log.py lasker:~/.local/bin/hw_log.py
ssh lasker "uv run ~/.local/bin/hw_log.py"
```

**Assess (you, the user):**
- Block character rendering is crisp — font supports Unicode box-drawing characters
- Logo legibility at viewing distance from the 7" screen
- Font size is appropriate — if logo is too small, try increasing terminal font size or switching emulator
- Status line visible below the logo

**Possible outcomes:**
- Switch terminal emulator (e.g. `foot` → `alacritty`)
- Adjust font size in Sway/emulator config
- Fall back to smaller logo variant (plain `HEADWATER` text instead of block art)

**Do not proceed to Task 6 until this gate passes.**

---

## Task 6: `hw_log.py` — row assembly and internal path filtering *(AC-4, AC-9)*

**Files:**
- Modify: `scripts/tui/hw_log.py`
- Create: `scripts/tui/tests/__init__.py`
- Create: `scripts/tui/tests/conftest.py`
- Create: `scripts/tui/tests/test_hw_log_assembly.py`

- [ ] **Step 1: Create test infrastructure**

Create `scripts/tui/tests/__init__.py` — empty file.

Create `scripts/tui/tests/conftest.py`:

```python
from __future__ import annotations
import sys
from pathlib import Path

# Make hw_log and hw_vitals importable in tests
sys.path.insert(0, str(Path(__file__).parent.parent))
```

Create `scripts/tui/tests/test_hw_log_assembly.py`:

```python
from __future__ import annotations
import time
import hw_log


def make_entry(message: str, request_id: str, extra: dict | None = None, ts: float | None = None) -> dict:
    return {
        "timestamp": ts or time.time(),
        "level": "DEBUG",
        "logger": "router",
        "message": message,
        "pathname": "/x.py",
        "request_id": request_id,
        "extra": extra,
    }


def test_proxy_request_creates_pending_row():
    """AC-4: proxy_request entry creates a pending row keyed by request_id."""
    pending: dict[str, hw_log.PendingRow] = {}
    seen: set[str] = set()
    completed: list[hw_log.PendingRow] = []

    entries = [make_entry("proxy_request", "req-1", {"service": "conduit", "backend": "http://x:8080", "path": "conduit/generate", "route": "conduit", "model": None})]
    hw_log.process_entries(entries, pending, seen, completed)

    assert "req-1" in pending
    assert pending["req-1"].service == "conduit"
    assert pending["req-1"].route == "conduit"
    assert not completed


def test_complete_row_emitted_after_all_three_events():
    """AC-4: row is completed and emitted when proxy_response + request_finished arrive."""
    pending: dict[str, hw_log.PendingRow] = {}
    seen: set[str] = set()
    completed: list[hw_log.PendingRow] = []

    entries = [
        make_entry("proxy_request", "req-2", {"service": "conduit", "backend": "http://x:8080", "path": "conduit/generate", "route": "conduit", "model": None}),
        make_entry("proxy_response", "req-2", {"upstream_status": 200}),
        make_entry("request_finished", "req-2", {"method": "POST", "duration_ms": 312.0}),
    ]
    hw_log.process_entries(entries, pending, seen, completed)

    assert "req-2" not in pending
    assert "req-2" in seen
    assert len(completed) == 1
    row = completed[0]
    assert row.upstream_status == 200
    assert row.method == "POST"
    assert row.duration_ms == 312.0


def test_internal_path_not_added_to_pending():
    """AC-9: proxy_request for /ping is not added to pending rows."""
    pending: dict[str, hw_log.PendingRow] = {}
    seen: set[str] = set()
    completed: list[hw_log.PendingRow] = []

    entries = [make_entry("proxy_request", "req-3", {"service": "ping", "backend": "http://x:8080", "path": "ping", "route": "ping", "model": None})]
    hw_log.process_entries(entries, pending, seen, completed)

    assert "req-3" not in pending
    assert not completed


def test_pending_row_timed_out_after_max_cycles():
    """AC-4: incomplete rows are emitted with None fields after MAX_PENDING_CYCLES poll increments."""
    pending: dict[str, hw_log.PendingRow] = {}
    seen: set[str] = set()
    completed: list[hw_log.PendingRow] = []

    entries = [make_entry("proxy_request", "req-4", {"service": "conduit", "backend": "http://x:8080", "path": "conduit/generate", "route": "conduit", "model": None})]
    hw_log.process_entries(entries, pending, seen, completed)

    # Simulate MAX_PENDING_CYCLES + 1 poll cycles with no response
    for _ in range(hw_log.MAX_PENDING_CYCLES + 1):
        hw_log.process_entries([], pending, seen, completed)

    assert "req-4" not in pending
    assert len(completed) == 1
    assert completed[0].upstream_status is None  # timed out, missing field


def test_already_seen_request_id_ignored():
    """AC-4: duplicate proxy_request for same request_id is ignored."""
    pending: dict[str, hw_log.PendingRow] = {}
    seen: set[str] = set(["req-5"])
    completed: list[hw_log.PendingRow] = []

    entries = [make_entry("proxy_request", "req-5", {"service": "conduit", "backend": "http://x:8080", "path": "conduit/generate", "route": "conduit", "model": None})]
    hw_log.process_entries(entries, pending, seen, completed)

    assert "req-5" not in pending
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/test_hw_log_assembly.py -v
```

Expected: FAIL — `hw_log.PendingRow` and `hw_log.process_entries` not defined.

- [ ] **Step 3: Add `PendingRow` dataclass and `process_entries()` to `hw_log.py`**

Add after the constant definitions, before `build_header`:

```python
from dataclasses import dataclass, field as dc_field
import collections

@dataclass
class PendingRow:
    timestamp: float
    path: str
    service: str
    backend: str
    model: str | None
    route: str | None
    upstream_status: int | None = None
    method: str | None = None
    duration_ms: float | None = None
    cycles: int = 0


def process_entries(
    entries: list[dict],
    pending: dict[str, PendingRow],
    seen: set[str],
    completed: list[PendingRow],
) -> None:
    """Process new log entries; update pending rows; emit completed or timed-out rows."""
    for entry in entries:
        req_id = entry.get("request_id")
        msg = entry.get("message")
        extra = entry.get("extra") or {}

        if msg == "proxy_request" and req_id and req_id not in seen and req_id not in pending:
            path = extra.get("path", "")
            if is_internal_path(path):
                continue
            pending[req_id] = PendingRow(
                timestamp=entry["timestamp"],
                path=path,
                service=extra.get("service", ""),
                backend=extra.get("backend", ""),
                model=extra.get("model"),
                route=extra.get("route"),
            )

        elif msg == "proxy_response" and req_id and req_id in pending:
            status = extra.get("upstream_status")
            if status is not None:
                pending[req_id].upstream_status = int(status)

        elif msg == "request_finished" and req_id and req_id in pending:
            pending[req_id].method = extra.get("method")
            dur = extra.get("duration_ms")
            if dur is not None:
                pending[req_id].duration_ms = float(dur)

    # Emit completed rows (both fields present)
    to_complete = [rid for rid, row in pending.items()
                   if row.upstream_status is not None and row.method is not None]
    for rid in to_complete:
        row = pending.pop(rid)
        seen.add(rid)
        completed.append(row)

    # Age all remaining pending rows by one cycle
    for row in pending.values():
        row.cycles += 1

    # Emit timed-out rows
    timed_out = [rid for rid, row in pending.items() if row.cycles >= MAX_PENDING_CYCLES]
    for rid in timed_out:
        row = pending.pop(rid)
        seen.add(rid)
        completed.append(row)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/test_hw_log_assembly.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/tui/hw_log.py \
        scripts/tui/tests/__init__.py \
        scripts/tui/tests/conftest.py \
        scripts/tui/tests/test_hw_log_assembly.py
git commit -m "feat(AC-4,AC-9): hw_log row assembly with pending dict and internal path filtering"
```

---

## Task 7: `hw_log.py` — color coding for status and route columns *(AC-5, AC-6)*

**Files:**
- Modify: `scripts/tui/hw_log.py` — add `build_log_table()`, wire rows into Live display
- Create: `scripts/tui/tests/test_hw_log_colors.py`

- [ ] **Step 1: Write the failing tests**

Create `scripts/tui/tests/test_hw_log_colors.py`:

```python
from __future__ import annotations
import hw_log


def test_status_color_2xx():
    """AC-5: 2xx status codes are green."""
    assert hw_log.status_color(200) == "#4ec9b0"
    assert hw_log.status_color(201) == "#4ec9b0"


def test_status_color_4xx():
    """AC-5: 4xx status codes are amber."""
    assert hw_log.status_color(400) == "#e8c07d"
    assert hw_log.status_color(404) == "#e8c07d"


def test_status_color_5xx():
    """AC-5: 5xx status codes are red."""
    assert hw_log.status_color(500) == "#f44747"
    assert hw_log.status_color(503) == "#f44747"


def test_status_color_none():
    """AC-5: None status (incomplete row) is muted."""
    assert hw_log.status_color(None) == hw_log.MUTED


def test_route_color_standard():
    """AC-6: Standard route key returns purple."""
    assert hw_log.route_color("conduit") == "#c586c0"
    assert hw_log.route_color("siphon") == "#c586c0"
    assert hw_log.route_color("embeddings") == "#c586c0"


def test_route_color_special():
    """AC-6: Special route keys return amber."""
    assert hw_log.route_color("heavy_inference") == "#e8c07d"
    assert hw_log.route_color("ambient_inference") == "#e8c07d"
    assert hw_log.route_color("reranker_heavy") == "#e8c07d"


def test_route_color_none():
    """AC-6: None route key (timed-out row) returns purple (not amber)."""
    assert hw_log.route_color(None) == "#c586c0"


def test_truncate_short_string():
    assert hw_log.truncate("hello", 10) == "hello"


def test_truncate_long_string():
    result = hw_log.truncate("conduit/generate_with_context", 20)
    assert len(result) == 20
    assert result.endswith("…")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/test_hw_log_colors.py -v
```

Expected: most PASS (pure functions already exist), but verify all pass. If any fail, fix the implementation.

- [ ] **Step 3: Add `build_log_table()` to `hw_log.py`**

Add the table-building function and update `main()` to render rows:

```python
def build_log_table(rows: list[PendingRow]) -> Table:
    """Build a Rich table from completed rows. Most-recent row is last."""
    table = Table(
        show_header=True,
        header_style=f"dim {MUTED}",
        box=None,
        padding=(0, 1, 0, 0),
        expand=True,
    )
    table.add_column("TIME",    style=MUTED,   width=COL_WIDTHS["TIME"],    no_wrap=True)
    table.add_column("METH",   style=GREEN,   width=COL_WIDTHS["METH"],    no_wrap=True)
    table.add_column("SERVICE/PATH", style=YELLOW, width=COL_WIDTHS["PATH"], no_wrap=True)
    table.add_column("ROUTE",  width=COL_WIDTHS["ROUTE"],   no_wrap=True)
    table.add_column("BACKEND", style=BLUE,   width=COL_WIDTHS["BACKEND"], no_wrap=True)
    table.add_column("MODEL",  style=ORANGE,  width=COL_WIDTHS["MODEL"],   no_wrap=True)
    table.add_column("ST",     width=COL_WIDTHS["ST"],      no_wrap=True)
    table.add_column("DUR",    style=MUTED,   width=COL_WIDTHS["DUR"],     no_wrap=True)

    for row in rows:
        ts = datetime.fromtimestamp(row.timestamp).strftime("%H:%M:%S")
        route_str = truncate(row.route or "—", COL_WIDTHS["ROUTE"])
        rc = route_color(row.route)
        st_str = str(row.upstream_status) if row.upstream_status is not None else "—"
        sc = status_color(row.upstream_status)
        backend_short = row.backend.split("//")[-1].split(":")[0]  # "172.16.0.4" → host only

        table.add_row(
            ts,
            row.method or "—",
            truncate(row.path, COL_WIDTHS["PATH"]),
            f"[{rc}]{route_str}[/{rc}]",
            f"→ {backend_short}",
            truncate(row.model or "—", COL_WIDTHS["MODEL"]),
            f"[{sc}]{st_str}[/{sc}]",
            format_duration(row.duration_ms),
        )
    return table
```

- [ ] **Step 4: Run color tests to verify all pass**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/test_hw_log_colors.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/tui/hw_log.py scripts/tui/tests/test_hw_log_colors.py
git commit -m "feat(AC-5,AC-6): hw_log color coding for status codes and route keys"
```

---

## Task 8: `hw_log.py` — row cap and terminal resize *(AC-8)*

**Files:**
- Modify: `scripts/tui/hw_log.py` — add `compute_row_cap()` and enforce cap on row deque
- Create: `scripts/tui/tests/test_hw_log_resize.py`

- [ ] **Step 1: Write the failing tests**

Create `scripts/tui/tests/test_hw_log_resize.py`:

```python
from __future__ import annotations
import hw_log


def test_compute_row_cap_normal():
    """AC-8: Standard 40-line terminal yields positive cap."""
    cap = hw_log.compute_row_cap(40, hw_log.HEADER_HEIGHT)
    assert cap > 0
    assert cap == 40 - hw_log.HEADER_HEIGHT - 2


def test_compute_row_cap_minimum_is_one():
    """AC-8: Tiny terminals clamp to at least 1 row."""
    cap = hw_log.compute_row_cap(5, hw_log.HEADER_HEIGHT)
    assert cap == 1


def test_compute_row_cap_exact_boundary():
    """AC-8: Terminal exactly header_height + 3 yields 1 row."""
    cap = hw_log.compute_row_cap(hw_log.HEADER_HEIGHT + 3, hw_log.HEADER_HEIGHT)
    assert cap == 1
```

- [ ] **Step 2: Run tests to verify they fail (or pass — `compute_row_cap` already exists)**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/test_hw_log_resize.py -v
```

If these already pass (the function exists), continue. If they fail, the function is missing — verify it's present in the constants section.

- [ ] **Step 3: Update `main()` to enforce row cap via deque**

Replace the `main()` function in `hw_log.py` with the full version that enforces the row cap:

```python
def main() -> None:
    console = Console()
    router_status = "UNREACHABLE"
    backend_count = 0
    last_successful_poll: float | None = None

    pending: dict[str, PendingRow] = {}
    seen: set[str] = set()
    row_deque: collections.deque[PendingRow] = collections.deque()
    last_seen_ts: float = 0.0

    with Live(console=console, refresh_per_second=2, screen=False) as live:
        while True:
            term_height = console.size.height
            row_cap = compute_row_cap(term_height, HEADER_HEIGHT)

            try:
                resp = httpx.get(f"{ROUTER_URL}/logs/last?n=100", timeout=3.0)
                resp.raise_for_status()
                data = resp.json()
                router_status = "up"
                last_successful_poll = time.time()

                # Count healthy backends from status endpoint (best-effort)
                try:
                    s = httpx.get(f"{ROUTER_URL}/status", timeout=2.0)
                    status_data = s.json()
                    backend_count = status_data.get("backend_count", backend_count)
                except Exception:
                    pass

                entries = data.get("entries", [])
                new_entries = [e for e in entries if e.get("timestamp", 0) > last_seen_ts]
                if new_entries:
                    last_seen_ts = max(e["timestamp"] for e in new_entries)

                completed: list[PendingRow] = []
                process_entries(new_entries, pending, seen, completed)

                for row in completed:
                    row_deque.append(row)

            except Exception:
                router_status = "UNREACHABLE"

            # Trim deque to current row cap
            while len(row_deque) > row_cap:
                row_deque.popleft()

            header = build_header(console, router_status, backend_count, last_successful_poll)
            table = build_log_table(list(row_deque))
            from rich.console import Group
            live.update(Group(header, table))

            time.sleep(POLL_INTERVAL)
```

- [ ] **Step 4: Run resize tests**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/test_hw_log_resize.py -v
```

Expected: all PASS.

- [ ] **Step 5: Smoke-test the script locally**

```bash
uv run scripts/tui/hw_log.py
```

Expected: logo header renders, table appears below with column headers. If the router is running, real rows should appear.

- [ ] **Step 6: Commit**

```bash
git add scripts/tui/hw_log.py scripts/tui/tests/test_hw_log_resize.py
git commit -m "feat(AC-8): hw_log row cap enforced from terminal height; resize recalculates cap"
```

---

## HITL Gate 3 — Full `hw-log` with live rows, color, and filtering on Lasker

**Deploy:**
```bash
scp scripts/tui/hw_log.py lasker:~/.local/bin/hw_log.py
ssh lasker "uv run ~/.local/bin/hw_log.py"
```

**While the script runs, send a few real requests through the router from another session.**

**Assess:**
- Rows appear within ~2 seconds of requests being sent
- Column widths hold — no wrapping or truncation of short paths
- Status codes green/amber/red correctly (trigger a 503 to test red)
- `heavy_inference` route shows in amber; `conduit` shows in purple
- `/ping` requests do not appear (send one manually to verify)
- 1s refresh rate is acceptable — no visible flicker on Lasker's display

**Possible outcomes:**
- Adjust column widths for real-world path lengths
- Change poll interval
- Color value tweaks
- Escalate to Textual if Rich Live flicker is unacceptable on that terminal emulator

**Do not proceed to Task 9 until this gate passes.**

---

## Task 9: `hw_log.py` — unreachable router handling and staleness indicator *(AC-7)*

**Files:**
- Modify: `scripts/tui/hw_log.py` — UNREACHABLE state, staleness amber after 5s

No new test file needed — the behavior is visible in Gate 3. The `UNREACHABLE` path is already present in the main loop from Task 8. This task verifies it and adds the amber staleness indicator.

- [ ] **Step 1: Verify unreachable behavior manually**

With hw_log.py running, temporarily block router access (or point `ROUTER_URL` to a bad address) and observe:
- Status line shows `UNREACHABLE` in red
- Existing rows remain visible
- Script does not crash

If the behavior is correct from Task 8's implementation, proceed.

- [ ] **Step 2: Verify staleness indicator turns amber after 5s**

The `build_header()` function already implements this: `staleness_style = AMBER if age > 5 else MUTED`. Verify the `last_poll_s` threshold matches the spec (5 seconds for hw-log).

Confirm in `build_header()`:
```python
staleness_style = AMBER if age > 5 else MUTED
```

This is already present. No code change needed.

- [ ] **Step 3: Commit if any changes were made**

If no changes, skip commit. If staleness threshold was wrong and was fixed:

```bash
git add scripts/tui/hw_log.py
git commit -m "fix(AC-7): staleness indicator turns amber after 5s; UNREACHABLE state persists last rows"
```

---

## Task 10: `hw_log.py` — complete the script and integrate `Group` render *(AC-3, AC-7, AC-8 integration)*

**Files:**
- Modify: `scripts/tui/hw_log.py` — ensure `Group` import is at top level, not inside loop

- [ ] **Step 1: Move `Group` import to top of file**

Move the import from inside `main()` to the top-level imports in `hw_log.py`:

```python
from rich.console import Console, Group
```

Remove the inline `from rich.console import Group` inside `main()`.

- [ ] **Step 2: Run the script end-to-end**

```bash
uv run scripts/tui/hw_log.py
```

Expected: no import errors, logo renders, rows appear from real traffic if router is running.

- [ ] **Step 3: Run all hw_log tests together**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add scripts/tui/hw_log.py
git commit -m "refactor: move Group import to module level in hw_log.py"
```

---

## Task 11: `hw_vitals.py` — panel layout with mock data *(AC-10)*

**Files:**
- Create: `scripts/tui/hw_vitals.py`
- Create: `scripts/tui/tests/test_hw_vitals_helpers.py`

- [ ] **Step 1: Write the failing helper tests**

Create `scripts/tui/tests/test_hw_vitals_helpers.py`:

```python
from __future__ import annotations
import hw_vitals


def test_temp_color_green():
    """AC-11: Temperature below 70°C is green."""
    assert hw_vitals.temp_color(50) == "#4ec9b0"
    assert hw_vitals.temp_color(69) == "#4ec9b0"


def test_temp_color_amber():
    """AC-11: Temperature 70–85°C is amber."""
    assert hw_vitals.temp_color(70) == "#e8c07d"
    assert hw_vitals.temp_color(85) == "#e8c07d"


def test_temp_color_red():
    """AC-11: Temperature above 85°C is red."""
    assert hw_vitals.temp_color(86) == "#f44747"
    assert hw_vitals.temp_color(95) == "#f44747"


def test_metric_color_gpu_green():
    """AC-11: GPU util below 60% is green."""
    assert hw_vitals.metric_color(50, "gpu") == "#4ec9b0"


def test_metric_color_gpu_amber():
    """AC-11: GPU util 60–85% is amber."""
    assert hw_vitals.metric_color(75, "gpu") == "#e8c07d"


def test_metric_color_gpu_red():
    """AC-11: GPU util above 85% is red."""
    assert hw_vitals.metric_color(90, "gpu") == "#f44747"


def test_metric_color_vram_thresholds():
    """AC-11: VRAM thresholds are 70/90."""
    assert hw_vitals.metric_color(65, "vram") == "#4ec9b0"
    assert hw_vitals.metric_color(80, "vram") == "#e8c07d"
    assert hw_vitals.metric_color(95, "vram") == "#f44747"


def test_metric_color_cpu_thresholds():
    """AC-11: CPU thresholds are 60/80."""
    assert hw_vitals.metric_color(50, "cpu") == "#4ec9b0"
    assert hw_vitals.metric_color(70, "cpu") == "#e8c07d"
    assert hw_vitals.metric_color(85, "cpu") == "#f44747"


def test_mb_to_gb():
    """GpuInfo uses MB; display in GB."""
    assert hw_vitals.mb_to_gb(4096) == pytest.approx(4.0, rel=0.01)
    assert hw_vitals.mb_to_gb(16384) == pytest.approx(16.0, rel=0.01)


def test_bytes_to_gb():
    """sysinfo returns bytes; display in GB."""
    assert hw_vitals.bytes_to_gb(17_179_869_184) == pytest.approx(16.0, rel=0.01)


def test_format_uptime_days_hours():
    assert hw_vitals.format_uptime(2 * 86400 + 4 * 3600) == "2d 4h"


def test_format_uptime_hours_only():
    assert hw_vitals.format_uptime(3 * 3600) == "0d 3h"


import pytest
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/test_hw_vitals_helpers.py -v
```

Expected: FAIL — `hw_vitals` module not found.

- [ ] **Step 3: Create `scripts/tui/hw_vitals.py` with mock panel layout**

Create `scripts/tui/hw_vitals.py`:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["rich>=13", "httpx>=0.27"]
# ///
from __future__ import annotations

import time

import httpx
from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.progress import ProgressBar

# ── Constants ─────────────────────────────────────────────────────────────────

BYWATER_URL  = "http://172.16.0.4:8080"
DEEPWATER_URL = "http://172.16.0.2:8080"
ROUTER_URL   = "http://172.16.0.4:8081"
POLL_INTERVAL = 2.0

GREEN  = "#4ec9b0"
AMBER  = "#e8c07d"
RED    = "#f44747"
BLUE   = "#9cdcfe"
ORANGE = "#ce9178"
MUTED  = "#555555"
DIM    = "#333333"

# Color thresholds
_GPU_THRESHOLDS  = (60, 85)
_VRAM_THRESHOLDS = (70, 90)
_CPU_THRESHOLDS  = (60, 80)
_TEMP_THRESHOLDS = (70, 85)

# ── Pure helpers ───────────────────────────────────────────────────────────────

def temp_color(celsius: int | None) -> str:
    if celsius is None:
        return MUTED
    if celsius > _TEMP_THRESHOLDS[1]:
        return RED
    if celsius >= _TEMP_THRESHOLDS[0]:
        return AMBER
    return GREEN


def metric_color(pct: float, kind: str) -> str:
    """Return color for a percentage metric. kind: 'gpu', 'vram', 'cpu'."""
    thresholds = {
        "gpu": _GPU_THRESHOLDS,
        "vram": _VRAM_THRESHOLDS,
        "cpu": _CPU_THRESHOLDS,
    }.get(kind, (60, 80))
    if pct > thresholds[1]:
        return RED
    if pct >= thresholds[0]:
        return AMBER
    return GREEN


def mb_to_gb(mb: int) -> float:
    return mb / 1024.0


def bytes_to_gb(b: int) -> float:
    return b / (1024 ** 3)


def format_uptime(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    return f"{days}d {hours}h"


def compute_req_per_s(
    entries: list[dict],
    backend_url: str,
    now: float,
    start_time: float,
) -> float:
    window = 60.0
    cutoff = now - window
    count = sum(
        1 for e in entries
        if e.get("message") == "proxy_response"
        and (e.get("extra") or {}).get("backend") == backend_url
        and e.get("timestamp", 0) > cutoff
    )
    elapsed = min(window, now - start_time)
    return count / elapsed if elapsed > 0 else 0.0


def compute_error_count(
    entries: list[dict],
    backend_url: str,
    now: float,
) -> int:
    cutoff = now - 60.0
    return sum(
        1 for e in entries
        if e.get("message") == "proxy_response"
        and (e.get("extra") or {}).get("backend") == backend_url
        and (e.get("extra") or {}).get("upstream_status", 0) >= 400
        and e.get("timestamp", 0) > cutoff
    )


# ── Panel builders ─────────────────────────────────────────────────────────────

def build_backend_panel(
    name: str,
    hostname: str,
    gpu_name: str,
    uptime_s: float | None,
    gpu_pct: int | None,
    vram_used_mb: int | None,
    vram_total_mb: int | None,
    temp_c: int | None,
    cpu_pct: float | None,
    ram_used_bytes: int | None,
    ram_total_bytes: int | None,
    ollama_models: list[dict],
    req_per_s: float,
    error_count: int,
    offline: bool = False,
) -> Panel:
    t = Text()

    if offline:
        t.append(f"{name}  ✕  OFFLINE\n", style=f"bold {RED}")
        t.append(f"{hostname}\n", style=MUTED)
        t.append("GPU  —\nVRAM  —\nCPU  —\nRAM  —\n", style=MUTED)
        t.append("OLLAMA  —\n", style=MUTED)
        return Panel(t, title=f"[{RED}]{name}[/{RED}]", border_style=RED)

    tc = temp_color(temp_c)
    temp_str = f"{temp_c}°C" if temp_c is not None else "—"
    uptime_str = format_uptime(uptime_s) if uptime_s is not None else "—"

    # Header
    t.append(f"{name}  ", style=f"bold {BLUE}")
    t.append("● ", style=f"bold {tc}")
    t.append(f"{temp_str}\n", style=tc)
    t.append(f"{hostname} · {gpu_name} · up {uptime_str}\n", style=MUTED)
    t.append("\n")

    def metric_row(label: str, pct: float | None, used: str, total: str, kind: str) -> None:
        mc = metric_color(pct or 0, kind)
        t.append(f"{label:<10}", style=MUTED)
        bar_fill = int((pct or 0) / 100 * 20)
        t.append("█" * bar_fill, style=mc)
        t.append("░" * (20 - bar_fill), style=DIM)
        t.append(f"  {pct or '—'}%  {used}/{total}\n", style=mc)

    if gpu_pct is not None and vram_used_mb is not None and vram_total_mb is not None:
        metric_row("GPU UTIL", gpu_pct, f"{mb_to_gb(vram_used_mb):.1f}", f"{mb_to_gb(vram_total_mb):.1f} GB", "gpu")
        vram_pct = int(vram_used_mb / vram_total_mb * 100) if vram_total_mb else 0
        metric_row("VRAM", vram_pct, f"{mb_to_gb(vram_used_mb):.1f}", f"{mb_to_gb(vram_total_mb):.1f} GB", "vram")
    else:
        t.append("GPU  —\nVRAM  —\n", style=MUTED)

    if cpu_pct is not None and ram_used_bytes is not None and ram_total_bytes is not None:
        metric_row("CPU UTIL", cpu_pct, f"{bytes_to_gb(ram_used_bytes):.1f}", f"{bytes_to_gb(ram_total_bytes):.1f} GB", "cpu")
        ram_pct = int(ram_used_bytes / ram_total_bytes * 100) if ram_total_bytes else 0
        metric_row("RAM", ram_pct, f"{bytes_to_gb(ram_used_bytes):.1f}", f"{bytes_to_gb(ram_total_bytes):.1f} GB", "cpu")
    else:
        t.append("CPU  —\nRAM  —\n", style=MUTED)

    t.append("\n")
    t.append("OLLAMA\n", style=MUTED)
    if ollama_models:
        for m in ollama_models:
            model_name = m.get("name", "—")
            size_gb = mb_to_gb(m.get("size_mb", 0))
            cpu = m.get("cpu_pct", 0)
            gpu = m.get("vram_pct", 0)
            t.append(f"  {model_name}  {size_gb:.1f} GB", style=ORANGE)
            if cpu >= 1:
                t.append(f"  {int(cpu)}% cpu", style=AMBER)
            t.append(f"  {int(gpu)}% gpu\n", style=metric_color(gpu, "gpu"))
            err_style = RED if error_count > 0 else MUTED
            t.append(f"  {req_per_s:.1f} req/s · ", style=MUTED)
            t.append(f"{error_count} err\n", style=err_style)
    else:
        t.append("  no models loaded\n", style=MUTED)

    return Panel(t, title=f"[{BLUE}]{name}[/{BLUE}]", border_style="#2a2a2a")


def build_router_status_bar(router_up: bool, backend_count: int, total_backends: int, last_poll_s: float | None) -> Text:
    t = Text()
    if last_poll_s is None:
        age = "—"
        age_style = MUTED
    else:
        age = f"{time.time() - last_poll_s:.1f}s ago"
        age_style = AMBER if (time.time() - last_poll_s) > 10 else MUTED

    line_style = AMBER if not router_up else MUTED
    t.append(f"ROUTER · caruana:8081 · ", style=line_style)
    t.append("up" if router_up else "UNREACHABLE", style=GREEN if router_up else RED)
    t.append(f" · {backend_count}/{total_backends} backends healthy · ", style=line_style)
    t.append(f"last poll {age}", style=age_style)
    return t


# ── Hardcoded mock data for Gate 4 visual review ───────────────────────────────

_MOCK_BYWATER = dict(
    name="bywater", hostname="caruana", gpu_name="RTX 4090M", uptime_s=2 * 86400 + 4 * 3600,
    gpu_pct=8, vram_used_mb=4096, vram_total_mb=16384, temp_c=54,
    cpu_pct=12.0, ram_used_bytes=5_798_205_440, ram_total_bytes=17_179_869_184,
    ollama_models=[{"name": "gpt-oss:latest", "size_mb": 3276, "vram_pct": 8, "cpu_pct": 0}],
    req_per_s=1.2, error_count=0, offline=False,
)
_MOCK_DEEPWATER = dict(
    name="deepwater", hostname="alphablue", gpu_name="RTX 3090", uptime_s=2 * 86400 + 4 * 3600,
    gpu_pct=91, vram_used_mb=40755, vram_total_mb=49152, temp_c=81,
    cpu_pct=5.0, ram_used_bytes=24_000_000_000, ram_total_bytes=68_719_476_736,
    ollama_models=[{"name": "qwq:latest", "size_mb": 34918, "vram_pct": 91, "cpu_pct": 18}],
    req_per_s=0.1, error_count=0, offline=False,
)


def main() -> None:
    console = Console()

    with Live(console=console, refresh_per_second=1, screen=False) as live:
        while True:
            bw_panel = build_backend_panel(**_MOCK_BYWATER)
            dw_panel = build_backend_panel(**_MOCK_DEEPWATER)

            layout = Layout()
            layout.split_row(Layout(bw_panel, name="bywater"), Layout(dw_panel, name="deepwater"))

            status_bar = build_router_status_bar(True, 2, 2, time.time())
            from rich.console import Group
            live.update(Group(layout, status_bar))
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run helper tests to verify they pass**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/test_hw_vitals_helpers.py -v
```

Expected: all PASS.

- [ ] **Step 5: Smoke-test the mock layout locally**

```bash
uv run scripts/tui/hw_vitals.py
```

Expected: two panels side-by-side with mock GPU/CPU metrics visible. Ctrl-C to exit.

- [ ] **Step 6: Commit**

```bash
git add scripts/tui/hw_vitals.py scripts/tui/tests/test_hw_vitals_helpers.py
git commit -m "feat(AC-10): hw_vitals.py panel layout with mock data; pure helper functions"
```

---

## HITL Gate 4 — `hw-vitals` panel layout visual review on Lasker (mock data)

**Deploy:**
```bash
scp scripts/tui/hw_vitals.py lasker:~/.local/bin/hw_vitals.py
ssh lasker "uv run ~/.local/bin/hw_vitals.py"
```

**Assess:**
- bywater and deepwater panels occupy ~50% of screen width each
- Progress bars are visible at the 7" screen's resolution
- Temperature in panel header is readable
- Two-column metric grid (GPU/VRAM, CPU/RAM) fits without overflow
- Ollama section renders cleanly below metrics
- Router status bar visible at bottom

**Possible outcomes:**
- Adjust bar length (currently 20 chars) if too narrow or wide
- Reflow label/bar/value alignment
- Change metric grid to 1-column if screen is narrower than expected

**Do not proceed to Task 12 until this gate passes.**

---

## Task 12: `hw_vitals.py` — wire live GPU data and temperature colors *(AC-11)*

**Files:**
- Modify: `scripts/tui/hw_vitals.py` — replace mock data with live `/gpu` polling

- [ ] **Step 1: Write the failing test for GPU data fetch**

Add to `scripts/tui/tests/test_hw_vitals_helpers.py`:

```python
def test_compute_req_per_s_counts_matching_backend(monkeypatch):
    """AC-14: req/s counts proxy_response records for matching backend in last 60s."""
    now = 1000.0
    entries = [
        {"message": "proxy_response", "timestamp": 990.0, "extra": {"backend": "http://bw:8080"}},
        {"message": "proxy_response", "timestamp": 995.0, "extra": {"backend": "http://bw:8080"}},
        {"message": "proxy_response", "timestamp": 995.0, "extra": {"backend": "http://other:8080"}},
        {"message": "proxy_request", "timestamp": 998.0, "extra": {"backend": "http://bw:8080"}},  # wrong message
    ]
    rate = hw_vitals.compute_req_per_s(entries, "http://bw:8080", now, now - 60)
    assert rate == pytest.approx(2 / 60.0, rel=0.01)


def test_compute_error_count_counts_4xx_and_5xx():
    """AC-14: error count includes 4xx and 5xx upstream_status."""
    now = 1000.0
    entries = [
        {"message": "proxy_response", "timestamp": 999.0, "extra": {"backend": "http://bw:8080", "upstream_status": 200}},
        {"message": "proxy_response", "timestamp": 999.0, "extra": {"backend": "http://bw:8080", "upstream_status": 503}},
        {"message": "proxy_response", "timestamp": 999.0, "extra": {"backend": "http://bw:8080", "upstream_status": 400}},
    ]
    count = hw_vitals.compute_error_count(entries, "http://bw:8080", now)
    assert count == 2
```

- [ ] **Step 2: Run to verify new tests pass (they should — functions already exist)**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/test_hw_vitals_helpers.py -v
```

Expected: all PASS.

- [ ] **Step 3: Replace mock-data `main()` with live polling from `/gpu`**

Replace the `main()` function in `hw_vitals.py`:

```python
def main() -> None:
    console = Console()
    router_up = False
    last_successful_poll: float | None = None
    start_time = time.time()
    log_entries: list[dict] = []

    backends = {
        "bywater": BYWATER_URL,
        "deepwater": DEEPWATER_URL,
    }

    with Live(console=console, refresh_per_second=1, screen=False) as live:
        while True:
            panels = []

            # Fetch ring buffer for req/s and error counts
            try:
                resp = httpx.get(f"{ROUTER_URL}/logs/last?n=500", timeout=3.0)
                resp.raise_for_status()
                log_entries = resp.json().get("entries", [])
                router_up = True
                last_successful_poll = time.time()
            except Exception:
                router_up = False

            for name, base_url in backends.items():
                offline = False
                gpu_data: dict | None = None
                sys_data: dict | None = None
                status_data: dict | None = None

                try:
                    r = httpx.get(f"{base_url}/gpu", timeout=5.0)
                    r.raise_for_status()
                    gpu_data = r.json()
                except Exception:
                    offline = True

                if not offline:
                    try:
                        r = httpx.get(f"{base_url}/sysinfo", timeout=5.0)
                        r.raise_for_status()
                        sys_data = r.json()
                    except Exception as exc:
                        # 404 handled in Task 13; other errors degrade gracefully
                        sys_data = None

                    try:
                        r = httpx.get(f"{base_url}/status", timeout=5.0)
                        r.raise_for_status()
                        status_data = r.json()
                    except Exception:
                        status_data = None

                now = time.time()
                rps = compute_req_per_s(log_entries, base_url, now, start_time)
                errs = compute_error_count(log_entries, base_url, now)

                if offline or gpu_data is None:
                    panels.append(build_backend_panel(
                        name=name, hostname="—", gpu_name="—", uptime_s=None,
                        gpu_pct=None, vram_used_mb=None, vram_total_mb=None, temp_c=None,
                        cpu_pct=None, ram_used_bytes=None, ram_total_bytes=None,
                        ollama_models=[], req_per_s=0.0, error_count=0, offline=True,
                    ))
                    continue

                gpus = gpu_data.get("gpus", [])
                gpu = gpus[0] if gpus else {}
                gpu_pct = gpu.get("utilization_pct")
                vram_used_mb = gpu.get("vram_used_mb")
                vram_total_mb = gpu.get("vram_total_mb")
                temp_c = gpu.get("temperature_c")
                hostname = gpu_data.get("server_name", name)
                gpu_name = gpu.get("name", "—")
                uptime_s = status_data.get("uptime") if status_data else None
                cpu_pct = sys_data.get("cpu_percent") if sys_data else None
                ram_used = sys_data.get("ram_used_bytes") if sys_data else None
                ram_total = sys_data.get("ram_total_bytes") if sys_data else None
                ollama_models = gpu_data.get("ollama_loaded_models", [])

                panels.append(build_backend_panel(
                    name=name, hostname=hostname, gpu_name=gpu_name, uptime_s=uptime_s,
                    gpu_pct=gpu_pct, vram_used_mb=vram_used_mb, vram_total_mb=vram_total_mb,
                    temp_c=temp_c, cpu_pct=cpu_pct, ram_used_bytes=ram_used, ram_total_bytes=ram_total,
                    ollama_models=ollama_models, req_per_s=rps, error_count=errs,
                    offline=False,
                ))

            layout = Layout()
            layout.split_row(*[Layout(p, name=n) for n, p in zip(backends.keys(), panels)])
            status_bar = build_router_status_bar(router_up, sum(1 for p in panels if True), len(backends), last_successful_poll)
            from rich.console import Group
            live.update(Group(layout, status_bar))

            time.sleep(POLL_INTERVAL)
```

- [ ] **Step 4: Smoke-test live polling**

```bash
uv run scripts/tui/hw_vitals.py
```

Expected: live GPU data from bywater and deepwater. If either host is unreachable, its panel shows OFFLINE.

- [ ] **Step 5: Commit**

```bash
git add scripts/tui/hw_vitals.py
git commit -m "feat(AC-11): hw_vitals wired to live /gpu endpoint with temperature color coding"
```

---

## Task 13: `hw_vitals.py` — `/sysinfo` 404 handling *(AC-15)*

**Files:**
- Modify: `scripts/tui/hw_vitals.py` — one-time stderr warning on 404

- [ ] **Step 1: Add 404-specific handling in the `/sysinfo` fetch block**

In `main()`, replace the bare `except Exception` for the sysinfo fetch with:

```python
                    _sysinfo_404_warned: set[str] = getattr(main, "_sysinfo_404_warned", set())
                    try:
                        r = httpx.get(f"{base_url}/sysinfo", timeout=5.0)
                        if r.status_code == 404:
                            if name not in _sysinfo_404_warned:
                                import sys
                                print(f"WARNING: {name} /sysinfo returned 404 — CPU/RAM will show —", file=sys.stderr)
                                _sysinfo_404_warned.add(name)
                                main._sysinfo_404_warned = _sysinfo_404_warned
                            sys_data = None
                        else:
                            r.raise_for_status()
                            sys_data = r.json()
                    except httpx.HTTPStatusError:
                        sys_data = None
                    except Exception:
                        sys_data = None
```

When `sys_data is None`, the panel already shows `cpu_pct=None, ram_used_bytes=None, ram_total_bytes=None`, which renders as `—` for CPU and RAM. *(AC-15)*

- [ ] **Step 2: Smoke-test**

```bash
uv run scripts/tui/hw_vitals.py
```

Verify no crash. If you temporarily point a backend URL to an address without /sysinfo, you should see the one-time warning on stderr and `—` values in the panel.

- [ ] **Step 3: Commit**

```bash
git add scripts/tui/hw_vitals.py
git commit -m "feat(AC-15): one-time stderr warning when /sysinfo returns 404; CPU/RAM show — without crashing"
```

---

## HITL Gate 5 — `hw-vitals` with live data on Lasker

**Deploy:**
```bash
scp scripts/tui/hw_vitals.py lasker:~/.local/bin/hw_vitals.py
ssh lasker "uv run ~/.local/bin/hw_vitals.py"
```

**Assess (you, the user):**
- Real GPU names display without overflow (`NVIDIA GeForce RTX 3090` etc.)
- Real model names (`deepseek-r1:70b`, `qwq:latest`) display — truncation OK?
- Temperature color correct — deepwater should show amber or red during inference
- req/s increments as you send requests through the router
- CPU offload visible when a heavy model is running (cpu_pct ≥ 1%)

**Possible outcomes:**
- Truncation rules for GPU name and model name
- Panel width adjustments

**Do not proceed to Task 14 until this gate passes.**

---

## Task 14: `hw_vitals.py` — backend offline state *(AC-12)*

**Files:**
- Modify: `scripts/tui/hw_vitals.py` — verify offline panel render

The offline path is already implemented: when `/gpu` raises an exception, `offline=True` is passed to `build_backend_panel()`, which renders `✕ OFFLINE` in red and shows `—` for all values.

- [ ] **Step 1: Manually verify offline recovery**

Temporarily set `DEEPWATER_URL = "http://127.0.0.1:9999"` (unused port) in hw_vitals.py, run the script, and verify:
- deepwater panel shows `✕ OFFLINE` in red border
- bywater panel continues to show live data
- No exception or crash

Restore `DEEPWATER_URL` to `"http://172.16.0.2:8080"`.

- [ ] **Step 2: Verify panel auto-recovers**

With the correct URL restored, verify the panel returns to normal on next poll without restart.

- [ ] **Step 3: Commit (URL restored)**

```bash
git add scripts/tui/hw_vitals.py
git commit -m "verify(AC-12): offline panel renders correctly; auto-recovery confirmed"
```

---

## Task 15: `hw_vitals.py` — Ollama section correctness *(AC-13)*

**Files:**
- Modify: `scripts/tui/hw_vitals.py` — verify Ollama section "no models loaded" case

The Ollama section is already implemented in `build_backend_panel()`. This task verifies the edge cases.

- [ ] **Step 1: Verify "no models loaded" displays correctly**

In the `build_backend_panel()` function, verify the Ollama section:

```python
    if ollama_models:
        for m in ollama_models:
            ...
    else:
        t.append("  no models loaded\n", style=MUTED)
```

This is already present. Confirm it renders correctly by running with a host that has no active Ollama models.

- [ ] **Step 2: Verify CPU% hidden when < 1%**

In the per-model row, the condition is:
```python
            if cpu >= 1:
                t.append(f"  {int(cpu)}% cpu", style=AMBER)
```

This hides sub-1% CPU load per the spec. *(AC-13)*

- [ ] **Step 3: Run all vitals tests**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/test_hw_vitals_helpers.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit if any adjustments were made**

```bash
git add scripts/tui/hw_vitals.py
git commit -m "verify(AC-13): Ollama section shows 'no models loaded'; cpu% hidden when < 1%"
```

---

## Task 16: `hw_vitals.py` — req/s from rolling 60s window and error count *(AC-14)*

**Files:**
- No new files — `compute_req_per_s()` and `compute_error_count()` are already implemented. This task wires the ring buffer results into the correct panel data and verifies the elapsed-time denominator for short runs.

- [ ] **Step 1: Verify denominator handling for short uptime**

`compute_req_per_s` uses `elapsed = min(window, now - start_time)` so if the script has only been running 10 seconds, `elapsed = 10` (not 60). This is already implemented. Confirm by reading the function.

- [ ] **Step 2: Verify error count is per-backend**

`compute_error_count` filters by `backend_url` matching the `extra.backend` field in proxy_response records. Confirm the backend URL passed is the raw URL from `backends` dict (e.g. `"http://172.16.0.4:8080"`), which matches what the router logs in `extra.backend`.

- [ ] **Step 3: Run full test suite**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit any adjustments**

```bash
git add scripts/tui/hw_vitals.py
git commit -m "verify(AC-14): req/s rolling 60s window and error count wired to ring buffer"
```

---

## Task 17: `hw_vitals.py` — router status bar + `Group` import cleanup *(AC-10 integration)*

**Files:**
- Modify: `scripts/tui/hw_vitals.py` — move `Group` import to module level, finalize router status bar

- [ ] **Step 1: Move `Group` import to top of `hw_vitals.py`**

```python
from rich.console import Console, Group
```

Remove the inline `from rich.console import Group` inside `main()`.

- [ ] **Step 2: Verify router status bar amber state**

The `build_router_status_bar()` function turns the full line amber when `router_up=False`. The staleness threshold is 10 seconds (from the spec). Confirm in the function:

```python
    age_style = AMBER if (time.time() - last_poll_s) > 10 else MUTED
```

- [ ] **Step 3: Final smoke test**

```bash
uv run scripts/tui/hw_vitals.py
```

Expected: full layout with live data, status bar at bottom, no import errors.

- [ ] **Step 4: Run all tests**

```bash
uv run --with pytest --with rich --with httpx pytest scripts/tui/tests/ -v
cd headwater-server && uv run pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/tui/hw_vitals.py
git commit -m "refactor: move Group import to module level in hw_vitals.py; finalize status bar"
```

---

## HITL Gate 6 — Both screens on Lasker simultaneously

**Deploy both scripts:**
```bash
scp scripts/tui/hw_log.py scripts/tui/hw_vitals.py lasker:~/.local/bin/
```

**Open both in separate terminals, each assigned to its screen via Sway:**
```bash
# Terminal 1 (left screen — DP-1)
ssh lasker "uv run ~/.local/bin/hw_log.py"

# Terminal 2 (right screen — DP-2)
ssh lasker "uv run ~/.local/bin/hw_vitals.py"
```

**Assess:**
- Both scripts running simultaneously — no interference
- Left screen: request log scrolling, logo visible at top
- Right screen: GPU panels, Ollama models, router status bar at bottom
- At viewing distance from the 7" screens, both are legible
- No flicker in either terminal
- When a heavy model request is sent, req/s updates on right, row appears on left

**Final validation:**
- Send `conduit/generate` with `qwq:latest` model: should appear as `heavy_inference` (amber) on left; deepwater GPU spike on right
- Force a router outage: left shows UNREACHABLE, right status bar goes amber
- Resize terminal: left redraws without crash

**Gate passes when both screens are readable side-by-side under ambient light.**

---

## Deployment Notes

**Lasker installation:**

```bash
# On Lasker — run once
mkdir -p ~/.local/bin
scp scripts/tui/hw_log.py lasker:~/.local/bin/hw_log.py
scp scripts/tui/hw_vitals.py lasker:~/.local/bin/hw_vitals.py
chmod +x ~/.local/bin/hw_log.py ~/.local/bin/hw_vitals.py
```

**Sway autostart:**

```
# ~/.config/sway/config
exec foot --output DP-1 uv run /home/user/.local/bin/hw_log.py
exec foot --output DP-2 uv run /home/user/.local/bin/hw_vitals.py
```

Both scripts use `uv run` with inline metadata — no virtualenv or pip required on Lasker beyond `uv` itself.
