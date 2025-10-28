from headwater_api.client.headwater_client import HeadwaterClient
from headwater_api.classes import CuratorRequest, CuratorResponse


def test_curator():
    curator_request = CuratorRequest(
        query_string="sexual harassment in the workplace",
    )
    cc = HeadwaterClient()
    curator_response: CuratorResponse = cc.curator.curate(curator_request)
    assert curator_response is not None
    assert isinstance(curator_response, CuratorResponse)
    print(curator_response)
