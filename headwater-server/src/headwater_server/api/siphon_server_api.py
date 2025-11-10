from fastapi import FastAPI
from siphon_api.api.siphon_request import SiphonRequest
from siphon_api.models import ProcessedContent


class SiphonServerAPI:
    def __init__(self, app: FastAPI):
        self.app: FastAPI = app

    def register_routes(self):
        """
        Register all Siphon routes.
        """

        @self.app.post("/siphon/process", response_model=ProcessedContent)
        def process_siphon(request: SiphonRequest):
            """
            Curate items based on the provided request
            """
            from headwater_server.services.siphon_service.process_siphon_service import (
                process_siphon_service,
            )

            return process_siphon_service(request)
