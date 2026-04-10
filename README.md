# Headwater

Headwater is a unified API and client library for distributed LLM inference, vector embeddings, and content ingestion. It provides a centralized routing gateway to coordinate processing across multiple compute nodes, specializing in high-throughput generation and document ranking.

## Installation

```bash
pip install headwater-client headwater-api
```

The project requires Python 3.12 or higher.

## Quick Start

The system uses a centralized `HeadwaterClient` to interact with inference and embedding services.

```python
from headwater_client.client.headwater_client import HeadwaterClient
from headwater_api.classes import GenerationRequest
from conduit.domain.request.generation_params import GenerationParams
from conduit.domain.message.message import UserMessage

# Initialize client pointing to the default headwater router
client = HeadwaterClient(host_alias="headwater")

# Synchronous generation query
request = GenerationRequest(
    messages=[UserMessage(content="Explain quantum entanglement in one sentence.")],
    params=GenerationParams(model="haiku", max_tokens=50)
)

response = client.conduit.query_generate(request)
print(response.message.content)
```

## Core Capabilities

### LLM Inference (Conduit)
Headwater leverages the Conduit engine to handle both synchronous generation and high-concurrency batch processing. It supports OpenAI-compatible endpoints and local model providers.

```python
from headwater_api.classes import BatchRequest

# Process thousands of prompts concurrently
batch = BatchRequest(
    prompt_strings_list=["Prompt 1", "Prompt 2", "Prompt 3"],
    params=GenerationParams(model="llama3.1", max_tokens=100),
    max_concurrent=10
)
results = client.conduit.query_batch(batch)
```

### Vector Embeddings
The system manages embedding generation and collection operations via ChromaDB integration. It includes an automated "research" service to fetch model specifications (dimensions, sequence length) and stores them in a local registry.

```python
from headwater_api.classes import QuickEmbeddingRequest

# Generate a single embedding
embedding = client.embeddings.quick_embedding(
    QuickEmbeddingRequest(query="Sample text for vectorization")
)

# Search an existing collection
results = client.embeddings.query_collection(
    QueryCollectionRequest(name="knowledge_base", query="retrieval topic", k=5)
)
```

### Document Reranking
Specialized reranker support allows for re-scoring search results using models like BGE, FlashRank, or Cross-Encoders to improve retrieval precision.

```python
from headwater_api.classes import RerankRequest

reranked = client.reranker.rerank(RerankRequest(
    query="machine learning fundamentals",
    documents=["Doc A content...", "Doc B content..."],
    model_name="flash",
    k=3
))
```

### Content Extraction (Siphon)
The Siphon service handles complex content ingestion, extracting raw text and metadata from URIs or file paths for downstream processing.

## Architecture

Headwater operates as a distributed system composed of a Router and several Backend Subservers:

| Component | Description | Default Port |
| :--- | :--- | :--- |
| **Router** | Acts as a gateway. Resolves requests based on model weight and service type. | 8081 |
| **Subserver** | Executes heavy compute tasks (Inference, Embeddings, Reranking). | 8080 |

### Routing Logic
The router inspects incoming requests and directs traffic based on a `routes.yaml` configuration. It supports "Heavy Routing," where specific large models (e.g., Llama-70B) are automatically directed to dedicated high-VRAM backends.

### Backend Aliases
The client supports predefined host aliases for standard network environments:
* `headwater`: The primary router (Gateway).
* `bywater`, `backwater`, `deepwater`, `stillwater`: Specialized compute nodes.

## Server Deployment

To start a compute subserver:
```bash
uv run hw-up
```

To start the routing gateway:
```bash
uv run hw-route
```

The server includes built-in Prometheus metrics at `/metrics` and GPU utilization monitoring for NVIDIA hardware.

## Configuration

The system looks for a routing configuration at `~/.config/headwater/routes.yaml`.

```yaml
backends:
  primary: "http://172.16.0.4:8080"
  heavy: "http://172.16.0.5:8080"

routes:
  conduit: "primary"
  embeddings: "primary"
  heavy_inference: "heavy"

heavy_models:
  - "llama3.1:70b"
  - "deepseek-coder:33b"
```
