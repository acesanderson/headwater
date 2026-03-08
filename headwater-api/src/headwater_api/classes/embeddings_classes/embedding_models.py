from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_embedding_models_file = Path(__file__).parent / "embedding_models.json"


@dataclass
class ModelPromptSpec:
    prompt_required: bool
    valid_prefixes: list[str] | None
    prompt_unsupported: bool
    task_map: dict[str, str] | None


def load_embedding_models() -> list[str]:
    with open(_embedding_models_file, "r", encoding="utf-8") as f:
        data: dict = json.load(f)
    return list(data["embedding_models"].keys())


def get_model_prompt_spec(model_name: str) -> ModelPromptSpec:
    with open(_embedding_models_file, "r", encoding="utf-8") as f:
        data: dict = json.load(f)
    entry = data["embedding_models"][model_name]
    return ModelPromptSpec(
        prompt_required=entry["prompt_required"],
        valid_prefixes=entry["valid_prefixes"],
        prompt_unsupported=entry["prompt_unsupported"],
        task_map=entry["task_map"],
    )
