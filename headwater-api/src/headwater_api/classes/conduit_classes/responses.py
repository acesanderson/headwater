from pydantic import BaseModel, Field
from conduit.domain.result.response import GenerationResponse
from conduit.domain.conversation.conversation import Conversation


# Async
class BatchResponse(BaseModel):
    """Response model for batch processing"""

    results: list[Conversation] = Field(
        ..., description="List of results for each input"
    )


class TokenizationResponse(BaseModel):
    """Response model for tokenization requests"""

    model: str = Field(..., description="The model used for tokenization")
    input_text: str = Field(..., description="The original input text")
    token_count: int = Field(..., description="The number of tokens in the input text")


__all__ = [
    "BatchResponse",
    "GenerationResponse",
    "TokenizationResponse",
]
