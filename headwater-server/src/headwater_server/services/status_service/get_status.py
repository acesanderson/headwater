from __future__ import annotations
from headwater_api.classes import StatusResponse
import logging

logger = logging.getLogger(__name__)


async def get_status_service(
    startup_time: float,
    server_name: str = "Headwater API Server",
) -> StatusResponse:
    try:
        logger.info("Retrieving server status...")

        import torch
        import time

        # Is ollama working?
        try:
            import httpx
            resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
            ollama_working = resp.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama test failed: {str(e)}")
            ollama_working = False

        # Is CUDA available?
        gpu_enabled = torch.cuda.is_available() if torch else False

        # Get available models
        from conduit.core.model.models.modelstore import ModelStore

        models_available = ModelStore.local_models()

        # What's the status?
        status = "healthy" if ollama_working and gpu_enabled else "degraded"

        # Uptime
        # In your status endpoint, replace the uptime line:
        uptime = time.time() - startup_time

        return StatusResponse(
            status=status,
            gpu_enabled=gpu_enabled,
            message="Server is running",
            models_available=models_available,
            uptime=uptime,
            server_name=server_name,
        )
    except Exception as e:
        return StatusResponse(
            status="error",
            gpu_enabled=False,
            message=f"Error retrieving status: {str(e)}",
            models_available={},
            uptime=None,
            server_name=server_name,
        )
