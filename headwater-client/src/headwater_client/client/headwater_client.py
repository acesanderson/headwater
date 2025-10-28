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

from headwater_api.api.conduit_api import ConduitAPI
from headwater_api.api.curator_api import CuratorAPI
from headwater_api.api.embeddings_api import EmbeddingsAPI
from headwater_api.api.siphon_api import SiphonAPI
from headwater_api.transport.headwater_transport import HeadwaterTransport
from headwater_api.classes import StatusResponse


class HeadwaterClient:
    def __init__(self):
        self._transport = HeadwaterTransport()
        self.conduit = ConduitAPI(self._transport)
        self.curator = CuratorAPI(self._transport)
        self.embeddings = EmbeddingsAPI(self._transport)
        self.siphon = SiphonAPI(self._transport)

    def ping(self) -> bool:
        """Ping the Headwater service to check connectivity."""
        return self._transport.ping()

    def get_status(self) -> StatusResponse:
        """Get the status of the Headwater service."""
        return self._transport.get_status()
