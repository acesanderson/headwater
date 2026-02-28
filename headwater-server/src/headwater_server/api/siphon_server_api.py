from fastapi import FastAPI
from headwater_api.classes import EmbedBatchRequest, EmbedBatchResponse
from siphon_api.api.siphon_request import SiphonRequest
from siphon_api.api.siphon_response import SiphonResponse


class SiphonServerAPI:
    def __init__(self, app: FastAPI):
        self.app: FastAPI = app

    def register_routes(self):
        """
        Register all Siphon routes.
        """

        @self.app.post("/siphon/process", response_model=SiphonResponse)
        async def process_siphon(request: SiphonRequest):
            """
            Curate items based on the provided request
            """
            from headwater_server.services.siphon_service.process_siphon_service import (
                process_siphon_service,
            )

            return await process_siphon_service(request)

        @self.app.post("/siphon/embed-batch", response_model=EmbedBatchResponse)
        async def embed_batch(request: EmbedBatchRequest):
            """
            Batch-embed siphon records by URI.

            Fetches title+summary from DB, skips already-embedded rows (unless
            force=True), encodes in chunks of 128, and writes vectors back.
            """
            from headwater_server.services.siphon_service.embed_batch_siphon_service import (
                embed_batch_siphon_service,
            )

            return await embed_batch_siphon_service(request)
