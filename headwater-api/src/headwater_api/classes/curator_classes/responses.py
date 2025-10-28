from pydantic import BaseModel, Field


# Curator
class CuratorResult(BaseModel):
    id: str = Field(..., description="Unique identifier for the curated item")
    score: float = Field(..., description="Curation score for the item")


class CuratorResponse(BaseModel):
    results: list[CuratorResult] = Field(
        ..., description="List of curation results with IDs and scores"
    )
