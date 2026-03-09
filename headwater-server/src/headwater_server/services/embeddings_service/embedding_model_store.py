from __future__ import annotations
import json
import itertools
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from headwater_api.classes import EmbeddingModelSpec, EmbeddingProvider

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).parent / "embedding_models.json"


class EmbeddingModelStore:
    @classmethod
    def models(cls) -> dict[str, list[str]]:
        with open(_REGISTRY_PATH) as f:
            return json.load(f)

    @classmethod
    def list_models(cls) -> list[str]:
        return list(itertools.chain.from_iterable(cls.models().values()))

    @classmethod
    def identify_provider(cls, model: str) -> EmbeddingProvider:
        from headwater_api.classes import EmbeddingProvider
        matches = [
            provider for provider, model_list in cls.models().items()
            if model in model_list
        ]
        if len(matches) == 0:
            raise ValueError(f"Provider not found for model: '{model}'.")
        if len(matches) > 1:
            raise ValueError(
                f"Model '{model}' found under multiple providers: {matches}. Registry is malformed."
            )
        return EmbeddingProvider(matches[0])

    @classmethod
    def is_supported(cls, model: str) -> bool:
        return model in cls.list_models()
