from fastapi import FastAPI
from headwater_api.classes import (
    GenerationRequest,
    GenerationResponse,
    BatchRequest,
    BatchResponse,
    TokenizationRequest,
    TokenizationResponse,
)


class ConduitServerAPI:
    def __init__(self, app: FastAPI):
        self.app: FastAPI = app

    def register_routes(self):
        """
        Register all conduit routes
        """

        @self.app.post("/conduit/generate", response_model=GenerationResponse)
        async def conduit_generate(request: GenerationRequest) -> GenerationResponse:
            from headwater_server.services.conduit_service.conduit_generate_service import (
                conduit_generate_service,
            )

            return await conduit_generate_service(request)

        @self.app.post("/conduit/batch", response_model=BatchResponse)
        async def conduit_batch(batch: BatchRequest) -> BatchResponse:
            from headwater_server.services.conduit_service.conduit_batch_service import (
                conduit_batch_service,
            )

            return await conduit_batch_service(batch)

        @self.app.post("/conduit/tokenize", response_model=TokenizationResponse)
        async def conduit_tokenize(
            request: TokenizationRequest,
        ) -> TokenizationResponse:
            from headwater_server.services.conduit_service.conduit_tokenize_service import (
                conduit_tokenize_service,
            )

            return conduit_tokenize_service(request)
