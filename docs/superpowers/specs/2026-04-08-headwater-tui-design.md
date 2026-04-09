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

**Rendering approach for screen 1:** Rich `Live` with a fixed-height logo panel at the top and a capped log table filling the remainder. Rich redraws by repositioning the cursor and overwriting in place (not clear-screen), so flicker at 1s intervals is imperceptible. The table is capped at `terminal_height - header_height` rows and drops the oldest on overflow. On resize, recalculate the cap from `console.size`.

The terminal escape-code scroll region approach (used in the existing `logo.py` server startup) was considered and rejected — it is unreliable across terminal emulators and breaks on resize. Rich `Live` handles resize events correctly via `console.size`.

If Rich `Live` causes rendering issues on Lasker's terminal emulator in practice, Textual (`Header` + `RichLog`) is the clean upgrade path — logic unchanged, rendering layer swapped.

---

## Explicit Non-Goals

These are excluded because a subagent might reasonably add them. They are explicitly out of scope:

- **No keyboard input** — Ctrl-C exits. No `q`, no filters, no scrollback navigation.
- **No file output** — nothing written to disk. No request log file, no error log file.
- **No config file** — backends and poll intervals are hardcoded constants or env vars. No YAML/TOML config.
- **No alerts** — no visual flash, no terminal bell, no desktop notification on errors or high temp.
- **No auto-reconnect backoff** — on poll failure, retry on next cycle. No exponential backoff, no jitter.
- **No historical data** — no sparklines, no rolling averages displayed, no time-series storage.
- **No authentication** — scripts assume the local network is trusted. No API keys, no tokens.
- **Grafana / Prometheus** — separate concern, future work.
- **backwater and stillwater** — not yet running; not included.

---

## Screen 1 — `hw-log` (left)

### Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  HEADWATER logo (green, fixed, 76-char wide)                                │
│  router · caruana:8081 · up · N backends healthy · last poll Xs ago         │
├─────────────────────────────────────────────────────────────────────────────┤
│  TIME     METH  SERVICE/PATH              ROUTE              BACKEND   MODEL        ST   DUR   │
├─────────────────────────────────────────────────────────────────────────────┤
│  14:32:01 POST  conduit/generate          conduit            → bywater  gpt-oss     200  312ms │
│  ...                                                                        │
│  ▋                                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Header element

- HEADWATER logo rendered as a `rich.text.Text` block in green (`#4ec9b0`), taken verbatim from `logo.py`
- Background `#0a0a0a` for both logo and status subtitle — one unified `Panel`
- Status line: `router · caruana:8081 · {up|UNREACHABLE} · N backends healthy · last poll Xs ago`
- "last poll Xs ago" counts seconds since the last successful `get_logs_last()` call
- Separated from log body by Rich's default panel border

### Column layout

Fixed column widths to fit ~120 terminal columns (typical for a 7" screen at reasonable font size). If terminal is narrower than 80 columns, truncate MODEL and ROUTE to fit; never wrap a row.

| Col | Width | Content |
|---|---|---|
| TIME | 8 | `HH:MM:SS` |
| METH | 5 | `GET`, `POST`, etc. |
| SERVICE/PATH | 28 | e.g. `conduit/generate` — truncate with `…` if longer |
| ROUTE | 18 | route key — truncate with `…` if longer |
| BACKEND | 12 | `→ bywater` etc. |
| MODEL | 16 | model name or `—` — truncate with `…` if longer |
| ST | 4 | status code |
| DUR | 7 | `NNNNms` |

### Request rows

One line per proxied request. Colors:

| Field | Color |
|---|---|
| TIME | `#333333` muted |
| METH | `#4ec9b0` green |
| SERVICE/PATH | `#dcdcaa` yellow |
| ROUTE — standard (route key == service name) | `#c586c0` purple |
| ROUTE — special (`heavy_inference`, `ambient_inference`, `reranker_heavy`) | `#e8c07d` amber |
| BACKEND | `#6a9fb5` blue |
| MODEL | `#ce9178` orange |
| STATUS 2xx | `#4ec9b0` green |
| STATUS 4xx | `#e8c07d` amber |
| STATUS 5xx | `#f44747` red |
| DUR | `#333333` muted |

**Filtered out:** `/ping`, `/status`, `/metrics`, `/logs/last`, `/routes/`, `/gpu`, `/sysinfo` requests hitting the router. These are internal health-check traffic and are noise in the request stream.

### Data source and row assembly

Poll `HeadwaterClient.get_logs_last(n=100)` on the router every **1 second**. Deduplicate by tracking the timestamp of the last-seen record; only process records newer than that.

Each displayed row requires three log events joined on `req_id`:
- `proxy_request`: `path`, `service`, `backend`, `model`, `route`
- `proxy_response`: `upstream_status`
- `request_finished`: `method`, `duration_ms`

**Incomplete row timeout:** hold pending rows (awaiting response) for up to **3 poll cycles (3 seconds)**. After 3 cycles, emit the row with available fields; missing fields render as `—`.

**Row buffer:** maintain a deque capped at `max(1, terminal_height - header_height - 2)` rows. Oldest dropped on overflow. Header height is 8 lines (6 logo + 1 status + 1 column header).

### Route key logging requirement

The router logs `proxy_request` with `service`, `backend`, and `model` but not the resolved route key. The router must add `route` (string) to the `proxy_request` log record's `extra` dict. Value is the route key string (e.g. `"heavy_inference"`, `"conduit"`). When routing fails before resolution (RoutingError), `route` should be `"unknown"`. This is a one-line change in `router.py`.

### Failure handling

| Condition | Behaviour |
|---|---|
| Router unreachable | Status line shows `UNREACHABLE`; log area freezes on last-known rows; retry every poll cycle |
| `get_logs_last()` returns empty | Log area shows last-known rows; no error displayed |
| Poll takes longer than 1s | Next poll starts immediately after previous completes; no queuing |
| Terminal < 76 columns wide | Logo replaced with plain text `HEADWATER` in green; layout continues normally |

### Poll interval

1 second.

---

## Screen 2 — `hw-vitals` (right)

### Layout

```
┌──────────────────────────┐  ┌──────────────────────────┐
│  bywater  ●  54°C        │  │  deepwater  ●  81°C       │
│  caruana · RTX 4090M     │  │  alphablue · {gpu_name}   │
│  up 2d 4h                │  │  up 2d 4h                 │
│                          │  │                           │
│  GPU UTIL  [████      ]  │  │  GPU UTIL  [█████████  ]  │
│  8%                      │  │  91%                      │
│  VRAM      [██        ]  │  │  VRAM      [████████   ]  │
│  4.1 / 16 GB             │  │  39.8 / 48 GB             │
│                          │  │                           │
│  CPU UTIL  [█         ]  │  │  CPU UTIL  [█          ]  │
│  12%                     │  │  5%                       │
│  RAM       [███       ]  │  │  RAM       [██         ]  │
│  5.4 / 16 GB             │  │  22.4 / 64 GB             │
│                          │  │                           │
│  OLLAMA                  │  │  OLLAMA                   │
│  gpt-oss:latest          │  │  qwq:latest               │
│  3.2 GB  —  8% gpu       │  │  34.1 GB  18% cpu  91%gpu │
│  1.2 req/s · 0 err       │  │  0.1 req/s · 0 err        │
└──────────────────────────┘  └──────────────────────────┘

ROUTER · caruana:8081 · up · 2/2 backends healthy · last poll 0.8s ago
```

### Panel contents (per GPU host)

**Header:** `{backend_name}  ●  {temp}°C` — temp color applied to both the `●` and the value  
**Subtitle:** `{hostname} · {gpu_name_from_pynvml} · up {uptime}`

If a host has multiple GPUs, render one GPU UTIL + VRAM row pair per GPU, labelled `GPU 0`, `GPU 1`, etc. Temperature shown is the maximum across all GPUs.

**Metrics grid (2-column, left=label+bar, right=value):**
- GPU UTIL: `rich.progress.ProgressBar` + `{pct}%` — bar color tracks GPU util thresholds
- VRAM: bar + `{used:.1f} / {total:.1f} GB`
- CPU UTIL: bar + `{pct}%`
- RAM: bar + `{used:.1f} / {total:.1f} GB`

**Ollama section:**

When models are loaded:
```
{model_name}   {total_gb:.1f} GB   [{cpu_pct}% cpu]   {gpu_pct}% gpu
{req/s:.1f} req/s · {err_count} err
```
- `cpu_pct` shown only when ≥ 1% (integer threshold; hides sub-1% floating point noise)
- `err_count` is muted grey when 0; red `#f44747` when > 0
- req/s is `count of proxy_response records for this backend / 60`, computed from the router ring buffer rolling window; if script has been running < 60s, use elapsed seconds as denominator
- One row-pair per loaded model

When no models are loaded: show `OLLAMA  —  no models loaded` in muted grey. Do not hide the section.

### Backend offline state

When a subserver is unreachable (any httpx error on `/gpu` or `/sysinfo`):
- Panel header shows `{backend_name}  ✕  OFFLINE` in red
- All metric bars show at 0, values show `—`
- Ollama section shows `—`
- Last known temperature not retained — show `—`
- Continue polling every cycle; recover automatically when backend responds

### Router status bar

Single line at the bottom:  
`ROUTER · caruana:8081 · {up|UNREACHABLE} · N/N backends healthy · last poll {X}s ago`

When router is unreachable: `N/N` shows last known count; entire line turns amber.

### Data sources

| Metric | Endpoint | Field |
|---|---|---|
| GPU util | `GET {subserver}/gpu` → `GpuResponse.gpus[i].utilization` | pynvml `utilization.gpu / 100.0` |
| VRAM used/total | `GET {subserver}/gpu` → `GpuResponse.gpus[i]` | `memory_used`, `memory_total` (bytes) |
| Temperature | `GET {subserver}/gpu` → `GpuResponse.gpus[i].temperature_celsius` | pynvml temp |
| Ollama models | `GET {subserver}/gpu` → `GpuResponse.ollama_loaded_models` | name, size, size_vram |
| CPU % | `GET {subserver}/sysinfo` → `cpu_percent` | psutil |
| RAM used/total | `GET {subserver}/sysinfo` → `ram_used_bytes`, `ram_total_bytes` | psutil |
| Uptime | `GET {subserver}/status` → `StatusResponse.uptime_seconds` | formatted as `Nd Nh` |
| Backend health | `GET router/ping` per backend or `headwater.backend.up` metric | ping 200 = up |
| req/s, error count | Router ring buffer `proxy_response` records, per `backend` field | rolling 60s window |

### New endpoint required: `/sysinfo`

```python
# GET /sysinfo — registered on HeadwaterServerAPI before catch-all
{
    "cpu_percent": 12.4,          # psutil.cpu_percent(interval=None)
    "ram_used_bytes": 5798205440,
    "ram_total_bytes": 17179869184,
}
```

`psutil.cpu_percent(interval=None)` returns non-blocking instantaneous reading. The first call after process start may return 0.0 — this is acceptable; the TUI will show 0% until the next poll.

If `/sysinfo` returns 404 (server not yet updated), hw-vitals shows `cpu —` and `ram —` for that backend and logs a one-time warning to stderr. It does not crash.

### Poll interval

2 seconds for `/gpu` and `/sysinfo`. Router ring buffer polled every 2 seconds for req/s and error counts.

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

## Observability

**Both scripts — error visibility:**
- All poll errors (network timeout, HTTP error, parse failure) are displayed inline in the UI — never silently swallowed
- `hw-log`: poll errors appear in the header status line (e.g. `UNREACHABLE`)
- `hw-vitals`: poll errors appear in the affected panel (e.g. `✕ OFFLINE`)
- Unhandled exceptions at the top level print a traceback to stderr before exiting; stdout (the TUI) is not used for error output

**Staleness indicators:**
- `hw-log` header: `last poll Xs ago` — turns amber if > 5s since last successful poll
- `hw-vitals` status bar: `last poll Xs ago` — turns amber if > 10s since last successful poll

**Server-side (`/sysinfo`):**
- Endpoint logged at `DEBUG` level with `cpu_percent` and `ram_used_bytes` in extra fields
- No new metrics registered for `/sysinfo` — it is an internal diagnostic endpoint

**Server-side (route key logging):**
- `route` field appears in existing `proxy_request` log records — no new log lines, no new metrics

---

## Acceptance Criteria

### Server-side

**AC-1** `/sysinfo` endpoint exists on bywater and deepwater, returns `cpu_percent` (float), `ram_used_bytes` (int), `ram_total_bytes` (int), and responds within 500ms under normal load.

**AC-2** Router `proxy_request` log records include a `route` field (string). Value is the resolved route key (e.g. `"conduit"`, `"heavy_inference"`). Value is `"unknown"` when routing fails before resolution.

### `hw-log`

**AC-3** The HEADWATER logo renders in green (`#4ec9b0`) and does not scroll when new log rows arrive.

**AC-4** Each proxied request that completes appears as exactly one row within 2 poll cycles (≤ 2s) of `proxy_response` being logged.

**AC-5** Status code column is green for 2xx, amber for 4xx, red for 5xx.

**AC-6** ROUTE column is purple for standard routes and amber for `heavy_inference`, `ambient_inference`, `reranker_heavy`.

**AC-7** When the router is unreachable, the script does not crash; the header shows `UNREACHABLE`; existing rows remain visible.

**AC-8** When the terminal is resized, the row buffer recalculates and the display redraws correctly without crashing.

**AC-9** Internal requests (`/ping`, `/status`, `/metrics`, `/logs/last`, `/routes/`, `/gpu`, `/sysinfo`) do not appear in the log stream.

### `hw-vitals`

**AC-10** bywater and deepwater each occupy approximately 50% of terminal width as side-by-side panels.

**AC-11** Temperature color is green below 70°C, amber 70–85°C, red above 85°C. Applied to both the `●` indicator and the temperature value.

**AC-12** When a subserver is unreachable, its panel shows `✕ OFFLINE` in red; metric values show `—`; the script does not crash; the panel recovers automatically when the backend responds.

**AC-13** The Ollama section shows `no models loaded` (muted) when no models are active. CPU % is shown per model only when ≥ 1%.

**AC-14** req/s is computed as `count of proxy_response records for this backend in the last 60s / 60` (or elapsed seconds if script has run < 60s).

**AC-15** When `/sysinfo` returns 404, CPU and RAM fields show `—`; a one-time warning is printed to stderr; the script does not crash.

---

## Human-in-the-Loop Review Gates

TUI output is visually opaque to automated verification. Six explicit HITL gates are required during implementation. The plan must pause at each gate and not proceed until the user approves.

**Gate 1 — Header only (hw-log)**  
Implement the HEADWATER logo + status line only. Run on Lasker before any log rows are built.  
*Assess:* block character rendering, font/terminal emulator choice, font size, logo legibility.  
*Possible outcomes:* switch terminal emulator, change font size, fall back to smaller logo variant.

**Gate 2 — Live log rows, no color (hw-log)**  
Plain unstyled rows scrolling from real traffic. No color, no filtering applied yet.  
*Assess:* column widths with real request paths (`siphon/process_document_with_audio` etc.), truncation, 1s refresh flicker on Lasker.  
*Possible outcomes:* adjust column widths, shorten SERVICE/PATH, widen MODEL, change poll interval, escalate to Textual if flicker is unacceptable.

**Gate 3 — Full hw-log with color and filtering**  
All colors applied, route highlighting active, internal requests filtered.  
*Assess:* purple/amber route distinction, muted timestamp legibility, overall color harmony at viewing distance.  
*Possible outcomes:* color value adjustments, muting level changes.

**Gate 4 — hw-vitals panel layout with static/mock data**  
Both panels rendering with hardcoded values; no live API calls yet.  
*Assess:* progress bar visibility, two-column grid on actual screen real estate, temperature placement in header.  
*Possible outcomes:* bar height, label positioning, grid density changes.

**Gate 5 — hw-vitals with live data**  
Real GPU names (e.g. `NVIDIA GeForce RTX 3090`), real model names (`deepseek-r1:70b`), real temps.  
*Assess:* layout breaks from longer-than-expected strings, truncation behaviour with real data.  
*Possible outcomes:* truncation rules for GPU name and model name fields.

**Gate 6 — Both screens on Lasker simultaneously**  
Final integration: both scripts running, both 7" screens live side by side.  
*Assess:* readability at viewing distance, ambient light, complementarity of the two screens.  
*Possible outcomes:* font size increase, terminal emulator brightness/contrast tuning, column visibility changes.

---

## Deployment

Lasker runs Ubuntu Server + Sway. Each script is opened in a terminal emulator (e.g. `foot`) assigned to its output via Sway config:

```bash
# Sway config excerpt
output DP-1 { ... }   # left screen  → hw-log
output DP-2 { ... }   # right screen → hw-vitals
```

Scripts installed to `~/.local/bin/hw-log` and `~/.local/bin/hw-vitals` and launched on login via Sway's `exec` directive or a startup script.
