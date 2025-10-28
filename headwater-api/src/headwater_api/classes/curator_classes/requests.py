from pydantic import BaseModel, Field


class CuratorRequest(BaseModel):
    # Mandatory fields
    query_string: str = Field(..., description="The query string for retrieval.")
    # Optional fields with defaults
    k: int = Field(default=5, description="Number of top documents to retrieve.")
    n_results: int = Field(
        default=30, description="Total number of results to consider."
    )
    model_name: str = Field(
        default="bge", description="The embedding model to use for retrieval."
    )
    cached: bool = Field(default=True, description="Whether to use cached results.")
