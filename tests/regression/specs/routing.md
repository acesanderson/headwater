# Routing Spec — Headwater Regression Tests

Router-specific tests covering backend selection, the catch-all proxy, error handling, and middleware behavior.

---

### Catch-all proxy — correct backend selection (light model)
- **Description**: Requests to service endpoints (conduit, embeddings, reranker, curator, siphon) with a non-heavy model are routed to the default backend for that service per routes.yaml.
- **Hosts to test**: headwater (router only)
- **Key inputs**:
  - Any valid conduit generate request with `model: "gpt-oss:latest"` (assumes gpt-oss:latest is not in `heavy_models`)
- **Expected response**:
  - 200 (proxied response from subserver)
  - Router logs should show `proxy_request` and `proxy_response` with `upstream_status: 200`
- **Edge cases**: none for happy path
- **Already covered**: no

---

### Catch-all proxy — heavy model routing (conduit)
- **Description**: Conduit requests with a model in `heavy_models` list are routed to the `heavy_inference` backend, not the default conduit backend.
- **Hosts to test**: headwater (router only)
- **Key inputs**:
  - Conduit generate request with a model name that appears in routes.yaml `heavy_models` list
- **Expected response**:
  - 200 if heavy backend is up; proxy transparently forwards to heavy_inference backend
  - Router logs `route: "heavy_inference"`
- **Edge cases**:
  - Heavy backend down → 503 with `error_type: "backend_unavailable"`
- **Already covered**: no

---

### Catch-all proxy — reranker routing
- **Description**: Reranker requests are routed based on model weight: heavy models → `reranker_heavy` backend; all others → `reranker_light` backend.
- **Hosts to test**: headwater (router only)
- **Key inputs**:
  - Reranker request with default model (light path)
  - Reranker request with a model in `heavy_models` (heavy path)
- **Expected response**:
  - 200 (proxied response)
  - Router logs show `route: "reranker_light"` or `route: "reranker_heavy"` accordingly
- **Edge cases**: none beyond basic routing correctness
- **Already covered**: no

---

### Catch-all proxy — unknown service returns 400
- **Description**: Requests to an unknown service prefix (not in routes.yaml `routes` dict) return 400 with `error_type: "routing_error"`.
- **Hosts to test**: headwater (router only)
- **Key inputs**:
  - POST to `/{unknown_service}/anything` where `unknown_service` is not in routes.yaml
  - Example: `POST /nonexistent/endpoint`
- **Expected response**:
  - 400
  - Body: `HeadwaterServerError` with `error_type: "routing_error"`
  - `message` should mention unknown service name
- **Edge cases**: none
- **Already covered**: no

---

### Catch-all proxy — backend unreachable returns 503
- **Description**: If the resolved backend is reachable at the network level but returns `ConnectError`, the router returns 503 with `error_type: "backend_unavailable"`.
- **Hosts to test**: headwater (router only)
- **Key inputs**: requires temporarily broken or fake backend URL — may need routes.yaml manipulation or testing with a known-down backend
- **Expected response**:
  - 503
  - Body: `HeadwaterServerError` with `error_type: "backend_unavailable"`
  - `context.backend` should contain the backend URL
- **Edge cases**: this is difficult to trigger in live regression; document as known behavior
- **Already covered**: no

---

### Catch-all proxy — backend timeout returns 503
- **Description**: If the upstream request exceeds 300s, router returns 503 with `error_type: "backend_timeout"`.
- **Hosts to test**: headwater (router only)
- **Key inputs**: not easily triggered in live regression
- **Expected response**:
  - 503
  - Body: `HeadwaterServerError` with `error_type: "backend_timeout"`
- **Edge cases**: document as known behavior; test via mocked backend if needed
- **Already covered**: no

---

### Correlation middleware — X-Request-ID header
- **Description**: Every response from the router includes an `X-Request-ID` header. If the client sends a valid UUIDv4 in `X-Request-ID`, it is echoed back unchanged. Otherwise a new UUIDv4 is generated.
- **Hosts to test**: headwater (router only); subservers also implement this middleware
- **Key inputs**:
  - Request with no `X-Request-ID` header
  - Request with a valid UUIDv4 `X-Request-ID` header
  - Request with an invalid/non-UUID string in `X-Request-ID`
- **Expected response**:
  - Response always has `X-Request-ID` header
  - If client sent a valid UUIDv4: response echoes the same value
  - If client sent nothing or invalid value: response contains a new UUIDv4
- **Edge cases**: non-UUID string (e.g. `"abc"`) → router assigns new UUID, ignores client value
- **Already covered**: no

---

### GET /routes/ — router config contents
- **Description**: Router-only endpoint returns the parsed routes.yaml config with `backends`, `routes`, `heavy_models`, `config_path`.
- **Hosts to test**: headwater (router only)
- **Key inputs**: none
- **Expected response**:
  - 200
  - Dict with keys: `backends` (dict[str,str]), `routes` (dict[str,str]), `heavy_models` (list[str]), `config_path` (str)
  - All route values in `routes` must reference keys in `backends`
  - `backends` must be non-empty
- **Edge cases**: none — read-only config snapshot
- **Already covered**: no

---

### Router /ping, /status, /logs/last — router-native endpoints
- **Description**: These endpoints are handled natively by the router, not proxied to a backend.
- **Hosts to test**: headwater (router only)
- **Key inputs**: standard infra inputs (see infra.md)
- **Expected response**: same as infra.md specs
- **Edge cases**: confirm that `/ping` on the router never hits the catch-all proxy (it is registered before `/{path:path}`)
- **Already covered**: no (see infra.md for full specs)

---

### GET /metrics — router-native, registered before catch-all
- **Description**: `/metrics` on the router is injected before the catch-all route to avoid being swallowed. Must return Prometheus metrics, not be proxied.
- **Hosts to test**: headwater (router only)
- **Key inputs**: none
- **Expected response**:
  - 200
  - Content-Type: `text/plain; version=0.0.4`
  - Must contain `headwater_backend_up` metric
- **Edge cases**: if registration order is wrong, request would be proxied and return wrong content
- **Already covered**: no
