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
- Request body is read fully into memory for model name extraction — no streaming, no chunked handling
- `httpx.AsyncClient` is created per-request — no shared connection pool, no connection reuse configuration
- Backend base URLs are forwarded verbatim — the router does not rewrite the `Host` header

### Non-Goals
- Load balancing across multiple instances of the same backend
- Authentication or rate limiting
- Health checking or backend discovery
- Streaming / SSE forwarding
- Dynamic config reload without restart
- Routing by anything other than service type and model `heavy` flag
- Alias-based routing (e.g. "sporadic", "interactive") — deferred, no timeline
- VRAM offload detection — tracked separately in `docs/backlog.md`
- Request body size limiting — no max body size enforced; out of scope
- Header sanitization beyond hop-by-hop removal (see Section 3)
- Query parameter inspection or modification — query strings are forwarded verbatim

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

All three top-level keys (`backends`, `routes`, `heavy_models`) are required. A missing key is a `RoutingConfigError` at startup. All values in `routes` must reference a key present in `backends`.

### URL path to service mapping

The service name is derived from the first segment of the request path:

| Incoming path prefix | Resolved service |
|---|---|
| `/conduit/...` | `conduit` (or `heavy_inference` if model is heavy) |
| `/embeddings/...` | `embeddings` |
| `/reranker/...` | `reranker_light` or `reranker_heavy` depending on model |
| `/siphon/...` | `siphon` |
| `/curator/...` | `curator` |
| `/ambient_inference/...` | `ambient_inference` |

The full path is forwarded verbatim to the backend. A `POST /conduit/generate` to the router becomes `POST /conduit/generate` to the resolved backend — no path rewriting.

Query strings are forwarded verbatim.

### RouterConfig

Loaded once at startup from `~/.config/headwater/routes.yaml`. Immutable after load.

```python
@dataclass(frozen=True)
class RouterConfig:
    backends: dict[str, str]   # backend name -> base_url (validated as URLs at load time)
    routes: dict[str, str]     # service name -> backend name
    heavy_models: list[str]    # model names that trigger heavy_inference routing
```

Validation at load time:
- All three keys present in YAML
- Every value in `routes` exists as a key in `backends`
- Every value in `backends` is a valid HTTP URL (scheme + host)

### Route resolution

```python
def resolve_backend(service: str, model: str | None, config: RouterConfig) -> str:
    """
    Returns a backend base_url for the given service and model.
    Raises RoutingError(HTTP 400) if service is not in config.routes.
    Never returns None. Never falls back silently.
    """
```

Resolution logic (evaluated in order):
1. If `service == "conduit"` and `model in config.heavy_models` → use `config.routes["heavy_inference"]`
2. If `service == "reranker"` and `model in config.heavy_models` → use `config.routes["reranker_heavy"]`
3. If `service == "reranker"` and `model not in config.heavy_models` (or model is None) → use `config.routes["reranker_light"]`
4. Otherwise → `config.routes[service]`; raise `RoutingError` if not present

Unknown models (not in `heavy_models`) are treated as light — route to the default backend for that service.

### Header forwarding

The router forwards all incoming request headers to the backend with two exceptions:
- Hop-by-hop headers are stripped: `Connection`, `Transfer-Encoding`, `TE`, `Trailer`, `Upgrade`, `Keep-Alive`, `Proxy-Authorization`, `Proxy-Authenticate`
- `X-Request-ID` is set to the router's own correlation ID (generated or passed through from the client), overwriting any existing value

Response headers from the backend are forwarded verbatim to the client, with hop-by-hop headers stripped.

### Proxy timeout

Fixed at 300 seconds. Not configurable via `routes.yaml`. This is not a connection timeout — it is the total request timeout.

### HeadwaterRouter class

New class in `headwater-server/src/headwater_server/server/`, alongside `HeadwaterServer`:

```python
class HeadwaterRouter:
    def __init__(self, name: str = "Headwater Router"): ...
    def _load_config(self) -> RouterConfig: ...   # reads routes.yaml, raises on missing/invalid file
    def _register_routes(self): ...               # catch-all proxy route + /ping
    def _register_middleware(self): ...           # reuses existing correlation middleware
    def _register_error_handlers(self): ...       # reuses existing error handlers
```

Two registered routes:
1. `GET /ping` → returns `{"message": "pong"}` (health check, does not proxy)
2. `@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])` → proxy

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

`HeadwaterTransport._get_url()` adds a `case "deepwater"` and `case "stillwater"` branch. The `"headwater"` case resolves to `ctx.headwater_server` as before — only the underlying IP:port changes in `dbclients`.

---

## 4. Acceptance Criteria

- **AC-1:** `HeadwaterClient()` (no args) constructs a transport whose `base_url` equals `http://172.16.0.4:8081`
- **AC-2:** `HeadwaterClient(host_alias="deepwater")` constructs a transport whose `base_url` equals `http://172.16.0.2:8080`
- **AC-3:** `resolve_backend("conduit", "llama3.2:3b", config)` returns the Bywater base URL when `"llama3.2:3b"` is not in `heavy_models` — verified by asserting the return value, not by making a network call
- **AC-4:** `resolve_backend("conduit", "qwq:latest", config)` returns the Deepwater base URL when `"qwq:latest"` is in `heavy_models`
- **AC-5:** `resolve_backend("reranker", "qwq:latest", config)` returns the Bywater base URL; `resolve_backend("reranker", "some-light-model", config)` returns the Backwater base URL
- **AC-6:** `resolve_backend("unknown_service", None, config)` raises `RoutingError`; the HTTP response has status 400 and a `HeadwaterServerError` body with `error_type="routing_error"`
- **AC-7:** When the backend returns HTTP 422, the router response has status 422 and the body is byte-for-byte identical to the backend response body; response hop-by-hop headers are stripped
- **AC-8:** When the backend is unreachable (mock httpx to raise `httpx.ConnectError`), the router returns HTTP 503 with `HeadwaterServerError(error_type="backend_unavailable")` containing the backend name and URL
- **AC-9:** Starting the router with `routes.yaml` absent raises `FileNotFoundError` before the server begins accepting connections; the error message includes the expected file path
- **AC-10:** Starting the router with `routes.yaml` containing a route that references an undefined backend raises `RoutingConfigError` before the server begins accepting connections; the error message includes the offending key
- **AC-11:** Every proxied request includes an `X-Request-ID` header on the upstream call equal to `request.state.request_id`
- **AC-12:** `HeadwaterClient(host_alias="stillwater")` constructs a transport whose `base_url` equals `http://172.16.0.3:8080`
- **AC-13:** `GET /ping` on the router returns HTTP 200 `{"message": "pong"}` without proxying to any backend

---

## 5. Error Handling / Failure Modes

| Failure | Behavior |
|---|---|
| `routes.yaml` not found at startup | Raise `FileNotFoundError` with full path; server does not start |
| `routes.yaml` missing required top-level key | Raise `RoutingConfigError` at startup naming the missing key |
| `routes.yaml` route references undefined backend | Raise `RoutingConfigError` at startup with the offending route key and backend name |
| `routes.yaml` backend value is not a valid HTTP URL | Raise `RoutingConfigError` at startup with the offending backend name |
| `routes.yaml` is malformed YAML | Raise `yaml.YAMLError` at startup; server does not start |
| Service not in `routes` | Return HTTP 400 `HeadwaterServerError(error_type="routing_error")` with service name |
| Backend unreachable (connection refused) | Return HTTP 503 `HeadwaterServerError(error_type="backend_unavailable")` with backend name + URL |
| Backend timeout (>300s) | Return HTTP 503 `HeadwaterServerError(error_type="backend_timeout")` with backend name + URL |
| Backend returns 4xx | Propagate status code and body verbatim; strip hop-by-hop headers |
| Backend returns 5xx | Propagate status code and body verbatim; strip hop-by-hop headers |

The router never silently swallows errors. All 5xx and proxy failures are logged at ERROR level with `request_id`, `backend`, `path`, and `status_code`.

---

## 6. Code Example

This shows the style conventions to follow — specifically how `resolve_backend` and the proxy route interact, and how hop-by-hop headers are stripped:

```python
HOP_BY_HOP = frozenset({
    "connection", "transfer-encoding", "te", "trailer",
    "upgrade", "keep-alive", "proxy-authorization", "proxy-authenticate",
})

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(request: Request, path: str) -> Response:
    service = path.split("/")[0]

    body = await request.body()
    model: str | None = None
    if body:
        try:
            model = orjson.loads(body).get("model")
        except Exception:
            pass

    backend_url = resolve_backend(service, model, config)  # raises RoutingError if unknown
    target = f"{backend_url}/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in HOP_BY_HOP
    }
    forward_headers["x-request-id"] = request.state.request_id

    async with httpx.AsyncClient() as client:
        upstream = await client.request(
            method=request.method,
            url=target,
            headers=forward_headers,
            content=body,
            timeout=300.0,
        )

    response_headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in HOP_BY_HOP
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )
```

---

## 7. Observability

### Startup log

On successful startup, the router logs the loaded route table at INFO level:

```
router_started: backends=[deepwater, bywater, backwater, stillwater] routes={conduit: bywater, ...} heavy_models=[qwq:latest, ...]
```

On startup failure (missing file, config error), the error is logged at CRITICAL before the process exits.

### Per-request structured log fields

Every proxied request emits two log entries using the existing `request_started` / `request_finished` pattern from `HeadwaterServer`, plus one additional router-specific field on `request_finished`:

| Field | Description |
|---|---|
| `path` | Incoming request path |
| `method` | HTTP method |
| `service` | Resolved service name (e.g. `conduit`, `reranker_light`) |
| `backend` | Backend name selected (e.g. `bywater`) |
| `backend_url` | Full upstream URL targeted |
| `model` | Model name extracted from body, or `null` |
| `status_code` | Final HTTP status code returned to client |
| `duration_ms` | Total round-trip time including upstream |

### Error log fields

On backend unreachable or timeout, log at ERROR with: `request_id`, `backend`, `backend_url`, `error_type`, `path`.

### Health check

`GET /ping` returns `{"message": "pong"}` — sufficient for a basic uptime check. No backend health is checked at ping time.

---

## 8. Domain Language

These are the exact nouns the implementation is allowed to use. Do not invent synonyms.

| Term | Definition |
|---|---|
| **Router** | The HeadwaterRouter instance running on Caruana:8081 |
| **Backend** | A named upstream server (deepwater, bywater, backwater, stillwater) |
| **Service** | A logical capability group derived from the URL path prefix: `conduit`, `embeddings`, `reranker`, `siphon`, `curator`, `ambient_inference` |
| **Route** | A mapping from service name to backend name in routes.yaml |
| **Heavy model** | A model whose name appears in `heavy_models` in routes.yaml |
| **Light model** | Any model not in `heavy_models` — treated as light by default |
| **RouterConfig** | The in-memory representation of routes.yaml, loaded at startup |
| **Deepwater** | AlphaBlue's inference server (172.16.0.2:8080) — previously called "headwater" |
| **Stillwater** | Botvinnik's inference server (172.16.0.3:8080) — ambient inference |
| **RoutingError** | A `HeadwaterServerError` returned when a service cannot be resolved to a backend (HTTP 400) |
| **RoutingConfigError** | A startup exception raised when `routes.yaml` fails validation |

---

## 9. Invalid State Transitions

These state mutations must raise errors — not silently degrade:

- `RouterConfig` modified after startup → must not be possible; `RouterConfig` is `frozen=True`
- Router starts with `routes.yaml` absent → must raise `FileNotFoundError`, not fall back to defaults
- Router starts with a route pointing to a backend name not in `backends` → must raise `RoutingConfigError` at config load time, not at request time
- `resolve_backend` called with a service not in `config.routes` → must raise `RoutingError`, not return a default backend silently
- `HeadwaterTransport` instantiated with an unrecognized `host_alias` → must raise `ValueError` (already enforced; extend the match to include `"deepwater"` and `"stillwater"`)

---

## 10. Dependent Changes (Other Repositories)

These changes are required before or alongside router deployment:

| Repo | Change |
|---|---|
| `dbclients-project` | Add `deepwater_server`, `stillwater_server` to `NetworkContext`; update `headwater_server` to resolve to `172.16.0.4:8081` |
| `conduit-project` | Add `heavy: bool` to `ModelSpec`; update Perplexity research prompts; add `export_heavy_models.py`; update Ollama model list to per-server scheme |
| `headwater-client` | Add `"deepwater"` and `"stillwater"` to `host_alias` Literal; add `case` branches in `_get_url()` |

The `dbclients` change and router deployment must be rolled out together. Do not deploy either independently.
