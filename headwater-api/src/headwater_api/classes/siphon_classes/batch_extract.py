from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator


class BatchExtractRequest(BaseModel):
    sources: list[str]
    max_concurrent: int = Field(default=10, ge=1)


class ExtractResult(BaseModel):
    source: str
    text: str | None
    error: str | None

    @model_validator(mode='after')
    def check_exclusive_state(self) -> ExtractResult:
        if self.text is None and self.error is None:
            raise ValueError("ExtractResult must have either text or error set, not neither")
        if self.text is not None and self.error is not None:
            raise ValueError("ExtractResult cannot have both text and error set")
        return self


class BatchExtractResponse(BaseModel):
    results: list[ExtractResult]
