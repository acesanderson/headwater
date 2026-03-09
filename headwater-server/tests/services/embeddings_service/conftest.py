from __future__ import annotations
import json
import pytest
from tinydb import TinyDB


REGISTRY_DATA = {
    "huggingface": ["BAAI/bge-m3", "BAAI/bge-base-en-v1.5"],
    "openai": [],
    "cohere": [],
    "jina": [],
}


@pytest.fixture
def registry_path(tmp_path):
    path = tmp_path / "embedding_models.json"
    path.write_text(json.dumps(REGISTRY_DATA))
    return path


@pytest.fixture
def tmp_db(tmp_path):
    return TinyDB(tmp_path / "embedding_modelspecs.json")


@pytest.fixture
def patched_store(monkeypatch, registry_path, tmp_db):
    import headwater_server.services.embeddings_service.embedding_modelspecs_crud as crud
    monkeypatch.setattr(crud, "db", tmp_db)
    try:
        import headwater_server.services.embeddings_service.embedding_model_store as store_mod
        monkeypatch.setattr(store_mod, "_REGISTRY_PATH", registry_path)
    except ImportError:
        pass
