from __future__ import annotations

from pydantic import BaseModel, Field


class GpuInfo(BaseModel):
    index: int = Field(..., description="GPU device index")
    name: str = Field(..., description="GPU model name")
    vram_total_mb: int = Field(..., description="Total VRAM in MB")
    vram_used_mb: int = Field(..., description="Used VRAM in MB")
    vram_free_mb: int = Field(..., description="Free VRAM in MB")
    utilization_pct: int = Field(..., description="GPU compute utilization (0-100)")
    temperature_c: int | None = Field(None, description="GPU temperature in Celsius")


class OllamaLoadedModel(BaseModel):
    name: str = Field(..., description="Model name as reported by Ollama")
    size_mb: int = Field(..., description="Total loaded size in MB (VRAM + CPU RAM)")
    vram_mb: int = Field(..., description="Portion loaded into VRAM in MB")
    cpu_offload_mb: int = Field(..., description="Portion offloaded to CPU RAM in MB")
    vram_pct: int = Field(..., description="Percentage of model in VRAM (0-100)")
    cpu_pct: int = Field(..., description="Percentage of model on CPU RAM (0-100)")


class GpuResponse(BaseModel):
    server_name: str = Field(..., description="Name of the subserver reporting GPU stats")
    gpus: list[GpuInfo] = Field(default_factory=list, description="Per-device GPU stats")
    ollama_loaded_models: list[OllamaLoadedModel] = Field(
        default_factory=list, description="Models currently loaded in memory by Ollama"
    )
    error: str | None = Field(None, description="Error message if GPU stats could not be retrieved")


class RouterGpuResponse(BaseModel):
    backends: dict[str, GpuResponse] = Field(
        ..., description="GPU stats keyed by backend name"
    )
