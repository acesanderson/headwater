from headwater_api.classes.embeddings_classes.embedding_provider import EmbeddingProvider


def test_provider_values():
    assert EmbeddingProvider.HUGGINGFACE == "huggingface"
    assert EmbeddingProvider.OPENAI == "openai"
    assert EmbeddingProvider.COHERE == "cohere"
    assert EmbeddingProvider.JINA == "jina"


def test_provider_from_string():
    assert EmbeddingProvider("huggingface") == EmbeddingProvider.HUGGINGFACE
