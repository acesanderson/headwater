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
