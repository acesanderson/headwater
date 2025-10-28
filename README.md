# Headwater

A high-performance API server and client for unified LLM operations, semantic search, and embeddings management.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Installation and Setup](#installation-and-setup)
- [Core Capabilities](#core-capabilities)
- [Architecture](#architecture)

## Overview

Headwater provides a robust server and a straightforward Python client for interacting with complex AI systems. It offers a unified interface for several key services:

*   **Conduit**: A high-throughput gateway for synchronous and asynchronous large language model (LLM) queries.
*   **Embeddings**: An API for generating text embeddings and managing vector collections.
*   **Curator**: A service for performing sophisticated semantic search and reranking over document sets.

The system is designed as a client-server application, allowing AI capabilities to be centralized and accessed efficiently by multiple applications.

## Quick Start

This example demonstrates a simple, synchronous LLM query using the Headwater client.

**Prerequisites**: The Headwater server must be running. See [Installation and Setup](#installation-and-setup).

1.  **Install the client library:**
    ```bash
    # From the root of the project
    pip install -e headwater-client
    ```

2.  **Run the following Python script:**
    ```python
    from headwater_client.client import HeadwaterClient
    from headwater_api.classes import ConduitRequest
    from conduit.message.textmessage import TextMessage

    # Initialize the client
    client = HeadwaterClient()

    # Verify connection to the server
    if not client.ping():
        print("Could not connect to Headwater server. Please ensure it is running.")
        exit()

    # Create a request
    request = ConduitRequest(
        messages=[TextMessage(role="user", content="Name three species of owls.")],
        model="llama3.1:latest" # Assumes a local Ollama model
    )

    # Execute the synchronous query
    try:
        response = client.conduit.query_sync(request)
        print("Response from Headwater server:")
        print(response.content)
    except Exception as e:
        print(f"An error occurred: {e}")

    ```

## Installation and Setup

### Prerequisites

*   Python 3.10+ and `pip`.
*   A running LLM provider, such as [Ollama](https://ollama.com/), for the Conduit service.
*   Git for cloning the repository.

### Server Setup

The Headwater server is a FastAPI application that exposes the core AI services.

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd headwater
    ```

2.  **Install server dependencies:**
    It is recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install -e headwater-api
    pip install -e headwater-server
    ```

3.  **Run the server:**
    ```bash
    python -m headwater_server.server.main
    ```
    The server will start on `http://0.0.0.0:8080` by default.

### Client Setup

The client is a Python package for interacting with the server API.

1.  **Install client and API packages:**
    In a separate terminal, set up the client environment.
    ```bash
    # From the root of the project
    cd headwater
    python -m venv client-venv
    source client-venv/bin/activate
    pip install -e headwater-api
    pip install -e headwater-client
    ```
    The `headwater-client` is now available for use in your Python projects.

## Core Capabilities

The `HeadwaterClient` provides access to the server's primary functions. The following examples showcase its main capabilities.

### Conduit API: Batch LLM Processing

Execute multiple LLM queries in parallel with a single asynchronous API call. This is ideal for high-throughput tasks.

```python
from headwater_client.client import HeadwaterClient
from headwater_api.classes import BatchRequest, BatchResponse

client = HeadwaterClient()

# Define a batch of prompts with a template
batch_request = BatchRequest(
    model="llama3.1:latest",
    prompt_str="List three famous {things}.",
    input_variables_list=[
        {"things": "scientific theories"},
        {"things": "impressionist painters"},
        {"things": "programming languages"},
    ],
)

# Execute the asynchronous batch request
response: BatchResponse = client.conduit.query_async(batch_request)

# Process the results
for i, result in enumerate(response.results):
    print(f"--- Prompt {i+1} ---")
    print(result.content)
    print()

```

### Curator API: Semantic Search and Reranking

Perform a semantic query against a pre-configured document collection and receive reranked, contextually relevant results.

```python
from headwater_client.client import HeadwaterClient
from headwater_api.classes import CuratorRequest, CuratorResponse

client = HeadwaterClient()

# Create a request to find relevant documents
curator_request = CuratorRequest(
    query_string="best practices for team leadership",
    k=3  # Return the top 3 results
)

# Get curated results
response: CuratorResponse = client.curator.curate(curator_request)

print(f"Top {len(response.results)} results for '{curator_request.query_string}':")
for result in response.results:
    print(f"  ID: {result.id}, Score: {result.score:.4f}")

```

### Embeddings API: Text Embedding Generation

Generate vector embeddings for a batch of documents using a specified transformer model.

```python
from headwater_client.client import HeadwaterClient
from headwater_api.classes import EmbeddingsRequest, ChromaBatch

client = HeadwaterClient()

# Define documents to be embedded
documents_to_embed = [
    "The sun rises in the east.",
    "Data science combines statistics with computer science.",
    "Good architecture requires careful planning.",
]

# Create a batch request
batch = ChromaBatch(
    ids=[str(i) for i in range(len(documents_to_embed))],
    documents=documents_to_embed,
)

request = EmbeddingsRequest(
    model="sentence-transformers/all-MiniLM-L6-v2",
    batch=batch
)

# Generate embeddings
response = client.embeddings.generate_embeddings(request)

print(f"Generated {len(response.embeddings)} embeddings.")
print("Dimension of first embedding:", len(response.embeddings[0]))

```

## Architecture

Headwater is structured as a monorepo containing three distinct but interconnected Python packages:

*   **`headwater-server`**: The core FastAPI application. It implements the business logic for all AI services and exposes them via a RESTful API. It is designed to run as a persistent, centralized service.

*   **`headwater-client`**: A user-facing Python library that acts as an SDK for the server. It handles HTTP transport, request serialization, and response parsing, providing a clean programmatic interface to the server's capabilities.

*   **`headwater-api`**: A shared library containing Pydantic models for all request and response objects. This package ensures data consistency and type safety between the server and client.
