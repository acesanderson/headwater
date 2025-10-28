from headwater_api.client.headwater_client import HeadwaterClient
from headwater_api.classes import (
    ConduitRequest,
    ConduitResponse,
    BatchRequest,
    BatchResponse,
    ConduitError,
)
from conduit.message.textmessage import TextMessage


def test_conduit_sync_client():
    message = TextMessage(role="user", content="name three birds")
    messages = [message]
    request = ConduitRequest(messages=messages, model="gpt-oss:latest")
    client = HeadwaterClient()
    response = client.conduit.query_sync(request=request)
    assert isinstance(response, ConduitResponse)
    assert len(str(response.content)) > 0
    print(str(response.content))


def test_conduit_async_service_prompt_strings():
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
    client = HeadwaterClient()
    response = client.conduit.query_async(batch_request)

    # Assert that the response is as expected
    assert isinstance(response, BatchResponse)
    assert isinstance(response.results, list)
    assert len(response.results) == 3
    assert not isinstance(response.results[0], ConduitError)
    print(response)


def test_conduit_async_service_input_variables():
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
    client = HeadwaterClient()
    response = client.conduit.query_async(batch_request)

    # Assert that the response is as expected
    assert isinstance(response, BatchResponse)
    assert isinstance(response.results, list)
    assert len(response.results) == 4
    assert not isinstance(response.results[0], ConduitError)
