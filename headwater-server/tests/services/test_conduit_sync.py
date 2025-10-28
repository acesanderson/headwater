from headwater_api.classes import ConduitRequest, ConduitResponse
from headwater_server.services.conduit_service.conduit_sync_service import (
    conduit_sync_service,
)
from conduit.message.textmessage import TextMessage


def test_conduit_sync_service_success():
    message = TextMessage(role="user", content="name three birds")
    messages = [message]
    request = ConduitRequest(messages=messages, model="gpt-oss:latest")
    response = conduit_sync_service(request)
    assert isinstance(response, ConduitResponse)
    assert len(str(response.content)) > 0
