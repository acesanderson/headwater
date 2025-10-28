"""
Base class for all API classes.
Handles the transport dependency injection.
"""

from headwater_client.transport.headwater_transport import HeadwaterTransport


class BaseAPI:
    def __init__(self, transport: HeadwaterTransport):
        self._transport = transport

    def _request(self, method: str, endpoint: str, json_payload: str) -> str:
        """
        Internal method to send requests via the transport layer.
        Flattens the interface for subclasses while still allowing for composition.
        """
        return self._transport._request(method, endpoint, json_payload=json_payload)
