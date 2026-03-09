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
