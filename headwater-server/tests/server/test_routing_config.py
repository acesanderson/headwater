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
    url, _ = resolve_backend("conduit", "llama3.2:3b", config)
    assert url == "http://172.16.0.4:8080"  # bywater


def test_conduit_heavy_model_routes_to_deepwater(config: RouterConfig):
    """AC-4: conduit request with a heavy model routes to Deepwater."""
    url, _ = resolve_backend("conduit", "qwq:latest", config)
    assert url == "http://172.16.0.2:8080"  # deepwater


def test_reranker_heavy_model_routes_to_bywater(config: RouterConfig):
    """AC-5: reranker request with a heavy model routes to Bywater (reranker_heavy)."""
    url, _ = resolve_backend("reranker", "qwq:latest", config)
    assert url == "http://172.16.0.4:8080"  # bywater — reranker_heavy


def test_reranker_light_model_routes_to_backwater(config: RouterConfig):
    """AC-5: reranker request with a non-heavy model routes to Backwater (reranker_light)."""
    url, _ = resolve_backend("reranker", "some-light-reranker", config)
    assert url == "http://172.16.0.9:8080"  # backwater — reranker_light


def test_reranker_none_model_routes_to_backwater(config: RouterConfig):
    """AC-5: reranker request with no model name routes to Backwater (treated as light)."""
    url, _ = resolve_backend("reranker", None, config)
    assert url == "http://172.16.0.9:8080"  # backwater — reranker_light


def test_unknown_service_raises_routing_error(config: RouterConfig):
    """AC-6: resolve_backend raises RoutingError for unknown services."""
    with pytest.raises(RoutingError) as exc_info:
        resolve_backend("unknown_service", None, config)
    assert "unknown_service" in str(exc_info.value)


def test_resolve_backend_returns_tuple_for_conduit(config: RouterConfig):
    """resolve_backend returns (url, route_key) tuple for standard conduit route."""
    result = resolve_backend("conduit", None, config)
    assert isinstance(result, tuple), "Expected tuple, got non-tuple"
    assert len(result) == 2
    url, route_key = result
    assert url == "http://172.16.0.4:8080"
    assert route_key == "conduit"


def test_resolve_backend_returns_tuple_for_heavy_conduit(config: RouterConfig):
    """conduit + heavy model → heavy_inference route key."""
    url, route_key = resolve_backend("conduit", "qwq:latest", config)
    assert url == "http://172.16.0.2:8080"
    assert route_key == "heavy_inference"


def test_resolve_backend_returns_tuple_for_reranker_light(config: RouterConfig):
    """reranker + non-heavy model → reranker_light route key."""
    url, route_key = resolve_backend("reranker", "small-model", config)
    assert route_key == "reranker_light"


def test_resolve_backend_returns_tuple_for_reranker_heavy(config: RouterConfig):
    """reranker + heavy model → reranker_heavy route key."""
    url, route_key = resolve_backend("reranker", "qwq:latest", config)
    assert route_key == "reranker_heavy"


def test_conduit_embeddings_path_routes_to_backwater(config: RouterConfig):
    """conduit/embeddings sub-path → embeddings route key → backwater."""
    url, route_key = resolve_backend("conduit", None, config, path="conduit/embeddings")
    assert route_key == "embeddings"
    assert url == "http://172.16.0.9:8080"  # backwater


def test_conduit_embeddings_quick_path_routes_to_backwater(config: RouterConfig):
    """conduit/embeddings/quick sub-path → embeddings route key → backwater."""
    url, route_key = resolve_backend("conduit", None, config, path="conduit/embeddings/quick")
    assert route_key == "embeddings"
    assert url == "http://172.16.0.9:8080"  # backwater


def test_conduit_embeddings_path_ignores_heavy_model(config: RouterConfig):
    """embeddings path takes priority over heavy model check."""
    url, route_key = resolve_backend("conduit", "qwq:latest", config, path="conduit/embeddings")
    assert route_key == "embeddings"
    assert url == "http://172.16.0.9:8080"  # backwater
