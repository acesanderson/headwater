# Conduit Spec — Headwater Regression Tests

All generation, tokenization, batch, and compatibility endpoints under `/conduit/*` and `/v1/*`.
All inference tests use model `gpt-oss:latest`.

---

### POST /conduit/generate
- **Description**: Single-shot LLM generation. Takes a `GenerationRequest` (from conduit library) and returns a `GenerationResponse`.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `params.model` (str): `"gpt-oss:latest"`
  - `params.prompt_str` or `options` fields as required by `GenerationRequest`/`GenerationParams`
  - Minimal valid example:
    ```json
    {
      "params": {"model": "gpt-oss:latest"},
      "options": {"prompt_str": "Say hello in one word."}
    }
    ```
    (Exact shape depends on conduit library — verify against `GenerationRequest` Pydantic model)
- **Expected response**:
  - 200
  - Shape: `GenerationResponse` — contains response content; exact fields from conduit library
- **Edge cases**:
  - Missing required field → 422 with `error_type: "pydantic_validation"`
  - Unknown model → 4xx with structured `HeadwaterServerError`
  - Empty prompt → may return 422 or succeed with minimal output
- **Already covered**: no

---

### POST /conduit/batch
- **Description**: Batch LLM generation. Processes multiple prompts concurrently.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `prompt_strings_list` (list[str]) OR `input_variables_list` (list[dict]) — exactly one required
  - `prompt_str` (str|None): required when `input_variables_list` is provided
  - `max_concurrent` (int, default 8): concurrency cap
  - `params`: GenerationParams with `model: "gpt-oss:latest"`
  - `options`: ConduitOptions
  - Example using `prompt_strings_list`:
    ```json
    {
      "prompt_strings_list": ["Say hello.", "Say goodbye."],
      "params": {"model": "gpt-oss:latest"},
      "options": {},
      "max_concurrent": 2
    }
    ```
- **Expected response**:
  - 200
  - Shape: `BatchResponse` — field `results` (list[Conversation])
  - `len(results)` should equal number of input prompts
- **Edge cases**:
  - Both `prompt_strings_list` and `input_variables_list` provided → 422
  - Neither provided → 422
  - `input_variables_list` provided without `prompt_str` → 422
  - Empty list in `prompt_strings_list` → 422
- **Already covered**: no

---

### POST /conduit/tokenize
- **Description**: Tokenize text using a named model's tokenizer. Returns token count.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `model` (str): `"gpt-oss:latest"`
  - `text` (str): text to tokenize; example `"Hello world"`
- **Expected response**:
  - 200
  - Shape: `TokenizationResponse` — fields `model` (str), `input_text` (str), `token_count` (int)
  - `token_count` should be positive int
  - `model` should match the requested model
  - `input_text` should match the submitted text
- **Edge cases**:
  - Missing `model` → 422
  - Missing `text` → 422
  - Unknown model → 4xx with structured error
  - Empty string as `text` → may return 0 token count or 422
- **Already covered**: no

---

### GET /conduit/models
- **Description**: List all available models in the conduit registry, optionally filtered by provider.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `provider` (query param, str, optional): filter by provider name; example `?provider=ollama`
- **Expected response**:
  - 200
  - Shape: dict (provider → list of model names or model objects)
  - Must contain at least one entry when no filter applied
- **Edge cases**:
  - No `provider` param → returns all providers
  - Unknown provider value → may return empty dict or 4xx; document actual behavior
- **Already covered**: no

---

### GET /v1/models
- **Description**: OpenAI-compatible model list endpoint.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**: none
- **Expected response**:
  - 200
  - Shape: `{"object": "list", "data": [...]}`
  - `object` must equal `"list"`
  - `data` must be a non-empty list
- **Edge cases**: none beyond basic shape validation
- **Already covered**: yes (covered by `tests/test_openai_compliance.py`)

---

### POST /v1/chat/completions
- **Description**: OpenAI-compatible chat completions. Non-streaming only.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `model` (str): `"gpt-oss:latest"`
  - `messages` (list[OpenAIChatMessage], min_length=1): e.g. `[{"role": "user", "content": "Say hello."}]`
  - `max_tokens` (int|None, ge=1): e.g. `16`
  - `temperature` (float|None, 0.0–2.0): optional
  - `top_p` (float|None, 0.0–1.0): optional
  - `stop` (list[str]|str|None): optional
  - `stream` (bool, default False): must be False
  - `use_cache` (bool, default True): optional
- **Expected response**:
  - 200
  - Shape: OpenAI chat completion dict — required fields: `id`, `object`, `created`, `model`, `choices`
  - `object` must equal `"chat.completion"`
  - `model` must match the requested model
  - `choices[0].message` must be present
  - `choices[0].finish_reason` should be present
  - `usage` block should have `prompt_tokens`, `completion_tokens`, `total_tokens`
- **Edge cases**:
  - `stream: true` → 422 (streaming not supported; validated by `OpenAIChatRequest`)
  - Unknown model → 4xx with structured error
  - Empty `messages` list → 422 (min_length=1)
  - `messages` with `role="assistant"` and `content=null` → 422
  - `messages` with `role="tool"` and no `tool_call_id` → 422
  - `temperature` outside 0.0–2.0 → 422
  - `max_tokens` < 1 → 422
- **Already covered**: yes (partially — `tests/test_openai_compliance.py` covers shape, model echo, unknown model, streaming rejection, empty messages)

---

### POST /v1/messages
- **Description**: Anthropic-compatible messages endpoint. Non-streaming returns full response; stream=true returns SSE stream.
- **Hosts to test**: headwater (via router proxy), bywater, deepwater
- **Key inputs**:
  - `model` (str): `"gpt-oss:latest"`
  - `max_tokens` (int, ge=1): e.g. `64`
  - `messages` (list[AnthropicMessage], min_length=1): e.g. `[{"role": "user", "content": "Say hello."}]`
  - `system` (str|None): optional system prompt
  - `temperature` (float|None, 0.0–1.0): optional
  - `top_p` (float|None, 0.0–1.0): optional
  - `stop_sequences` (list[str]|None): optional
  - `stream` (bool, default False)
- **Expected response (non-streaming)**:
  - 200
  - Shape: Anthropic message response dict — fields `id`, `type`, `role`, `content`, `model`, `stop_reason`, `usage`
  - `type` should equal `"message"`
  - `role` should equal `"assistant"`
  - `content` should be a list with at least one block
  - `stop_reason` should be present
- **Expected response (streaming)**:
  - 200 with `Content-Type: text/event-stream`
  - SSE events: `message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, `message_delta`, `message_stop`
- **Edge cases**:
  - Missing `max_tokens` → 422
  - Empty `messages` → 422 (min_length=1)
  - Unknown model → 4xx
  - `temperature` outside 0.0–1.0 → 422 (note: tighter range than OpenAI's 0.0–2.0)
  - `max_tokens` < 1 → 422
  - Content as list of `AnthropicContentBlock` (type="text") should work in addition to plain string content
- **Already covered**: no
