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


def create_embedding_spec(model: str, provider: str) -> None:
    from headwater_server.services.embeddings_service.research_embedding_models import (
        create_embedding_spec as _create,
    )
    _create(model, provider)


class EmbeddingModelStore:
    @classmethod
    def models(cls) -> dict[str, list[str]]:
        with open(_REGISTRY_PATH) as f:
            return json.load(f)

    @classmethod
    def list_models(cls) -> list[str]:
        return list(dict.fromkeys(itertools.chain.from_iterable(cls.models().values())))

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

    @classmethod
    def get_spec(cls, model: str) -> EmbeddingModelSpec:
        from headwater_api.classes import EmbeddingModelSpec
        from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
            get_embedding_spec_by_name,
            in_db,
        )
        if not cls.is_supported(model):
            raise ValueError(
                f"Model '{model}' is not in the embedding model registry."
            )
        if not in_db(model):
            raise ValueError(
                f"Model '{model}' has no spec record — run update_embedding_modelstore."
            )
        return get_embedding_spec_by_name(model)

    @classmethod
    def get_all_specs(cls) -> list[EmbeddingModelSpec]:
        from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
            get_all_embedding_specs,
        )
        return get_all_embedding_specs()

    @classmethod
    def by_provider(cls, provider: EmbeddingProvider) -> list[EmbeddingModelSpec]:
        return [s for s in cls.get_all_specs() if s.provider == provider]

    @classmethod
    def _is_consistent(cls) -> bool:
        from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
            get_all_spec_model_names,
        )
        registry_names = set(cls.list_models())
        db_names = set(get_all_spec_model_names())
        all_entries = list(itertools.chain.from_iterable(cls.models().values()))
        if len(all_entries) != len(set(all_entries)):
            logger.warning("Duplicate model IDs detected in registry.")
            return False
        return registry_names == db_names

    @classmethod
    def update(cls) -> None:
        if not cls._is_consistent():
            logger.info("Embedding model specs inconsistent with registry. Updating...")
            cls._update_models()
        else:
            logger.info("Embedding model specs consistent. No update needed.")

    @classmethod
    def _update_models(cls) -> None:
        import headwater_server.services.embeddings_service.embedding_model_store as _self_mod
        from headwater_server.services.embeddings_service.embedding_modelspecs_crud import (
            get_all_spec_model_names,
            delete_embedding_spec,
        )
        registry_names = set(cls.list_models())
        db_names = set(get_all_spec_model_names())
        to_add = registry_names - db_names
        to_delete = db_names - registry_names
        logger.info(f"Models to add: {len(to_add)}, to delete: {len(to_delete)}")
        for model in to_delete:
            delete_embedding_spec(model)
            logger.info(f"Deleted orphaned spec for {model}")
        for model in to_add:
            provider = cls.identify_provider(model)
            _self_mod.create_embedding_spec(model, provider.value)
            logger.info(f"Created spec for {model} ({provider})")
        if not cls._is_consistent():
            raise ValueError("Specs still inconsistent after update().")
