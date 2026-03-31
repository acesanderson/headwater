from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from headwater_server.server.routing_config import (
    RouterConfig,
    RoutingConfigError,
    RoutingError,
    load_router_config,
    resolve_backend,
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


def test_conduit_light_model_routes_to_bywater(config: RouterConfig):
    """AC-3: conduit request with a non-heavy model routes to Bywater."""
    result = resolve_backend("conduit", "llama3.2:3b", config)
    assert result == "http://172.16.0.4:8080"  # bywater


def test_conduit_heavy_model_routes_to_deepwater(config: RouterConfig):
    """AC-4: conduit request with a heavy model routes to Deepwater."""
    result = resolve_backend("conduit", "qwq:latest", config)
    assert result == "http://172.16.0.2:8080"  # deepwater
