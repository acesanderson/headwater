from headwater_api.transport.headwater_transport import HeadwaterTransport
from headwater_api.classes import StatusResponse


def test_headwater_transport_initialization():
    transport = HeadwaterTransport()
    assert transport is not None
    assert isinstance(transport, HeadwaterTransport)


def test_ping():
    transport = HeadwaterTransport()
    response = transport.ping()
    assert response is True


def test_get_status():
    transport = HeadwaterTransport()
    status = transport.get_status()
    assert isinstance(status, StatusResponse)
    print(StatusResponse)
