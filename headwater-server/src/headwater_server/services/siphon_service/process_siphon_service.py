from siphon_api.api.siphon_request import SiphonRequest
from siphon_api.api.siphon_response import SiphonResponse
from siphon_api.models import (
    SourceInfo,
    ProcessedContent,
    PipelineClass,
)
from siphon_api.enums import SourceOrigin, ActionType
from siphon_api.api.from_siphon_request import ensure_temp_file
from siphon_server.core.pipeline import SiphonPipeline


async def process_siphon_service(request: SiphonRequest) -> SiphonResponse:
    """
    Process content through the Siphon pipeline based on source origin.

    Handle both file path and URL sources by delegating to the appropriate pipeline
    processor. Preserves original source information in the returned payload.
    """
    source_origin: SourceOrigin = request.origin
    use_cache = request.params.use_cache
    action: ActionType = request.params.action
    match source_origin:
        case SourceOrigin.FILE_PATH:
            with ensure_temp_file(request) as file_path:
                pipeline = SiphonPipeline()
                payload: PipelineClass = await pipeline.process(
                    str(file_path), action=action, use_cache=use_cache
                )
            # With temp file having served its purpose, reassign the original request path
            if isinstance(payload, SourceInfo):
                payload.original_source = request.source
            elif isinstance(payload, ProcessedContent):
                payload.source.original_source = request.source
        case SourceOrigin.URL:
            pipeline = SiphonPipeline()
            payload = await pipeline.process(
                request.source, action=action, use_cache=use_cache
            )
    # Construct response
    source_type = payload.source_type
    response = SiphonResponse(
        source_type=source_type,
        payload=payload,
    )
    return response
