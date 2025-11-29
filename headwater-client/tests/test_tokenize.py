from headwater_client.client.headwater_client import HeadwaterClient
from headwater_api.classes import (
    BatchRequest,
    TokenizationRequest,
)

hc = HeadwaterClient()

# Test Tokenization
tok_req = TokenizationRequest(model="gpt-oss:latest", text="Hello world")
resp = hc.conduit.tokenize(tok_req)
print(f"Tokenization result: {resp}")

# # Test Async Batch Query
# batch_req = BatchRequest(
#     model="gpt-oss:latest", prompt_strings=["Say hi", "Say bye"]
# )
# print(f"Batch result: {api.query_async(batch_req)}")
