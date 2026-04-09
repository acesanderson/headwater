from __future__ import annotations

from headwater_api.classes import StatusResponse, LogsLastResponse, GpuResponse
from fastapi import FastAPI, Query
import time

startup_time = time.time()


class HeadwaterServerAPI:
    def __init__(self, app: FastAPI, server_name: str = "Headwater API Server"):
        self.app: FastAPI = app
        self._server_name = server_name

    def register_routes(self):
        """
        Register all routes for default headwater server.
        """
        server_name = self._server_name  # capture for closure

        @self.app.get("/ping")
        def ping():
            return {"message": "pong"}

        @self.app.get("/status", response_model=StatusResponse)
        async def status():
            from headwater_server.services.status_service.get_status import (
                get_status_service,
            )

            return await get_status_service(startup_time, server_name=server_name)

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

        @self.app.get("/logs/last", response_model=LogsLastResponse)
        def logs_last(n: int = Query(default=50, ge=1)):
            from headwater_server.server.logging_config import ring_buffer
            return ring_buffer.get_response(n)

        @self.app.get("/sysinfo")
        async def sysinfo():
            from headwater_server.services.status_service.sysinfo_service import get_sysinfo_service
            return await get_sysinfo_service()

        @self.app.get("/gpu", response_model=GpuResponse)
        async def gpu():
            from headwater_server.services.gpu_service.get_gpu import get_gpu_service
            return await get_gpu_service(server_name)
