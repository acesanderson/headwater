from fastapi import FastAPI, Query
from headwater_api.classes import (
    GenerationRequest,
    GenerationResponse,
    BatchRequest,
    BatchResponse,
    TokenizationRequest,
    TokenizationResponse,
    OpenAIChatRequest,
    AnthropicRequest,
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

            return await conduit_tokenize_service(request)

        @self.app.get("/conduit/models")
        async def conduit_models(provider: str | None = Query(default=None)) -> dict:
            from headwater_server.services.conduit_service.conduit_models_service import (
                conduit_models_service,
            )
            return await conduit_models_service(provider)

        @self.app.get("/v1/models")
        async def conduit_list_models() -> dict:
            from headwater_server.services.conduit_service.conduit_list_models_service import (
                conduit_list_models_service,
            )
            return await conduit_list_models_service()

        @self.app.post("/v1/chat/completions")
        async def conduit_openai_chat(request: OpenAIChatRequest) -> dict:
            from headwater_server.services.conduit_service.conduit_openai_service import (
                conduit_openai_service,
            )
            return await conduit_openai_service(request)

        @self.app.post("/v1/messages")
        async def conduit_anthropic_messages(request: AnthropicRequest):
            if request.stream:
                from headwater_server.services.conduit_service.conduit_anthropic_stream_service import (
                    conduit_anthropic_stream_service,
                )
                return await conduit_anthropic_stream_service(request)
            from headwater_server.services.conduit_service.conduit_anthropic_service import (
                conduit_anthropic_service,
            )
            return await conduit_anthropic_service(request)
