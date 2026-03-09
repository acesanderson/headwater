from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from headwater_api.classes.embeddings_classes.embedding_provider import EmbeddingProvider


class EmbeddingModelSpec(BaseModel):
    model: str
    provider: EmbeddingProvider
    description: str | None = Field(default=None)
    embedding_dim: int | None = Field(default=None)
    max_seq_length: int | None = Field(default=None)
    multilingual: bool = Field(default=False)
    parameter_count: str | None = Field(default=None)
    prompt_required: bool = Field(default=False)
    valid_prefixes: list[str] | None = Field(default=None)
    prompt_unsupported: bool = Field(default=False)
    task_map: dict[str, str] | None = Field(default=None)

    @model_validator(mode="after")
    def _prompt_flags_not_contradictory(self) -> EmbeddingModelSpec:
        if self.prompt_required and self.prompt_unsupported:
            raise ValueError("prompt_required and prompt_unsupported cannot both be True.")
        return self
