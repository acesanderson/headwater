# Infra Spec — Headwater Regression Tests

Infrastructure endpoints common to all hosts (ping, status, routes, logs, sysinfo, gpu, metrics).

---

### GET /ping
- **Description**: Liveness check. Returns `{"message": "pong"}` immediately.
- **Hosts to test**: all (headwater, bywater, deepwater)
- **Key inputs**: none
- **Expected response**: 200, `{"message": "pong"}`
- **Edge cases**: response must be JSON with key `message` equal to `"pong"`; must respond within 5s
- **Already covered**: no

---

### GET /status
- **Description**: Returns server health, available models, GPU state, uptime, and server name.
- **Hosts to test**: all (headwater, bywater, deepwater)
- **Key inputs**: none
- **Expected response**:
  - 200
  - Shape: `StatusResponse` — fields `status`, `message`, `models_available` (list[str]), `gpu_enabled` (bool), `uptime` (float|None), `server_name` (str)
  - `status` must be one of `"healthy"`, `"degraded"`, `"error"`
- **Edge cases**:
  - `server_name` differs per host (e.g. `"Bywater API Server"` on bywater, `"Deepwater API Server"` on deepwater)
  - `uptime` should be positive float
- **Already covered**: no

---

### GET /routes (subserver) / GET /routes/ (router)
- **Description**: On subservers returns list of active FastAPI routes. On the router returns the routing config dict (backends, routes, heavy_models, config_path).
- **Hosts to test**: all (headwater, bywater, deepwater)
- **Key inputs**: none
- **Expected response**:
  - Subserver: 200, list of dicts with keys `path`, `methods`, `name`
  - Router (`/routes/`): 200, dict with keys `backends` (dict), `routes` (dict), `heavy_models` (list), `config_path` (str)
- **Edge cases**:
  - Router response must contain at least one entry in `backends`
  - Router response must contain keys in `routes` mapping known services to backends
- **Already covered**: no

---

### GET /logs/last
- **Description**: Returns the last N log entries from the in-process ring buffer.
- **Hosts to test**: all (headwater, bywater, deepwater)
- **Key inputs**:
  - `n` (query param, int, default 50, min 1): number of entries to return; example `n=10`
- **Expected response**:
  - 200
  - Shape: `LogsLastResponse` — fields `entries` (list[LogEntry]), `total_buffered` (int), `capacity` (int)
  - Each `LogEntry` has: `timestamp` (float), `level` (str), `logger` (str), `message` (str), `pathname` (str), optional `request_id`, optional `extra`
- **Edge cases**:
  - `n=1` returns at most 1 entry
  - `n=0` should return 422 (query param `ge=1`)
  - `n` larger than `capacity` returns at most `capacity` entries
  - `total_buffered` and `capacity` are always non-negative ints
- **Already covered**: no

---

### GET /sysinfo
- **Description**: Returns CPU and RAM stats from the host OS. Subserver-only endpoint.
- **Hosts to test**: bywater, deepwater (subservers only; router does not expose /sysinfo)
- **Key inputs**: none
- **Expected response**:
  - 200
  - JSON dict with CPU and memory fields (exact shape from `get_sysinfo_service`; expect keys like `cpu_percent`, `memory_total_mb`, `memory_used_mb`, `memory_free_mb`)
- **Edge cases**:
  - All numeric values must be non-negative
  - `cpu_percent` should be in range 0–100
- **Already covered**: no

---

### GET /gpu (subserver)
- **Description**: Returns per-device GPU stats and Ollama loaded models for the local host.
- **Hosts to test**: bywater, deepwater
- **Key inputs**: none
- **Expected response**:
  - 200
  - Shape: `GpuResponse` — fields `server_name` (str), `gpus` (list[GpuInfo]), `ollama_loaded_models` (list[OllamaLoadedModel]), `error` (str|None)
  - `GpuInfo` fields: `index`, `name`, `vram_total_mb`, `vram_used_mb`, `vram_free_mb`, `utilization_pct`, `temperature_c`
  - `OllamaLoadedModel` fields: `name`, `size_mb`, `vram_mb`, `cpu_offload_mb`, `vram_pct`, `cpu_pct`
- **Edge cases**:
  - If GPU is unavailable: `error` is set and `gpus` is empty
  - `vram_free_mb` + `vram_used_mb` should equal `vram_total_mb`
  - `utilization_pct` should be in range 0–100
- **Already covered**: no

---

### GET /gpu (router)
- **Description**: Aggregates GPU stats from all configured backends. Router-only endpoint.
- **Hosts to test**: headwater (router only)
- **Key inputs**: none
- **Expected response**:
  - 200
  - Shape: `RouterGpuResponse` — field `backends` (dict[str, GpuResponse]), keyed by backend name
  - Each value is a `GpuResponse` (same shape as subserver /gpu)
- **Edge cases**:
  - If a backend is unreachable, its `GpuResponse` should have `error` set rather than the whole request failing
  - `backends` dict must contain an entry for each backend defined in routes.yaml
- **Already covered**: no

---

### GET /metrics
- **Description**: Prometheus text exposition format metrics endpoint.
- **Hosts to test**: all (headwater, bywater, deepwater)
- **Key inputs**: none
- **Expected response**:
  - 200
  - Content-Type: `text/plain; version=0.0.4`
  - Body: Prometheus text format (lines starting with `#` or metric name patterns)
- **Edge cases**:
  - Response must not be empty
  - Must contain at least one `# HELP` or `# TYPE` line
  - Router should expose backend-health metrics (e.g. `headwater_backend_up`)
  - Subservers should expose GPU metrics (e.g. `headwater_gpu_available`)
- **Already covered**: no
