from pydantic import BaseModel, Field
from conduit.result.response import Response as ConduitResponse
from conduit.result.error import ConduitError


# Async
class BatchResponse(BaseModel):
    """Response model for batch processing"""

    results: list[ConduitResponse | ConduitError] = Field(
        ..., description="List of results for each input"
    )


__all__ = [
    "BatchResponse",
    "ConduitResponse",
    "ConduitError",
]
