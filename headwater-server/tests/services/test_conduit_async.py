import pytest
from headwater_api.classes import (
    BatchRequest,
    BatchResponse,
    ConduitResponse,
    ConduitError,
)
from headwater_server.services.conduit_service.conduit_async_service import (
    conduit_async_service,
)


@pytest.mark.asyncio
async def test_conduit_async_service_prompt_strings():
    # Create a sample BatchRequest
    batch_request = BatchRequest(
        model="gpt-oss:latest",
        prompt_strings=[
            "What is the capital of France?",
            "Explain the theory of relativity.",
            "Describe the process of photosynthesis.",
        ],
    )

    # Call the conduit_async_service with the batch request
    response = await conduit_async_service(batch_request)

    # Assert that the response is as expected
    assert isinstance(response, BatchResponse)
    assert isinstance(response.results, list)
    assert len(response.results) == 3
    assert not isinstance(response.results[0], ConduitError)


@pytest.mark.asyncio
async def test_conduit_async_service_input_variables():
    # Create a sample BatchRequest with input variables
    batch_request = BatchRequest(
        model="gpt-oss:latest",
        input_variables_list=[
            {"things": "countries"},
            {"things": "scientific theories"},
            {"things": "biological processes"},
            {"things": "programming languages"},
        ],
        prompt_str="Name 3 {things}.",
    )

    # Call the conduit_async_service with the batch request
    response = await conduit_async_service(batch_request)

    # Assert that the response is as expected
    assert isinstance(response, BatchResponse)
    assert isinstance(response.results, list)
    assert len(response.results) == 4
    assert not isinstance(response.results[0], ConduitError)
