from pydantic import BaseModel, Field


# Status
class StatusResponse(BaseModel):
    """
    Server status response
    """

    status: str = Field(
        ..., description="Server status: 'healthy', 'degraded', 'error'"
    )
    message: str = Field(..., description="Status message")
    models_available: list[str] = Field(..., description="Available models by provider")
    gpu_enabled: bool = Field(..., description="Whether GPU acceleration is available")
    uptime: float | None = Field(None, description="Server uptime in seconds")


class PingResponse(BaseModel):
    """
    Ping response indicating server reachability.
    """

    message: str = Field(..., description="Ping response message")
