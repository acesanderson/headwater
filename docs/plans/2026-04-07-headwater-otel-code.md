# Headwater OTel Metrics — Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/metrics` endpoints to all three Headwater services (bywater, deepwater, headwaterrouter) with OTel SDK instrumentation covering GPU, Ollama, HTTP, and router backend health.

**Architecture:** New `metrics.py` module exposes two public functions — `register_metrics()` for subservers and `register_router_metrics()` for the router. Both mount `/metrics` on the FastAPI app via `make_asgi_app()` and activate HTTP auto-instrumentation. Tests call these functions directly on bare FastAPI apps for isolation; wiring into production entry points happens last (Task 9).

**Tech Stack:** opentelemetry-sdk, opentelemetry-exporter-prometheus, opentelemetry-instrumentation-fastapi, opentelemetry-instrumentation-httpx, prometheus-client, pynvml (already in deps as nvidia-ml-py)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `headwater-server/src/headwater_server/server/metrics.py` | `register_metrics()`, `register_router_metrics()`, all observable callbacks |
| Modify | `headwater-server/src/headwater_server/server/headwater.py` | Call `register_metrics()` at module level after app creation |
| Modify | `headwater-server/src/headwater_server/server/router.py` | Call `register_router_metrics()` at module level after router creation |
| Modify | `headwater-server/pyproject.toml` | Add OTel dependencies |
| Create | `headwater-server/tests/server/test_metrics.py` | All metrics unit tests (AC-1 through AC-7) |

---

### Task 1: Add OTel dependencies

**Files:**
- Modify: `headwater-server/pyproject.toml`

- [ ] **Step 1: Add OTel packages to dependencies**

In `headwater-server/pyproject.toml`, add to the `dependencies` list:

```toml
[project]
dependencies = [
    # ... existing deps ...
    "opentelemetry-sdk>=1.25",
    "opentelemetry-exporter-prometheus>=0.46b0",
    "opentelemetry-instrumentation-fastapi>=0.46b0",
    "opentelemetry-instrumentation-httpx>=0.46b0",
]
```

- [ ] **Step 2: Lock dependencies**

```bash
cd headwater-server && uv lock
```

Expected: `uv.lock` updated with OTel packages and their transitive deps (opentelemetry-api, prometheus-client, wrapt, etc.).

- [ ] **Step 3: Verify import works**

```bash
cd headwater-server && uv run python -c "from opentelemetry.sdk.metrics import MeterProvider; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add headwater-server/pyproject.toml headwater-server/uv.lock
git commit -m "feat: add opentelemetry sdk and exporter dependencies"
```

---

### Task 2: `register_metrics()` skeleton + AC-1 (bywater `/metrics` returns 200 + content-type)

**Files:**
- Create: `headwater-server/src/headwater_server/server/metrics.py`
- Create: `headwater-server/tests/server/test_metrics.py`

- [ ] **Step 1: Write the failing test** *(AC-1)*

Create `headwater-server/tests/server/test_metrics.py`:

```python
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_metrics_state():
    """Reset OTel and prometheus_client state between tests for isolation."""
    from opentelemetry import metrics as otel_metrics
    from prometheus_client import REGISTRY

    otel_metrics.set_meter_provider(otel_metrics.NoOpMeterProvider())
    before = set(REGISTRY._collectors)

    yield

    otel_metrics.set_meter_provider(otel_metrics.NoOpMeterProvider())
    for c in set(REGISTRY._collectors) - before:
        try:
            REGISTRY.unregister(c)
        except Exception:
            pass
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    try:
        FastAPIInstrumentor().uninstrument()
    except Exception:
        pass


def _make_client(server_name: str = "bywater") -> TestClient:
    from headwater_server.server.metrics import register_metrics
    app = FastAPI()
    register_metrics(app, server_name)
    return TestClient(app)


def test_bywater_metrics_returns_200_with_prometheus_content_type():
    """AC-1: GET /metrics on bywater returns 200 with text/plain; version=0.0.4."""
    client = _make_client("bywater")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "version=0.0.4" in response.headers["content-type"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_bywater_metrics_returns_200_with_prometheus_content_type -v
```

Expected: FAIL — `ModuleNotFoundError` or `ImportError` because `metrics.py` doesn't exist yet.

- [ ] **Step 3: Create `metrics.py` with `register_metrics()` skeleton**

Create `headwater-server/src/headwater_server/server/metrics.py`:

```python
from __future__ import annotations

import importlib.metadata
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from headwater_server.server.routing_config import RouterConfig


def register_metrics(app: FastAPI, server_name: str) -> None:
    """Register OTel metrics for a subserver (bywater/deepwater).

    Mounts /metrics on app, activates HTTP auto-instrumentation,
    and registers GPU + Ollama observable gauges.
    Idempotent: returns early if an SDK MeterProvider is already active.
    """
    from opentelemetry import metrics as otel_metrics
    from opentelemetry.sdk.metrics import MeterProvider as SdkMeterProvider

    if isinstance(otel_metrics.get_meter_provider(), SdkMeterProvider):
        return

    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from prometheus_client import make_asgi_app

    resource = Resource.create({
        SERVICE_NAME: server_name,
        "host.name": os.uname().nodename,
        "service.version": importlib.metadata.version("headwater_server"),
    })
    reader = PrometheusMetricReader()
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    otel_metrics.set_meter_provider(provider)

    app.mount("/metrics", make_asgi_app())
    FastAPIInstrumentor().instrument_app(app)

    meter = otel_metrics.get_meter("headwater")
    _register_gpu_metrics(meter)
    _register_ollama_metrics(meter)


def register_router_metrics(
    app: FastAPI,
    server_name: str,
    router_config: RouterConfig,
) -> None:
    """Register OTel metrics for the router.

    Mounts /metrics on app, activates HTTP auto-instrumentation,
    and registers backend health gauges.
    Idempotent: returns early if an SDK MeterProvider is already active.
    """
    from opentelemetry import metrics as otel_metrics
    from opentelemetry.sdk.metrics import MeterProvider as SdkMeterProvider

    if isinstance(otel_metrics.get_meter_provider(), SdkMeterProvider):
        return

    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from prometheus_client import make_asgi_app

    resource = Resource.create({
        SERVICE_NAME: server_name,
        "host.name": os.uname().nodename,
        "service.version": importlib.metadata.version("headwater_server"),
    })
    reader = PrometheusMetricReader()
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    otel_metrics.set_meter_provider(provider)

    app.mount("/metrics", make_asgi_app())
    FastAPIInstrumentor().instrument_app(app)

    meter = otel_metrics.get_meter("headwater")
    _register_backend_metrics(meter, router_config)


def _register_gpu_metrics(meter) -> None:
    from opentelemetry.metrics import Observation

    def _observe_gpu_available(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            yield Observation(1, {})
        except Exception:
            yield Observation(0, {})

    def _observe_gpu_memory_used(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                info = pynvml.nvmlDeviceGetMemoryInfo(h)
                name = pynvml.nvmlDeviceGetName(h)
                yield Observation(info.used, {"gpu_index": str(i), "gpu_name": name})
        except Exception:
            return

    def _observe_gpu_memory_free(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                info = pynvml.nvmlDeviceGetMemoryInfo(h)
                name = pynvml.nvmlDeviceGetName(h)
                yield Observation(info.free, {"gpu_index": str(i), "gpu_name": name})
        except Exception:
            return

    def _observe_gpu_memory_total(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                info = pynvml.nvmlDeviceGetMemoryInfo(h)
                name = pynvml.nvmlDeviceGetName(h)
                yield Observation(info.total, {"gpu_index": str(i), "gpu_name": name})
        except Exception:
            return

    def _observe_gpu_utilization(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                name = pynvml.nvmlDeviceGetName(h)
                yield Observation(util.gpu / 100.0, {"gpu_index": str(i), "gpu_name": name})
        except Exception:
            return

    def _observe_gpu_temperature(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
                name = pynvml.nvmlDeviceGetName(h)
                yield Observation(temp, {"gpu_index": str(i), "gpu_name": name})
        except Exception:
            return

    meter.create_observable_gauge("headwater.gpu.available", callbacks=[_observe_gpu_available],
                                  description="1 if GPU is accessible via pynvml, 0 otherwise")
    meter.create_observable_gauge("headwater.gpu.memory.used", callbacks=[_observe_gpu_memory_used],
                                  unit="By", description="Used GPU VRAM in bytes")
    meter.create_observable_gauge("headwater.gpu.memory.free", callbacks=[_observe_gpu_memory_free],
                                  unit="By", description="Free GPU VRAM in bytes")
    meter.create_observable_gauge("headwater.gpu.memory.total", callbacks=[_observe_gpu_memory_total],
                                  unit="By", description="Total GPU VRAM in bytes")
    meter.create_observable_gauge("headwater.gpu.utilization.ratio", callbacks=[_observe_gpu_utilization],
                                  description="GPU compute utilization as a ratio 0.0-1.0")
    meter.create_observable_gauge("headwater.gpu.temperature.celsius", callbacks=[_observe_gpu_temperature],
                                  description="GPU temperature in degrees Celsius")


def _register_ollama_metrics(meter) -> None:
    from opentelemetry.metrics import Observation

    def _observe_ollama_loaded(options):
        try:
            import httpx
            resp = httpx.get("http://localhost:11434/api/ps", timeout=2.0)
            resp.raise_for_status()
            for model in resp.json().get("models", []):
                yield Observation(1, {"model_name": model["name"]})
        except Exception:
            return

    def _observe_ollama_vram(options):
        try:
            import httpx
            resp = httpx.get("http://localhost:11434/api/ps", timeout=2.0)
            resp.raise_for_status()
            for model in resp.json().get("models", []):
                yield Observation(model.get("size_vram", 0), {"model_name": model["name"]})
        except Exception:
            return

    def _observe_ollama_cpu_offload(options):
        try:
            import httpx
            resp = httpx.get("http://localhost:11434/api/ps", timeout=2.0)
            resp.raise_for_status()
            for model in resp.json().get("models", []):
                total = model.get("size", 0)
                vram = model.get("size_vram", 0)
                ratio = max(0.0, (total - vram) / total) if total > 0 else 0.0
                yield Observation(ratio, {"model_name": model["name"]})
        except Exception:
            return

    meter.create_observable_gauge("headwater.ollama.model.loaded", callbacks=[_observe_ollama_loaded],
                                  description="1 if Ollama model is currently loaded")
    meter.create_observable_gauge("headwater.ollama.model.vram", callbacks=[_observe_ollama_vram],
                                  unit="By", description="VRAM used by loaded Ollama model")
    meter.create_observable_gauge("headwater.ollama.model.cpu.offload.ratio",
                                  callbacks=[_observe_ollama_cpu_offload],
                                  description="Fraction of model layers on CPU (0.0=all GPU, 1.0=all CPU)")


def _register_backend_metrics(meter, router_config) -> None:
    from opentelemetry.metrics import Observation
    import httpx

    config = router_config  # live reference; reads .backends at observation time

    def _observe_backend_up(options):
        for name, url in config.backends.items():
            try:
                resp = httpx.get(f"{url}/ping", timeout=2.0)
                up = 1 if resp.status_code == 200 else 0
            except Exception:
                up = 0
            yield Observation(up, {"backend_name": name, "backend_url": url})

    meter.create_observable_gauge("headwater.backend.up", callbacks=[_observe_backend_up],
                                  description="1 if backend responds to /ping within 2s, 0 otherwise")
```

- [ ] **Step 4: Run test to verify it passes** *(AC-1)*

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_bywater_metrics_returns_200_with_prometheus_content_type -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add headwater-server/src/headwater_server/server/metrics.py \
        headwater-server/tests/server/test_metrics.py
git commit -m "feat: add register_metrics() for subservers with GPU/Ollama callbacks; AC-1 green"
```

---

### Task 3: AC-2 — deepwater `/metrics` returns 200 with correct content-type

**Files:**
- Modify: `headwater-server/tests/server/test_metrics.py`

- [ ] **Step 1: Write the test** *(AC-2)*

Append to `headwater-server/tests/server/test_metrics.py`:

```python
def test_deepwater_metrics_returns_200_with_prometheus_content_type():
    """AC-2: GET /metrics on deepwater returns 200 with text/plain; version=0.0.4."""
    client = _make_client("deepwater")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "version=0.0.4" in response.headers["content-type"]
```

- [ ] **Step 2: Run test — expect immediate green** *(AC-2)*

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_deepwater_metrics_returns_200_with_prometheus_content_type -v
```

Expected: PASS — bywater and deepwater share the same `register_metrics()` code path; no implementation change needed.

- [ ] **Step 3: Commit**

```bash
git add headwater-server/tests/server/test_metrics.py
git commit -m "test: add AC-2 deepwater /metrics content-type assertion"
```

---

### Task 4: `register_router_metrics()` wired into router + AC-3 (headwaterrouter `/metrics`)

**Files:**
- Modify: `headwater-server/tests/server/test_metrics.py`
- Modify: `headwater-server/src/headwater_server/server/router.py`

- [ ] **Step 1: Write the failing test** *(AC-3)*

Append to `headwater-server/tests/server/test_metrics.py`:

```python
def test_router_metrics_returns_200_with_prometheus_content_type():
    """AC-3: GET /metrics on headwaterrouter returns 200 with text/plain; version=0.0.4."""
    import yaml
    from pathlib import Path
    from fastapi.testclient import TestClient
    from headwater_server.server.router import HeadwaterRouter
    from headwater_server.server.metrics import register_router_metrics

    config = {
        "backends": {"bywater": "http://localhost:8080"},
        "routes": {"conduit": "bywater"},
        "heavy_models": [],
    }
    tmp = Path("/tmp/test_routes_ac3.yaml")
    tmp.write_text(yaml.dump(config))

    router = HeadwaterRouter(config_path=tmp)
    register_router_metrics(router.app, router._name, router._config)
    client = TestClient(router.app)

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "version=0.0.4" in response.headers["content-type"]
```

- [ ] **Step 2: Run test to verify it fails** *(AC-3)*

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_router_metrics_returns_200_with_prometheus_content_type -v
```

Expected: FAIL — `register_router_metrics` exists but router has no `/metrics` route yet (the test itself calls `register_router_metrics` so it should actually work — if it fails with a different error, diagnose before proceeding).

- [ ] **Step 3: Wire `register_router_metrics()` into router.py**

In `headwater-server/src/headwater_server/server/router.py`, after the module-level try/except block at the bottom (after line ~264), add:

```python
# Register OTel metrics on the router app
try:
    from headwater_server.server.metrics import register_router_metrics
    if _router is not None:
        register_router_metrics(_router.app, _router._name, _router._config)
except Exception:
    pass  # metrics are optional; never block startup
```

Note: the `_router` variable is set in the try/except block. Reference it by name — do not inline this inside the existing try/except or you will register metrics even when the router falls back to a bare FastAPI app.

The existing bottom of `router.py` becomes:

```python
try:
    _router = HeadwaterRouter()
    app = _router.app
except FileNotFoundError:
    _router = None
    app = FastAPI(
        title="Headwater Router",
        description="Headwater routing gateway",
        version="1.0.0",
    )

if _router is not None:
    from headwater_server.server.metrics import register_router_metrics
    register_router_metrics(_router.app, _router._name, _router._config)
```

- [ ] **Step 4: Run test to verify it passes** *(AC-3)*

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_router_metrics_returns_200_with_prometheus_content_type -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add headwater-server/src/headwater_server/server/router.py \
        headwater-server/tests/server/test_metrics.py
git commit -m "feat: wire register_router_metrics() into router.py; AC-3 green"
```

---

### Task 5: AC-4 — GPU unavailable: `headwater_gpu_available=0`, no GPU gauge lines

**Files:**
- Modify: `headwater-server/tests/server/test_metrics.py`

- [ ] **Step 1: Write the failing test** *(AC-4)*

Append to `headwater-server/tests/server/test_metrics.py`:

```python
def test_gpu_unavailable_shows_zero_and_omits_gpu_gauges():
    """AC-4: When pynvml.nvmlInit raises, gpu_available=0 and no GPU memory/util lines."""
    from unittest.mock import patch

    client = _make_client("bywater")

    with patch("pynvml.nvmlInit", side_effect=Exception("no GPU")):
        response = client.get("/metrics")

    assert response.status_code == 200
    text = response.text

    # headwater_gpu_available must be present with value 0
    lines = [l for l in text.splitlines() if "headwater_gpu_available" in l and not l.startswith("#")]
    assert lines, "headwater_gpu_available metric missing from response"
    assert any("0.0" in l for l in lines), f"expected gpu_available=0, got: {lines}"

    # GPU detail metrics must be absent when GPU is unavailable
    assert "headwater_gpu_memory_used" not in text
    assert "headwater_gpu_memory_free" not in text
    assert "headwater_gpu_memory_total" not in text
    assert "headwater_gpu_utilization" not in text
    assert "headwater_gpu_temperature" not in text

    # HTTP metrics from auto-instrumentation must still be present
    assert "http_server" in text or "http_request" in text
```

- [ ] **Step 2: Run test to verify it fails** *(AC-4)*

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_gpu_unavailable_shows_zero_and_omits_gpu_gauges -v
```

Expected: FAIL — the GPU callbacks and `headwater_gpu_available` metric are not yet registered (they exist in the code from Task 2, but the test is verifying the graceful fallback behavior which may not yet emit `gpu_available=0` correctly).

If the test unexpectedly passes here, inspect the response text to confirm the assertions are actually meaningful before proceeding.

- [ ] **Step 3: Run test to verify it passes** *(AC-4)*

The GPU callbacks were already written in Task 2's `metrics.py`. `_observe_gpu_available` yields `Observation(0, {})` on exception. Run:

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_gpu_unavailable_shows_zero_and_omits_gpu_gauges -v
```

Expected: PASS — if this fails, inspect the actual metric name OTel generates for `headwater.gpu.available` (dots become underscores; the Prometheus name may have a `_total` suffix or differ). Adjust the assertion string to match the actual output.

- [ ] **Step 4: Commit**

```bash
git add headwater-server/tests/server/test_metrics.py
git commit -m "test: AC-4 GPU unavailable fallback — gpu_available=0, detail metrics omitted"
```

---

### Task 6: AC-5 — Ollama unreachable: no `headwater_ollama_*` lines

**Files:**
- Modify: `headwater-server/tests/server/test_metrics.py`

- [ ] **Step 1: Write the failing test** *(AC-5)*

Append to `headwater-server/tests/server/test_metrics.py`:

```python
def test_ollama_unreachable_omits_ollama_metrics():
    """AC-5: When Ollama HTTP call raises ConnectError, no headwater_ollama_* lines appear."""
    from unittest.mock import patch
    import httpx

    client = _make_client("bywater")

    with patch("httpx.get", side_effect=httpx.ConnectError("ollama not running")):
        response = client.get("/metrics")

    assert response.status_code == 200
    text = response.text

    assert "headwater_ollama" not in text
```

- [ ] **Step 2: Run test to verify it fails** *(AC-5)*

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_ollama_unreachable_omits_ollama_metrics -v
```

Expected: FAIL or PASS depending on whether `httpx.get` patch intercepts the callback. If PASS immediately, inspect response text to confirm `headwater_ollama` is genuinely absent before committing.

- [ ] **Step 3: Run full test to verify it passes** *(AC-5)*

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_ollama_unreachable_omits_ollama_metrics -v
```

Expected: PASS — the Ollama callbacks catch all exceptions and `return` (no `yield`), so no observations are emitted. If this fails, check that `httpx.get` is being patched at the right module path — the callbacks in `metrics.py` call `httpx.get` directly, so the patch target is `httpx.get`.

- [ ] **Step 4: Commit**

```bash
git add headwater-server/tests/server/test_metrics.py
git commit -m "test: AC-5 Ollama unreachable — ollama metrics omitted from response"
```

---

### Task 7: AC-6 — Backend unreachable: `headwater_backend_up=0` in router metrics

**Files:**
- Modify: `headwater-server/tests/server/test_metrics.py`

- [ ] **Step 1: Write the failing test** *(AC-6)*

Append to `headwater-server/tests/server/test_metrics.py`:

```python
def test_backend_unreachable_shows_backend_up_zero():
    """AC-6: When a backend is unreachable, headwater_backend_up{backend_name=...} = 0."""
    import yaml
    import re
    from pathlib import Path
    from unittest.mock import patch
    import httpx
    from fastapi.testclient import TestClient
    from headwater_server.server.router import HeadwaterRouter
    from headwater_server.server.metrics import register_router_metrics

    config = {
        "backends": {"bywater": "http://localhost:8080"},
        "routes": {"conduit": "bywater"},
        "heavy_models": [],
    }
    tmp = Path("/tmp/test_routes_ac6.yaml")
    tmp.write_text(yaml.dump(config))

    router = HeadwaterRouter(config_path=tmp)
    register_router_metrics(router.app, router._name, router._config)
    client = TestClient(router.app)

    with patch("httpx.get", side_effect=httpx.ConnectError("backend down")):
        response = client.get("/metrics")

    assert response.status_code == 200
    text = response.text

    # Must contain headwater_backend_up with backend_name="bywater" and value 0
    lines = [l for l in text.splitlines() if "headwater_backend_up" in l and not l.startswith("#")]
    assert lines, "headwater_backend_up metric missing"
    backend_line = next((l for l in lines if 'backend_name="bywater"' in l), None)
    assert backend_line is not None, f"No line with backend_name=bywater in: {lines}"
    assert backend_line.strip().endswith("0.0"), f"Expected 0.0, got: {backend_line}"
```

- [ ] **Step 2: Run test to verify it fails** *(AC-6)*

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_backend_unreachable_shows_backend_up_zero -v
```

Expected: FAIL — `headwater_backend_up` metric is missing because `register_router_metrics` callback hasn't been exercised yet in this test fixture.

- [ ] **Step 3: Run test to verify it passes** *(AC-6)*

The `_register_backend_metrics` callback was written in Task 2. The `/ping` probe raises `httpx.ConnectError` (patched), so `up = 0`. Run:

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_backend_unreachable_shows_backend_up_zero -v
```

Expected: PASS. If the metric name in the output differs from `headwater_backend_up`, inspect the response text and adjust the assertion to match the actual Prometheus-rendered name.

- [ ] **Step 4: Commit**

```bash
git add headwater-server/tests/server/test_metrics.py
git commit -m "test: AC-6 backend unreachable — headwater_backend_up=0 asserted"
```

---

### Task 8: AC-7 — All metrics carry `service_name` label matching server name

**Files:**
- Modify: `headwater-server/tests/server/test_metrics.py`

- [ ] **Step 1: Write the test** *(AC-7)*

Append to `headwater-server/tests/server/test_metrics.py`:

```python
def test_metrics_carry_service_name_label():
    """AC-7: All metric lines carry exactly one service_name label matching the server name."""
    import re

    client = _make_client("bywater")
    response = client.get("/metrics")
    assert response.status_code == 200

    # Collect all service_name values from non-comment metric lines
    service_names_found = set(
        re.findall(r'service_name="([^"]+)"', response.text)
    )

    assert service_names_found, "No service_name labels found in /metrics output"
    assert service_names_found == {"bywater"}, (
        f"Expected only service_name='bywater', got: {service_names_found}"
    )
```

- [ ] **Step 2: Run test — expect immediate green** *(AC-7)*

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py::test_metrics_carry_service_name_label -v
```

Expected: PASS — `SERVICE_NAME: server_name` is set in the `Resource` in `register_metrics()`, and the OTel Prometheus exporter attaches resource attributes as labels on every metric.

If this fails because `service_name` is rendered differently (e.g., as `job` or `otel_scope_name`), inspect the actual output with:
```bash
cd headwater-server && uv run python -c "
from fastapi import FastAPI
from fastapi.testclient import TestClient
from headwater_server.server.metrics import register_metrics
app = FastAPI()
register_metrics(app, 'bywater')
c = TestClient(app)
print(c.get('/metrics').text[:2000])
"
```
Then adjust the label name in the assertion.

- [ ] **Step 3: Run full test suite to verify no regressions**

```bash
cd headwater-server && uv run pytest tests/server/test_metrics.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add headwater-server/tests/server/test_metrics.py
git commit -m "test: AC-7 service_name label present and correct on all metrics"
```

---

### Task 9: Wire `register_metrics()` into `headwater.py` + run full suite

**Files:**
- Modify: `headwater-server/src/headwater_server/server/headwater.py`

- [ ] **Step 1: Add `register_metrics()` call at module level in `headwater.py`**

At the bottom of `headwater-server/src/headwater_server/server/headwater.py`, after the existing module-level lines:

```python
_server = HeadwaterServer(name=_detect_server_name())
app = _server.app
```

Add:

```python
from headwater_server.server.metrics import register_metrics
register_metrics(app, _server._name)
```

The full bottom of the file becomes:

```python
_server = HeadwaterServer(name=_detect_server_name())
app = _server.app
from headwater_server.server.metrics import register_metrics
register_metrics(app, _server._name)
```

- [ ] **Step 2: Run the full server test suite to confirm no regressions**

```bash
cd headwater-server && uv run pytest tests/server/ -v
```

Expected: all tests PASS including pre-existing tests in `test_router.py`, `test_headwater_server.py`, `test_middleware.py`, `test_logging_config.py`.

If any pre-existing test fails due to OTel state leaking, check that the `reset_metrics_state` fixture in `test_metrics.py` is properly cleaning up after itself (it's `autouse=True` but scoped to that file — it should not affect other test files).

- [ ] **Step 3: Commit**

```bash
git add headwater-server/src/headwater_server/server/headwater.py
git commit -m "feat: wire register_metrics() into headwater.py module startup"
```

---

### Task 10: Deploy with `--sync-deps`

- [ ] **Step 1: Deploy to both hosts**

```bash
cd /Users/bianders/Brian_Code/headwater && bash scripts/deploy.sh --sync-deps
```

Expected: deploys to caruana (bywater + headwaterrouter) and alphablue (deepwater), restarts services, polls `/ping` until up.

- [ ] **Step 2: Smoke test `/metrics` on each service**

```python
from headwater_client.client.headwater_client import HeadwaterClient

bywater = HeadwaterClient(host_alias="bywater")
router  = HeadwaterClient(host_alias="headwater")

# Quick check — these should not raise
import httpx
for alias, port in [("bywater", 8080), ("router", 8081)]:
    r = httpx.get(f"http://caruana:{port}/metrics", timeout=10)
    assert r.status_code == 200, f"{alias} /metrics returned {r.status_code}"
    assert "text/plain" in r.headers["content-type"]
    print(f"{alias}: OK ({len(r.text)} bytes)")

r = httpx.get("http://alphablue:8080/metrics", timeout=10)
assert r.status_code == 200
print(f"deepwater: OK ({len(r.text)} bytes)")
```

- [ ] **Step 3: Commit deploy confirmation**

```bash
git commit --allow-empty -m "deploy: headwater-otel-code deployed to caruana + alphablue"
```
