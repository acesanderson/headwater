from __future__ import annotations

from enum import Enum


class EmbeddingTask(str, Enum):
    query = "query"
    document = "document"
    classification = "classification"
    clustering = "clustering"
