# Design: OpenAI-Compatible Chat Completions Endpoint

**Date:** 2026-03-07
**Status:** Draft

---

## 1. Goal

Expose `POST /conduit/v1/chat/completions` on the headwater server as a strict OpenAI-spec chat completions endpoint. This allows external robots and OpenAI-compatible clients to route requests through headwater's Conduit LLM framework by specifying a model as `headwater/<model_name>`. The headwater-client returns a first-class `openai.types.chat.ChatCompletion` object.

---

## 2. Constraints and Non-Goals

**In scope:**
- Non-streaming chat completions only
- Text content messages (system, user, assistant, tool roles)
- Model routing via `headwater/<model_name>` prefix convention
- Cache reuse under project name `"headwater"`
- Endpoint visible in FastAPI `/docs` (verified via `/openapi.json`)
- Structured outputs via `response_format: {"type": "json_schema", ...}` (OpenAI Structured Outputs spec)

**Not in scope — the following must not be implemented, even if they seem natural:**
- Streaming (`stream: true`) — hard 400 rejected, not deferred
- Tool calling / function calling (`tools`, `tool_choice` fields) — 422 if present
- `response_format: {"type": "text"}` — 422 if present; only `"json_schema"` is accepted
- `response_format: {"type": "json_object"}` — 422 if present
- Logprobs
- Vision / multimodal message content
- OpenAI model listing endpoint (`GET /conduit/v1/models`)
- Fine-tuned model support
- Any headwater-specific extension fields on the response object
- `n` parameter (multiple completions) — 422 if present
- `user`, `presence_penalty`, `frequency_penalty` fields — silently ignored if present (forward-compat)
- Per-request project name or repository override
- Authentication / API key validation
- Rate limiting
- The sync headwater-client (async client only in this spec)

---

## 3. Interface Contracts

### 3.1 API Endpoint

```
POST /conduit/v1/chat/completions
Content-Type: application/json
```

### 3.2 Request model — `headwater-api`

**File:** `headwater_api/classes/conduit_classes/openai_compat.py`

```python
class OpenAIChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None

class JsonSchemaFormat(BaseModel):
    model_config = ConfigDict(populate_by_name=True)  # required: allows both alias and field name

    name: str                                          # required per OpenAI spec
    description: str | None = None
    schema_: dict[str, Any] = Field(alias="schema")   # "schema" on the wire; "schema_" in Python
    strict: bool | None = None                        # accepted but not forwarded to Conduit; ignored

class ResponseFormat(BaseModel):
    type: Literal["json_schema"]                       # only this value is supported; others → 422
    json_schema: JsonSchemaFormat

class OpenAIChatRequest(BaseModel):
    model: str                       # must match "headwater/<non-empty-model-name>"
    messages: list[OpenAIChatMessage] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
    stop: list[str] | str | None = None
    stream: bool = False
    response_format: ResponseFormat | None = None
    use_cache: bool = True           # headwater server extension; the server honours this field;
                                     # OpenAI SDK clients will not send it (that is fine)

    @property
    def conduit_model(self) -> str:
        """Returns the bare model name, e.g. 'claude-sonnet-4-6'."""
        return self.model.removeprefix("headwater/")

    @property
    def normalized_stop(self) -> list[str] | None:
        """Always list[str] or None — normalizes the str shorthand."""
        if isinstance(self.stop, str):
            return [self.stop]
        return self.stop
```

**Validation rules** (enforced via `model_validator(mode="after")`):
- `model` must match `r"^headwater/.+"` (non-empty suffix) — else 422
- `stream: true` — hard 400: `"Streaming is not supported on this endpoint."`
- `role="tool"` message with `tool_call_id=None` — hard 400: `"tool_call_id is required for messages with role='tool'."`
- `role="assistant"` message with `content=None` — hard 400: `"Assistant messages with null content are not supported. While null content is valid per OpenAI spec (e.g. for tool-call-only turns), Conduit requires at least one payload field on AssistantMessage."`

**Note on `stop` normalization:** `normalized_stop` is a property on the request model, not a mutation. The service must use `request.normalized_stop` when building `GenerationParams`, never `request.stop` directly.

### 3.3 Response — wire shape

The server returns a JSON body that exactly matches `openai.types.chat.ChatCompletion`. No extension fields.

```
id:      "chatcmpl-<16 hex chars>"
object:  "chat.completion"
created: <unix timestamp int, seconds, set at response build time>
model:   "<echoed verbatim from request.model, e.g. 'headwater/claude-sonnet-4-6'>"
choices: [
  {
    index: 0,
    message: { role: "assistant", content: "<str — never null, never empty string>" },
    finish_reason: "stop" | "length" | "tool_calls" | "content_filter" | "error"
  }
]
usage: {
  prompt_tokens: int,
  completion_tokens: int,
  total_tokens: int      # must equal prompt_tokens + completion_tokens
}
```

**`finish_reason` mapping from `StopReason`:**

| `StopReason` | `finish_reason` |
|---|---|
| `STOP` | `"stop"` |
| `LENGTH` | `"length"` |
| `TOOL_CALLS` | `"tool_calls"` |
| `CONTENT_FILTER` | `"content_filter"` |
| `ERROR` | `"error"` |
| any other / unknown value | `"error"` (log a warning) |

**Content coercion rules (applied in order, exactly one branch executes):**

1. If `response_format` was present:
   - `result.message.parsed` is a `BaseModel` → `content = result.message.parsed.model_dump_json()`
   - `result.message.parsed` is a `list` → `content = json.dumps([item.model_dump() if isinstance(item, BaseModel) else item for item in result.message.parsed])`
   - `result.message.parsed` is `None` → HTTP 500: `"Structured output failed: instructor did not return a parsed result."`
2. If `response_format` was absent:
   - `content = str(result.message)` — non-text content (Perplexity citations, etc.) is coerced; this is explicitly lossy
   - If `str(result.message)` returns `""` (e.g. `result.message.content` is `None`) → HTTP 500: `"Model returned an empty response."`

`content` in the response must never be `null` or `""`.

### 3.4 Server route — `headwater-server`

**File:** `headwater_server/api/conduit_server_api.py` (added to existing `register_routes`)

```python
@self.app.post("/conduit/v1/chat/completions")
async def conduit_openai_chat(request: OpenAIChatRequest) -> dict:
    from headwater_server.services.conduit_service.conduit_openai_service import (
        conduit_openai_service,
    )
    return await conduit_openai_service(request)
```

Return type is `dict` (not a Pydantic `response_model`) because the response shape is governed by the OpenAI spec, not a headwater Pydantic class.

### 3.5 Service — `headwater-server`

**File:** `headwater_server/services/conduit_service/conduit_openai_service.py`

```python
async def conduit_openai_service(request: OpenAIChatRequest) -> dict:
    ...
```

Responsibilities (in order):
1. Validate model via `ModelStore.validate_model(request.conduit_model)` — map exceptions to HTTP errors (see §5); do not proceed past this point on failure
2. Convert `OpenAIChatMessage` list → `Sequence[MessageUnion]` (see §8 for invalid transitions)
3. Build `GenerationParams`:
   - Use `request.normalized_stop` (never `request.stop`)
   - If `response_format` present: set `response_model_schema = request.response_format.json_schema.schema_`; do NOT set `response_model`
   - `strict` on `JsonSchemaFormat` is accepted on the wire but not forwarded to Conduit
4. Build `ConduitOptions`: `project_name="headwater"`, `verbosity=Verbosity.SILENT`, `include_history=False`, `use_cache=request.use_cache`
5. Build `GenerationRequest` with `include_history=False` (must match `ConduitOptions.include_history`)
6. Call `ModelAsync(model_name).query(gen_request)`
7. Apply content coercion rules (§3.3) and raise on empty/null result
8. Build and return OpenAI-spec dict

### 3.6 Client — `headwater-client`

**File:** `headwater_client/api/openai_async_api.py`

```python
class OpenAICompatAsyncAPI(BaseAsyncAPI):
    async def chat_completions(self, request: OpenAIChatRequest) -> ChatCompletion:
        from openai.types.chat import ChatCompletion  # lazy import
        response = await self._request(
            "POST",
            "/conduit/v1/chat/completions",
            json_payload=request.model_dump_json(by_alias=True),  # "schema" not "schema_"
        )
        return ChatCompletion.model_validate_json(response)
```

`openai` must be declared as an explicit dependency in `headwater-client/pyproject.toml`.

**Note on serialization:** `model_dump_json(by_alias=True)` is required so that `schema_` is serialized as `"schema"` on the wire.

---

## 4. Acceptance Criteria

**Basic flow:**
- `POST /conduit/v1/chat/completions` with a valid `headwater/<model>` request returns HTTP 200 and a body that passes `ChatCompletion.model_validate(response_json)` without error
- `choices[0].message.content` is a non-empty string
- `choices[0].finish_reason` is one of: `"stop"`, `"length"`, `"tool_calls"`, `"content_filter"`, `"error"`
- `usage.total_tokens == usage.prompt_tokens + usage.completion_tokens`
- `model` in the response is identical to `model` in the request (including `"headwater/"` prefix)
- `GET /openapi.json` response body contains the path `"/conduit/v1/chat/completions"`

**Validation rejections:**
- `stream: true` → HTTP 400, response body contains `"Streaming is not supported"`
- `model` without `"headwater/"` prefix → HTTP 422
- `model` equal to exactly `"headwater/"` (empty suffix) → HTTP 422
- Unrecognized model name after prefix strip → HTTP 400
- Missing or unreadable `aliases.json` / `models.json` → HTTP 502
- `role="tool"` message with no `tool_call_id` → HTTP 400
- `role="assistant"` message with `content=null` → HTTP 400
- `response_format: {"type": "text"}` → HTTP 422
- `response_format: {"type": "json_object"}` → HTTP 422
- `response_format.json_schema` missing `name` field → HTTP 422

**Structured outputs:**
- Request with valid `response_format.json_schema` returns HTTP 200; `choices[0].message.content` is a string that parses as valid JSON via `json.loads()` without error
- Request with valid `response_format.json_schema` where instructor returns `parsed=None` → HTTP 500, body contains `"Structured output failed"`

**Client:**
- `OpenAICompatAsyncAPI.chat_completions()` returns an instance of `openai.types.chat.ChatCompletion`
- `model_dump_json(by_alias=True)` on `OpenAIChatRequest` containing `response_format` produces JSON with key `"schema"` (not `"schema_"`)

---

## 5. Error Handling / Failure Modes

| Condition | HTTP Status | Response detail |
|---|---|---|
| `stream: true` | 400 | `"Streaming is not supported on this endpoint."` |
| `model` missing `"headwater/"` prefix or empty suffix | 422 | Pydantic validation error |
| Model name unrecognized by `ModelStore` | 400 | `"Unrecognized model: '<name>'. Check ModelStore for supported models."` |
| `aliases.json` or `models.json` unreadable | 502 | `"Model store unavailable. Server configuration error."` |
| `role="tool"` with `tool_call_id=None` | 400 | `"tool_call_id is required for messages with role='tool'."` |
| `role="assistant"` with `content=None` | 400 | `"Assistant messages with null content are not supported. While null content is valid per OpenAI spec (e.g. for tool-call-only turns), Conduit requires at least one payload field on AssistantMessage."` |
| `response_format.type` not `"json_schema"` | 422 | Pydantic validation error |
| `response_format.json_schema.name` missing | 422 | Pydantic validation error |
| Structured output: `parsed=None` after query | 500 | `"Structured output failed: instructor did not return a parsed result."` |
| Plain response: `str(result.message)` returns `""` | 500 | `"Model returned an empty response."` |
| `ModelAsync.query()` raises unexpectedly | 500 | Surfaced via existing FastAPI error handlers |
| Empty `messages` list | 422 | Pydantic validation error |
| Messages list contains only system messages | 400 | `"messages must contain at least one non-system message."` |

`ModelStore` exceptions must be caught in the service and re-raised as `HTTPException`. They must not surface as unhandled 500s.

---

## 6. Observability

All log statements use `logger = logging.getLogger(__name__)` at module level, consistent with the rest of the service layer.

**Request-level logging (INFO):**
- On entry: `"OpenAI-compat request: model=%s structured_output=%s use_cache=%s"` — logged before any Conduit call

**Response-level logging (INFO):**
- On success: `"OpenAI-compat response: model=%s finish_reason=%s input_tokens=%d output_tokens=%d cache_hit=%s duration_ms=%.1f"`

**Error logging:**
- HTTP 400/422 validation errors: DEBUG (expected client errors, not actionable server-side)
- HTTP 502 (model store unavailable): ERROR (server misconfiguration)
- HTTP 500 (structured output failure, empty response, unexpected exception): ERROR

**Specific warning:**
- Unknown `StopReason` value mapped to `"error"`: `WARNING "Unknown StopReason '%s', defaulting finish_reason to 'error'"`

**Not in scope for this spec:** metrics, distributed tracing, alerting. These are cross-cutting concerns handled at the infrastructure layer.

---

## 7. Conventions / Style Reference

Follow the pattern established in `conduit_generate_service.py`. All conduit imports are deferred (inside the function body).

```python
async def conduit_openai_service(request: OpenAIChatRequest) -> dict:
    import json
    import time
    import uuid
    from conduit.core.model.model_async import ModelAsync
    from conduit.core.model.models.modelstore import ModelStore
    from conduit.domain.config.conduit_options import ConduitOptions
    from conduit.domain.request.generation_params import GenerationParams
    from conduit.domain.request.request import GenerationRequest
    from conduit.domain.result.response_metadata import StopReason
    from conduit.utils.progress.verbosity import Verbosity
    from fastapi import HTTPException

    logger.info(
        "OpenAI-compat request: model=%s structured_output=%s use_cache=%s",
        request.model,
        request.response_format is not None,
        request.use_cache,
    )

    try:
        model_name = ModelStore.validate_model(request.conduit_model)
    except FileNotFoundError as exc:
        logger.error("Model store unavailable: %s", exc)
        raise HTTPException(status_code=502, detail="Model store unavailable. Server configuration error.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unrecognized model: '{request.conduit_model}'. Check ModelStore for supported models.") from exc

    # ... build messages, params, options, gen_request ...

    model = ModelAsync(model_name)
    result = await model.query(gen_request)

    # Content coercion
    if request.response_format is not None:
        if result.message.parsed is None:
            logger.error("Structured output failed: parsed=None for model=%s", model_name)
            raise HTTPException(status_code=500, detail="Structured output failed: instructor did not return a parsed result.")
        # ... serialize parsed ...
    else:
        content = str(result.message)
        if not content:
            logger.error("Model returned empty response: model=%s", model_name)
            raise HTTPException(status_code=500, detail="Model returned an empty response.")

    _stop_reason_map = {
        StopReason.STOP: "stop",
        StopReason.LENGTH: "length",
        StopReason.TOOL_CALLS: "tool_calls",
        StopReason.CONTENT_FILTER: "content_filter",
        StopReason.ERROR: "error",
    }
    finish_reason = _stop_reason_map.get(result.metadata.stop_reason)
    if finish_reason is None:
        logger.warning("Unknown StopReason '%s', defaulting finish_reason to 'error'", result.metadata.stop_reason)
        finish_reason = "error"

    logger.info(
        "OpenAI-compat response: model=%s finish_reason=%s input_tokens=%d output_tokens=%d cache_hit=%s duration_ms=%.1f",
        model_name,
        finish_reason,
        result.metadata.input_tokens,
        result.metadata.output_tokens,
        result.metadata.cache_hit,
        result.metadata.duration,
    )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": result.metadata.input_tokens,
            "completion_tokens": result.metadata.output_tokens,
            "total_tokens": result.metadata.input_tokens + result.metadata.output_tokens,
        },
    }
```

---

## 8. Domain Language

| Term | Definition |
|---|---|
| **OpenAI-compat endpoint** | The single route `POST /conduit/v1/chat/completions` |
| **headwater model string** | A model identifier of the form `"headwater/<model_name>"` where `<model_name>` is non-empty, e.g. `"headwater/claude-sonnet-4-6"` |
| **conduit model name** | The bare model name after stripping `"headwater/"`, validated by `ModelStore` |
| **OpenAIChatRequest** | The Pydantic request model defined in `headwater-api` |
| **OpenAIChatMessage** | A single message entry in the request |
| **ResponseFormat** | The Pydantic model representing `response_format` in the request |
| **JsonSchemaFormat** | The Pydantic model representing the `json_schema` object inside `ResponseFormat`; field is `schema_` in Python, `"schema"` on the wire |
| **structured output** | A request that includes `response_format` with `type="json_schema"`; instructor is invoked server-side |
| **content coercion** | The deterministic process (§3.3) of converting `GenerationResponse` content to a non-empty string for the OpenAI response |
| **GenerationRequest** | Conduit's internal request type (`conduit.domain.request.request.GenerationRequest`) |
| **GenerationResponse** | Conduit's internal response type (`conduit.domain.result.response.GenerationResponse`) |
| **ChatCompletion** | The official `openai.types.chat.ChatCompletion` type returned by the headwater-client |
| **ModelStore** | `conduit.core.model.models.modelstore.ModelStore` — the authority for model validation |
| **conduit_openai_service** | The async service function in `headwater-server` that performs the full translation pipeline |

---

## 9. Invalid State Transitions

The following must raise and must not silently proceed:

- `conduit_openai_service` called with `stream=True` — must raise `HTTPException(400)` before any Conduit call is made
- `role="assistant"` message with `content=None` passed into message conversion — must raise `HTTPException(400)` before `AssistantMessage(...)` is constructed
- `role="tool"` message with `tool_call_id=None` passed into message conversion — must raise `HTTPException(400)` before `ToolMessage(...)` is constructed
- `ModelAsync(model_name).query(...)` called before `ModelStore.validate_model()` has returned successfully — model validation must precede pipeline entry
- `response_format` present but `response_model_schema` not set on `GenerationParams` — if structured output was requested, the schema must be forwarded; omitting it silently degrades to unstructured output
- `content` set to `""` or `None` in the response dict — must raise `HTTPException(500)` instead
- `total_tokens` computed as anything other than `input_tokens + output_tokens` — must not diverge
- `model_dump_json()` called without `by_alias=True` on a request containing `response_format` — serializes `"schema_"` instead of `"schema"`, breaking the wire format; always use `by_alias=True`
