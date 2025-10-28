"""
Client for interacting with the Siphon service.
"""

from headwater_api.api.base_api import BaseAPI
from headwater_api.classes import (
    SyntheticData,
    SyntheticDataRequest,
)


class SiphonAPI(BaseAPI):
    def generate_synthetic_data(self, request: SyntheticDataRequest) -> SyntheticData:
        """Send a synchronous query to the server"""
        method = "POST"
        endpoint = "/siphon/synthetic_data"
        json_payload = request.model_dump_json()
        response = self._request(method, endpoint, json_payload=json_payload)
        return SyntheticData.model_validate_json(response)
