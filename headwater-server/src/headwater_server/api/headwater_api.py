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

        @self.app.get("/routes")
        def list_routes():
            """
            Return all active endpoints with their HTTP methods.
            """
            route_info: list[dict[str, list[str] | str]] = []
            for route in self.app.routes:
                if hasattr(route, "methods"):
                    route_info.append(
                        {
                            "path": route.path,
                            "methods": list(route.methods),
                            "name": route.name,
                        }
                    )
            return route_info
