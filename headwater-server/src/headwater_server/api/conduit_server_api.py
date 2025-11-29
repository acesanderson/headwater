from fastapi import FastAPI
from headwater_api.classes import (
    ConduitRequest,
    ConduitResponse,
    ConduitError,
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

        @self.app.post("/conduit/sync", response_model=ConduitResponse | ConduitError)
        def conduit_sync(request: ConduitRequest):
            from headwater_server.services.conduit_service.conduit_sync_service import (
                conduit_sync_service,
            )

            return conduit_sync_service(request)

        @self.app.post("/conduit/async", response_model=BatchResponse)
        async def conduit_async(batch: BatchRequest) -> BatchResponse:
            from headwater_server.services.conduit_service.conduit_async_service import (
                conduit_async_service,
            )

            return await conduit_async_service(batch)

        @self.app.post("/conduit/tokenize", response_model=TokenizationResponse)
        async def conduit_tokenize(
            request: TokenizationRequest,
        ) -> TokenizationResponse:
            from headwater_server.services.conduit_service.conduit_tokenize_service import (
                conduit_tokenize_service,
            )

            return conduit_tokenize_service(request)
