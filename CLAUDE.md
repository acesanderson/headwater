# Headwater — Agent Development Guide

Headwater is a FastAPI routing gateway + subserver stack running on two Linux hosts. This file tells you how to develop, deploy, and debug it as a coding agent.

## Host Map

| Service | Host | Port | `host_alias` |
|---|---|---|---|
| `headwaterrouter` | caruana | 8081 | `"headwater"` (default) |
| `bywater` | caruana | 8080 | `"bywater"` |
| `deepwater` | alphablue | 8080 | `"deepwater"` |

Default `HeadwaterClient()` hits the **router** (8081). Target subservers directly with `host_alias`.

---

## The Inner Loop

**1. Make code changes locally.**

**2. Deploy:**
```bash
bash scripts/deploy.sh            # push + deploy to both hosts
bash scripts/deploy.sh caruana    # router + bywater only
bash scripts/deploy.sh alphablue  # deepwater only
bash scripts/deploy.sh --sync-deps  # add this when pyproject.toml/uv.lock changed
```

The script: pushes to GitHub → `git pull` on each host → `systemctl restart` → polls `/ping` until up. It will exit non-zero and print the failing service name if startup times out.

**3. Verify + inspect:**
```python
from headwater_client.client.headwater_client import HeadwaterClient

router  = HeadwaterClient(host_alias="headwater")
bywater = HeadwaterClient(host_alias="bywater")

router.ping()               # True/False
router.get_status()         # uptime, server name, version
router.get_logs_last(n=20)  # last N log records from ring buffer
router.get_routes()         # parsed routes.yaml: backends, routes, heavy_models
bywater.get_logs_last(n=20) # drill into subserver logs
```

---

## Triage Decision Tree

```
client failure
  → router.get_logs_last()
      routing error / backend unreachable / timeout?  → fix routing or network
      "proxy_response" log present with upstream_status?
        → subserver.get_logs_last()
            service error / bad model / validation?   → fix service logic
```

The router logs `proxy_request` (before) and `proxy_response` (after, includes `upstream_status`) for every proxied request. If neither appears, the request never reached the router.

---

## Ground Rules

- **Deploy before testing.** Local edits do nothing until `deploy.sh` runs.
- **Never assume a deploy succeeded** — the script polls `/ping`; trust that, not the git output.
- **Test against the router by default.** Use subserver `host_alias` only when isolating a subserver-specific bug.
- **New router endpoints must be registered before the catch-all** (`/{path:path}`). FastAPI matches routes in order — anything registered after the catch-all is silently swallowed.
- **`--sync-deps` is slow** — skip it unless `pyproject.toml` or `uv.lock` actually changed.
- **If a service fails to come up**, read logs before retrying a deploy. A syntax error or import failure will loop forever otherwise.

---

## Project Layout

```
headwater/
  headwater-api/      shared Pydantic models (StatusResponse, LogsLastResponse, etc.)
  headwater-client/   sync HeadwaterClient + async HeadwaterAsyncClient
  headwater-server/   FastAPI servers (router, bywater, deepwater entry points)
  scripts/deploy.sh   deploy script
  docs/plans/         feature specs and implementation plans
```

Local dependencies (conduit, dbclients, siphon) are installed as editable sources in `headwater-server/.venv`. If you add a new local dep, run `deploy.sh --sync-deps`.
