# Headwater

Headwater is a unified platform for content ingestion, embedding generation, and LLM orchestration. It provides a centralized server and Python client for processing documents, managing vector collections, and executing model-agnostic inference.

## Quick Start

### 1. Install and Start the Server
The server requires Python 3.12+ and manages the heavy lifting for embeddings and LLM orchestration.

```bash
pip install headwater_server
headwater
```

### 2. Use the Client
The client provides a high-level interface to all Headwater services.

```python
from headwater_client.client.headwater_client import HeadwaterClient
from headwater_api.classes import QuickEmbeddingRequest

client = HeadwaterClient()

# Check connectivity
if client.ping():
    # Generate an embedding
    req = QuickEmbeddingRequest(query="Sample text for vectorization")
    response = client.embeddings.quick_embedding(req)
    print(response.embedding)
```

## Core Value Demonstration: Semantic Search & Reranking

Headwater simplifies the path from raw query to curated results by combining vector retrieval with advanced reranking models.

```python
from headwater_client.client.headwater_client import HeadwaterClient
from headwater_api.classes import CuratorRequest

client = HeadwaterClient()

# Search across a collection with BGE-based reranking
request = CuratorRequest(
    query_string="Graph neural networks in NLP",
    k=5,
    model_name="flash",
    cached=True
)

response = client.curator.curate(request)

for result in response.results:
    print(f"ID: {result.id} | Score: {result.score:.4f}")
```

## Architecture Overview

Headwater is structured into three primary packages:

1.  **Headwater Server**: A FastAPI application that serves as the execution engine. It interfaces with local LLMs, vector databases (Chroma), and embedding models (SentenceTransformers).
2.  **Headwater Client**: A Python SDK providing both synchronous (`HeadwaterClient`) and asynchronous (`HeadwaterAsyncClient`) transports.
3.  **Headwater API**: A shared library of Pydantic models ensuring type safety and schema consistency between the server and clients.

### Key Service Modules

| Module | Purpose | Key Technologies |
| :--- | :--- | :--- |
| **Conduit** | LLM orchestration and batching | Ollama, OpenAI-compat |
| **Embeddings** | Vector generation and collection management | SentenceTransformers, Chroma |
| **Curator** | High-precision retrieval and reranking | Flashrank, Cross-Encoders |
| **Siphon** | Content ingestion and pipeline processing | Local files, URLs |
| **Reranker** | Standalone document scoring | Flashrank, BGE |

## Installation & Setup

### Prerequisites
- Python 3.12 or higher
- CUDA-capable GPU (recommended for embedding generation)
- Running Ollama instance (optional, for Conduit LLM features)

### Client Installation
```bash
pip install headwater_client
```

### Server Configuration
The server respects the following environment variables:
- `PYTHON_LOG_LEVEL`: 1 (WARNING), 2 (INFO), 3 (DEBUG)
- `COHERE_API_KEY`: Required if using Cohere reranking models
- `JINA_API_KEY`: Required if using Jina reranking models

## Basic Usage

### Asynchronous Client
For high-concurrency applications, use the `HeadwaterAsyncClient` as a context manager.

```python
import asyncio
from headwater_client.client.headwater_client_async import HeadwaterAsyncClient
from headwater_api.classes import GenerationRequest

async def main():
    async with HeadwaterAsyncClient() as client:
        status = await client.get_status()
        print(f"Server Status: {status.status}")

if __name__ == "__main__":
    asyncio.run(main())
```

### OpenAI Compatibility
Headwater provides an OpenAI-compatible endpoint for integrating with existing tooling.

```python
from headwater_client.client.headwater_client_async import HeadwaterAsyncClient
from headwater_api.classes import OpenAIChatRequest, OpenAIChatMessage

async with HeadwaterAsyncClient() as client:
    request = OpenAIChatRequest(
        model="headwater/llama3.1:latest",
        messages=[OpenAIChatMessage(role="user", content="Explain late chunking")]
    )
    response = await client.openai.chat_completions(request)
    print(response.choices[0].message.content)
```

### Document Ingestion (Siphon)
Process local files or remote URLs into structured content.

```python
from siphon_api.api.siphon_request import SiphonRequest
from siphon_api.enums import SourceOrigin, ActionType

request = SiphonRequest(
    source="https://arxiv.org/pdf/1706.03762.pdf",
    origin=SourceOrigin.URL,
    params={"action": ActionType.SUMMARIZE, "use_cache": True}
)

response = client.siphon.process(request)
print(response.payload.summary)
```

## Configuration Options

The `StatusResponse` provides insight into the server's current capabilities:

| Field | Description |
| :--- | :--- |
| `status` | Current health state (healthy, degraded, error) |
| `gpu_enabled` | Boolean indicating if CUDA is available |
| `models_available` | List of local LLM and embedding models |
| `uptime` | Server uptime in seconds |
