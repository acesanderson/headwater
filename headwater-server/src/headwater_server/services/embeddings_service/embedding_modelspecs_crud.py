from __future__ import annotations
from pathlib import Path
from tinydb import TinyDB, Query
from headwater_api.classes import EmbeddingModelSpec

_dir = Path(__file__).parent
db = TinyDB(_dir / "embedding_modelspecs.json")


def add_embedding_spec(spec: EmbeddingModelSpec) -> None:
    db.insert(spec.model_dump())


def get_all_embedding_specs() -> list[EmbeddingModelSpec]:
    return [EmbeddingModelSpec(**item) for item in db.all()]


def get_embedding_spec_by_name(model: str) -> EmbeddingModelSpec:
    q = Query()
    results = db.search(q.model == model)
    if not results:
        raise ValueError(f"EmbeddingModelSpec for '{model}' not found.")
    return EmbeddingModelSpec(**results[0])


def get_all_spec_model_names() -> list[str]:
    return [item["model"] for item in db.all()]


def delete_embedding_spec(model: str) -> None:
    q = Query()
    db.remove(q.model == model)


def in_db(model: str) -> bool:
    q = Query()
    return bool(db.search(q.model == model))


def wipe_and_repopulate(specs: list[EmbeddingModelSpec]) -> None:
    db.truncate()
    for spec in specs:
        db.insert(spec.model_dump())
