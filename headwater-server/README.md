# Headwater Server

An API server for orchestrating diverse AI operations, including text generation, embeddings, and semantic search, with GPU acceleration.

## Quick Start

This example assumes the server is running on `localhost:8080`. Execute the following command to get a synchronous text completion from a local Ollama model.

```bash
curl -X POST http://localhost:8080/conduit/sync \
-H "Content-Type: application/json" \
-d '{
  "messages": [
    {
      "role": "user",
      "content": "Name three species of owls native to North America."
    }
  ],
  "model": "llama3.1:latest"
}'
```

Expected Response:

```json
{
  "content": "Certainly! Three species of owls native to North America are:\n\n1.  **Great Horned Owl** (*Bubo virginianus*)\n2.  **Snowy Owl** (*Bubo scandiacus*)\n3.  **Barn Owl** (*Tyto alba*)",
  "model": "llama3.1:latest",
  "usage": {
    "prompt_tokens": 19,
    "completion_tokens": 64,
    "total_tokens": 83
  }
}
```

## Installation and Setup

### Prerequisites

-   Python 3.9+
-   An Ollama instance running locally. See the [Ollama documentation](https://ollama.com/) for installation instructions. Ensure you have pulled a model, for example: `ollama pull llama3.1`.

### Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/headwater-server-project.git
    cd headwater-server-project
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate
    # On Windows, use: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **(Optional) Configure API Keys:**
    For services that use external rerankers (like Cohere or Jina), set the corresponding environment variables:
    ```bash
    export COHERE_API_KEY="your_cohere_api_key"
    export JINA_API_KEY="your_jina_api_key"
    ```

### Running the Server

Launch the server using Uvicorn:

```bash
uvicorn headwater_server.server.main:app --host 0.0.0.0 --port 8080
```

The API will be available at `http://localhost:8080`.

## API Endpoints

The server provides several endpoints for different AI tasks.

### Text Generation (Conduit)

These endpoints interface with LLMs for text generation tasks.

#### `POST /conduit/sync`

Processes a single, synchronous request to an LLM.

**Example:**
```bash
curl -X POST http://localhost:8080/conduit/sync \
-H "Content-Type: application/json" \
-d '{
  "messages": [{"role": "user", "content": "name three birds"}],
  "model": "llama3.1:latest"
}'
```

#### `POST /conduit/async`

Processes a batch of prompts asynchronously. This is efficient for running multiple prompts against the same model, especially using a prompt template.

**Example:**
This request uses a single prompt template (`"Name 3 {things}."`) and applies it to a list of different inputs.

```bash
curl -X POST http://localhost:8080/conduit/async \
-H "Content-Type: application/json" \
-d '{
  "model": "llama3.1:latest",
  "input_variables_list": [
    {"things": "countries in Africa"},
    {"things": "programming languages"},
    {"things": "biological processes"}
  ],
  "prompt_str": "Name 3 {things}."
}'
```

### Embeddings

#### `POST /conduit/embeddings`

Generates vector embeddings for a batch of documents using a specified sentence-transformer model.

**Example:**
```bash
curl -X POST http://localhost:8080/conduit/embeddings \
-H "Content-Type: application/json" \
-d '{
  "model": "sentence-transformers/all-mpnet-base-v2",
  "batch": {
    "ids": ["doc1", "doc2"],
    "documents": [
      "Headwater Server provides robust API endpoints.",
      "Vector embeddings are useful for semantic search."
    ]
  }
}'
```

### Semantic Search (Curator)

#### `POST /curator/curate`

Performs semantic search. It takes a user query, retrieves a set of candidate documents from a vector store, and uses a reranker model to provide the most relevant results.

**Example:**
```bash
curl -X POST http://localhost:8080/curator/curate \
-H "Content-Type: application/json" \
-d '{
  "query_string": "strategies for pivoting your career",
  "k": 3,
  "n_results": 20,
  "model_name": "bge",
  "cached": true
}'
```

### Server Status

#### `GET /status`

Provides a health check and information about the server, including GPU status and available local models.

**Example:**
```bash
curl http://localhost:8080/status
```

**Expected Response:**
```json
{
  "status": "healthy",
  "gpu_enabled": true,
  "message": "Server is running",
  "models_available": [
    "llama3.1:latest",
    "codegemma:latest",
    "mixtral:latest"
  ],
  "uptime": 1234.56
}
```
