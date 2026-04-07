from __future__ import annotations

import logging
import httpx

from headwater_api.classes import GpuInfo, GpuResponse, OllamaLoadedModel

logger = logging.getLogger(__name__)

OLLAMA_PS_URL = "http://localhost:11434/api/ps"
BYTES_PER_MB = 1024 * 1024


def _get_gpu_info() -> list[GpuInfo]:
    import pynvml

    pynvml.nvmlInit()
    device_count = pynvml.nvmlDeviceGetCount()
    gpus = []
    for i in range(device_count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
        name = pynvml.nvmlDeviceGetName(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        try:
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        except pynvml.NVMLError:
            temp = None
        gpus.append(
            GpuInfo(
                index=i,
                name=name,
                vram_total_mb=mem.total // BYTES_PER_MB,
                vram_used_mb=mem.used // BYTES_PER_MB,
                vram_free_mb=mem.free // BYTES_PER_MB,
                utilization_pct=util.gpu,
                temperature_c=temp,
            )
        )
    pynvml.nvmlShutdown()
    return gpus


async def _get_ollama_loaded_models() -> list[OllamaLoadedModel]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(OLLAMA_PS_URL)
        response.raise_for_status()
        data = response.json()

    models = []
    for m in data.get("models", []):
        size = m.get("size", 0)
        size_vram = m.get("size_vram", 0)
        cpu_offload = max(0, size - size_vram)
        if size > 0:
            vram_pct = round(size_vram / size * 100)
            cpu_pct = round(cpu_offload / size * 100)
        else:
            vram_pct = 0
            cpu_pct = 0
        models.append(
            OllamaLoadedModel(
                name=m.get("name", "unknown"),
                size_mb=size // BYTES_PER_MB,
                vram_mb=size_vram // BYTES_PER_MB,
                cpu_offload_mb=cpu_offload // BYTES_PER_MB,
                vram_pct=vram_pct,
                cpu_pct=cpu_pct,
            )
        )
    return models


async def get_gpu_service(server_name: str) -> GpuResponse:
    gpus: list[GpuInfo] = []
    ollama_models: list[OllamaLoadedModel] = []
    errors: list[str] = []

    try:
        gpus = _get_gpu_info()
    except Exception as exc:
        logger.warning(f"pynvml error: {exc}")
        errors.append(f"pynvml: {exc}")

    try:
        ollama_models = await _get_ollama_loaded_models()
    except Exception as exc:
        logger.warning(f"Ollama /api/ps error: {exc}")
        errors.append(f"ollama: {exc}")

    return GpuResponse(
        server_name=server_name,
        gpus=gpus,
        ollama_loaded_models=ollama_models,
        error="; ".join(errors) if errors else None,
    )
