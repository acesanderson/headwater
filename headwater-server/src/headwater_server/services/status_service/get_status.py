from __future__ import annotations
from headwater_api.classes import StatusResponse
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conduit.domain.message.message import MessageUnion

logger = logging.getLogger(__name__)


async def get_status_service(startup_time: float) -> StatusResponse:
    try:
        logger.info("Retrieving server status...")

        from conduit.async_ import (
            ModelAsync,
            GenerationRequest,
            GenerationResponse,
            Verbosity,
            GenerationParams,
            ConduitOptions,
        )
        from conduit.domain.message.message import UserMessage
        import torch
        import time

        # Is ollama working?
        try:
            messages = [UserMessage(content="ping")]
            params = GenerationParams(model="llama3.1:latest", max_tokens=1)
            options = ConduitOptions(
                project_name="headwater", verbosity=Verbosity.SILENT
            )
            request = GenerationRequest(
                messages=messages, params=params, options=options
            )
            test_model = ModelAsync("llama3.1:latest")
            test_response = await test_model.query(request)
            if isinstance(test_response, GenerationResponse):
                ollama_working = True
            else:
                logger.warning("Ollama test response is not a GenerationResponse.")
                ollama_working = False
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
        )
    except Exception as e:
        return StatusResponse(
            status="error",
            gpu_enabled=False,
            message=f"Error retrieving status: {str(e)}",
            models_available={},
            uptime=None,
        )
