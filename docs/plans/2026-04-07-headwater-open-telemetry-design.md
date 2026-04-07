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
- `headwater_backend_up` gauge on the router
- Alloy config on caruana (scrapes bywater + headwaterrouter, ships journald to Loki)
- Alloy config on alphablue (scrapes deepwater, ships journald to Loki)
- Lasker: Prometheus, Loki, Grafana installed as bare-metal systemd services
- Lasker: Cage + Chromium kiosk, auto-login, dual-monitor layout

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
headwater_ollama_model_loaded{service_name, host_name, model_name}        UpDownCounter
headwater_ollama_model_vram_bytes{service_name, host_name, model_name}
headwater_ollama_model_cpu_offload_ratio{service_name, host_name, model_name}   0.0–1.0
```

**HTTP instruments** (automatic via opentelemetry-instrumentation-fastapi):
```
http_server_request_duration_seconds (histogram)
http_server_active_requests (gauge)
```

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
  endpoint { url = "http://<lasker_ip>:9090/api/v1/write" }
}

loki.source.journal "system" {
  forward_to = [loki.write.lasker.receiver]
}

loki.write "lasker" {
  endpoint { url = "http://<lasker_ip>:3100/loki/api/v1/push" }
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

Prometheus receives metrics via Alloy's `remote_write` — it does **not** scrape Headwater directly. Enable the remote write receiver:

```yaml
# /etc/prometheus/prometheus.yml
global:
  scrape_interval: 15s

# No scrape_configs for Headwater — Alloy owns all scraping.
# Start Prometheus with: --web.enable-remote-write-receiver
```

Loki and Grafana use their default configs with storage paths set to `/var/lib/loki` and `/var/lib/grafana` respectively.

### 3.7 Lasker kiosk

```
Display stack:  Cage (Wayland kiosk compositor) + Chromium
Auto-login:     getty autologin → ~/.bash_profile → cage
Chromium flags: --kiosk --noerrdialogs --disable-restore-session-state
Grafana URL:    http://localhost:3000?kiosk
Dual monitor:   two Chromium instances, one per DP output, separate dashboard URLs
```

---

## 4. Acceptance Criteria

**AC-1:** `GET /metrics` on bywater returns HTTP 200 with `Content-Type: text/plain; version=0.0.4`.

**AC-2:** `GET /metrics` on deepwater returns HTTP 200 with `Content-Type: text/plain; version=0.0.4`.

**AC-3:** `GET /metrics` on headwaterrouter returns HTTP 200.

**AC-4:** When pynvml is unavailable, `headwater_gpu_available` equals 0, no GPU gauge lines are present, HTTP metrics are present, and the response is HTTP 200.

**AC-5:** When Ollama is unreachable, no `headwater_ollama_*` lines are present and the response is HTTP 200.

**AC-6:** When a backend is unreachable, the router's `/metrics` includes `headwater_backend_up{backend_name="<name>"} 0`.

**AC-7:** All metrics carry `service_name` matching the server's configured name ("bywater", "deepwater", "headwaterrouter").

**AC-8:** Prometheus on Lasker reports all three scrape targets as UP in its targets page.

**AC-9:** Loki on Lasker receives journald logs from caruana within 60 seconds of a log event.

**AC-10:** Loki on Lasker receives journald logs from alphablue within 60 seconds of a log event.

**AC-11:** Grafana on Lasker has both a Prometheus data source and a Loki data source configured and shows green health status.

**AC-12:** On Lasker boot, Chromium launches fullscreen in kiosk mode displaying the Grafana dashboard without manual intervention.

---

## 5. Error Handling / Failure Modes

| Failure | Behaviour |
|---|---|
| pynvml unavailable or raises | `headwater_gpu_available 0`; GPU gauges omitted; HTTP 200 |
| Ollama unreachable | Ollama model metrics omitted; HTTP 200 |
| Both pynvml and Ollama fail | Only HTTP auto-instrumentation metrics present; HTTP 200 |
| `/metrics` endpoint itself panics | HTTP 500; Prometheus records scrape failure; Grafana shows gap |
| Backend unreachable (router) | `headwater_backend_up 0`; 2-second connect timeout per backend |
| Alloy agent down on a host | Metrics scrapes still work (Alloy only handles forwarding); log gap in Loki |
| Lasker unreachable | Headwater services unaffected (pure pull architecture) |
| Prometheus remote_write fails | Alloy buffers locally up to configured WAL size; no data loss for short outages |

---

## 6. Conventions Example

```python
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.prometheus import PrometheusMetricReader

def register_metrics(app: FastAPI, server_name: str) -> None:
    resource = Resource.create({
        SERVICE_NAME: server_name,
        "host.name": os.uname().nodename,
        "service.version": importlib.metadata.version("headwater_server"),
    })
    reader = PrometheusMetricReader()  # serves /metrics via prometheus_client's default registry
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    meter = metrics.get_meter("headwater")

    def observe_gpu_memory_free(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            yield metrics.Observation(mem.free, {"gpu_index": "0"})
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
- Instrument names use dots (`headwater.gpu.memory.free`); Prometheus renders as underscores
- Unit is always `"By"` for bytes — never MB
- Ratios are `0.0–1.0` — never percentages
- Observable callbacks `return` (not `raise`) on error; the `headwater_gpu_available` gauge is the error signal
- `register_metrics()` is called once at startup alongside `register_routes()`

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
| **kiosk** | Chromium running fullscreen via Cage, pointed at Grafana, with no interactive chrome |
| **remote_write** | The Prometheus protocol by which Alloy pushes scraped metrics to Prometheus on Lasker |
| **WAL** | Alloy's write-ahead log; buffers metrics locally when Lasker is temporarily unreachable |

---

## 8. Invalid State Transitions

- **GPU gauges MUST NOT be emitted when `headwater_gpu_available` is 0.** Emitting a value for `headwater_gpu_memory_free_bytes` alongside `headwater_gpu_available 0` is a contradiction.
- **`headwater_backend_up` MUST NOT be emitted without a `backend_name` label.** An unlabelled backend_up metric is uninterpretable.
- **The router MUST NOT re-expose subserver GPU metrics.** The router's `/metrics` scope is routing-layer signals only; GPU metrics belong to the subserver that owns the hardware.
- **`register_metrics()` MUST NOT be called more than once per process.** Calling it twice creates duplicate metric registrations that will panic the OTel SDK.
- **Observable callbacks MUST NOT raise.** An exception in a callback aborts the entire scrape collection. Callbacks must catch all errors and either yield a value or return silently.
