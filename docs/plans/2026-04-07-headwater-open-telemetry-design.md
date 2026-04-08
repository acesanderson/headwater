# Headwater OpenTelemetry — Design Spec
**Project:** headwater-open-telemetry
**Date:** 2026-04-07

---

## 1. Goal

Add OTel-compliant observability to the Headwater stack: a `/metrics` endpoint on each service (subservers + router) exposing Prometheus-format metrics via the OTel SDK, Alloy agents on caruana and alphablue shipping metrics and logs to Lasker, and a Grafana stack on Lasker displaying both pillars on two kiosk monitors.

The end state is a fully pull-based NOC: Lasker scrapes and displays, Headwater services emit passively, no code changes required for the log path.

---

## 2. Constraints and Non-Goals

**In scope:**
- `/metrics` endpoint on bywater, deepwater, and headwaterrouter
- OTel SDK instrumentation (opentelemetry-sdk, opentelemetry-exporter-prometheus, opentelemetry-instrumentation-fastapi, opentelemetry-instrumentation-httpx)
- GPU metrics (pynvml) and Ollama loaded model metrics per subserver
- `headwater_backend_up` gauge on the router — probed synchronously at scrape time (not a background poll); timeout is 2 seconds per backend; backends enumerated from the live `RouterConfig` loaded via `routes.yaml`. Current backend count is 2 (bywater + deepwater), giving a worst-case scrape time of 4s — well within Prometheus's 10s default scrape timeout. If backend count grows beyond 4, raise `scrape_timeout` in Alloy's prometheus.scrape config.
- Alloy config on caruana (scrapes bywater + headwaterrouter, ships journald to Loki)
- Alloy config on alphablue (scrapes deepwater, ships journald to Loki)
- Lasker: Prometheus, Loki, Grafana installed as bare-metal systemd services
- Lasker: Sway + Chromium kiosk, getty autologin, dual-monitor layout
- `pyproject.toml` updated with new OTel dependencies; `deploy.sh --sync-deps` required for this deploy

**Not in scope:**
- OTLP push (Prometheus scrape only; OTLP is a future exporter swap)
- Traces or profiles pillar
- Alerting rules or notification channels
- Grafana dashboard provisioning as code (dashboards built manually in UI)
- Caching between scrapes
- Log shipping code inside Headwater (logs via Alloy/journald only)
- Docker on Lasker
- The router re-exposing subserver GPU metrics (Prometheus scrapes each service independently)
- Any changes to `/gpu`, `/status`, `/ping`, or `/logs/last` endpoints
- Node Exporter (can be added later; out of scope here)
- Lasker RAM upgrade (hardware concern, separate)
- Authentication on `/metrics` — intentionally unauthenticated, same as other observability endpoints
- Adding `/metrics` to `HeadwaterClient` — it returns Prometheus text, not JSON; no client method needed
- Background health-polling loop on the router — `headwater_backend_up` probes at scrape time only

**Prerequisites — must be resolved before implementation begins:**
- Lasker display output identifiers for dual-monitor kiosk (e.g. `DP-1`, `DP-2` — verify with `wlr-randr` on Lasker)

**Known host facts — Lasker:**
- OS: Ubuntu Server 24.04 LTS
- IP: 176.16.0.11
- Install method for Prometheus, Loki, Grafana: download prebuilt binaries from GitHub releases (Ubuntu 24.04 ships old versions via apt; use binaries for version control); use latest stable release at time of install
- Install method for Alloy: Grafana apt repo (`grafana.list`) — `grafana-alloy` package
- Kiosk compositor: **Sway** (`apt install sway`) — replaces Cage; Cage is single-output only and cannot drive two monitors
- Chromium: `apt install chromium-browser`
- No display manager needed — getty autologin on tty1 → `.bash_profile` → `sway`
- Display output identifiers: run `swaymsg -t get_outputs` after first Sway boot to get connector names for dual-monitor config

---

## 3. Interface Contracts

### 3.1 `GET /metrics` — subservers (bywater, deepwater)

Returns `text/plain; version=0.0.4` Prometheus exposition format.

**GPU instruments** (omitted when `headwater_gpu_available` is 0):
```
headwater_gpu_available{service_name, host_name}                          Gauge 0|1
headwater_gpu_memory_used_bytes{service_name, host_name, gpu_index, gpu_name}
headwater_gpu_memory_free_bytes{service_name, host_name, gpu_index, gpu_name}
headwater_gpu_memory_total_bytes{service_name, host_name, gpu_index, gpu_name}
headwater_gpu_utilization_ratio{service_name, host_name, gpu_index, gpu_name}   0.0–1.0
headwater_gpu_temperature_celsius{service_name, host_name, gpu_index, gpu_name}
```

**Ollama instruments** (omitted when Ollama is unreachable):
```
headwater_ollama_model_loaded{service_name, host_name, model_name}        ObservableGauge (0|1 per model)
headwater_ollama_model_vram_bytes{service_name, host_name, model_name}    ObservableGauge
headwater_ollama_model_cpu_offload_ratio{service_name, host_name, model_name}   ObservableGauge 0.0–1.0
```
All three are `ObservableGauge` (current state at collection time). Do NOT use `UpDownCounter` — that type accumulates deltas and would drift unboundedly across scrapes.

**HTTP instruments** (via opentelemetry-instrumentation-fastapi):
```
http_server_request_duration_seconds (histogram)
http_server_active_requests (gauge)
```
Activated by calling `FastAPIInstrumentor().instrument_app(app)` inside `register_metrics()`, after the `MeterProvider` is set.

**Resource attributes** on all instruments:
```
service.name    = "bywater" | "deepwater"
service.version = from pyproject.toml
host.name       = os.uname().nodename
```

### 3.2 `GET /metrics` — headwaterrouter

```
headwater_backend_up{backend_name, backend_url}    Gauge 0|1
```
Plus HTTP instruments (automatic). Does NOT re-expose subserver GPU metrics.

### 3.3 `register_metrics(app: FastAPI, server_name: str) -> None`

Called during server startup (alongside existing `register_routes()`). Initialises the OTel `MeterProvider`, registers observable callbacks, and mounts the Prometheus exporter at `/metrics`. Must be called exactly once per process.

**File location:** new file `headwater-server/src/headwater_server/server/metrics.py` — do not add to `logging_config.py` or `router.py`.

**Double-call guard required:** the function must check `metrics.get_meter_provider().__class__.__name__ != "MeterProvider"` (or equivalent) and return early if already initialized. This prevents test-suite panics when multiple tests construct FastAPI app instances.

**Mounting `/metrics` on FastAPI:** `PrometheusMetricReader()` alone starts a separate server on port 9464. To serve `/metrics` on the existing FastAPI app instead:
```python
from prometheus_client import make_asgi_app
app.mount("/metrics", make_asgi_app())
```
This must be done after `PrometheusMetricReader()` is constructed. Do NOT rely on the default prometheus_client HTTP server.

### 3.4 Alloy config — caruana

```river
// scrape bywater and headwaterrouter; forward to Prometheus on Lasker
// scrape journald; forward to Loki on Lasker
prometheus.scrape "headwater" {
  targets = [
    {"__address__" = "localhost:8080"},  // bywater
    {"__address__" = "localhost:8081"},  // headwaterrouter
  ]
  forward_to = [prometheus.remote_write.lasker.receiver]
}

prometheus.remote_write "lasker" {
  endpoint { url = "http://176.16.0.11:9090/api/v1/write" }
}

loki.source.journal "system" {
  forward_to = [loki.write.lasker.receiver]
}

loki.write "lasker" {
  endpoint { url = "http://176.16.0.11:3100/loki/api/v1/push" }
}
```

### 3.5 Alloy config — alphablue

Same shape as caruana but targets `localhost:8080` (deepwater only).

### 3.6 Lasker services

| Service    | Port | Config path                        |
|------------|------|------------------------------------|
| Prometheus | 9090 | `/etc/prometheus/prometheus.yml`   |
| Loki       | 3100 | `/etc/loki/config.yaml`            |
| Grafana    | 3000 | `/etc/grafana/grafana.ini`         |

Prometheus receives metrics via Alloy's `remote_write` — it does **not** scrape Headwater directly. Enable the remote write receiver by passing `--web.enable-remote-write-receiver` in the systemd unit's `ExecStart`:

```ini
# /etc/systemd/system/prometheus.service
[Service]
ExecStart=/usr/local/bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --web.enable-remote-write-receiver
```

```yaml
# /etc/prometheus/prometheus.yml
global:
  scrape_interval: 15s

# No scrape_configs for Headwater — Alloy owns all scraping.
```

Loki and Grafana use their default configs with storage paths set to `/var/lib/loki` and `/var/lib/grafana` respectively.

### 3.7 Lasker kiosk

```
Display stack:  Sway (Wayland compositor) + Chromium
Auto-login:     getty autologin (tty1) → ~/.bash_profile → sway
Chromium flags: --kiosk --noerrdialogs --disable-restore-session-state
Grafana URL:    http://localhost:3000/d/<dashboard-uid>?kiosk
Dual monitor:   sway config assigns one Chromium instance per output,
                each pointing at a different Grafana dashboard URL
Output names:   determined at first boot via `swaymsg -t get_outputs`
```

Sway config pattern (output names filled in after first boot):
```
output <OUTPUT-1> { ... }
output <OUTPUT-2> { ... }

exec chromium --kiosk --noerrdialogs http://localhost:3000/d/<dashboard1>?kiosk
exec chromium --kiosk --noerrdialogs http://localhost:3000/d/<dashboard2>?kiosk
```

---

## 4. Acceptance Criteria

**AC-1:** `GET /metrics` on bywater returns HTTP 200 with `Content-Type: text/plain; version=0.0.4`.

**AC-2:** `GET /metrics` on deepwater returns HTTP 200 with `Content-Type: text/plain; version=0.0.4`.

**AC-1 through AC-7 are unit tests** using `TestClient` against a locally constructed FastAPI app — no deployed service needed.

**AC-8 through AC-12 are manual HITL verification steps** against live infrastructure on Lasker.

---

**AC-3:** `GET /metrics` on headwaterrouter returns HTTP 200 with `Content-Type: text/plain; version=0.0.4`.

**AC-4:** When pynvml is unavailable, `headwater_gpu_available` equals 0, no GPU gauge lines are present, HTTP metrics are present, and the response is HTTP 200.
- Mock strategy: `sys.modules["pynvml"] = None` before constructing the app, or patch `pynvml.nvmlInit` to raise `Exception`. Restore after the test.
- Parse the response text and assert no line starts with `headwater_gpu_memory`.

**AC-5:** When Ollama is unreachable, no `headwater_ollama_*` lines are present and the response is HTTP 200.
- Mock strategy: patch the httpx call to the Ollama API to raise `httpx.ConnectError`.
- Parse the response text and assert no line starts with `headwater_ollama_`.

**AC-6:** When a backend is unreachable, the router's `/metrics` includes `headwater_backend_up{backend_name="<name>"} 0`.
- Mock strategy: patch the httpx probe inside the `headwater_backend_up` callback to raise `httpx.ConnectError` for the target backend URL.
- Parse the response text and assert the line `headwater_backend_up{...} 0` is present.

**AC-7:** All metrics carry `service_name` matching the server's configured name ("bywater", "deepwater", "headwaterrouter").
- Test approach: call `GET /metrics` via TestClient, parse the response text line by line, collect all unique `service_name` label values. Assert exactly one value is present and it matches the name passed to `register_metrics()`.
- Do not use a full Prometheus text parser — a regex on `service_name="<value>"` is sufficient.

**AC-8:** Prometheus on Lasker has received timeseries from all three Headwater services.
- Verification: `GET http://176.16.0.11:9090/api/v1/query?query=up` — Alloy sends the `up` metric alongside scraped metrics via remote_write. Assert the JSON response contains results with `job` labels covering bywater, headwaterrouter, and deepwater.
- Note: Prometheus's `/targets` page will be empty (no local scrape_configs). The `up` metric is the correct health signal.

**AC-9:** Loki on Lasker receives journald logs from caruana within 60 seconds of a log event.
- Verification: on caruana, emit a log line with a unique string (e.g. `logger -t headwater-test "ac9-probe-<timestamp>"`). Then poll `GET http://176.16.0.11:3100/loki/api/v1/query?query={host="caruana"}` until the entry appears or 60 seconds elapse.

**AC-10:** Loki on Lasker receives journald logs from alphablue within 60 seconds of a log event.
- Same as AC-9 but emit on alphablue and query `{host="alphablue"}`.

**AC-11:** Grafana on Lasker has both a Prometheus data source and a Loki data source configured and shows green health status.
- Verification: `GET http://176.16.0.11:3000/api/datasources` with admin credentials. Assert two entries exist with `type: "prometheus"` and `type: "loki"`. Then `POST /api/datasources/<id>/health` for each and assert `status: "OK"`.

**AC-12:** On Lasker boot, Chromium launches fullscreen in kiosk mode displaying the Grafana dashboard without manual intervention.
- Verification: reboot Lasker, wait for display to come up, confirm Chromium is fullscreen on both monitors showing Grafana. This is a manual visual check — no automated test.

---

## 5. Error Handling / Failure Modes

| Failure | Behaviour |
|---|---|
| pynvml unavailable or raises | `headwater_gpu_available 0`; GPU gauges omitted; HTTP 200 |
| Ollama unreachable | Ollama model metrics omitted; HTTP 200 |
| Both pynvml and Ollama fail | Only HTTP auto-instrumentation metrics present; HTTP 200 |
| `/metrics` endpoint itself panics | HTTP 500; Prometheus records scrape failure; Grafana shows gap |
| Backend unreachable (router) | `headwater_backend_up 0`; 2-second connect timeout per backend |
| Alloy agent down on a host | Metrics scrapes stop for that host (Alloy owns scraping); Prometheus shows gap; log gap in Loki |
| Lasker unreachable | Headwater services unaffected (pure pull architecture) |
| Prometheus remote_write fails | Alloy buffers locally up to configured WAL size; no data loss for short outages |
| OTel SDK init fails in `register_metrics()` | Service startup aborts; treat as a fatal error — do not catch and continue |

---

## 6. Conventions Example

```python
from __future__ import annotations

import importlib.metadata
import os
from typing import TYPE_CHECKING

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.metrics.export import Observation
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import make_asgi_app

if TYPE_CHECKING:
    from fastapi import FastAPI


def register_metrics(app: FastAPI, server_name: str) -> None:
    # Guard: return early if already initialized (prevents test-suite panics)
    if not isinstance(metrics.get_meter_provider(), metrics.NoOpMeterProvider):
        return

    resource = Resource.create({
        SERVICE_NAME: server_name,
        "host.name": os.uname().nodename,
        "service.version": importlib.metadata.version("headwater_server"),
    })
    reader = PrometheusMetricReader()
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    # Mount /metrics on the FastAPI app (do NOT use prometheus_client's default server on port 9464)
    app.mount("/metrics", make_asgi_app())

    # Activate automatic HTTP instrumentation
    FastAPIInstrumentor().instrument_app(app)

    meter = metrics.get_meter("headwater")

    def observe_gpu_memory_free(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            yield Observation(mem.free, {"gpu_index": "0"})
        except Exception:
            return  # omit when unavailable; headwater_gpu_available handles the signal

    meter.create_observable_gauge(
        "headwater.gpu.memory.free",
        callbacks=[observe_gpu_memory_free],
        unit="By",
        description="Free GPU VRAM in bytes",
    )
```

Key conventions:
- `Observation` is imported from `opentelemetry.sdk.metrics.export`, not from `opentelemetry.metrics`
- Instrument names use dots (`headwater.gpu.memory.free`); Prometheus renders as underscores
- Unit is always `"By"` for bytes — never MB
- Ratios are `0.0–1.0` — never percentages
- Observable callbacks `return` (not `raise`) on error; the `headwater_gpu_available` gauge is the error signal
- `register_metrics()` is called once at startup alongside `register_routes()`
- `service.version` uses `importlib.metadata.version("headwater_server")` — verify this package name matches the actual package name in `pyproject.toml` for each service

---

## 7. Domain Language

| Term | Definition |
|---|---|
| **instrument** | An OTel measurement object: `ObservableGauge`, `Counter`, `Histogram`, or `UpDownCounter` |
| **observable** | An instrument whose value is computed at collection time via a registered callback |
| **scrape** | A single Prometheus `GET /metrics` request that triggers observable callbacks |
| **collection** | The OTel SDK event that fires observable callbacks in response to a scrape |
| **resource** | The OTel entity descriptor attached to all metrics from a service (`service.name`, `host.name`, etc.) |
| **backend** | A named Headwater subserver as defined in `routes.yaml` (`bywater`, `deepwater`, etc.) |
| **Alloy** | The Grafana agent running on each host; responsible for scraping and forwarding metrics + logs |
| **kiosk** | Chromium running fullscreen via Sway, pointed at Grafana, with no interactive chrome |
| **remote_write** | The Prometheus protocol by which Alloy pushes scraped metrics to Prometheus on Lasker |
| **WAL** | Alloy's write-ahead log; buffers metrics locally when Lasker is temporarily unreachable |

---

## 8. Invalid State Transitions

- **GPU gauges MUST NOT be emitted when `headwater_gpu_available` is 0.** Emitting a value for `headwater_gpu_memory_free_bytes` alongside `headwater_gpu_available 0` is a contradiction.
- **`headwater_backend_up` MUST NOT be emitted without a `backend_name` label.** An unlabelled backend_up metric is uninterpretable.
- **The router MUST NOT re-expose subserver GPU metrics.** The router's `/metrics` scope is routing-layer signals only; GPU metrics belong to the subserver that owns the hardware.
- **`register_metrics()` MUST NOT be called more than once per process.** Calling it twice creates duplicate metric registrations that will panic the OTel SDK.
- **Observable callbacks MUST NOT raise.** An exception in a callback aborts the entire scrape collection. Callbacks must catch all errors and either yield a value or return silently.
