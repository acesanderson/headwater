# Headwater TUI Monitor — Design Spec

## Overview

Two standalone Python scripts displayed on a pair of 7" screens connected to Lasker (Ubuntu Server, Sway). Each script runs in its own terminal window. No coordination between them — each polls its data sources independently and fails/restarts independently.

**Left screen:** `hw-log` — HEADWATER logo header + live request stream from the router  
**Right screen:** `hw-vitals` — Hardware metrics for bywater and deepwater

---

## Architecture

```
Lasker (thin client, Sway)
  ├── terminal A  →  hw-log     polls router ring buffer (caruana:8081)
  └── terminal B  →  hw-vitals  polls router ring buffer (req/s, errors, health)
                                 polls each subserver /gpu + /sysinfo (GPU, Ollama, CPU, RAM)
```

Two scripts, no shared state, no IPC. Each uses `uv run` with inline dependencies. Deployed to `~/.local/bin/` on Lasker (or equivalent).

Both scripts use **Rich** (`rich.live.Live`) for rendering. No Textual — Rich's `Live` + `Layout` + `Panel` covers everything needed without the added complexity.

**Rendering approach for screen 1:** Rich `Live` with a fixed-height logo panel at the top and a capped log table filling the remainder. Rich redraws by repositioning the cursor and overwriting in place (not clear-screen), so flicker at 1s intervals is imperceptible. The table is capped at `terminal_height - header_height` rows and drops the oldest on overflow.

The terminal escape-code scroll region approach (used in the existing `logo.py` server startup) was considered and rejected — it is unreliable across terminal emulators and breaks on resize. Rich `Live` handles resize events correctly via `console.size`.

If Rich `Live` causes rendering issues on Lasker's terminal emulator in practice, Textual (`Header` + `RichLog`) is the clean upgrade path — logic unchanged, rendering layer swapped.

---

## Screen 1 — `hw-log` (left)

### Layout

```
┌─────────────────────────────────────────────────────────┐
│  HEADWATER logo (green block letters, fixed)            │
│  router · caruana:8081 · up · N backends healthy        │
├─────────────────────────────────────────────────────────┤
│  TIME    METHOD  SERVICE/PATH  ROUTE  BACKEND  MODEL  STATUS  DUR  │  ← muted header
├─────────────────────────────────────────────────────────┤
│  scrolling request rows (newest at bottom)              │
│  ...                                                    │
│  ▋                                                      │
└─────────────────────────────────────────────────────────┘
```

### Header element

- HEADWATER logo from `logo.py` rendered as a `rich.text.Text` block in green (`#4ec9b0`)
- Background `#0a0a0a` (same for logo and status subtitle — one unified panel)
- Status line below logo: `router · caruana:8081 · up · N backends healthy` in muted grey
- Separated from log body by a single dark rule

### Request rows

One line per proxied request. Fields:

| Field | Source | Color |
|---|---|---|
| TIME | log record timestamp | `#333333` (muted) |
| METHOD | `request_finished.method` | `#4ec9b0` green |
| SERVICE/PATH | `proxy_request.path` | `#dcdcaa` yellow |
| ROUTE | resolved route key (e.g. `heavy_inference`, `conduit`) | `#c586c0` purple; `#e8c07d` amber for non-default routes |
| BACKEND | `proxy_request.backend` | `#6a9fb5` blue |
| MODEL | `proxy_request.model` (omit `—` if none) | `#ce9178` orange |
| STATUS | `proxy_response.upstream_status` | `#4ec9b0` 2xx · `#e8c07d` 4xx · `#f44747` 5xx |
| DUR | `request_finished.duration_ms` | `#333333` muted |

**Route coloring rule:** purple for routes where route key == service name (normal); amber for special routing decisions (`heavy_inference`, `ambient_inference`, `reranker_heavy`).

### Data source

Poll `HeadwaterClient.get_logs_last(n=100)` on the router every **1 second**. Track the last-seen log ID/timestamp to emit only new records. Join `proxy_request` + `proxy_response` log pairs on `req_id` to assemble one complete row per request.

Log events needed per row:
- `proxy_request`: service, backend, model, path, **route** (see below)
- `proxy_response`: upstream_status, req_id
- `request_finished`: method, duration_ms

If a pair is incomplete (response not yet logged), hold the row for one more poll cycle before emitting with partial data.

**Route key logging requirement:** The router must log the resolved route key (e.g. `heavy_inference`, `reranker_light`) as a field in the `proxy_request` log record. Without this, the TUI would need to re-implement `resolve_backend()` logic and hold a copy of routes.yaml — coupling that doesn't belong in a display script. Adding `route` to the `proxy_request` extra dict is a one-line server-side change.

### Scroll behavior

Newest requests at the bottom. Buffer the last N rows that fit the terminal height minus the header. On resize, recalculate.

### Poll interval

1 second.

---

## Screen 2 — `hw-vitals` (right)

### Layout

```
┌──────────────────────┐  ┌──────────────────────┐
│  bywater  ●  54°C    │  │  deepwater  ●  81°C   │
│  caruana · RTX 4090M │  │  alphablue · RTX 3090 │
│  up 2d 4h            │  │  up 2d 4h             │
│                      │  │                       │
│  GPU UTIL  [████  ]  │  │  GPU UTIL  [████████] │
│  8%                  │  │  91%                  │
│  VRAM      [██    ]  │  │  VRAM      [███████ ] │
│  4.1 / 16 GB         │  │  39.8 / 48 GB         │
│                      │  │                       │
│  CPU UTIL  [█     ]  │  │  CPU UTIL  [█       ] │
│  12%                 │  │  5%                   │
│  RAM       [███   ]  │  │  RAM       [██      ] │
│  5.4 / 16 GB         │  │  22.4 / 64 GB         │
│                      │  │                       │
│  OLLAMA              │  │  OLLAMA               │
│  gpt-oss:latest      │  │  qwq:latest           │
│  3.2 GB  0%cpu  8%gpu│  │  34.1 GB  18%cpu  91%gpu│
│  1.2 req/s · 0 err   │  │  0.1 req/s · 0 err   │
└──────────────────────┘  └──────────────────────┘

ROUTER · caruana:8081 · up · 2/2 backends healthy · last poll 0.8s ago
```

### Panel contents (per GPU host)

**Header:** `{backend_name}  ●  {temp}°C` — temp color: green <70°C, amber 70–85°C, red >85°C  
**Subtitle:** `{hostname} · {gpu_name} · up {uptime}`

**Metrics grid (2-column):**
- GPU UTIL: progress bar + percentage — bar color mirrors temp threshold (green/amber/red)
- VRAM: progress bar + `used / total GB`
- CPU UTIL: progress bar + percentage
- RAM: progress bar + `used / total GB`

**Ollama section:**  
One row per loaded model:
```
{model_name}   {total_size}   {cpu_offload%} cpu   {gpu%} gpu
{req/s} req/s · {err_count} err
```
CPU % shown only when >0 (model partially offloaded to CPU — fat model case).  
Error count muted grey when 0; red when >0.

### Router status bar

Single line at the bottom of the screen:  
`ROUTER · caruana:8081 · up · N/N backends healthy · last poll Xs ago`

### Data sources

| Metric | Source | Available now? |
|---|---|---|
| GPU util, VRAM, temperature | `GET /gpu` on each subserver (GpuResponse, pynvml) | Yes |
| Ollama loaded models + VRAM + CPU offload | `GET /gpu` → `ollama_loaded_models` | Yes |
| Uptime | `HeadwaterClient.get_status()` | Yes |
| Backend health | `HeadwaterClient.ping()` or router `/metrics` `headwater.backend.up` | Yes |
| **CPU %** | **Not currently exposed — needs `/sysinfo` endpoint** | **No** |
| **RAM used/total** | **Not currently exposed — needs `/sysinfo` endpoint** | **No** |
| req/s per backend | Router ring buffer: count `proxy_response` records per backend in a rolling 60s window | Yes (computed) |
| Error count | Router ring buffer: count `proxy_response` records with `upstream_status >= 500` per backend, rolling 60s | Yes (computed) |

### New endpoint required: `/sysinfo`

A lightweight endpoint on each subserver returning CPU % and RAM via `psutil`:

```python
# Response shape
{
    "cpu_percent": 12.4,
    "ram_used_bytes": 5798205440,
    "ram_total_bytes": 17179869184,
}
```

This is the only new server-side work required. One endpoint, one `psutil` call, registered on `HeadwaterServerAPI`.

### Poll interval

2 seconds (GPU metrics change slowly; sub-second refresh adds no value).

### Color thresholds

| Metric | Green | Amber | Red |
|---|---|---|---|
| GPU util | < 60% | 60–85% | > 85% |
| VRAM | < 70% | 70–90% | > 90% |
| CPU util | < 60% | 60–80% | > 80% |
| Temperature | < 70°C | 70–85°C | > 85°C |

---

## Technology

- **Runtime:** Python 3.12, `uv run` with inline script metadata
- **Rendering:** `rich` — `Live`, `Layout`, `Panel`, `Text`, `Progress` — used for both screens
- **HTTP client:** `HeadwaterClient` (sync) for ring buffer polling; raw `httpx` for `/gpu` and `/sysinfo` subserver calls
- **Dependencies:** `rich`, `httpx`, `headwater-client` (installed on Lasker)

### Key rendering decisions

| Decision | Chosen | Rejected | Reason |
|---|---|---|---|
| Screen 1 rendering | Rich `Live` (cursor reposition) | Escape-code scroll region | Escape codes unreliable across terminal emulators and on resize |
| Screen 2 rendering | Rich `Live` | — | Static panel layout, 2s refresh, no flicker concern |
| Framework | Rich | Textual | Sufficient for read-only display; Textual is upgrade path if needed |

---

## Deployment

Lasker runs Ubuntu Server + Sway. Each script is opened in a terminal emulator (e.g. `foot`) assigned to its output via Sway config or `swaymsg`:

```bash
# Sway config excerpt
output DP-1 { ... }   # left screen  → hw-log
output DP-2 { ... }   # right screen → hw-vitals
```

Scripts installed to `~/.local/bin/hw-log` and `~/.local/bin/hw-vitals` and launched on login via Sway's `exec` directive or a startup script.

---

## Out of Scope

- Grafana / Prometheus (separate concern, future)
- backwater and stillwater backends (not yet running)
- Interactivity / filtering (read-only display only)
- Alerting / notifications
- Historical data / sparklines

---

## Open Questions

- Does alphablue's GPU need to be identified by name in the server (currently "GPU (alphablue)" in the mockup)? The actual name will come from pynvml.
- Should `hw-log` also show non-proxied requests (e.g. `/ping`, `/status` hitting the router directly)? Suggested default: filter those out — they're noise.
