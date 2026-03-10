from __future__ import annotations

import logging
import os
import threading
from typing import Protocol

import torch
from sentence_transformers import SentenceTransformer

from headwater_api.classes import ChromaBatch
from headwater_server.services.embeddings_service.embedding_model_store import EmbeddingModelStore

logger = logging.getLogger(__name__)
_DEVICE_CACHE = None
_model_cache: dict[str, EmbeddingModel] = {}
_cache_lock = threading.Lock()
HUGGINGFACE_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")
os.environ["HF_TOKEN"] = HUGGINGFACE_API_TOKEN

_TRUST_REMOTE_CODE_MODELS = {
    "Alibaba-NLP/gte-large-en-v1.5",
    "nomic-ai/nomic-embed-text-v1.5",
}


class EmbeddingFunction(Protocol):
    def __call__(
        self, documents: list[str], prompt: str | None = None
    ) -> list[list[float]]: ...


class EmbeddingModel:
    def __init__(self, model_name: str):
        self.model_name = model_name
        if model_name not in self.models():
            raise ValueError(f"Model '{model_name}' is not supported.")

        self._st_model = SentenceTransformer(
            model_name,
            device=self.device(),
            model_kwargs={"torch_dtype": torch.bfloat16},
            trust_remote_code=model_name in _TRUST_REMOTE_CODE_MODELS,
        )

        self.embedding_function: EmbeddingFunction = self._get_handler(model_name)

    def _get_handler(self, model_name: str) -> EmbeddingFunction:
        match model_name:
            case "google/embeddinggemma-300m":
                return self._gemma_handler
            case name if "bge-" in name:
                return self._bge_handler
            case _:
                return self._default_handler

    # --- Specialized Handlers ---

    def _gemma_handler(
        self, documents: list[str], prompt: str | None = None
    ) -> list[list[float]]:
        if prompt is not None:
            return self._st_model.encode(
                documents,
                prompt=prompt,
                batch_size=64,
                convert_to_tensor=False,
            ).tolist()
        return self._st_model.encode(
            documents,
            prompt_name="STS",
            batch_size=64,
            convert_to_tensor=False,
        ).tolist()

    def _bge_handler(
        self, documents: list[str], prompt: str | None = None
    ) -> list[list[float]]:
        kwargs: dict = {"batch_size": 128, "convert_to_tensor": False}
        if prompt is not None:
            kwargs["prompt"] = prompt
        return self._st_model.encode(documents, **kwargs).tolist()

    def _default_handler(
        self, documents: list[str], prompt: str | None = None
    ) -> list[list[float]]:
        kwargs: dict = {"batch_size": 128, "convert_to_tensor": False}
        if prompt is not None:
            kwargs["prompt"] = prompt
        return self._st_model.encode(documents, **kwargs).tolist()

    # --- Standard Interface Methods ---

    @classmethod
    def models(cls) -> list[str]:
        return EmbeddingModelStore.list_models()

    @classmethod
    def device(cls) -> str:
        global _DEVICE_CACHE
        if _DEVICE_CACHE is None:
            _DEVICE_CACHE = "cuda" if torch.cuda.is_available() else "cpu"
        return _DEVICE_CACHE

    @classmethod
    def get(cls, model_name: str) -> EmbeddingModel:
        if model_name not in _model_cache:
            with _cache_lock:
                if model_name not in _model_cache:
                    # Evict all other models from GPU before loading the new one.
                    # Keeps peak VRAM usage to one model at a time.
                    for name in list(_model_cache.keys()):
                        logger.info("evicting model from GPU: %s", name)
                        _model_cache[name]._st_model.cpu()
                        del _model_cache[name]
                    torch.cuda.empty_cache()

                    logger.info("embedding model loading: %s", model_name)
                    try:
                        _model_cache[model_name] = cls(model_name)
                    except Exception as e:
                        logger.error("Failed to instantiate EmbeddingModel '%s': %s", model_name, e)
                        raise
                    logger.info("embedding model cached: %s", model_name)
                else:
                    logger.info("embedding model cache hit: %s", model_name)
        else:
            logger.info("embedding model cache hit: %s", model_name)
        return _model_cache[model_name]

    def generate_embeddings(
        self, batch: ChromaBatch, prompt: str | None = None
    ) -> ChromaBatch:
        embeddings = self.embedding_function(batch.documents, prompt=prompt)
        return ChromaBatch(
            ids=batch.ids,
            documents=batch.documents,
            metadatas=batch.metadatas,
            embeddings=embeddings,
        )

    def generate_embedding(self, document: str, prompt: str | None = None) -> list[float]:
        return self.embedding_function([document], prompt=prompt)[0]
