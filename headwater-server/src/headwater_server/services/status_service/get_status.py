from headwater_api.classes import StatusResponse


def get_status_service(startup_time: float) -> StatusResponse:
    try:
        from conduit.sync import Model, Response, Verbosity
        import torch
        import time

        # Is ollama working?
        try:
            test_model = Model("llama3.1:latest")  # Local Ollama model
            test_response = test_model.query("ping", verbose=Verbosity.SILENT)
            if isinstance(test_response, Response):
                ollama_working = True
            else:
                raise ValueError(f"Invalid response from Ollama model: {test_response}")

        except Exception as e:
            ollama_working = False

        # Is CUDA available?
        gpu_enabled = torch.cuda.is_available() if torch else False

        # Get available models
        models_available = Model.models()["ollama"] if ollama_working else []

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
