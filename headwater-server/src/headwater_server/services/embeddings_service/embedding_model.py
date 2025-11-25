import json
from pathlib import Path
from headwater_api.classes import ChromaBatch, load_embedding_models
from typing import Protocol

_DEVICE_CACHE = None
EMBEDDING_MODELS_FILE = Path(__file__).parent / "embedding_models.json"


class EmbeddingFunction(Protocol):
    """
    A protocol for embedding functions; matches Chroma's expected signature.
    """

    def __call__(self, documents: list[str]) -> list[list[float]]: ...


class EmbeddingModel:
    def __init__(self, model_name: str):
        self.model_name: str = model_name
        if model_name not in self.models():
            raise ValueError(
                f"Model '{model_name}' is not in the list of supported models."
            )
        self.embedding_function: EmbeddingFunction = self.get_embedding_function(
            model_name
        )

    def get_embedding_function(self, model_name: str) -> EmbeddingFunction:
        """
        Get the embedding function for the specified model.
        For now this is just huggingface transformers models; in the future we may add cloud APIs or other interfaces.
        """

        def hugging_face_embedding_function(documents: list[str]) -> list[list[float]]:
            from transformers import AutoModel, AutoTokenizer
            import torch

            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModel.from_pretrained(model_name).to(self.device())

            inputs = tokenizer(
                documents, padding=True, truncation=True, return_tensors="pt"
            )
            inputs = {k: v.to(self.device()) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = model(**inputs)
                embeddings = outputs.last_hidden_state.mean(dim=1).cpu().tolist()
            return embeddings

        def openai_embedding_function(documents: list[str]) -> list[list[float]]: ...

        def google_embedding_function(documents: list[str]) -> list[list[float]]: ...

        def cohere_embedding_function(documents: list[str]) -> list[list[float]]: ...

        return hugging_face_embedding_function

    @classmethod
    def models(cls) -> list[str]:
        embedding_models: list[str] = load_embedding_models()
        return embedding_models

    @classmethod
    def device(cls) -> str:
        global _DEVICE_CACHE
        if _DEVICE_CACHE is None:
            import torch

            _DEVICE_CACHE = (
                "mps"
                if torch.backends.mps.is_available()
                else "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )
        return _DEVICE_CACHE

    def generate_embeddings(self, batch: ChromaBatch) -> ChromaBatch:
        """
        Generate embeddings for a batch of documents.

        Args:
            batch (ChromaBatch): A batch of ids and documents to generate embeddings for.
        Returns:
            ChromaBatch: A new batch the original ids and documents, as well as generated embeddings.
        """
        embeddings = self.embedding_function(batch.documents)

        new_batch = ChromaBatch(
            ids=batch.ids,
            documents=batch.documents,
            metadatas=batch.metadatas,
            embeddings=embeddings,
        )
        return new_batch

    def generate_embedding(self, document: str) -> list[float]:
        """
        Generate an embedding for a single document.
        Wraps generate_embeddings for convenience.
        """
        batch = ChromaBatch(
            ids=["0"],
            documents=[document],
            metadatas=[{}],
        )
        embedded_batch = self.generate_embeddings(batch)
        if not embedded_batch.embeddings:
            raise ValueError("No embeddings were generated.")
        return embedded_batch.embeddings[0]
