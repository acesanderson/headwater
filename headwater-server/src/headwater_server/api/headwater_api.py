from headwater_api.classes import StatusResponse
from fastapi import FastAPI
import time

startup_time = time.time()


class HeadwaterServerAPI:
    def __init__(self, app: FastAPI):
        self.app: FastAPI = app

    def register_routes(self):
        """
        Register all routes for default headwater server.
        """

        @self.app.get("/ping")
        def ping():
            return {"message": "pong"}

        @self.app.get("/status", response_model=StatusResponse)
        def status():
            from headwater_server.services.status_service.get_status import (
                get_status_service,
            )

            return get_status_service(startup_time)
