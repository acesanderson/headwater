from __future__ import annotations

from headwater_api.classes import (
    GpuResponse,
    HeadwaterServerError,
    HeadwaterServerException,
    RouterGpuResponse,
    StatusResponse,
)
from dbclients.discovery.host import get_network_context
from urllib.parse import urljoin
from typing import TYPE_CHECKING, Literal
import httpx
import logging
import json

logger = logging.getLogger(__name__)

# Constants
HEADWATER_SERVER_DEFAULT_PORT = 8080
HEADWATER_ROUTER_PORT = 8081


class HeadwaterAsyncTransport:
    """
    Async transport layer for communicating with HeadwaterServer.
    """

    def __init__(
        self,
        base_url: str = "",
        host_alias: Literal["headwater", "bywater", "backwater", "deepwater", "stillwater"] = "headwater",
    ):
        self._host_alias = host_alias
        if base_url == "":
            self.base_url: str = self._get_url()
        else:
            self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def _get_url(self) -> str:
        """Get HeadwaterServer URL with same host detection logic as PostgreSQL"""
        ctx = get_network_context()
        match self._host_alias:
            case "headwater":
                ip = ctx.headwater_server
                port = HEADWATER_ROUTER_PORT
            case "bywater":
                ip = ctx.bywater_server
                port = HEADWATER_SERVER_DEFAULT_PORT
            case "backwater":
                ip = ctx.backwater_server
                port = HEADWATER_SERVER_DEFAULT_PORT
            case "deepwater":
                ip = ctx.deepwater_server
                port = HEADWATER_SERVER_DEFAULT_PORT
            case "stillwater":
                ip = ctx.stillwater_server
                port = HEADWATER_SERVER_DEFAULT_PORT
            case _:
                raise ValueError(
                    f"Invalid host_alias '{self._host_alias}'. Must be one of: "
                    "'headwater', 'bywater', 'backwater', 'deepwater', 'stillwater'."
                )
        url = f"http://{ip}:{port}"
        logger.debug(f"[{self._host_alias}] resolved to {ip}:{port}")
        return url

    async def __aenter__(self):
        """Async context manager entry with proper timeout configuration"""
        # Set timeout to None to allow long-running inference tasks to complete
        timeout = httpx.Timeout(None, connect=10.0)
        self._client = httpx.AsyncClient(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._client:
            await self._client.aclose()

    async def _ensure_client(self):
        """Ensure client is initialized if not using context manager"""
        if self._client is None:
            timeout = httpx.Timeout(None, connect=10.0)
            self._client = httpx.AsyncClient(timeout=timeout)

    def _handle_error_response(self, response: httpx.Response) -> None:
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

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_payload: str | None = None,  # Expects an already serialized JSON string
    ) -> str:  # Returns the raw JSON string response body
        """
        Sends an optional JSON string payload, handles errors,
        and returns the raw JSON string response body.
        """
        await self._ensure_client()

        safe_endpoint = endpoint.lstrip("/")
        full_url = urljoin(self.base_url, safe_endpoint)
        headers = {}

        # Set Content-Type header if sending data
        if json_payload is not None:
            headers["Content-Type"] = "application/json"
            # httpx expects bytes for 'content', encode the string
            data_bytes = json_payload.encode("utf-8")
        else:
            data_bytes = None

        try:
            response = await self._client.request(
                method=method,
                url=full_url,
                headers=headers,
                content=data_bytes,  # Use 'content' for pre-encoded bytes/strings
            )

            # Check for HTTP errors (should raise)
            if not response.is_success:
                # This should raise an exception (e.g., HTTPError or custom)
                self._handle_error_response(response)

            # Warn if the router fell back to a secondary backend
            if routed_via := response.headers.get("X-Headwater-Routed-Via"):
                primary = response.headers.get("X-Headwater-Primary-Backend", "primary")
                logger.warning(f"Request routed via fallback backend '{routed_via}' ('{primary}' was unavailable)")

            # Return the raw response text (which should be JSON)
            return response.text

        except httpx.RequestError as e:
            logger.error(f"Network error requesting {full_url}: {e}")
            # Raise a specific custom exception for network errors
            raise HeadwaterServerException(
                HeadwaterServerError(
                    error_type="network_error", message=str(e), status_code=503
                )
            )
        except HeadwaterServerException:
            # Re-raise exceptions already handled (like from _handle_error_response)
            raise

    # General server methods
    async def ping(self) -> bool:
        """
        Sends a ping request to the server to check reachability.

        Returns:
            bool: True if the server responds with 'pong', False otherwise.

        This doesn't use ._request() because we want to handle timeouts and connection errors.
        """
        await self._ensure_client()

        endpoint = "/ping"  # Or just "ping" if base_url ends with /
        full_url = urljoin(self.base_url, endpoint.lstrip("/"))

        try:
            # Use a timeout to prevent waiting indefinitely
            response = await self._client.get(full_url, timeout=5.0)  # 5-second timeout

            # Check for non-2xx status codes (includes 4xx, 5xx)
            if not response.is_success:
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
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    f"Ping failed: Server response was not valid JSON: {response.text}"
                )
                return False

        except httpx.TimeoutException:
            logger.warning(f"Ping failed: Request timed out after 5 seconds.")
            return False
        except httpx.ConnectError as e:
            logger.warning(
                f"Ping failed: Could not connect to server at {self.base_url}. Error: {e}"
            )
            return False
        except httpx.RequestError as e:  # Catch other potential request errors
            logger.warning(f"Ping failed: An unexpected request error occurred: {e}")
            return False

    async def get_status(self) -> StatusResponse:
        """
        Get server status + configuration.
        """
        await self._ensure_client()

        method = "GET"
        endpoint = "/status"
        response = await self._client.request(
            method=method,
            url=urljoin(self.base_url, endpoint.lstrip("/")),
            headers={},
        )
        response.raise_for_status()
        status_response = StatusResponse(**response.json())
        return status_response

    async def get_logs_last(self, n: int = 50):
        """Fetch the last n log entries from the server."""
        from headwater_api.classes import LogsLastResponse
        response = await self._request("GET", f"/logs/last?n={n}")
        return LogsLastResponse.model_validate_json(response)

    async def get_routes(self) -> dict | list:
        """Fetch routing config (router) or FastAPI route list (subserver). (GET /routes/)"""
        await self._ensure_client()
        response = await self._client.request(
            method="GET",
            url=urljoin(self.base_url, "routes/"),
            headers={},
        )
        response.raise_for_status()
        return response.json()

    async def list_routes(self) -> dict:
        """
        List all available routes on the server. (GET /routes)
        """
        await self._ensure_client()

        method = "GET"
        endpoint = "/routes"
        response = await self._client.request(
            method=method,
            url=urljoin(self.base_url, endpoint.lstrip("/")),
            headers={},
        )
        response.raise_for_status()
        return response.json()

    async def get_gpu(self) -> GpuResponse | RouterGpuResponse:
        """Fetch GPU stats. Returns RouterGpuResponse from the router, GpuResponse from subservers."""
        response = await self._request("GET", "/gpu")
        if self._host_alias == "headwater":
            return RouterGpuResponse.model_validate_json(response)
        return GpuResponse.model_validate_json(response)

    async def get_metrics(self) -> str:
        """Fetch Prometheus metrics in text exposition format (GET /metrics)."""
        return await self._request("GET", "/metrics")

    async def get_sysinfo(self) -> dict:
        """Fetch CPU and RAM stats from a subserver (GET /sysinfo)."""
        import json
        return json.loads(await self._request("GET", "/sysinfo"))
