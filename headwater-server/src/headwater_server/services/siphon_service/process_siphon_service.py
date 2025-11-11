from siphon_api.api.siphon_request import SiphonRequest
from siphon_api.models import ProcessedContent
from siphon_api.enums import SourceOrigin
from siphon_api.api.from_siphon_request import ensure_temp_file
from siphon_server.core.pipeline import SiphonPipeline


def process_siphon_service(request: SiphonRequest) -> ProcessedContent:
    source_origin: SourceOrigin = request.origin
    match source_origin:
        case SourceOrigin.FILE_PATH:
            with ensure_temp_file(request) as file_path:
                pipeline = SiphonPipeline()
                processed_content = pipeline.process(str(file_path))
            # With temp file having served its purpose, reassign the original request path
            processed_content.source.original_source = request.source
            return processed_content
        case SourceOrigin.URL:
            pipeline = SiphonPipeline()
            processed_content = pipeline.process(request.source)
            return processed_content
