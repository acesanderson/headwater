from headwater_server.services.curator_service.curate import CurateAsync
from headwater_api.classes import CuratorRequest
from headwater_api.classes import CuratorResponse, CuratorResult


async def curator_service(request: CuratorRequest) -> CuratorResponse:
    """
    Process a CuratorRequest and return the curation results.
    """
    results = await CurateAsync(**request.model_dump())
    result_objs = []
    for res in results:
        result_objs.append(CuratorResult(id=res[0], score=res[1]))
    response = CuratorResponse(results=result_objs)
    return response
