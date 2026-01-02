from fastapi import FastAPI
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
