from headwater_client.client.headwater_client import HeadwaterClient
from headwater_api.classes import (
    QuickEmbeddingRequest,
    GetCollectionRequest,
    QueryCollectionRequest,
)

hc = HeadwaterClient()
e = hc.embeddings


# list_embedding_models
print(hc.embeddings.list_embedding_models())

# quick_embedding
request = QuickEmbeddingRequest(
    query="The quick brown fox jumps over the lazy dog.",
)
print(hc.embeddings.quick_embedding(request))

# list_collections
print(hc.embeddings.list_collections())

# get_collection
collection_name = "arxiv_abstracts"
request = GetCollectionRequest(
    collection_name=collection_name,
)
print(hc.embeddings.get_collection(request))

# query_collection
request = QueryCollectionRequest(
    name="arxiv_abstracts",
    query="Graph neural networks for natural language processing",
    query_embeddings=None,
    k=5,
    n_results=10,
)
print(hc.embeddings.query_collection(request))

# create_collection

# delete_collection
