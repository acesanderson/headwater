# curator-project

## Project Purpose

curator-project is a semantic search and reranking system for course content. It queries a vector database to retrieve course descriptions matching a user query, then applies configurable reranking models to improve result relevance. The system includes caching functionality to optimize repeated queries and supports both synchronous and asynchronous operation modes.

## Architecture Overview

- **curate.py**: Main entry point providing query orchestration. Handles vector database retrieval, reranking pipeline coordination, cache management, and CLI interface.
- **rerank.py**: Reranking layer supporting multiple model backends (BGE, MixedBread, Cohere, Jina, FlashRank, ColBERT, T5, RankLLM). Wraps the `rerankers` library and normalizes output across different model types.
- **cache module**: SQLite-based query cache (referenced but not provided in codebase). Stores query-response pairs to reduce redundant computation.

## Dependencies

Major dependencies inferred from imports:

- **rerankers**: Core reranking functionality
- **rich**: Console output formatting and status indicators
- **kramer**: Local/internal dependency providing vector database access via `Chroma_curate` module

External API requirements (via environment variables):
- Cohere API (COHERE_API_KEY)
- Jina API (JINA_API_KEY)
- OpenAI API (OPENAI_API_KEY)

## API Documentation

### `Curate(query_string, k=5, n_results=30, model_name="bge", cached=True)`

Synchronous query interface for course recommendations.

**Parameters:**
- `query_string` (str): Search query
- `k` (int): Number of final results to return
- `n_results` (int): Size of initial retrieval pool before reranking
- `model_name` (str): Reranking model identifier (see `rankers` dict for options)
- `cached` (bool): Enable cache lookup and storage

**Returns:** List of tuples `[(course_title: str, confidence_score: float), ...]`

### `CurateAsync(query_string, k=5, n_results=30, model_name="bge", cached=True)`

Asynchronous version of `Curate`.

**Parameters:** Identical to `Curate`

**Returns:** List of tuples `[(course_title: str, confidence_score: float), ...]`

### `rerank_options(options, query, k=5, model_name="bge")`

Reranks a list of course options against a query.

**Parameters:**
- `options` (list[dict]): Course objects containing `course_title` and `course_description` keys
- `query` (str): Query string for relevance scoring
- `k` (int): Number of top results to return
- `model_name` (str): Reranking model key from `rankers` dict

**Returns:** List of tuples `[(course_title: str, score: float), ...]` sorted by descending score

### `rerank_options_async(options, query, k=5, model_name="bge")`

Asynchronous version of `rerank_options`.

**Parameters:** Identical to `rerank_options`

**Returns:** List of tuples `[(course_title: str, score: float), ...]`

### Available Reranking Models

Model names for `model_name` parameter:
- `bge`: BAAI/bge-reranker-large
- `mxbai`: MixedBread mxbai-rerank-large-v1
- `cohere`: Cohere API reranker
- `jina`: Jina reranker v2 (multilingual)
- `flash`, `mini`, `colbert`, `t5`, `rankllm`, `ce`, `llm`: Additional model variants

## Usage Examples

### Basic synchronous query

```python
from curator.curate import Curate

results = Curate(
    query_string="machine learning fundamentals",
    k=5,
    model_name="bge"
)

for course_title, confidence in results:
    print(f"{course_title}: {confidence:.3f}")
```

### Asynchronous query with custom parameters

```python
import asyncio
from curator.curate import CurateAsync

async def search_courses():
    results = await CurateAsync(
        query_string="advanced neural networks",
        k=10,
        n_results=50,
        model_name="cohere",
        cached=False
    )
    return results

results = asyncio.run(search_courses())
```

### CLI usage

```bash
# Basic query
python -m curator.curate "introduction to python"

# Customized retrieval parameters
python -m curator.curate "data science" -k 10 -n 100

# Display application status
python -m curator.curate --status
```