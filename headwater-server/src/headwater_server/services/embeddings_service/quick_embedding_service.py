from headwater_api.classes import QuickEmbeddingRequest, QuickEmbeddingResponse


def quick_embedding_service(
    request: QuickEmbeddingRequest,
) -> QuickEmbeddingResponse:
    from embedding_model import EmbeddingModel

    query = request.query
    model = request.model
    embedding_model = EmbeddingModel(model)
    embedding = embedding_model.generate_embedding(query)
    return QuickEmbeddingResponse(embedding=embedding)
