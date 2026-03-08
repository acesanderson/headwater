from __future__ import annotations
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DIR = Path(__file__).parent

try:
    with open(_DIR / "aliases.json") as f:
        _ALIASES: dict[str, str] = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    logger.error("Failed to load aliases.json: %s", e)
    raise

try:
    with open(_DIR / "reranking_models.json") as f:
        _MODELS: dict[str, dict] = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    logger.error("Failed to load reranking_models.json: %s", e)
    raise


def resolve_model_name(model_name: str) -> str:
    resolved = _ALIASES.get(model_name, model_name)
    if resolved not in _MODELS:
        raise ValueError(f"Model '{resolved}' is not in the allowlist (requested: '{model_name}')")
    return resolved


def get_model_config(resolved_name: str) -> dict:
    return _MODELS[resolved_name]


def list_models() -> list[dict]:
    return [
        {"name": name, "output_type": cfg["output_type"]}
        for name, cfg in _MODELS.items()
    ]
