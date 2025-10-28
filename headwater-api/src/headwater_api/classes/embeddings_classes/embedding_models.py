import json
from pathlib import Path

embedding_models_file = Path(__file__).parent / "embedding_models.json"


def load_embedding_models() -> list[str]:
    """
    Load the list of available embedding models from a JSON file.
    """
    with open(embedding_models_file, "r", encoding="utf-8") as f:
        models: dict[str, str] = json.load(f)
    embedding_models_list: list[str] = models["embedding_models"]
    return embedding_models_list
