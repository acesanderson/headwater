# HeadwaterRouter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build HeadwaterRouter, a thin FastAPI gateway on Caruana:8081 that routes `HeadwaterClient` requests to the correct backend (Deepwater/Bywater/Backwater/Stillwater) based on service type and model weight defined in `~/.config/headwater/routes.yaml`.

**Architecture:** `HeadwaterRouter` is a new FastAPI app in `headwater-server` that catches all requests via a single catch-all route, extracts the service name from the URL path prefix, optionally reads the model name from the JSON body, and proxies the full request to the resolved backend using `httpx.AsyncClient`. Config is loaded from `routes.yaml` at startup into a frozen `RouterConfig` dataclass. `dbclients` and `HeadwaterTransport` are updated so `host_alias="headwater"` now resolves to the router (Caruana:8081) rather than AlphaBlue directly; AlphaBlue is accessed via the new `host_alias="deepwater"`.

**Tech Stack:** FastAPI, httpx (async HTTP client), PyYAML, pytest, unittest.mock

---

## File Map

**New files:**
- `headwater-server/src/headwater_server/server/routing_config.py` — `RouterConfig`, `RoutingConfigError`, `RoutingError`, `load_router_config()`, `resolve_backend()`
- `headwater-server/src/headwater_server/server/router.py` — `HeadwaterRouter` class; exports module-level `app`
- `headwater-server/tests/server/test_routing_config.py` — unit tests for config loading and route resolution
- `headwater-server/tests/server/test_router.py` — integration tests for the FastAPI router app

**Modified files:**
- `headwater-api/src/headwater_api/classes/server_classes/exceptions.py` — add `ROUTING_ERROR`, `BACKEND_UNAVAILABLE`, `BACKEND_TIMEOUT` to `ErrorType`
- `headwater-server/pyproject.toml` — add `httpx>=0.27`, `pyyaml>=6.0` to dependencies; add `headwater-router` entry point
- `headwater-server/src/headwater_server/server/main.py` — add `run_router()` and `router_main()`
- `dbclients-project/src/dbclients/discovery/host.py` — add `deepwater_server`, `stillwater_server` to `NetworkContext`; update `headwater_server` to Caruana IP
- `headwater-client/src/headwater_client/transport/headwater_transport.py` — add `HEADWATER_ROUTER_PORT`, add `"deepwater"` and `"stillwater"` cases, update `"headwater"` to use router port
- `headwater-client/src/headwater_client/client/headwater_client.py` — add `"deepwater"` and `"stillwater"` to `host_alias` Literal
- `headwater-client/tests/transport/test_transport.py` — update stale `_fake_ctx` helper; add tests for new aliases

---

## Task 1: Add new ErrorType variants to headwater-api

**Files:**
- Modify: `headwater-api/src/headwater_api/classes/server_classes/exceptions.py`

> Background: `ErrorType` is a `str, Enum`. The router needs three new values: `ROUTING_ERROR` (unknown service, HTTP 400), `BACKEND_UNAVAILABLE` (connection refused, HTTP 503), `BACKEND_TIMEOUT` (>300s, HTTP 503). These are used in Tasks 8, 11, 12.

- [ ] **Step 1: Write the failing test**

Create `headwater-api/tests/test_error_type_variants.py`:

```python
from __future__ import annotations

from headwater_api.classes.server_classes.exceptions import ErrorType


def test_routing_error_variant_exists():
    assert ErrorType.ROUTING_ERROR == "routing_error"


def test_backend_unavailable_variant_exists():
    assert ErrorType.BACKEND_UNAVAILABLE == "backend_unavailable"


def test_backend_timeout_variant_exists():
    assert ErrorType.BACKEND_TIMEOUT == "backend_timeout"
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd headwater-api && uv run pytest tests/test_error_type_variants.py -v
```

Expected: `AttributeError: ROUTING_ERROR` (or similar) — all three tests fail.

- [ ] **Step 3: Add the three new ErrorType variants**

In `headwater-api/src/headwater_api/classes/server_classes/exceptions.py`, add three lines to `ErrorType` after the existing `NETWORK_ERROR` line:

```python
class ErrorType(str, Enum):
    VALIDATION_ERROR = "validation_error"
    PYDANTIC_VALIDATION = "pydantic_validation"
    DATA_VALIDATION = "data_validation"
    MODEL_NOT_FOUND = "model_not_found"
    BATCH_SIZE_EXCEEDED = "batch_size_exceeded"
    INVALID_REQUEST = "invalid_request"
    INTERNAL_ERROR = "internal_error"
    TIMEOUT_ERROR = "timeout_error"
    DEPENDENCY_ERROR = "dependency_error"
    NETWORK_ERROR = "network_error"
    ROUTING_ERROR = "routing_error"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    BACKEND_TIMEOUT = "backend_timeout"
```

- [ ] **Step 4: Run to verify it passes**

```bash
cd headwater-api && uv run pytest tests/test_error_type_variants.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd headwater-api
git add src/headwater_api/classes/server_classes/exceptions.py tests/test_error_type_variants.py
git commit -m "feat(headwater-api): add ROUTING_ERROR, BACKEND_UNAVAILABLE, BACKEND_TIMEOUT to ErrorType"
```

---

## Task 2: Add httpx and pyyaml to headwater-server dependencies

**Files:**
- Modify: `headwater-server/pyproject.toml`

> No TDD cycle needed — this is a dependency declaration. Required before Tasks 9–12 can import `httpx` or `yaml`.

- [ ] **Step 1: Add dependencies**

In `headwater-server/pyproject.toml`, add to the `dependencies` list:

```toml
dependencies = [
    "fastapi>=0.116.1",
    "httpx>=0.27",
    "pyyaml>=6.0",
    ...  # existing entries unchanged
]
```

- [ ] **Step 2: Sync the environment**

```bash
cd headwater-server && uv sync
```

Expected: `httpx` and `pyyaml` installed with no errors.

- [ ] **Step 3: Verify imports work**

```bash
cd headwater-server && uv run python -c "import httpx; import yaml; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
cd headwater-server
git add pyproject.toml uv.lock
git commit -m "chore(headwater-server): add httpx and pyyaml dependencies"
```

---

## Task 3: dbclients — add deepwater_server and stillwater_server to NetworkContext *(AC-1, AC-2, AC-12 prerequisite)*

**Files:**
- Modify: `dbclients-project/src/dbclients/discovery/host.py`

> `NetworkContext` currently has `headwater_server` pointing to AlphaBlue (172.16.0.2). After this task: `headwater_server` points to Caruana (172.16.0.4, the router). New fields `deepwater_server` (AlphaBlue, 172.16.0.2) and `stillwater_server` (Botvinnik, 172.16.0.3) are added. All three are required dataclass fields (no defaults). Existing test `test_transport.py` uses a stale `_fake_ctx` helper — that will be fixed in Task 4.

- [ ] **Step 1: Write the failing tests** *(prerequisite for AC-1, AC-2, AC-12)*

Create `dbclients-project/tests/test_network_context_fields.py`:

```python
from __future__ import annotations

from unittest.mock import patch
from dbclients.discovery.host import get_network_context


def _patched_ctx():
    """Call get_network_context() with all network I/O mocked out."""
    with patch("dbclients.discovery.host.is_on_vpn", return_value=False), \
         patch("dbclients.discovery.host.is_on_local_network", return_value=False), \
         patch("dbclients.discovery.host.get_hostname", return_value="testhost"), \
         patch("dbclients.discovery.host.get_vpn_ip", return_value=None), \
         patch("dbclients.discovery.host.get_public_ip", return_value=None), \
         patch("dbclients.discovery.host.get_private_ip", return_value=None):
        return get_network_context()


def test_headwater_server_points_to_caruana():
    """headwater_server must be Caruana's VPN IP (the router), not AlphaBlue."""
    ctx = _patched_ctx()
    assert ctx.headwater_server == "172.16.0.4"


def test_deepwater_server_points_to_alphablue():
    """deepwater_server must be AlphaBlue's VPN IP (direct inference)."""
    ctx = _patched_ctx()
    assert ctx.deepwater_server == "172.16.0.2"


def test_stillwater_server_points_to_botvinnik():
    """stillwater_server must be Botvinnik's VPN IP."""
    ctx = _patched_ctx()
    assert ctx.stillwater_server == "172.16.0.3"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd dbclients-project && uv run pytest tests/test_network_context_fields.py -v
```

Expected: `AttributeError: 'NetworkContext' object has no attribute 'deepwater_server'` (and `stillwater_server`); the `headwater_server` test may pass or fail depending on current value.

- [ ] **Step 3: Update NetworkContext and get_network_context()**

In `dbclients-project/src/dbclients/discovery/host.py`, update the `NetworkContext` dataclass (add two required fields) and update `get_network_context()` to set them:

```python
@dataclass(frozen=True)
class NetworkContext:
    local_hostname: str
    is_on_vpn: bool
    is_local: bool
    is_database_server: bool
    is_siphon_server: bool
    preferred_host: str
    headwater_server: str   # Caruana:router — clients default here
    deepwater_server: str   # AlphaBlue — direct inference
    bywater_server: str     # Caruana — direct inference
    backwater_server: str   # Cheet — embeddings/light
    stillwater_server: str  # Botvinnik — ambient inference
    vpn_ip: str | None = None
    public_ip: str | None = None
    local_ip: str | None = None
```

In `get_network_context()`, update the IP constants block:

```python
    preferred_host = "172.16.0.4"    # Caruana VPN IP
    headwater_server = "172.16.0.4"  # Caruana — the router (was AlphaBlue)
    deepwater_server = "172.16.0.2"  # AlphaBlue VPN IP — direct inference
    bywater_server = "172.16.0.4"    # Caruana VPN IP — unchanged
    backwater_server = "172.16.0.9"  # Cheet VPN IP — unchanged
    stillwater_server = "172.16.0.3" # Botvinnik VPN IP

    return NetworkContext(
        local_hostname=hostname,
        is_on_vpn=vpn_connected,
        is_local=local_network,
        is_database_server=is_database_server,
        is_siphon_server=is_siphon_server,
        preferred_host=preferred_host,
        headwater_server=headwater_server,
        deepwater_server=deepwater_server,
        bywater_server=bywater_server,
        backwater_server=backwater_server,
        stillwater_server=stillwater_server,
        public_ip=public_ip,
        local_ip=private_ip,
        vpn_ip=vpn_ip,
    )
```

- [ ] **Step 4: Run to verify they pass**

```bash
cd dbclients-project && uv run pytest tests/test_network_context_fields.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd dbclients-project
git add src/dbclients/discovery/host.py tests/test_network_context_fields.py
git commit -m "feat(dbclients): add deepwater_server/stillwater_server to NetworkContext; headwater_server now points to router on Caruana"
```

---

## Task 4: HeadwaterTransport — add deepwater and stillwater aliases *(AC-1, AC-2, AC-12)*

**Files:**
- Modify: `headwater-client/src/headwater_client/transport/headwater_transport.py`
- Modify: `headwater-client/src/headwater_client/client/headwater_client.py`
- Modify: `headwater-client/tests/transport/test_transport.py`

> The existing `test_transport.py` has a broken `_fake_ctx` helper that passes `siphon_server=` — a field that doesn't exist on `NetworkContext` (which uses `headwater_server`). Fix this stale helper first, then add new alias tests. The `"headwater"` alias must now use port 8081 (router port) instead of 8080.

- [ ] **Step 1: Fix the stale _fake_ctx helper**

Replace the entire `_fake_ctx` function in `headwater-client/tests/transport/test_transport.py`:

```python
from __future__ import annotations

from headwater_client.transport.headwater_transport import HeadwaterTransport
from dbclients.discovery.host import NetworkContext


def _fake_ctx(
    headwater="1.1.1.1",
    deepwater="9.9.9.9",
    bywater="2.2.2.2",
    backwater="3.3.3.3",
    stillwater="4.4.4.4",
) -> NetworkContext:
    return NetworkContext(
        local_hostname="test",
        is_on_vpn=False,
        is_local=False,
        is_database_server=False,
        is_siphon_server=False,
        preferred_host="",
        headwater_server=headwater,
        deepwater_server=deepwater,
        bywater_server=bywater,
        backwater_server=backwater,
        stillwater_server=stillwater,
    )
```

Update existing tests that referenced `siphon` parameter to use `headwater`:

```python
def test_sync_transport_headwater_alias_uses_headwater_server(monkeypatch):
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(headwater="1.1.1.1", bywater="2.2.2.2"),
    )
    t = HeadwaterTransport(host_alias="headwater")
    assert "1.1.1.1" in t.base_url
    assert "2.2.2.2" not in t.base_url


def test_sync_transport_default_alias_is_headwater(monkeypatch):
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(headwater="1.1.1.1"),
    )
    t = HeadwaterTransport()
    assert "1.1.1.1" in t.base_url


def test_sync_transport_defers_resolution(monkeypatch):
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(headwater="9.8.7.6"),
    )
    t = HeadwaterTransport()
    assert "9.8.7.6" in t.base_url, (
        "base_url did not use the patched context — "
        "get_network_context() is likely still evaluated at module import"
    )
```

- [ ] **Step 2: Run existing transport tests to verify they still pass**

```bash
cd headwater-client && uv run pytest tests/transport/test_transport.py -v
```

Expected: all existing tests PASS (helper is now consistent with the real NetworkContext).

- [ ] **Step 3: Write failing test for AC-1 (headwater alias uses router port 8081)**

Append to `headwater-client/tests/transport/test_transport.py`:

```python
def test_headwater_alias_resolves_to_router_port_8081(monkeypatch):
    """AC-1: host_alias='headwater' resolves to base_url with port 8081."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(headwater="172.16.0.4"),
    )
    t = HeadwaterTransport(host_alias="headwater")
    assert t.base_url == "http://172.16.0.4:8081"
```

- [ ] **Step 4: Run to verify AC-1 test fails**

```bash
cd headwater-client && uv run pytest tests/transport/test_transport.py::test_headwater_alias_resolves_to_router_port_8081 -v
```

Expected: FAIL — currently the headwater alias uses port 8080.

- [ ] **Step 5: Write failing test for AC-2 (deepwater alias)**

Append to `headwater-client/tests/transport/test_transport.py`:

```python
def test_deepwater_alias_resolves_to_alphablue(monkeypatch):
    """AC-2: host_alias='deepwater' resolves to AlphaBlue IP on port 8080."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(deepwater="172.16.0.2"),
    )
    t = HeadwaterTransport(host_alias="deepwater")
    assert t.base_url == "http://172.16.0.2:8080"
```

- [ ] **Step 6: Run to verify AC-2 test fails**

```bash
cd headwater-client && uv run pytest tests/transport/test_transport.py::test_deepwater_alias_resolves_to_alphablue -v
```

Expected: FAIL — `"deepwater"` is not a recognized alias yet.

- [ ] **Step 7: Write failing test for AC-12 (stillwater alias)**

Append to `headwater-client/tests/transport/test_transport.py`:

```python
def test_stillwater_alias_resolves_to_botvinnik(monkeypatch):
    """AC-12: host_alias='stillwater' resolves to Botvinnik IP on port 8080."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(stillwater="172.16.0.3"),
    )
    t = HeadwaterTransport(host_alias="stillwater")
    assert t.base_url == "http://172.16.0.3:8080"
```

- [ ] **Step 8: Run to verify AC-12 test fails**

```bash
cd headwater-client && uv run pytest tests/transport/test_transport.py::test_stillwater_alias_resolves_to_botvinnik -v
```

Expected: FAIL — `"stillwater"` is not a recognized alias yet.

- [ ] **Step 9: Implement — update HeadwaterTransport**

In `headwater-client/src/headwater_client/transport/headwater_transport.py`, add a new constant and update `_get_url()`:

```python
# Constants
HEADWATER_SERVER_DEFAULT_PORT = 8080
HEADWATER_ROUTER_PORT = 8081


class HeadwaterTransport:
    def __init__(
        self,
        base_url: str = "",
        host_alias: Literal["headwater", "bywater", "backwater", "deepwater", "stillwater"] = "headwater",
    ):
        self._host_alias = host_alias
        if base_url == "":
            self.base_url: str = self._get_url()
        else:
            self.base_url = base_url.rstrip("/")
        self._session = requests.Session()

    def _get_url(self) -> str:
        ctx = get_network_context()
        match self._host_alias:
            case "headwater":
                ip = ctx.headwater_server
                port = HEADWATER_ROUTER_PORT
            case "bywater":
                ip = ctx.bywater_server
                port = HEADWATER_SERVER_DEFAULT_PORT
            case "backwater":
                ip = ctx.backwater_server
                port = HEADWATER_SERVER_DEFAULT_PORT
            case "deepwater":
                ip = ctx.deepwater_server
                port = HEADWATER_SERVER_DEFAULT_PORT
            case "stillwater":
                ip = ctx.stillwater_server
                port = HEADWATER_SERVER_DEFAULT_PORT
            case _:
                raise ValueError(
                    f"Invalid host_alias '{self._host_alias}'. Must be one of: "
                    "'headwater', 'bywater', 'backwater', 'deepwater', 'stillwater'."
                )
        url = f"http://{ip}:{port}"
        logger.debug(
            f"[{self._host_alias}] resolved to {ip}:{port}"
        )
        return url
```

- [ ] **Step 10: Update HeadwaterClient Literal**

In `headwater-client/src/headwater_client/client/headwater_client.py`, update the `host_alias` type:

```python
class HeadwaterClient:
    def __init__(
        self,
        host_alias: Literal["headwater", "bywater", "backwater", "deepwater", "stillwater"] = "headwater"
    ):
        self._transport = HeadwaterTransport(host_alias=host_alias)
        ...
```

- [ ] **Step 11: Run all three new tests to verify they pass (AC-1, AC-2, AC-12)**

```bash
cd headwater-client && uv run pytest tests/transport/test_transport.py -v
```

Expected: all tests PASS, including `test_headwater_alias_resolves_to_router_port_8081`, `test_deepwater_alias_resolves_to_alphablue`, `test_stillwater_alias_resolves_to_botvinnik`.

- [ ] **Step 12: Commit**

```bash
cd headwater-client
git add src/headwater_client/transport/headwater_transport.py \
        src/headwater_client/client/headwater_client.py \
        tests/transport/test_transport.py
git commit -m "feat(headwater-client): add deepwater/stillwater aliases; headwater alias now routes to router port 8081

AC-1: headwater resolves to http://172.16.0.4:8081
AC-2: deepwater resolves to http://172.16.0.2:8080
AC-12: stillwater resolves to http://172.16.0.3:8080"
```

---

## Task 5: RouterConfig dataclass and load_router_config *(AC-9, AC-10)*

**Files:**
- Create: `headwater-server/src/headwater_server/server/routing_config.py`
- Create: `headwater-server/tests/server/test_routing_config.py`

> This task builds the config loading layer only. `resolve_backend` is added in Tasks 6–9. `RoutingConfigError` is a startup exception (not HTTP). `RoutingError` is an HTTP 400 exception added in Task 9.

- [ ] **Step 1: Write failing test for AC-9 (missing routes.yaml)**

Create `headwater-server/tests/server/test_routing_config.py`:

```python
from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from headwater_server.server.routing_config import (
    RouterConfig,
    RoutingConfigError,
    load_router_config,
)

VALID_CONFIG = {
    "backends": {
        "deepwater": "http://172.16.0.2:8080",
        "bywater": "http://172.16.0.4:8080",
        "backwater": "http://172.16.0.9:8080",
        "stillwater": "http://172.16.0.3:8080",
    },
    "routes": {
        "conduit": "bywater",
        "heavy_inference": "deepwater",
        "siphon": "deepwater",
        "curator": "bywater",
        "embeddings": "backwater",
        "reranker_light": "backwater",
        "reranker_heavy": "bywater",
        "ambient_inference": "stillwater",
    },
    "heavy_models": ["qwq:latest", "deepseek-r1:70b"],
}


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "routes.yaml"
    path.write_text(yaml.dump(VALID_CONFIG))
    return path


@pytest.fixture
def config(config_path: Path) -> RouterConfig:
    return load_router_config(config_path)


def test_missing_routes_yaml_raises_file_not_found_error():
    """AC-9: routes.yaml absent at startup raises FileNotFoundError with the path."""
    missing = Path("/nonexistent/routes.yaml")
    with pytest.raises(FileNotFoundError) as exc_info:
        load_router_config(missing)
    assert "/nonexistent/routes.yaml" in str(exc_info.value)
```

- [ ] **Step 2: Run to verify AC-9 test fails**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py::test_missing_routes_yaml_raises_file_not_found_error -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `routing_config` doesn't exist yet.

- [ ] **Step 3: Write failing test for AC-10 (undefined backend in routes)**

Append to `headwater-server/tests/server/test_routing_config.py`:

```python
def test_route_referencing_undefined_backend_raises_routing_config_error(tmp_path: Path):
    """AC-10: routes.yaml with a route pointing to an undefined backend raises RoutingConfigError at load time."""
    bad_config = {
        **VALID_CONFIG,
        "routes": {**VALID_CONFIG["routes"], "conduit": "nonexistent_backend"},
    }
    path = tmp_path / "routes.yaml"
    path.write_text(yaml.dump(bad_config))
    with pytest.raises(RoutingConfigError) as exc_info:
        load_router_config(path)
    assert "conduit" in str(exc_info.value) or "nonexistent_backend" in str(exc_info.value)
```

- [ ] **Step 4: Run to verify AC-10 test fails**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py -v
```

Expected: both tests fail — module does not exist.

- [ ] **Step 5: Implement routing_config.py**

Create `headwater-server/src/headwater_server/server/routing_config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    pass

ROUTES_YAML_PATH = Path.home() / ".config" / "headwater" / "routes.yaml"

REQUIRED_TOP_LEVEL_KEYS = {"backends", "routes", "heavy_models"}


class RoutingConfigError(Exception):
    """Raised at startup when routes.yaml is present but structurally invalid."""


class RoutingError(ValueError):
    """Raised by resolve_backend when a service has no route entry."""


@dataclass(frozen=True)
class RouterConfig:
    backends: dict[str, str]   # backend name -> base_url
    routes: dict[str, str]     # service name -> backend name
    heavy_models: list[str]    # model names that trigger heavy routing


def load_router_config(path: Path = ROUTES_YAML_PATH) -> RouterConfig:
    """
    Load and validate routes.yaml into a RouterConfig.

    Raises:
        FileNotFoundError: if path does not exist (includes path in message).
        RoutingConfigError: if required keys are missing or a route references
                            an undefined backend.
    """
    if not path.exists():
        raise FileNotFoundError(f"routes.yaml not found at: {path}")

    with path.open() as f:
        raw = yaml.safe_load(f)

    missing_keys = REQUIRED_TOP_LEVEL_KEYS - set(raw.keys())
    if missing_keys:
        raise RoutingConfigError(
            f"routes.yaml missing required keys: {sorted(missing_keys)}"
        )

    backends: dict[str, str] = raw["backends"]
    routes: dict[str, str] = raw["routes"]
    heavy_models: list[str] = raw["heavy_models"] or []

    for service, backend_name in routes.items():
        if backend_name not in backends:
            raise RoutingConfigError(
                f"Route '{service}' references undefined backend '{backend_name}'. "
                f"Defined backends: {sorted(backends.keys())}"
            )

    return RouterConfig(
        backends=backends,
        routes=routes,
        heavy_models=heavy_models,
    )
```

- [ ] **Step 6: Run to verify AC-9 and AC-10 tests pass**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py -v
```

Expected: both tests PASS.

- [ ] **Step 7: Commit**

```bash
cd headwater-server
git add src/headwater_server/server/routing_config.py tests/server/test_routing_config.py
git commit -m "feat(headwater-server): add routing_config module with RouterConfig and load_router_config

AC-9: FileNotFoundError raised if routes.yaml absent
AC-10: RoutingConfigError raised if route references undefined backend"
```

---

## Task 6: resolve_backend — conduit light routing *(AC-3)*

**Files:**
- Modify: `headwater-server/src/headwater_server/server/routing_config.py`
- Modify: `headwater-server/tests/server/test_routing_config.py`

- [ ] **Step 1: Write failing test for AC-3**

Append to `headwater-server/tests/server/test_routing_config.py` (after the imports block, add the import; after the fixtures, add the test):

```python
# Add to imports at top of file:
# from headwater_server.server.routing_config import (
#     RouterConfig, RoutingConfigError, RoutingError,
#     load_router_config, resolve_backend,
# )

def test_conduit_light_model_routes_to_bywater(config: RouterConfig):
    """AC-3: conduit request with a non-heavy model routes to Bywater."""
    result = resolve_backend("conduit", "llama3.2:3b", config)
    assert result == "http://172.16.0.4:8080"  # bywater
```

Also update the import at the top of `test_routing_config.py` to include `resolve_backend`:

```python
from headwater_server.server.routing_config import (
    RouterConfig,
    RoutingConfigError,
    RoutingError,
    load_router_config,
    resolve_backend,
)
```

- [ ] **Step 2: Run to verify AC-3 test fails**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py::test_conduit_light_model_routes_to_bywater -v
```

Expected: `ImportError: cannot import name 'resolve_backend'`

- [ ] **Step 3: Implement resolve_backend (minimal — conduit default only)**

Append to `headwater-server/src/headwater_server/server/routing_config.py`:

```python
def resolve_backend(service: str, model: str | None, config: RouterConfig) -> str:
    """
    Return backend base_url for the given service and model.

    Raises:
        RoutingError: if service has no entry in config.routes.
    """
    if service not in config.routes:
        raise RoutingError(
            f"Unknown service '{service}'. Known services: {sorted(config.routes.keys())}"
        )

    backend_name = config.routes[service]
    return config.backends[backend_name]
```

- [ ] **Step 4: Run to verify AC-3 test passes**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py::test_conduit_light_model_routes_to_bywater -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd headwater-server
git add src/headwater_server/server/routing_config.py tests/server/test_routing_config.py
git commit -m "feat(headwater-server): add resolve_backend (conduit light routing)

AC-3: conduit with non-heavy model routes to Bywater"
```

---

## Task 7: resolve_backend — conduit heavy routing *(AC-4)*

**Files:**
- Modify: `headwater-server/src/headwater_server/server/routing_config.py`
- Modify: `headwater-server/tests/server/test_routing_config.py`

- [ ] **Step 1: Write failing test for AC-4**

Append to `headwater-server/tests/server/test_routing_config.py`:

```python
def test_conduit_heavy_model_routes_to_deepwater(config: RouterConfig):
    """AC-4: conduit request with a heavy model routes to Deepwater."""
    result = resolve_backend("conduit", "qwq:latest", config)
    assert result == "http://172.16.0.2:8080"  # deepwater
```

- [ ] **Step 2: Run to verify AC-4 test fails**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py::test_conduit_heavy_model_routes_to_deepwater -v
```

Expected: FAIL — currently `resolve_backend("conduit", "qwq:latest", config)` returns Bywater (heavy check not implemented).

- [ ] **Step 3: Add heavy inference check to resolve_backend**

Replace the body of `resolve_backend` in `routing_config.py`:

```python
def resolve_backend(service: str, model: str | None, config: RouterConfig) -> str:
    """
    Return backend base_url for the given service and model.

    Resolution order:
    1. conduit + heavy model → heavy_inference backend
    2. reranker + heavy model → reranker_heavy backend
    3. reranker + light/unknown model → reranker_light backend
    4. all other services → config.routes[service]

    Raises:
        RoutingError: if service has no entry in config.routes.
    """
    is_heavy = model is not None and model in config.heavy_models

    if service == "conduit" and is_heavy:
        backend_name = config.routes["heavy_inference"]
        return config.backends[backend_name]

    if service == "reranker":
        key = "reranker_heavy" if is_heavy else "reranker_light"
        backend_name = config.routes[key]
        return config.backends[backend_name]

    if service not in config.routes:
        raise RoutingError(
            f"Unknown service '{service}'. Known services: {sorted(config.routes.keys())}"
        )

    backend_name = config.routes[service]
    return config.backends[backend_name]
```

- [ ] **Step 4: Run to verify AC-4 test passes (and AC-3 still passes)**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py -v
```

Expected: all tests PASS, including AC-3 and AC-4.

- [ ] **Step 5: Commit**

```bash
cd headwater-server
git add src/headwater_server/server/routing_config.py tests/server/test_routing_config.py
git commit -m "feat(headwater-server): add heavy model routing to resolve_backend

AC-4: conduit with heavy model routes to Deepwater"
```

---

## Task 8: resolve_backend — reranker routing *(AC-5)*

**Files:**
- Modify: `headwater-server/tests/server/test_routing_config.py`

> The reranker logic was already implemented in Task 7. This task adds the tests that prove it.

- [ ] **Step 1: Write failing tests for AC-5**

Append to `headwater-server/tests/server/test_routing_config.py`:

```python
def test_reranker_heavy_model_routes_to_bywater(config: RouterConfig):
    """AC-5: reranker request with a heavy model routes to Bywater (reranker_heavy)."""
    result = resolve_backend("reranker", "qwq:latest", config)
    assert result == "http://172.16.0.4:8080"  # bywater — reranker_heavy


def test_reranker_light_model_routes_to_backwater(config: RouterConfig):
    """AC-5: reranker request with a non-heavy model routes to Backwater (reranker_light)."""
    result = resolve_backend("reranker", "some-light-reranker", config)
    assert result == "http://172.16.0.9:8080"  # backwater — reranker_light


def test_reranker_none_model_routes_to_backwater(config: RouterConfig):
    """AC-5: reranker request with no model name routes to Backwater (treated as light)."""
    result = resolve_backend("reranker", None, config)
    assert result == "http://172.16.0.9:8080"  # backwater — reranker_light
```

- [ ] **Step 2: Run to verify AC-5 tests pass**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py -v
```

Expected: all tests PASS — reranker logic was implemented in Task 7.

- [ ] **Step 3: Commit**

```bash
cd headwater-server
git add tests/server/test_routing_config.py
git commit -m "test(headwater-server): add AC-5 reranker routing tests"
```

---

## Task 9: resolve_backend — unknown service raises RoutingError *(AC-6)*

**Files:**
- Modify: `headwater-server/tests/server/test_routing_config.py`

> The unknown-service raise was already implemented in Task 6/7. This task adds the specific test and verifies the error message is useful.

- [ ] **Step 1: Write failing test for AC-6**

Append to `headwater-server/tests/server/test_routing_config.py`:

```python
def test_unknown_service_raises_routing_error(config: RouterConfig):
    """AC-6: resolve_backend raises RoutingError for unknown services."""
    with pytest.raises(RoutingError) as exc_info:
        resolve_backend("unknown_service", None, config)
    assert "unknown_service" in str(exc_info.value)
```

- [ ] **Step 2: Run to verify AC-6 test passes**

```bash
cd headwater-server && uv run pytest tests/server/test_routing_config.py::test_unknown_service_raises_routing_error -v
```

Expected: PASS — `RoutingError` is already raised with the service name in the message.

- [ ] **Step 3: Commit**

```bash
cd headwater-server
git add tests/server/test_routing_config.py
git commit -m "test(headwater-server): add AC-6 unknown service routing error test"
```

---

## Task 10: HeadwaterRouter class and /ping endpoint *(AC-13)*

**Files:**
- Create: `headwater-server/src/headwater_server/server/router.py`
- Create: `headwater-server/tests/server/test_router.py`

> `HeadwaterRouter` accepts an optional `config_path: Path | None` so tests can inject a temp config without patching globals.

- [ ] **Step 1: Write failing test for AC-13**

Create `headwater-server/tests/server/test_router.py`:

```python
from __future__ import annotations

import pytest
import yaml
from pathlib import Path
from fastapi.testclient import TestClient


VALID_CONFIG = {
    "backends": {
        "deepwater": "http://172.16.0.2:8080",
        "bywater": "http://172.16.0.4:8080",
        "backwater": "http://172.16.0.9:8080",
        "stillwater": "http://172.16.0.3:8080",
    },
    "routes": {
        "conduit": "bywater",
        "heavy_inference": "deepwater",
        "siphon": "deepwater",
        "curator": "bywater",
        "embeddings": "backwater",
        "reranker_light": "backwater",
        "reranker_heavy": "bywater",
        "ambient_inference": "stillwater",
    },
    "heavy_models": ["qwq:latest", "deepseek-r1:70b"],
}


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "routes.yaml"
    path.write_text(yaml.dump(VALID_CONFIG))
    return path


@pytest.fixture
def router_client(config_path: Path) -> TestClient:
    from headwater_server.server.router import HeadwaterRouter
    r = HeadwaterRouter(config_path=config_path)
    return TestClient(r.app)


def test_ping_returns_pong_without_proxying(router_client: TestClient):
    """AC-13: GET /ping returns 200 {"message": "pong"} and does not proxy."""
    response = router_client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"message": "pong"}
```

- [ ] **Step 2: Run to verify AC-13 test fails**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py::test_ping_returns_pong_without_proxying -v
```

Expected: `ImportError` — `router.py` does not exist yet.

- [ ] **Step 3: Implement HeadwaterRouter with /ping**

Create `headwater-server/src/headwater_server/server/router.py`:

```python
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import headwater_server.server.logging_config  # noqa: F401

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from headwater_server.server.routing_config import (
    RouterConfig,
    RoutingError,
    load_router_config,
    ROUTES_YAML_PATH,
)

logger = logging.getLogger(__name__)

HOP_BY_HOP = frozenset({
    "connection", "transfer-encoding", "te", "trailer",
    "upgrade", "keep-alive", "proxy-authorization", "proxy-authenticate",
})


class HeadwaterRouter:
    def __init__(
        self,
        name: str = "Headwater Router",
        config_path: Path | None = None,
    ):
        self._name = name
        self._config: RouterConfig = load_router_config(config_path or ROUTES_YAML_PATH)
        self.app: FastAPI = self._create_app()
        self._register_routes()
        self._register_middleware()

    def _create_app(self) -> FastAPI:
        return FastAPI(
            title=self._name,
            description="Headwater routing gateway",
            version="1.0.0",
        )

    def _register_routes(self) -> None:
        config = self._config

        @self.app.get("/ping")
        async def ping() -> dict:
            return {"message": "pong"}

        # Proxy route added in Task 11

    def _register_middleware(self) -> None:
        from fastapi.middleware.cors import CORSMiddleware

        @self.app.middleware("http")
        async def correlation_middleware(request: Request, call_next: Callable) -> Response:
            header_value = request.headers.get("X-Request-ID", "")
            try:
                parsed = uuid.UUID(header_value)
                assert parsed.version == 4
                request_id = header_value
            except (ValueError, AttributeError, AssertionError):
                request_id = str(uuid.uuid4())

            request.state.request_id = request_id
            start = time.monotonic()

            response = await call_next(request)

            duration_ms = round((time.monotonic() - start) * 1000, 1)
            logger.debug(
                "request_finished",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            response.headers["X-Request-ID"] = request_id
            return response

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


_router = HeadwaterRouter()
app = _router.app
```

- [ ] **Step 4: Run to verify AC-13 test passes**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py::test_ping_returns_pong_without_proxying -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd headwater-server
git add src/headwater_server/server/router.py tests/server/test_router.py
git commit -m "feat(headwater-server): add HeadwaterRouter with /ping endpoint

AC-13: GET /ping returns 200 pong without proxying"
```

---

## Task 11: Proxy route — X-Request-ID forwarding *(AC-11)*

**Files:**
- Modify: `headwater-server/src/headwater_server/server/router.py`
- Modify: `headwater-server/tests/server/test_router.py`

- [ ] **Step 1: Write failing test for AC-11**

Append to `headwater-server/tests/server/test_router.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


def test_proxy_forwards_x_request_id_to_backend(router_client: TestClient):
    """AC-11: Every proxied request includes X-Request-ID on the upstream call."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.content = b'{"result": "ok"}'
    mock_response.headers = {}

    with patch("headwater_server.server.router.httpx") as mock_httpx:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.request = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value = mock_async_client

        router_client.post(
            "/conduit/generate",
            json={"model": "llama3.2:3b", "prompt": "hello"},
        )

    call_kwargs = mock_async_client.request.call_args.kwargs
    assert "x-request-id" in {k.lower() for k in call_kwargs["headers"].keys()}
```

- [ ] **Step 2: Run to verify AC-11 test fails**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py::test_proxy_forwards_x_request_id_to_backend -v
```

Expected: FAIL — no proxy route exists yet.

- [ ] **Step 3: Add catch-all proxy route to HeadwaterRouter._register_routes()**

In `router.py`, replace `_register_routes` with:

```python
    def _register_routes(self) -> None:
        import httpx
        import orjson
        from headwater_api.classes import HeadwaterServerError, ErrorType
        from fastapi.responses import JSONResponse

        config = self._config

        @self.app.get("/ping")
        async def ping() -> dict:
            return {"message": "pong"}

        @self.app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
        async def proxy(request: Request, path: str) -> Response:
            service = path.split("/")[0]

            body = await request.body()
            model: str | None = None
            if body:
                try:
                    model = orjson.loads(body).get("model")
                except Exception:
                    pass

            try:
                from headwater_server.server.routing_config import resolve_backend
                backend_url = resolve_backend(service, model, config)
            except RoutingError as exc:
                error = HeadwaterServerError(
                    error_type=ErrorType.ROUTING_ERROR,
                    message=str(exc),
                    status_code=400,
                    path=request.url.path,
                    method=request.method,
                    request_id=request.state.request_id,
                )
                return JSONResponse(status_code=400, content=error.model_dump())

            target = f"{backend_url}/{path}"
            if request.url.query:
                target = f"{target}?{request.url.query}"

            forward_headers = {
                k: v for k, v in request.headers.items()
                if k.lower() not in HOP_BY_HOP
            }
            forward_headers["x-request-id"] = request.state.request_id

            logger.debug(
                "proxy_request",
                extra={
                    "service": service,
                    "backend": backend_url,
                    "model": model,
                    "path": path,
                },
            )

            try:
                async with httpx.AsyncClient() as client:
                    upstream = await client.request(
                        method=request.method,
                        url=target,
                        headers=forward_headers,
                        content=body,
                        timeout=300.0,
                    )
            except httpx.ConnectError as exc:
                logger.error(
                    "backend_unavailable",
                    extra={
                        "backend": backend_url,
                        "path": path,
                        "error": str(exc),
                        "request_id": request.state.request_id,
                    },
                )
                error = HeadwaterServerError(
                    error_type=ErrorType.BACKEND_UNAVAILABLE,
                    message=f"Backend unreachable: {backend_url}",
                    status_code=503,
                    path=request.url.path,
                    method=request.method,
                    request_id=request.state.request_id,
                    context={"backend": backend_url},
                )
                return JSONResponse(status_code=503, content=error.model_dump())
            except httpx.TimeoutException as exc:
                logger.error(
                    "backend_timeout",
                    extra={
                        "backend": backend_url,
                        "path": path,
                        "error": str(exc),
                        "request_id": request.state.request_id,
                    },
                )
                error = HeadwaterServerError(
                    error_type=ErrorType.BACKEND_TIMEOUT,
                    message=f"Backend timed out after 300s: {backend_url}",
                    status_code=503,
                    path=request.url.path,
                    method=request.method,
                    request_id=request.state.request_id,
                    context={"backend": backend_url},
                )
                return JSONResponse(status_code=503, content=error.model_dump())

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

- [ ] **Step 4: Run to verify AC-11 test passes**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py::test_proxy_forwards_x_request_id_to_backend -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd headwater-server
git add src/headwater_server/server/router.py tests/server/test_router.py
git commit -m "feat(headwater-server): add catch-all proxy route with X-Request-ID forwarding

AC-11: X-Request-ID set on all proxied upstream requests"
```

---

## Task 12: Proxy route — response passthrough *(AC-7)*

**Files:**
- Modify: `headwater-server/tests/server/test_router.py`

- [ ] **Step 1: Write failing test for AC-7**

Append to `headwater-server/tests/server/test_router.py`:

```python
def test_proxy_propagates_422_status_and_body_verbatim(router_client: TestClient):
    """AC-7: Backend 422 is forwarded with identical status code and body; hop-by-hop headers stripped."""
    error_body = b'{"detail": "validation error from backend"}'
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 422
    mock_response.content = error_body
    mock_response.headers = {
        "content-type": "application/json",
        "transfer-encoding": "chunked",  # hop-by-hop — must be stripped
        "x-custom-header": "keep-this",
    }

    with patch("headwater_server.server.router.httpx") as mock_httpx:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.request = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value = mock_async_client

        response = router_client.post(
            "/conduit/generate",
            json={"model": "llama3.2:3b"},
        )

    assert response.status_code == 422
    assert response.content == error_body
    assert "transfer-encoding" not in {k.lower() for k in response.headers}
    assert response.headers.get("x-custom-header") == "keep-this"
```

- [ ] **Step 2: Run to verify AC-7 test passes**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py::test_proxy_propagates_422_status_and_body_verbatim -v
```

Expected: PASS — response passthrough was implemented in Task 11.

- [ ] **Step 3: Commit**

```bash
cd headwater-server
git add tests/server/test_router.py
git commit -m "test(headwater-server): add AC-7 response passthrough test"
```

---

## Task 13: Proxy route — backend unreachable *(AC-8)*

**Files:**
- Modify: `headwater-server/tests/server/test_router.py`

- [ ] **Step 1: Write failing test for AC-8**

Append to `headwater-server/tests/server/test_router.py`:

```python
def test_proxy_returns_503_with_backend_unavailable_when_unreachable(router_client: TestClient):
    """AC-8: Backend ConnectError → HTTP 503 with error_type='backend_unavailable'."""
    with patch("headwater_server.server.router.httpx") as mock_httpx:
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.request = AsyncMock(
            side_effect=mock_httpx.ConnectError("Connection refused")
        )
        mock_httpx.AsyncClient.return_value = mock_async_client
        mock_httpx.ConnectError = httpx.ConnectError
        mock_httpx.TimeoutException = httpx.TimeoutException

        response = router_client.post(
            "/conduit/generate",
            json={"model": "llama3.2:3b"},
        )

    assert response.status_code == 503
    body = response.json()
    assert body["error_type"] == "backend_unavailable"
    assert "172.16.0.4" in body["message"] or "172.16.0.4" in str(body.get("context", ""))
```

- [ ] **Step 2: Run to verify AC-8 test passes**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py::test_proxy_returns_503_with_backend_unavailable_when_unreachable -v
```

Expected: PASS — ConnectError handling was implemented in Task 11.

- [ ] **Step 3: Run full router test suite**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py tests/server/test_routing_config.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
cd headwater-server
git add tests/server/test_router.py
git commit -m "test(headwater-server): add AC-8 backend unreachable test"
```

---

## Task 14: Entry point — router_main and pyproject.toml

**Files:**
- Modify: `headwater-server/src/headwater_server/server/main.py`
- Modify: `headwater-server/pyproject.toml`

> No AC-specific TDD here — this is the deployment wiring. Verify with an import test.

- [ ] **Step 1: Write importability test**

Append to `headwater-server/tests/server/test_router.py`:

```python
def test_router_app_module_level_app_is_importable():
    """router.py exposes a module-level `app` for uvicorn."""
    from headwater_server.server import router as router_module
    assert hasattr(router_module, "app")
    assert router_module.app.title == "Headwater Router"


def test_router_main_is_callable():
    """router_main entry point function exists and is callable."""
    from headwater_server.server.main import router_main
    assert callable(router_main)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py::test_router_main_is_callable -v
```

Expected: FAIL — `router_main` does not exist in `main.py` yet.

- [ ] **Step 3: Add router_main to main.py**

In `headwater-server/src/headwater_server/server/main.py`, add after the existing `run_server` and `main` functions:

```python
def run_router():
    from headwater_server.server.logo import print_logo
    from pathlib import Path
    import uvicorn
    import sys

    sys.stdout.write("\033[2J\033[H")
    print_logo("router")

    header_height = 10
    sys.stdout.write(f"\033[{header_height + 1};r")
    sys.stdout.write(f"\033[{header_height + 1};1H")
    sys.stdout.flush()

    try:
        uvicorn.run(
            "headwater_server.server.router:app",
            host="0.0.0.0",
            port=8081,
            reload=True,
            reload_dirs=[str(Path(__file__).parent.parent.parent)],
            log_config=None,
            log_level="info",
        )
    finally:
        sys.stdout.write("\033[r")
        sys.stdout.flush()


def router_main():
    run_router()
```

- [ ] **Step 4: Add entry point to pyproject.toml**

In `headwater-server/pyproject.toml`, add to `[project.scripts]`:

```toml
[project.scripts]
headwater = "headwater_server.server.main:main"
headwater-router = "headwater_server.server.main:router_main"
update-embedding-modelstore = "headwater_server.scripts.update_embedding_modelstore:main"
```

- [ ] **Step 5: Run to verify tests pass**

```bash
cd headwater-server && uv run pytest tests/server/test_router.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Verify entry point is registered**

```bash
cd headwater-server && uv run headwater-router --help
```

Expected: uvicorn help output (or "Headwater Router" logo startup).

- [ ] **Step 7: Final full test run**

```bash
cd headwater-server && uv run pytest tests/ -v
cd headwater-client && uv run pytest tests/ -v
cd headwater-api && uv run pytest tests/ -v
cd dbclients-project && uv run pytest tests/ -v
```

Expected: all tests across all packages PASS.

- [ ] **Step 8: Commit**

```bash
cd headwater-server
git add src/headwater_server/server/main.py pyproject.toml tests/server/test_router.py
git commit -m "feat(headwater-server): add headwater-router entry point on port 8081

Wires router_main() to uvicorn with port 8081. All ACs covered:
AC-1, AC-2, AC-12 (transport aliases)
AC-3, AC-4, AC-5, AC-6 (route resolution)
AC-7, AC-8, AC-11 (proxy behavior)
AC-9, AC-10 (config validation)
AC-13 (/ping endpoint)"
```

---

## Self-Review Checklist

- [x] AC-1: Task 4 step 3 (headwater alias → 8081)
- [x] AC-2: Task 4 step 5 (deepwater alias → AlphaBlue:8080)
- [x] AC-3: Task 6 (conduit light → Bywater)
- [x] AC-4: Task 7 (conduit heavy → Deepwater)
- [x] AC-5: Task 8 (reranker heavy/light split)
- [x] AC-6: Task 9 (unknown service → RoutingError)
- [x] AC-7: Task 12 (422 passthrough + hop-by-hop strip)
- [x] AC-8: Task 13 (ConnectError → 503 backend_unavailable)
- [x] AC-9: Task 5 step 1 (missing routes.yaml → FileNotFoundError)
- [x] AC-10: Task 5 step 3 (undefined backend → RoutingConfigError)
- [x] AC-11: Task 11 (X-Request-ID forwarded)
- [x] AC-12: Task 4 step 7 (stillwater alias → Botvinnik:8080)
- [x] AC-13: Task 10 (/ping returns pong, no proxy)
