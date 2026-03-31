# HeadwaterRouter Design

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan.

**Date:** 2026-03-30
**Status:** Approved

---

## 1. Goal

HeadwaterRouter is a thin gateway server that runs on Caruana (port 8081) and receives all requests from `HeadwaterClient` when no explicit backend is specified. It reads `~/.config/headwater/routes.yaml` at startup, determines the correct backend based on service type and model weight, and forwards the request via HTTP proxy — failing immediately on backend errors with no retries.

---

## 2. Constraints and Non-Goals

### Constraints
- No streaming support — router buffers and returns full responses only
- No retry or fallback on backend failure — fail immediately, propagate the upstream error
- `routes.yaml` is read at startup and cached in memory; changes require a server restart
- Router runs only on Caruana; it is not deployed on AlphaBlue, Cheet, or Botvinnik
- Router has no dependency on conduit, embeddings, or any headwater service library — it is a pure HTTP proxy
- Deployment of the router and the `dbclients` update (renaming `headwater_server` → router) must be coordinated as a single cutover; they are not independently safe to deploy

### Non-Goals
- Load balancing across multiple instances of the same backend
- Authentication or rate limiting
- Health checking or backend discovery
- Streaming / SSE forwarding
- Dynamic config reload without restart
- Routing by anything other than service type and model `heavy` flag
- Alias-based routing (e.g. "sporadic", "interactive") — deferred, no timeline
- VRAM offload detection — tracked separately in `docs/backlog.md`

---

## 3. Interface Contracts

### routes.yaml schema

```yaml
backends:
  deepwater:   http://172.16.0.2:8080
  bywater:     http://172.16.0.4:8080
  backwater:   http://172.16.0.9:8080
  stillwater:  http://172.16.0.3:8080

routes:
  conduit:           bywater
  heavy_inference:   deepwater
  siphon:            deepwater
  curator:           bywater
  embeddings:        backwater
  reranker_light:    backwater
  reranker_heavy:    bywater
  ambient_inference: stillwater

heavy_models:
  - qwq:latest
  - deepseek-r1:70b
```

### RouterConfig

Loaded once at startup from `~/.config/headwater/routes.yaml`. Immutable after load.

```python
@dataclass(frozen=True)
class RouterConfig:
    backends: dict[str, str]   # backend name -> base_url
    routes: dict[str, str]     # service name -> backend name
    heavy_models: list[str]    # model names that trigger heavy_inference routing
```

### Route resolution

```python
def resolve_backend(service: str, model: str | None, config: RouterConfig) -> str:
    """
    Returns a backend base_url for the given service and model.
    Raises RoutingError if the service is not in config.routes.
    """
```

Resolution logic (evaluated in order):
1. If `service == "conduit"` and `model in config.heavy_models` → use `config.routes["heavy_inference"]`
2. If `service == "reranker"` and `model in config.heavy_models` → use `config.routes["reranker_heavy"]`
3. If `service == "reranker"` and `model not in config.heavy_models` (or model is None) → use `config.routes["reranker_light"]`
4. Otherwise → `config.routes[service]`

Note: the URL path prefix for reranker requests is `reranker/...`. The router maps the `reranker` prefix to either `reranker_light` or `reranker_heavy` service keys internally — callers never use those keys directly.

Unknown models (not in `heavy_models`) are treated as light — route to the default backend for that service.

### HeadwaterRouter class

New class in `headwater-server/src/headwater_server/server/`, alongside `HeadwaterServer`:

```python
class HeadwaterRouter:
    def __init__(self, name: str = "Headwater Router"): ...
    def _load_config(self) -> RouterConfig: ...   # reads routes.yaml, raises on missing file
    def _register_routes(self): ...               # single catch-all proxy route
    def _register_middleware(self): ...           # reuses existing correlation middleware
    def _register_error_handlers(self): ...       # reuses existing error handlers
```

Single catch-all route:
```python
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str): ...
```

### pyproject.toml entry point

```toml
[project.scripts]
headwater-router = "headwater_server.server.main:router_main"
```

### dbclients — NetworkContext changes

```python
@dataclass(frozen=True)
class NetworkContext:
    ...
    headwater_server: str    # NOW: Caruana:8081 (the router) — was AlphaBlue:8080
    deepwater_server: str    # NEW: AlphaBlue:8080 (direct inference)
    stillwater_server: str   # NEW: Botvinnik:8080
    bywater_server: str      # unchanged: Caruana:8080
    backwater_server: str    # unchanged: Cheet:8080
```

VPN IP assignments:
- `headwater_server` → `172.16.0.4:8081` (Caruana, router)
- `deepwater_server` → `172.16.0.2:8080` (AlphaBlue)
- `stillwater_server` → `172.16.0.3:8080` (Botvinnik)

### HeadwaterClient / HeadwaterTransport changes

```python
host_alias: Literal[
    "headwater",   # router on Caruana:8081 (default)
    "bywater",     # Caruana:8080 (direct)
    "backwater",   # Cheet:8080 (direct)
    "deepwater",   # AlphaBlue:8080 (direct)
    "stillwater",  # Botvinnik:8080 (direct)
] = "headwater"
```

`HeadwaterTransport._get_url()` adds a `case "deepwater"` and `case "stillwater"` branch.

---

## 4. Acceptance Criteria

- **AC-1:** `HeadwaterClient()` (no args) resolves to Caruana:8081 after dbclients update
- **AC-2:** `HeadwaterClient(host_alias="deepwater")` resolves to AlphaBlue:8080 directly, bypassing the router
- **AC-3:** A `POST /conduit/generate` request with a non-heavy model is forwarded to Bywater
- **AC-4:** A `POST /conduit/generate` request with a model in `heavy_models` is forwarded to Deepwater
- **AC-5:** A `POST /reranker/rerank` request with a heavy model is forwarded to Bywater; a light model forwards to Backwater
- **AC-6:** A request to an unknown service (not in `routes`) returns a `RoutingError` with a meaningful message, not a 500
- **AC-7:** If the target backend returns a non-2xx response, the router propagates the status code and body verbatim to the client
- **AC-8:** If the target backend is unreachable (connection refused / timeout), the router returns 503 with a structured error
- **AC-9:** `routes.yaml` missing at startup raises a clear error and prevents the server from starting
- **AC-10:** `routes.yaml` referencing an undefined backend name raises a validation error at startup
- **AC-11:** `X-Request-ID` is propagated from the router to the upstream backend on every forwarded request
- **AC-12:** `HeadwaterClient(host_alias="stillwater")` resolves to Botvinnik:8080

---

## 5. Error Handling / Failure Modes

| Failure | Behavior |
|---|---|
| `routes.yaml` not found at startup | Raise `FileNotFoundError` with path; server does not start |
| `routes.yaml` references unknown backend | Raise `RoutingConfigError` at startup with the offending key |
| Service not in `routes` | Return `RoutingError` (HTTP 400) — bad request, not server error |
| Backend unreachable (connection refused) | Return HTTP 503 with `HeadwaterServerError(error_type="backend_unavailable")` |
| Backend timeout | Return HTTP 503 with `HeadwaterServerError(error_type="backend_timeout")` |
| Backend returns 4xx | Propagate status code and body verbatim — do not wrap |
| Backend returns 5xx | Propagate status code and body verbatim — do not wrap |
| `routes.yaml` is malformed YAML | Raise `yaml.YAMLError` at startup; server does not start |

The router never silently swallows errors. All failures are logged at ERROR level with request ID.

---

## 6. Code Example

This shows the style conventions to follow — specifically how `resolve_backend` and the proxy route interact:

```python
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str) -> Response:
    service = path.split("/")[0]  # e.g. "conduit" from "conduit/generate"

    body = await request.body()
    model: str | None = None
    if body:
        try:
            model = orjson.loads(body).get("model")
        except Exception:
            pass

    backend_url = resolve_backend(service, model, config)
    target = f"{backend_url}/{path}"

    async with httpx.AsyncClient() as client:
        upstream = await client.request(
            method=request.method,
            url=target,
            headers={**request.headers, "X-Request-ID": request.state.request_id},
            content=body,
            timeout=300.0,
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=dict(upstream.headers),
    )
```

---

## 7. Domain Language

These are the exact nouns the implementation is allowed to use. Do not invent synonyms.

| Term | Definition |
|---|---|
| **Router** | The HeadwaterRouter instance running on Caruana:8081 |
| **Backend** | A named upstream server (deepwater, bywater, backwater, stillwater) |
| **Service** | A logical capability group: `conduit`, `embeddings`, `reranker`, `siphon`, `curator`, `ambient_inference` |
| **Route** | A mapping from service name to backend name in routes.yaml |
| **Heavy model** | A model whose name appears in `heavy_models` in routes.yaml |
| **Light model** | Any model not in `heavy_models` — treated as light by default |
| **RouterConfig** | The in-memory representation of routes.yaml, loaded at startup |
| **Deepwater** | AlphaBlue's inference server (172.16.0.2:8080) — previously called "headwater" |
| **Stillwater** | Botvinnik's inference server (172.16.0.3:8080) — ambient inference |
| **RoutingError** | A structured error returned when a service cannot be resolved to a backend |

---

## 8. Invalid State Transitions

These state mutations must raise errors — not silently degrade:

- `RouterConfig` modified after startup → must not be possible; `RouterConfig` is frozen (`frozen=True`)
- Router starts with `routes.yaml` absent → must raise, not fall back to defaults
- Router starts with a route pointing to a backend name not in `backends` → must raise at config load time, not at request time
- `resolve_backend` called with a service not in `config.routes` → must raise `RoutingError`, not return a default backend silently
- `HeadwaterTransport` instantiated with an unrecognized `host_alias` → must raise `ValueError` (already enforced; add `"deepwater"` and `"stillwater"` to the match)

---

## 9. Dependent Changes (Other Repositories)

These changes are required before or alongside router deployment:

| Repo | Change |
|---|---|
| `dbclients-project` | Add `deepwater_server`, `stillwater_server` to `NetworkContext`; update `headwater_server` to resolve to Caruana:8081 |
| `conduit-project` | Add `heavy: bool` to `ModelSpec`; update Perplexity research prompts; add `export_heavy_models.py`; update Ollama model list to per-server scheme |
| `headwater-client` | Add `"deepwater"` and `"stillwater"` to `host_alias` Literal; add `case` branches in `_get_url()` |

The `dbclients` change and router deployment must be rolled out together. Do not deploy either independently.
