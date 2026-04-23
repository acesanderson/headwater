from __future__ import annotations

from dataclasses import dataclass, field
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
    backends: dict[str, str]              # backend name -> base_url
    routes: dict[str, str]                # service name -> backend name
    heavy_models: list[str]               # model names that trigger heavy routing
    fallbacks: dict[str, list[str]] = field(default_factory=dict)  # route_key -> [backend_name, ...]


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

    raw_fallbacks: dict[str, list[str]] = raw.get("fallbacks") or {}
    for route_key, fallback_names in raw_fallbacks.items():
        for fb_name in fallback_names:
            if fb_name not in backends:
                raise RoutingConfigError(
                    f"Fallback '{fb_name}' for route '{route_key}' references undefined backend. "
                    f"Defined backends: {sorted(backends.keys())}"
                )

    return RouterConfig(
        backends=backends,
        routes=routes,
        heavy_models=heavy_models,
        fallbacks=raw_fallbacks,
    )


def resolve_backend(service: str, model: str | None, config: RouterConfig) -> tuple[str, str]:
    """
    Return (backend_base_url, route_key) for the given service and model.

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
        route_key = "heavy_inference"
        backend_name = config.routes[route_key]
        return config.backends[backend_name], route_key

    if service == "reranker":
        route_key = "reranker_heavy" if is_heavy else "reranker_light"
        backend_name = config.routes[route_key]
        return config.backends[backend_name], route_key

    if service not in config.routes:
        raise RoutingError(
            f"Unknown service '{service}'. Known services: {sorted(config.routes.keys())}"
        )

    route_key = service
    backend_name = config.routes[service]
    return config.backends[backend_name], route_key


def get_fallback_urls(route_key: str, config: RouterConfig) -> list[str]:
    """Return ordered list of fallback backend base URLs for the given route key."""
    return [
        config.backends[name]
        for name in config.fallbacks.get(route_key, [])
        if name in config.backends
    ]
