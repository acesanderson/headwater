from headwater_api.client.headwater_client import HeadwaterClient
from headwater_api.classes import EmbeddingsRequest, ChromaBatch


def test_embeddings():
    model = "sentence-transformers/all-mpnet-base-v2"
    batch = ChromaBatch(
        ids=["1", "2"],
        documents=["This is a test document.", "This is another test document."],
        metadatas=[{}, {}],
    )
    request = EmbeddingsRequest(model=model, batch=batch)
    ec = HeadwaterClient()
    response = ec.embeddings.generate_embeddings(request)
    print(response.model_dump_json(indent=2))
