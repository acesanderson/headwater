import pytest
from headwater_server.services.curator_service.curator_service import curator_service
from headwater_api.classes import CuratorRequest


@pytest.mark.asyncio
async def test_curator_service():
    curator_request = CuratorRequest(
        query_string="pivoting your career",
        k=5,
        n_results=30,
        model_name="bge",
        cached=True,
    )
    # Test the Curate function
    response = await curator_service(curator_request)
    results = response.results
    for result in results:
        print(f"{result.id}: {result.score:.4f}")
