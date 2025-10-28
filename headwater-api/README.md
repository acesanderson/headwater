# Headwater API Client

A Python client library for interacting with the Headwater AI services, including LLM querying, text embeddings, and content curation.

## Quick Start

Install the library and run a synchronous query in under a minute. This example sends a single request to the Conduit LLM service and prints the response.

**1. Install the client**

```sh
pip install headwater-api
```

**2. Run a query**

```python
from headwater_api.client.headwater_client import HeadwaterClient
from headwater_api.classes import ConduitRequest
from conduit.message.textmessage import TextMessage

# Initialize the client
client = HeadwaterClient()

# Construct the request for a specific model
request = ConduitRequest(
    messages=[TextMessage(role="user", content="Name three species of birds native to North America.")],
    model="gpt-oss:latest"
)

# Execute the synchronous query
response = client.conduit.query_sync(request)

# Print the response content
if hasattr(response, 'content'):
    print(str(response.content))
else:
    print(f"Received an error: {response}")
```

## Features

The client provides a unified interface for three core services: **Conduit** (LLMs), **Embeddings**, and **Curator** (Retrieval). The following example demonstrates the primary function of each.

```python
from headwater_api.client.headwater_client import HeadwaterClient
from headwater_api.classes import (
    BatchRequest,
    EmbeddingsRequest,
    ChromaBatch,
    CuratorRequest,
)

# 1. Initialize the client
client = HeadwaterClient()

# 2. Perform a batch LLM query using Conduit for high throughput
print("--- Running Batch Conduit Query ---")
batch_request = BatchRequest(
    model="gpt-oss:latest",
    prompt_strings=[
        "What is the capital of France?",
        "Explain the theory of relativity in one sentence.",
    ],
)
batch_response = client.conduit.query_async(batch_request)
for i, result in enumerate(batch_response.results):
    print(f"Prompt {i+1}: {str(result.content)}")

# 3. Generate text embeddings
print("\n--- Generating Embeddings ---")
embeddings_request = EmbeddingsRequest(
    model="sentence-transformers/all-mpnet-base-v2",
    batch=ChromaBatch(
        ids=["doc1", "doc2"],
        documents=[
            "The sky is blue.",
            "Photosynthesis converts light energy into chemical energy."
        ]
    )
)
embeddings_response = client.embeddings.generate_embeddings(embeddings_request)
print(f"Generated {len(embeddings_response.embeddings)} embeddings.")

# 4. Curate and rank content with a query
print("\n--- Curating Content ---")
curator_request = CuratorRequest(
    query_string="workplace policy",
    k=3  # Retrieve top 3 results
)
curator_response = client.curator.curate(curator_request)
print(f"Found {len(curator_response.results)} curated results:")
for result in curator_response.results:
    print(f"  - ID: {result.id}, Score: {result.score:.4f}")
```

## Installation

Ensure you have Python 3.8+ installed.

```sh
pip install headwater-api
```

The client is configured to automatically connect to the Headwater Server via network discovery. No additional configuration is required for standard environments.

## API Usage

The `HeadwaterClient` is the main entry point and provides access to all services through its attributes.

```python
from headwater_api.client.headwater_client import HeadwaterClient

client = HeadwaterClient()
```

### Conduit: LLM Queries

The `client.conduit` service handles interactions with large language models.

#### Synchronous Queries
For single, blocking requests.

```python
from headwater_api.classes import ConduitRequest
from conduit.message.textmessage import TextMessage

request = ConduitRequest(
    messages=[TextMessage(role="user", content="Name three birds")],
    model="gpt-oss:latest"
)
response = client.conduit.query_sync(request)
print(response.content)
```

#### Asynchronous Batch Queries
For processing multiple prompts in a single API call. This is the recommended method for high-throughput tasks. A `BatchRequest` accepts either a list of pre-formatted prompts or a template string with a list of variables.

```python
from headwater_api.classes import BatchRequest

# Option 1: Using a list of prompt strings
batch_request_prompts = BatchRequest(
    model="gpt-oss:latest",
    prompt_strings=[
        "What is the capital of Canada?",
        "Describe the water cycle.",
    ],
)
response = client.conduit.query_async(batch_request_prompts)

# Option 2: Using a template and input variables
batch_request_vars = BatchRequest(
    model="gpt-oss:latest",
    prompt_str="Name 3 famous {things}.",
    input_variables_list=[
        {"things": "scientists"},
        {"things": "artists"},
    ],
)
response = client.conduit.query_async(batch_request_vars)
```

| Parameter              | Type                     | Description                                                                 |
| ---------------------- | ------------------------ | --------------------------------------------------------------------------- |
| `model`                | `str`                    | The model identifier to use for the batch job.                              |
| `prompt_strings`       | `list[str]`              | A list of complete prompt strings. Use this OR `input_variables_list`.      |
| `prompt_str`           | `str`                    | A template string with placeholders (e.g., `{topic}`). Required if using `input_variables_list`. |
| `input_variables_list` | `list[dict[str, str]]`   | A list of dictionaries to format into the `prompt_str`.                     |


### Embeddings: Text Embeddings

The `client.embeddings` service generates vector representations of text.

```python
from headwater_api.classes import EmbeddingsRequest, ChromaBatch

request = EmbeddingsRequest(
    model="sentence-transformers/all-mpnet-base-v2",
    batch=ChromaBatch(
        ids=["doc_a", "doc_b"],
        documents=[
            "This is the first document.",
            "This is the second document."
        ]
    )
)

response = client.embeddings.generate_embeddings(request)
# response.embeddings contains a list of float lists
print(f"Generated {len(response.embeddings)} embeddings.")
```

### Curator: Content Retrieval

The `client.curator` service retrieves and ranks relevant items based on a query string.

```python
from headwater_api.classes import CuratorRequest

request = CuratorRequest(
    query_string="sexual harassment in the workplace",
    k=5, # Return the top 5 results
)

response = client.curator.curate(request)
for result in response.results:
    print(f"ID: {result.id}, Score: {result.score}")
```

