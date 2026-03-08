from __future__ import annotations
from pydantic import BaseModel, Field, model_validator


class RerankDocument(BaseModel):
    text: str
    id: str | int | None = None
    metadata: dict | None = None


class RerankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    documents: list[str | RerankDocument] = Field(..., min_length=1)
    model_name: str = Field(default="flash")
    k: int | None = Field(default=5)
    normalize_scores: bool = Field(default=False)
    max_length: int = Field(default=512)

    @model_validator(mode="after")
    def normalize_documents(self) -> RerankRequest:
        self.documents = [
            d if isinstance(d, RerankDocument) else RerankDocument(text=d)
            for d in self.documents
        ]
        return self
