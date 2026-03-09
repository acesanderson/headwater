from __future__ import annotations

from enum import Enum


class EmbeddingProvider(str, Enum):
    HUGGINGFACE = "huggingface"
    OPENAI = "openai"
    COHERE = "cohere"
    JINA = "jina"
