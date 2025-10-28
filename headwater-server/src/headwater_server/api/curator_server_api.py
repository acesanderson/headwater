from fastapi import FastAPI
from headwater_api.classes import (
    CuratorRequest,
    CuratorResponse,
)


class CuratorServerAPI:
    def __init__(self, app: FastAPI):
        self.app: FastAPI = app

    def register_routes(self):
        """
        Register all conduit routes
        """

        @self.app.post("/curator/curate", response_model=CuratorResponse)
        async def curate(request: CuratorRequest):
            """Curate items based on the provided request"""
            from headwater_server.services.curator_service.curator_service import (
                curator_service,
            )

            return await curator_service(request)
