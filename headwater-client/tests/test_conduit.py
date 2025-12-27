from headwater_client.client.headwater_client import HeadwaterClient
from conduit.examples.sample_objects import (
    sample_request,
    sample_params,
    sample_options,
)
from conduit.batch import ConduitBatch


hc = HeadwaterClient()

conduit = hc.conduit


response = conduit.query_generate(sample_request)
