from __future__ import annotations

import asyncio

from headwater_api.classes import BatchExtractRequest
from headwater_api.classes import BatchExtractResponse
from headwater_api.classes import ExtractResult
from siphon_api.enums import ActionType
from siphon_server.core.pipeline import SiphonPipeline


async def batch_extract_siphon_service(request: BatchExtractRequest) -> BatchExtractResponse:
    pipeline = SiphonPipeline()
    semaphore = asyncio.Semaphore(request.max_concurrent)

    async def extract_one(source: str) -> ExtractResult:
        async with semaphore:
            try:
                content_data = await pipeline.process(source, action=ActionType.EXTRACT)
                text = content_data.text
                if not text:
                    return ExtractResult(source=source, text=None, error="empty extraction")
                return ExtractResult(source=source, text=text, error=None)
            except Exception as exc:
                return ExtractResult(source=source, text=None, error=str(exc))

    results = await asyncio.gather(*[extract_one(s) for s in request.sources])
    return BatchExtractResponse(results=list(results))
