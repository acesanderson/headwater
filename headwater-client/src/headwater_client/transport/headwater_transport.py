from headwater_api.classes import (
    HeadwaterServerError,
    HeadwaterServerException,
    StatusResponse,
)
from dbclients import get_network_context
from urllib.parse import urljoin
import requests
import logging
import json

logger = logging.getLogger(__name__)

# Constants
HEADWATER_SERVER_DEFAULT_PORT = 8080
HEADWATER_SERVER_IP = get_network_context().siphon_server


class HeadwaterTransport:
    """
    Transport layer for communicating with HeadwaterServer.
    """

    def __init__(self, base_url: str = ""):
        if base_url == "":
            self.base_url: str = self._get_url()
        else:
            self.base_url = base_url.rstrip("/")
        self._session = requests.Session()

    def _get_url(self) -> str:
        """Get HeadwaterServer URL with same host detection logic as PostgreSQL"""
        return f"http://{HEADWATER_SERVER_IP}:{HEADWATER_SERVER_DEFAULT_PORT}"

    def _handle_error_response(self, response: requests.Response) -> None:
        """Parse HeadwaterServerError from response and raise appropriate exception"""
        try:
            error_data = response.json()

            # Check if it's our structured error format
            if isinstance(error_data, dict) and "error_type" in error_data:
                server_error = HeadwaterServerError.model_validate(error_data)

                logger.error(
                    f"Server error [{server_error.request_id}]: {server_error.error_type}"
                )
                logger.error(f"Message: {server_error.message}")

                if server_error.validation_errors:
                    logger.error(
                        f"Validation errors: {json.dumps(server_error.validation_errors, indent=2)}"
                    )

                if server_error.context:
                    logger.error(
                        f"Context: {json.dumps(server_error.context, indent=2)}"
                    )

                raise HeadwaterServerException(server_error)

            # Fallback for non-structured errors
            logger.error(
                f"Non-structured error response: {json.dumps(error_data, indent=2)}"
            )

        except (json.JSONDecodeError, ValueError):
            # Raw text response
            logger.error(f"Raw error response: {response.text}")

        # Still raise the original HTTP error
        response.raise_for_status()

    def _request(
        self,
        method: str,
        endpoint: str,
        json_payload: str | None = None,  # Expects an already serialized JSON string
    ) -> str:  # Returns the raw JSON string response body
        """
        Sends an optional JSON string payload, handles errors,
        and returns the raw JSON string response body.
        """
        safe_endpoint = endpoint.lstrip("/")
        full_url = urljoin(self.base_url, safe_endpoint)
        headers = {}

        # Set Content-Type header if sending data
        if json_payload is not None:
            headers["Content-Type"] = "application/json"
            # requests expects bytes for 'data', encode the string
            data_bytes = json_payload.encode("utf-8")
        else:
            data_bytes = None

        try:
            response = self._session.request(
                method=method,
                url=full_url,
                headers=headers,
                data=data_bytes,  # Use 'data' for pre-encoded bytes/strings
            )

            # Check for HTTP errors (should raise)
            if not response.ok:
                # This should raise an exception (e.g., HTTPError or custom)
                self._handle_error_response(response)

            # Return the raw response text (which should be JSON)
            return response.text

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error requesting {full_url}: {e}")
            # Raise a specific custom exception for network errors
            raise HeadwaterServerException(
                HeadwaterServerError(
                    error_type="NETWORK_ERROR", message=str(e), status_code=503
                )
            ) from e
        except HeadwaterServerException:
            # Re-raise exceptions already handled (like from _handle_error_response)
            raise

    # General server methods
    def ping(self) -> bool:
        """
        Sends a ping request to the server to check reachability.

        Returns:
            bool: True if the server responds with 'pong', False otherwise.

        This doesn't use ._request() because we want to handle timeouts and connection errors.
        """
        endpoint = "/ping"  # Or just "ping" if base_url ends with /
        full_url = urljoin(self.base_url, endpoint.lstrip("/"))

        try:
            # Use a timeout to prevent waiting indefinitely
            response = self._session.get(full_url, timeout=5)  # 5-second timeout

            # Check for non-2xx status codes (includes 4xx, 5xx)
            if not response.ok:
                logger.warning(
                    f"Ping failed: Server returned status {response.status_code}"
                )
                return False

            # Check if the response body is the expected JSON
            try:
                data = response.json()
                if isinstance(data, dict) and data.get("message") == "pong":
                    logger.info("Ping successful: Server responded with 'pong'.")
                    return True
                else:
                    logger.warning(f"Ping failed: Unexpected response content: {data}")
                    return False
            except requests.exceptions.JSONDecodeError:
                logger.warning(
                    f"Ping failed: Server response was not valid JSON: {response.text}"
                )
                return False

        except requests.exceptions.Timeout:
            logger.warning(f"Ping failed: Request timed out after 5 seconds.")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.warning(
                f"Ping failed: Could not connect to server at {self.base_url}. Error: {e}"
            )
            return False
        except (
            requests.exceptions.RequestException
        ) as e:  # Catch other potential request errors
            logger.warning(f"Ping failed: An unexpected request error occurred: {e}")
            return False

    def get_status(self) -> StatusResponse:
        """
        Get server status + configuration.
        """
        method = "GET"
        endpoints = "/status"
        json_payload = None
        response = self._session.request(
            method=method,
            url=urljoin(self.base_url, endpoints.lstrip("/")),
            headers={},
            data=None,
        )
        response.raise_for_status()
        status_response = StatusResponse(**response.json())
        return status_response
