import pytest
from headwater_api.classes import EmbeddingsRequest, ChromaBatch
from headwater_server.services.embeddings_service.generate_embeddings_service import (
    generate_embeddings_service,
)


@pytest.mark.asyncio
async def test_embeddings_server():
    model = "sentence-transformers/all-mpnet-base-v2"
    batch = ChromaBatch(
        ids=["1", "2"],
        documents=["This is a test document.", "This is another test document."],
        metadatas=[{}, {}],
    )
    request = EmbeddingsRequest(model=model, batch=batch)
    embedded_batch = await generate_embeddings_service(request)
    print(embedded_batch.model_dump_json(indent=2))
