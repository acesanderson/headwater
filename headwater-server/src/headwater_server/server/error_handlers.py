from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from headwater_api.classes import HeadwaterServerError, ErrorType
import json
import logging

logger = logging.getLogger(__name__)


class ErrorHandlers:
    def __init__(self, app: FastAPI):
        self.app: FastAPI = app

    def register_error_handlers(self):
        """Register all conduit routes"""

        @self.app.exception_handler(422)
        async def validation_error_handler(
            request: Request, exc: HTTPException
        ) -> JSONResponse:
            """Enhanced 422 handler using HeadwaterServerError"""

            # Log request details for debugging
            try:
                body = await request.body()
                if body:
                    try:
                        json_body = json.loads(body)
                        logger.error(f"Request body: {json.dumps(json_body, indent=2)}")
                    except:
                        logger.error(f"Request body (raw): {body[:500]}...")
            except Exception as e:
                logger.error(f"Could not read request body: {e}")

            # Create structured error response
            error = HeadwaterServerError(
                error_type=ErrorType.VALIDATION_ERROR,
                message="Request validation failed",
                status_code=422,
                path=str(request.url.path),
                method=request.method,
                request_id=getattr(request.state, "request_id", None),
                original_exception=str(getattr(exc, "detail", "No details available")),
            ).add_context("headers", dict(request.headers))

            logger.error(f"Validation error: {error.model_dump_json()}")

            return JSONResponse(status_code=422, content=error.model_dump())

        @self.app.exception_handler(RequestValidationError)
        async def pydantic_validation_error_handler(
            request: Request, exc: RequestValidationError
        ):
            """Handle Pydantic validation errors with HeadwaterServerError"""

            error = HeadwaterServerError.from_validation_error(
                exc, request, include_traceback=False
            ).add_context("error_count", len(exc.errors()))

            logger.error(f"Pydantic validation error: {error.model_dump_json()}")

            return JSONResponse(status_code=422, content=error.model_dump())

        @self.app.exception_handler(ValidationError)
        async def general_validation_error_handler(
            request: Request, exc: ValidationError
        ):
            """Handle general Pydantic ValidationErrors"""

            error = HeadwaterServerError.from_validation_error(
                exc, request, include_traceback=True
            )
            error.error_type = ErrorType.DATA_VALIDATION

            logger.error(f"General validation error: {error.model_dump_json()}")

            return JSONResponse(status_code=422, content=error.model_dump())

        @self.app.exception_handler(Exception)
        async def general_exception_handler(request: Request, exc: Exception):
            """Catch-all exception handler"""

            error = HeadwaterServerError.from_general_exception(
                exc, request, status_code=500, include_traceback=True
            )

            logger.error(f"Unhandled exception: {error.model_dump_json()}")

            return JSONResponse(status_code=500, content=error.model_dump())
