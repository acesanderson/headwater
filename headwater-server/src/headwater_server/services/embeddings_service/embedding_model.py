import torch
import logging
import os
from typing import Protocol
from sentence_transformers import SentenceTransformer
from headwater_api.classes import ChromaBatch, load_embedding_models

logger = logging.getLogger(__name__)
_DEVICE_CACHE = None
HUGGINGFACE_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")
os.environ["HF_TOKEN"] = HUGGINGFACE_API_TOKEN


class EmbeddingFunction(Protocol):
    def __call__(self, documents: list[str]) -> list[list[float]]: ...


class EmbeddingModel:
    def __init__(self, model_name: str):
        self.model_name = model_name
        if model_name not in self.models():
            raise ValueError(f"Model '{model_name}' is not supported.")

        # Load the model once per instance
        self._st_model = SentenceTransformer(
            model_name,
            device=self.device(),
            model_kwargs={"torch_dtype": torch.bfloat16},  # Optimal for RTX 5090
        )

        # Direct to specialized logic via match/case
        self.embedding_function: EmbeddingFunction = self._get_handler(model_name)

    def _get_handler(self, model_name: str) -> EmbeddingFunction:
        """
        Routes the model name to the correct specialized embedding logic.
        """
        match model_name:
            case "google/embeddinggemma-300m":
                return self._gemma_handler
            case name if "bge-" in name:
                return self._bge_handler
            case _:
                return self._default_handler

    # --- Specialized Handlers ---

    def _gemma_handler(self, documents: list[str]) -> list[list[float]]:
        """
        Gemma 3 logic: Uses specialized instruction prompts for evaluation accuracy.
        """
        # For evaluation/loss, we treat inputs as similarity tasks
        return self._st_model.encode(
            documents,
            prompt_name="STS",  # Standard instruction for Semantic Textual Similarity
            batch_size=64,
            convert_to_tensor=False,
        ).tolist()

    def _bge_handler(self, documents: list[str]) -> list[list[float]]:
        """
        BGE logic: BGE v1.5 models are optimized for a specific query prefix.
        """
        # Note: BGE-large/base often perform better when asymmetric (query vs passage).
        # In a loss function context, we treat them as standard encodings.
        return self._st_model.encode(
            documents,
            batch_size=128,  # BGE is lighter, can handle bigger batches on 5090
            convert_to_tensor=False,
        ).tolist()

    def _default_handler(self, documents: list[str]) -> list[list[float]]:
        """
        Fallback for MiniLM, MPNet, and other standard SentenceTransformers.
        """
        return self._st_model.encode(
            documents, batch_size=128, convert_to_tensor=False
        ).tolist()

    # --- Standard Interface Methods ---

    @classmethod
    def models(cls) -> list[str]:
        return load_embedding_models()

    @classmethod
    def device(cls) -> str:
        global _DEVICE_CACHE
        if _DEVICE_CACHE is None:
            _DEVICE_CACHE = "cuda" if torch.cuda.is_available() else "cpu"
        return _DEVICE_CACHE

    def generate_embeddings(self, batch: ChromaBatch) -> ChromaBatch:
        embeddings = self.embedding_function(batch.documents)
        return ChromaBatch(
            ids=batch.ids,
            documents=batch.documents,
            metadatas=batch.metadatas,
            embeddings=embeddings,
        )

    def generate_embedding(self, document: str) -> list[float]:
        return self.embedding_function([document])[0]
