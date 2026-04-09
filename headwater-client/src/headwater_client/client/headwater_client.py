"""
Main client for interacting with Headwater APIs.
Usage:
```python
from headwater_api.headwater_client import HeadwaterClient
client = HeadwaterClient()
response = client.conduit.query_sync(request)
embeddings = client.embeddings.generate_embeddings(request)
curated_courses = client.curator.curate(request)
```
"""

from __future__ import annotations

from typing import Literal

from headwater_api.classes import GpuResponse, LogsLastResponse, RouterGpuResponse, StatusResponse
from headwater_client.api.conduit_api import ConduitAPI
from headwater_client.api.curator_api import CuratorAPI
from headwater_client.api.embeddings_api import EmbeddingsAPI
from headwater_client.api.reranker_api import RerankerAPI
from headwater_client.api.siphon_sync_api import SiphonAPI
from headwater_client.transport.headwater_transport import HeadwaterTransport


class HeadwaterClient:
    def __init__(
        self, host_alias: Literal["headwater", "bywater", "backwater", "deepwater", "stillwater"] = "headwater"
    ):
        self._transport = HeadwaterTransport(host_alias=host_alias)
        self.conduit = ConduitAPI(self._transport)
        self.curator = CuratorAPI(self._transport)
        self.embeddings = EmbeddingsAPI(self._transport)
        self.reranker = RerankerAPI(self._transport)
        self.siphon = SiphonAPI(self._transport)

    def ping(self) -> bool:
        """Ping the Headwater service to check connectivity."""
        return self._transport.ping()

    def get_status(self) -> StatusResponse:
        """Get the status of the Headwater service."""
        return self._transport.get_status()

    def list_routes(self) -> list[dict]:
        """List available API routes."""
        return self._transport.list_routes()

    def get_routes(self) -> dict | list:
        """Fetch routing config (router) or FastAPI route list (subserver)."""
        return self._transport.get_routes()

    def get_logs_last(self, n: int = 50) -> LogsLastResponse:
        """Fetch the last n log entries from the Headwater service."""
        return self._transport.get_logs_last(n)

    def get_gpu(self) -> GpuResponse | RouterGpuResponse:
        """Fetch GPU stats. Router returns RouterGpuResponse; subservers return GpuResponse."""
        return self._transport.get_gpu()

    def get_metrics(self) -> str:
        """Fetch Prometheus metrics in text exposition format (GET /metrics)."""
        return self._transport.get_metrics()

    def get_sysinfo(self) -> dict:
        """Fetch CPU and RAM stats from a subserver (GET /sysinfo)."""
        return self._transport.get_sysinfo()
