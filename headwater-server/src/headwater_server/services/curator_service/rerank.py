from rerankers import Reranker
import os


COHERE_API_KEY = os.getenv("COHERE_API_KEY")
JINA_API_KEY = os.getenv("JINA_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Reranker options
rankers = {
    "bge": {"model_name": "BAAI/bge-reranker-large", "model_type": "llm-layerwise"},
    "mxbai": {
        "model_name": "mixedbread-ai/mxbai-rerank-large-v1",
        "model_type": "cross-encoder",
    },
    "ce": {"model_name": "cross-encoder"},
    "flash": {"model_name": "flashrank"},
    "colbert": {"model_name": "colbert"},
    "llm": {"model_name": "llm-layerwise"},
    "mini": {"model_name": "ce-esci-MiniLM-L12-v2", "model_type": "flashrank"},
    "t5": {"model_name": "t5"},
    "jina": {
        "model_name": "jina-reranker-v2-base-multilingual",
        "api_key": JINA_API_KEY,
    },
    "cohere": {"model_name": "cohere", "api_key": COHERE_API_KEY, "lang": "en"},
    "rankllm": {"model_name": "rankllm", "api_key": OPENAI_API_KEY},
}


def rerank_options(
    options: list[dict], query: str, k: int = 5, model_name: str = "bge"
) -> list[tuple]:
    """
    Reranking magic.
    """
    ranker = Reranker(**rankers[model_name], verbose=False)
    if ranker is None:
        raise ValueError(
            f"Ranker {model_name} not found. Please check the model name and try again."
        )
    ranked_results: list[tuple] = []
    for option in options:
        course = option["course_title"]
        TOC = option["course_description"]
        ranked = ranker.rank(query=query, docs=[TOC])
        # Different models return different objects (RankedResults or Result)
        try:  # See if it's a RankedResults object
            score = ranked.results[0].score
        except:  # If not, it's a Result object
            score = ranked.score
        ranked_results.append((course, score))
    # sort ranked_results by highest score
    ranked_results.sort(key=lambda x: x[1], reverse=True)
    # Return the five best.
    return ranked_results[:k]


async def rerank_options_async(
    options: list[dict], query: str, k: int = 5, model_name: str = "bge"
) -> list[tuple]:
    """
    Reranking magic.
    """
    ranker = Reranker(**rankers[model_name], verbose=False)
    if ranker is None:
        raise ValueError(
            f"Ranker {model_name} not found. Please check the model name and try again."
        )
    ranked_results: list[tuple] = []
    for option in options:
        course = option["course_title"]
        TOC = option["course_description"]
        ranked = await ranker.rank_async(query=query, docs=[TOC])
        # Different models return different objects (RankedResults or Result)
        try:  # See if it's a RankedResults object
            score = ranked.results[0].score
        except:  # If not, it's a Result object
            score = ranked.score
        ranked_results.append((course, score))
    # sort ranked_results by highest score
    ranked_results.sort(key=lambda x: x[1], reverse=True)
    # Return the five best.
    return ranked_results[:k]
