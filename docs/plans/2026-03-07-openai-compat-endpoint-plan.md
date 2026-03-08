# OpenAI-Compatible Chat Completions Endpoint Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `POST /conduit/v1/chat/completions` as a strict OpenAI-spec endpoint routing through Conduit's `ModelAsync`, returning `openai.types.chat.ChatCompletion` from the headwater-client.

**Architecture:** Three-layer implementation: (1) Pydantic request/response models in `headwater-api`; (2) service logic + FastAPI route in `headwater-server`; (3) async client method in `headwater-client`. Service translates OpenAI-spec inputs to Conduit's `GenerationRequest`, calls `ModelAsync`, and maps `GenerationResponse` back to the OpenAI wire format.

**Tech Stack:** FastAPI, Pydantic v2 (with `ConfigDict`, `Field(alias=...)`), `openai` Python SDK (`openai.types.chat.ChatCompletion`), Conduit (`ModelAsync`, `ModelStore`, `GenerationParams`, `ConduitOptions`), pytest, `unittest.mock` (`patch`, `AsyncMock`, `MagicMock`), `fastapi.testclient.TestClient`

**Design doc:** `docs/plans/2026-03-07-openai-compat-endpoint-design.md` — read it before starting; all ACs referenced below are defined there.

---

## Background: key file locations

| What | Path |
|---|---|
| FastAPI app object | `headwater-server/src/headwater_server/server/headwater.py` → `app` |
| Route registration | `headwater-server/src/headwater_server/api/conduit_server_api.py` → `ConduitServerAPI.register_routes()` |
| Existing service pattern | `headwater-server/src/headwater_server/services/conduit_service/conduit_generate_service.py` |
| headwater-api classes init | `headwater-api/src/headwater_api/classes/__init__.py` |
| headwater-client async client | `headwater-client/src/headwater_client/client/headwater_client_async.py` |
| headwater-client base async API | `headwater-client/src/headwater_client/api/base_async_api.py` |

---

## Background: mock pattern for server tests

All server tests use `fastapi.testclient.TestClient` with `unittest.mock.patch` wrapping each `client.post(...)` call. The three things always patched:

```python
from unittest.mock import patch, MagicMock, AsyncMock

# Patch 1: ModelStore.validate_model — prevents file I/O, returns bare model name
# Patch 2: ModelAsync — prevents real LLM calls; .return_value.query is an AsyncMock
# Both patches must wrap the client.post(...) call, not just setup

def _make_mock_result(content="Hello, world!", stop_reason=None, input_tokens=10, output_tokens=5, parsed=None):
    from conduit.domain.result.response_metadata import StopReason
    message = MagicMock()
    message.__str__ = MagicMock(return_value=content)
    message.parsed = parsed
    metadata = MagicMock()
    metadata.stop_reason = stop_reason if stop_reason is not None else StopReason.STOP
    metadata.input_tokens = input_tokens
    metadata.output_tokens = output_tokens
    metadata.cache_hit = False
    metadata.duration = 100.0
    result = MagicMock()
    result.message = message
    result.metadata = metadata
    return result

VALID_PAYLOAD = {
    "model": "headwater/claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Hello"}],
}
```

Put `_make_mock_result` and `VALID_PAYLOAD` in `conftest.py` at the test directory root; import them in each test file.

---

## Task 1: headwater-api — create `openai_compat.py` and validate stream rejection

**Files:**
- Create: `headwater-api/src/headwater_api/classes/conduit_classes/openai_compat.py`
- Create: `headwater-api/tests/__init__.py`
- Create: `headwater-api/tests/conduit_classes/__init__.py`
- Create: `headwater-api/tests/conduit_classes/test_openai_compat.py`

---

### TDD Cycle 1 — Fulfills AC7: `stream: true` → HTTP 400

**Step 1: Write the failing test**

```python
# headwater-api/tests/conduit_classes/test_openai_compat.py
import pytest
from pydantic import ValidationError


def test_stream_true_raises_validation_error():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError) as exc_info:
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,
        )
    errors = exc_info.value.errors()
    assert any("Streaming is not supported" in str(e["msg"]) for e in errors)
```

**Step 2: Run to verify it fails**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-api
uv run pytest tests/conduit_classes/test_openai_compat.py::test_stream_true_raises_validation_error -v
```

Expected: `FAILED` — `ImportError` or `ModuleNotFoundError` (file doesn't exist yet)

**Step 3: Write minimal implementation**

```python
# headwater-api/src/headwater_api/classes/conduit_classes/openai_compat.py
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Any, Literal


class OpenAIChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None


class JsonSchemaFormat(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str | None = None
    schema_: dict[str, Any] = Field(alias="schema")
    strict: bool | None = None


class ResponseFormat(BaseModel):
    type: Literal["json_schema"]
    json_schema: JsonSchemaFormat


class OpenAIChatRequest(BaseModel):
    model: str
    messages: list[OpenAIChatMessage] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
    stop: list[str] | str | None = None
    stream: bool = False
    response_format: ResponseFormat | None = None
    use_cache: bool = True

    @property
    def conduit_model(self) -> str:
        return self.model.removeprefix("headwater/")

    @property
    def normalized_stop(self) -> list[str] | None:
        if isinstance(self.stop, str):
            return [self.stop]
        return self.stop

    @model_validator(mode="after")
    def _validate_request(self) -> OpenAIChatRequest:
        if self.stream:
            raise ValueError("Streaming is not supported on this endpoint.")
        return self
```

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_stream_true_raises_validation_error -v
```

Expected: `PASSED`

**Step 5: Commit**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-api
git add src/headwater_api/classes/conduit_classes/openai_compat.py \
        tests/__init__.py \
        tests/conduit_classes/__init__.py \
        tests/conduit_classes/test_openai_compat.py
git commit -m "feat: add OpenAIChatRequest with stream rejection (AC7)"
```

---

## Task 2: headwater-api — model prefix and message validation

**Files:**
- Modify: `headwater-api/src/headwater_api/classes/conduit_classes/openai_compat.py`
- Modify: `headwater-api/tests/conduit_classes/test_openai_compat.py`

---

### TDD Cycle 2 — Fulfills AC8: model without `headwater/` prefix → 422

**Step 1: Write the failing test**

```python
def test_model_missing_prefix_raises_validation_error():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError):
        OpenAIChatRequest(
            model="claude-sonnet-4-6",  # missing "headwater/" prefix
            messages=[{"role": "user", "content": "Hello"}],
        )
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_model_missing_prefix_raises_validation_error -v
```

Expected: `FAILED` — model is accepted without error

**Step 3: Add prefix validation to `_validate_request`**

```python
@model_validator(mode="after")
def _validate_request(self) -> OpenAIChatRequest:
    if self.stream:
        raise ValueError("Streaming is not supported on this endpoint.")
    import re
    if not re.fullmatch(r"headwater/.+", self.model):
        raise ValueError(
            "model must be 'headwater/<model_name>' with a non-empty model name. "
            f"Got: {self.model!r}"
        )
    return self
```

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_model_missing_prefix_raises_validation_error -v
```

Expected: `PASSED`

---

### TDD Cycle 3 — Fulfills AC9: `model="headwater/"` (empty suffix) → 422

**Step 1: Write the failing test**

```python
def test_model_empty_suffix_raises_validation_error():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError):
        OpenAIChatRequest(
            model="headwater/",
            messages=[{"role": "user", "content": "Hello"}],
        )
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_model_empty_suffix_raises_validation_error -v
```

Expected: `FAILED` — `"headwater/"` passes `.+` check? No — `.+` requires at least one character after `/`, so this should already pass. Run to confirm either way.

**Step 3: No implementation change needed if AC9 already passes due to regex**

If the test passes, note it in the commit message. If it fails, verify the regex pattern `r"headwater/.+"` is correct (`.+` requires at least one char).

**Step 4: Run full test file**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py -v
```

Expected: all tests `PASSED`

---

### TDD Cycle 4 — Fulfills AC12: `role="tool"` with `tool_call_id=None` → 400

**Step 1: Write the failing test**

```python
def test_tool_message_missing_tool_call_id_raises():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError) as exc_info:
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "tool", "content": "result", "tool_call_id": None},
            ],
        )
    errors = exc_info.value.errors()
    assert any("tool_call_id is required" in str(e["msg"]) for e in errors)
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_tool_message_missing_tool_call_id_raises -v
```

Expected: `FAILED` — no validation error raised

**Step 3: Add tool message validation to `_validate_request`**

```python
@model_validator(mode="after")
def _validate_request(self) -> OpenAIChatRequest:
    if self.stream:
        raise ValueError("Streaming is not supported on this endpoint.")
    import re
    if not re.fullmatch(r"headwater/.+", self.model):
        raise ValueError(
            "model must be 'headwater/<model_name>' with a non-empty model name. "
            f"Got: {self.model!r}"
        )
    for msg in self.messages:
        if msg.role == "tool" and msg.tool_call_id is None:
            raise ValueError("tool_call_id is required for messages with role='tool'.")
    return self
```

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_tool_message_missing_tool_call_id_raises -v
```

Expected: `PASSED`

---

### TDD Cycle 5 — Fulfills AC13: `role="assistant"` with `content=None` → 400

**Step 1: Write the failing test**

```python
def test_assistant_null_content_raises():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError) as exc_info:
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": None},
            ],
        )
    errors = exc_info.value.errors()
    assert any("null content" in str(e["msg"]) for e in errors)
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_assistant_null_content_raises -v
```

Expected: `FAILED`

**Step 3: Add assistant null content check to `_validate_request`**

```python
    for msg in self.messages:
        if msg.role == "tool" and msg.tool_call_id is None:
            raise ValueError("tool_call_id is required for messages with role='tool'.")
        if msg.role == "assistant" and msg.content is None:
            raise ValueError(
                "Assistant messages with null content are not supported. "
                "While null content is valid per OpenAI spec (e.g. for tool-call-only turns), "
                "Conduit requires at least one payload field on AssistantMessage."
            )
```

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py -v
```

Expected: all tests `PASSED`

**Step 5: Commit**

```bash
git add src/headwater_api/classes/conduit_classes/openai_compat.py \
        tests/conduit_classes/test_openai_compat.py
git commit -m "feat: add model prefix, message validation to OpenAIChatRequest (AC8, AC9, AC12, AC13)"
```

---

## Task 3: headwater-api — `response_format` validation and schema serialization

**Files:**
- Modify: `headwater-api/tests/conduit_classes/test_openai_compat.py`

(No changes to `openai_compat.py` — `ResponseFormat` with `type: Literal["json_schema"]` already rejects `"text"` and `"json_object"` via Pydantic; `name` is already required.)

---

### TDD Cycle 6 — Fulfills AC14: `response_format: {"type": "text"}` → 422

**Step 1: Write the failing test**

```python
def test_response_format_type_text_raises():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError):
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "Hello"}],
            response_format={"type": "text"},
        )
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_response_format_type_text_raises -v
```

Expected: `FAILED` (if so, `ResponseFormat` Literal needs to already reject it — likely passes if Pydantic is enforcing `Literal["json_schema"]`)

**Step 3: Confirm implementation — no change needed**

`type: Literal["json_schema"]` on `ResponseFormat` already rejects any other value. If the test passes without code changes, that's correct.

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_response_format_type_text_raises -v
```

Expected: `PASSED`

---

### TDD Cycle 7 — Fulfills AC15: `response_format: {"type": "json_object"}` → 422

**Step 1: Write the failing test**

```python
def test_response_format_type_json_object_raises():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError):
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "Hello"}],
            response_format={"type": "json_object"},
        )
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_response_format_type_json_object_raises -v
```

**Step 3: No implementation change needed** — same Literal enforcement as AC14.

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_response_format_type_json_object_raises -v
```

Expected: `PASSED`

---

### TDD Cycle 8 — Fulfills AC16: `response_format.json_schema` missing `name` → 422

**Step 1: Write the failing test**

```python
def test_response_format_missing_name_raises():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    with pytest.raises(ValidationError):
        OpenAIChatRequest(
            model="headwater/claude-sonnet-4-6",
            messages=[{"role": "user", "content": "Hello"}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    # "name" deliberately omitted
                    "schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
                },
            },
        )
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_response_format_missing_name_raises -v
```

**Step 3: No implementation change needed** — `name: str` (no default) on `JsonSchemaFormat` already requires it.

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_response_format_missing_name_raises -v
```

Expected: `PASSED`

---

### TDD Cycle 9 — Fulfills AC20: `model_dump_json(by_alias=True)` serializes `schema_` as `"schema"`

**Step 1: Write the failing test**

```python
import json

def test_schema_field_serialized_as_schema_by_alias():
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest
    request = OpenAIChatRequest(
        model="headwater/claude-sonnet-4-6",
        messages=[{"role": "user", "content": "Hello"}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "my_schema",
                "schema": {"type": "object"},
            },
        },
    )
    serialized = json.loads(request.model_dump_json(by_alias=True))
    assert "schema" in serialized["response_format"]["json_schema"]
    assert "schema_" not in serialized["response_format"]["json_schema"]
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py::test_schema_field_serialized_as_schema_by_alias -v
```

Expected: `FAILED` if `by_alias` isn't working; `PASSED` if Pydantic handles it correctly already.

**Step 3: No implementation change needed** — `Field(alias="schema")` already handles this.

**Step 4: Run full test file**

```bash
uv run pytest tests/conduit_classes/test_openai_compat.py -v
```

Expected: all `PASSED`

**Step 5: Commit**

```bash
git add tests/conduit_classes/test_openai_compat.py
git commit -m "test: verify response_format and schema serialization (AC14, AC15, AC16, AC20)"
```

---

## Task 4: headwater-api — export new classes

**Files:**
- Modify: `headwater-api/src/headwater_api/classes/conduit_classes/openai_compat.py` (add `__all__`)
- Modify: `headwater-api/src/headwater_api/classes/__init__.py`

**Step 1: Add `__all__` to `openai_compat.py`**

```python
__all__ = [
    "OpenAIChatMessage",
    "JsonSchemaFormat",
    "ResponseFormat",
    "OpenAIChatRequest",
]
```

**Step 2: Add imports to `headwater_api/classes/__init__.py`**

Add after the existing reranker imports:

```python
from headwater_api.classes.conduit_classes.openai_compat import (
    OpenAIChatMessage,
    JsonSchemaFormat,
    ResponseFormat,
    OpenAIChatRequest,
)
```

Add to `__all__`:

```python
"OpenAIChatMessage",
"JsonSchemaFormat",
"ResponseFormat",
"OpenAIChatRequest",
```

**Step 3: Verify imports resolve**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-api
uv run python -c "from headwater_api.classes import OpenAIChatRequest; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add src/headwater_api/classes/conduit_classes/openai_compat.py \
        src/headwater_api/classes/__init__.py
git commit -m "feat: export OpenAI compat models from headwater_api.classes"
```

---

## Task 5: headwater-server — `conduit_openai_service` with model store error handling

**Files:**
- Create: `headwater-server/src/headwater_server/services/conduit_service/conduit_openai_service.py`
- Create: `headwater-server/tests/__init__.py`
- Create: `headwater-server/tests/conduit_service/__init__.py`
- Create: `headwater-server/tests/conduit_service/test_conduit_openai_service.py`
- Create: `headwater-server/tests/conftest.py`

---

### TDD Cycle 10 — Fulfills AC10: unrecognized model → HTTP 400

**Step 1: Write conftest.py and the failing test**

```python
# headwater-server/tests/conftest.py
import pytest
from unittest.mock import MagicMock, AsyncMock
from conduit.domain.result.response_metadata import StopReason


def make_mock_result(
    content: str = "Hello, world!",
    stop_reason=None,
    input_tokens: int = 10,
    output_tokens: int = 5,
    parsed=None,
):
    if stop_reason is None:
        stop_reason = StopReason.STOP
    message = MagicMock()
    message.__str__ = MagicMock(return_value=content)
    message.parsed = parsed
    metadata = MagicMock()
    metadata.stop_reason = stop_reason
    metadata.input_tokens = input_tokens
    metadata.output_tokens = output_tokens
    metadata.cache_hit = False
    metadata.duration = 100.0
    result = MagicMock()
    result.message = message
    result.metadata = metadata
    return result


VALID_PAYLOAD = {
    "model": "headwater/claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Hello"}],
}


@pytest.fixture
def client():
    from headwater_server.server.headwater import app
    from fastapi.testclient import TestClient
    return TestClient(app)
```

```python
# headwater-server/tests/conduit_service/test_conduit_openai_service.py
from unittest.mock import patch
from tests.conftest import VALID_PAYLOAD, make_mock_result


def test_unrecognized_model_returns_400(client):
    """AC10: unrecognized model name after prefix strip → HTTP 400"""
    bad_payload = {**VALID_PAYLOAD, "model": "headwater/nonexistent-model-xyz"}
    with patch(
        "conduit.core.model.models.modelstore.ModelStore.validate_model",
        side_effect=ValueError("Model not found"),
    ):
        response = client.post("/conduit/v1/chat/completions", json=bad_payload)
    assert response.status_code == 400
    assert "nonexistent-model-xyz" in response.json()["detail"]
```

**Step 2: Run to verify it fails**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_unrecognized_model_returns_400 -v -p no:pdb
```

Expected: `FAILED` — route `404` (service file doesn't exist yet)

**Step 3: Write minimal service**

```python
# headwater-server/src/headwater_server/services/conduit_service/conduit_openai_service.py
from __future__ import annotations
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest

logger = logging.getLogger(__name__)


async def conduit_openai_service(request: OpenAIChatRequest) -> dict:
    from conduit.core.model.model_async import ModelAsync
    from conduit.core.model.models.modelstore import ModelStore
    from conduit.domain.config.conduit_options import ConduitOptions
    from conduit.domain.message.message import AssistantMessage, SystemMessage, ToolMessage, UserMessage
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

    # 1. Validate model
    try:
        model_name = ModelStore.validate_model(request.conduit_model)
    except FileNotFoundError as exc:
        logger.error("Model store unavailable: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Model store unavailable. Server configuration error.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unrecognized model: '{request.conduit_model}'. Check ModelStore for supported models.",
        ) from exc

    # 2. Convert messages
    messages = []
    for msg in request.messages:
        if msg.role == "system":
            messages.append(SystemMessage(content=msg.content))
        elif msg.role == "user":
            messages.append(UserMessage(content=msg.content, name=msg.name))
        elif msg.role == "assistant":
            messages.append(AssistantMessage(content=msg.content))
        elif msg.role == "tool":
            messages.append(ToolMessage(
                content=str(msg.content),
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            ))

    # Reject messages-only-system edge case
    non_system = [m for m in request.messages if m.role != "system"]
    if not non_system:
        raise HTTPException(
            status_code=400,
            detail="messages must contain at least one non-system message.",
        )

    # 3. Build GenerationParams
    params_kwargs: dict = {"model": model_name}
    if request.temperature is not None:
        params_kwargs["temperature"] = request.temperature
    if request.top_p is not None:
        params_kwargs["top_p"] = request.top_p
    if request.max_tokens is not None:
        params_kwargs["max_tokens"] = request.max_tokens
    if request.normalized_stop is not None:
        params_kwargs["stop"] = request.normalized_stop
    if request.response_format is not None:
        params_kwargs["response_model_schema"] = request.response_format.json_schema.schema_

    params = GenerationParams(**params_kwargs)

    # 4. Build ConduitOptions
    options = ConduitOptions(
        project_name="headwater",
        verbosity=Verbosity.SILENT,
        include_history=False,
        use_cache=request.use_cache,
    )

    # 5. Build GenerationRequest and query
    gen_request = GenerationRequest(
        messages=messages,
        params=params,
        options=options,
        use_cache=request.use_cache,
        include_history=False,
    )

    model = ModelAsync(model_name)
    result = await model.query(gen_request)

    # 6. Content coercion
    if request.response_format is not None:
        if result.message.parsed is None:
            logger.error("Structured output failed: parsed=None for model=%s", model_name)
            raise HTTPException(
                status_code=500,
                detail="Structured output failed: instructor did not return a parsed result.",
            )
        from pydantic import BaseModel as PydanticBaseModel
        if isinstance(result.message.parsed, PydanticBaseModel):
            content = result.message.parsed.model_dump_json()
        elif isinstance(result.message.parsed, list):
            content = json.dumps([
                item.model_dump() if isinstance(item, PydanticBaseModel) else item
                for item in result.message.parsed
            ])
        else:
            content = json.dumps(result.message.parsed)
    else:
        content = str(result.message)
        if not content:
            logger.error("Model returned empty response: model=%s", model_name)
            raise HTTPException(status_code=500, detail="Model returned an empty response.")

    # 7. Map finish_reason
    _stop_map = {
        StopReason.STOP: "stop",
        StopReason.LENGTH: "length",
        StopReason.TOOL_CALLS: "tool_calls",
        StopReason.CONTENT_FILTER: "content_filter",
        StopReason.ERROR: "error",
    }
    finish_reason = _stop_map.get(result.metadata.stop_reason)
    if finish_reason is None:
        logger.warning(
            "Unknown StopReason '%s', defaulting finish_reason to 'error'",
            result.metadata.stop_reason,
        )
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
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": result.metadata.input_tokens,
            "completion_tokens": result.metadata.output_tokens,
            "total_tokens": result.metadata.input_tokens + result.metadata.output_tokens,
        },
    }
```

**Step 4: Run to verify it passes** (still fails — route not registered yet)

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_unrecognized_model_returns_400 -v -p no:pdb
```

Expected: still `FAILED` — route not yet wired

---

## Task 6: headwater-server — register route in `ConduitServerAPI`

**Files:**
- Modify: `headwater-server/src/headwater_server/api/conduit_server_api.py`

**Step 1: Add route to `register_routes()`**

Add after the existing `conduit_tokenize` route:

```python
@self.app.post("/conduit/v1/chat/completions")
async def conduit_openai_chat(request: OpenAIChatRequest) -> dict:
    from headwater_server.services.conduit_service.conduit_openai_service import (
        conduit_openai_service,
    )
    return await conduit_openai_service(request)
```

Add `OpenAIChatRequest` to the import block at the top of `conduit_server_api.py`:

```python
from headwater_api.classes import (
    GenerationRequest,
    GenerationResponse,
    BatchRequest,
    BatchResponse,
    TokenizationRequest,
    TokenizationResponse,
    OpenAIChatRequest,
)
```

**Step 2: Verify the service test now passes**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_unrecognized_model_returns_400 -v -p no:pdb
```

Expected: `PASSED`

**Step 3: Commit**

```bash
git add src/headwater_server/services/conduit_service/conduit_openai_service.py \
        src/headwater_server/api/conduit_server_api.py \
        tests/__init__.py \
        tests/conftest.py \
        tests/conduit_service/__init__.py \
        tests/conduit_service/test_conduit_openai_service.py
git commit -m "feat: add conduit_openai_service and route registration (AC10)"
```

---

## Task 7: headwater-server — model store unavailable and basic response tests

**Files:**
- Modify: `headwater-server/tests/conduit_service/test_conduit_openai_service.py`

---

### TDD Cycle 11 — Fulfills AC11: missing model store → HTTP 502

**Step 1: Write the failing test**

```python
def test_model_store_unavailable_returns_502(client):
    """AC11: missing/corrupt aliases.json or models.json → HTTP 502"""
    with patch(
        "conduit.core.model.models.modelstore.ModelStore.validate_model",
        side_effect=FileNotFoundError("aliases.json not found"),
    ):
        response = client.post("/conduit/v1/chat/completions", json=VALID_PAYLOAD)
    assert response.status_code == 502
    assert "Model store unavailable" in response.json()["detail"]
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_model_store_unavailable_returns_502 -v -p no:pdb
```

Expected: `FAILED` (or passes — implementation already handles this)

**Step 3: No implementation change needed** — `FileNotFoundError` → 502 already implemented.

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_model_store_unavailable_returns_502 -v -p no:pdb
```

Expected: `PASSED`

---

### TDD Cycle 12 — Fulfills AC1: valid request → HTTP 200, body passes `ChatCompletion.model_validate()`

**Step 1: Write the failing test**

```python
from unittest.mock import patch, MagicMock, AsyncMock


def test_valid_request_returns_200_and_validates_as_chat_completion(client):
    """AC1: valid request → HTTP 200, body passes ChatCompletion.model_validate()"""
    from openai.types.chat import ChatCompletion
    mock_result = make_mock_result()
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/conduit/v1/chat/completions", json=VALID_PAYLOAD)
    assert response.status_code == 200
    ChatCompletion.model_validate(response.json())  # raises if shape is wrong
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_valid_request_returns_200_and_validates_as_chat_completion -v -p no:pdb
```

Expected: `FAILED` — likely import error or shape mismatch

**Step 3: Install `openai` in headwater-server dev deps**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-server
uv add openai
```

Re-run test; fix any shape issues in the service response dict if `ChatCompletion.model_validate()` fails.

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_valid_request_returns_200_and_validates_as_chat_completion -v -p no:pdb
```

Expected: `PASSED`

---

### TDD Cycle 13 — Fulfills AC2: `choices[0].message.content` is a non-empty string

**Step 1: Write the failing test**

```python
def test_response_content_is_non_empty_string(client):
    """AC2: choices[0].message.content is a non-empty string"""
    mock_result = make_mock_result(content="This is the response.")
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/conduit/v1/chat/completions", json=VALID_PAYLOAD)
    content = response.json()["choices"][0]["message"]["content"]
    assert isinstance(content, str)
    assert len(content) > 0
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_response_content_is_non_empty_string -v -p no:pdb
```

**Step 3: No implementation change needed** — `str(result.message)` already coerces to string; guard already raises 500 on empty.

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_response_content_is_non_empty_string -v -p no:pdb
```

Expected: `PASSED`

---

### TDD Cycle 14 — Fulfills AC3: `finish_reason` is a valid value

**Step 1: Write the failing test**

```python
def test_finish_reason_is_valid_value(client):
    """AC3: finish_reason is one of the allowed OpenAI values"""
    from conduit.domain.result.response_metadata import StopReason
    VALID_FINISH_REASONS = {"stop", "length", "tool_calls", "content_filter", "error"}
    mock_result = make_mock_result(stop_reason=StopReason.STOP)
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/conduit/v1/chat/completions", json=VALID_PAYLOAD)
    finish_reason = response.json()["choices"][0]["finish_reason"]
    assert finish_reason in VALID_FINISH_REASONS
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_finish_reason_is_valid_value -v -p no:pdb
```

**Step 3: No implementation change needed.**

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_finish_reason_is_valid_value -v -p no:pdb
```

Expected: `PASSED`

---

### TDD Cycle 15 — Fulfills AC4: `usage.total_tokens == prompt_tokens + completion_tokens`

**Step 1: Write the failing test**

```python
def test_usage_total_equals_prompt_plus_completion(client):
    """AC4: usage.total_tokens == usage.prompt_tokens + usage.completion_tokens"""
    mock_result = make_mock_result(input_tokens=42, output_tokens=17)
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/conduit/v1/chat/completions", json=VALID_PAYLOAD)
    usage = response.json()["usage"]
    assert usage["prompt_tokens"] == 42
    assert usage["completion_tokens"] == 17
    assert usage["total_tokens"] == 59
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_usage_total_equals_prompt_plus_completion -v -p no:pdb
```

**Step 3: No implementation change needed.**

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_usage_total_equals_prompt_plus_completion -v -p no:pdb
```

Expected: `PASSED`

---

### TDD Cycle 16 — Fulfills AC5: `model` in response echoes request's `model` field

**Step 1: Write the failing test**

```python
def test_response_model_echoes_request_model(client):
    """AC5: response.model is identical to request.model including 'headwater/' prefix"""
    mock_result = make_mock_result()
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/conduit/v1/chat/completions", json=VALID_PAYLOAD)
    assert response.json()["model"] == VALID_PAYLOAD["model"]
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_response_model_echoes_request_model -v -p no:pdb
```

**Step 3: No implementation change needed** — `"model": request.model` already echoes it.

**Step 4: Run all service tests**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py -v -p no:pdb
```

Expected: all `PASSED`

**Step 5: Commit**

```bash
git add tests/conduit_service/test_conduit_openai_service.py
git commit -m "test: basic response shape tests (AC11, AC1, AC2, AC3, AC4, AC5)"
```

---

## Task 8: headwater-server — structured output tests

**Files:**
- Modify: `headwater-server/tests/conduit_service/test_conduit_openai_service.py`

---

### TDD Cycle 17 — Fulfills AC17: structured output returns valid JSON string in content

**Step 1: Write the failing test**

```python
def test_structured_output_returns_valid_json_content(client):
    """AC17: request with valid response_format.json_schema → content is valid JSON string"""
    from pydantic import BaseModel as PydanticBaseModel

    class FakeAnswer(PydanticBaseModel):
        answer: str

    parsed_instance = FakeAnswer(answer="Paris")
    mock_result = make_mock_result(parsed=parsed_instance)

    payload = {
        **VALID_PAYLOAD,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "answer_schema",
                "schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
            },
        },
    }
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/conduit/v1/chat/completions", json=payload)

    assert response.status_code == 200
    content = response.json()["choices"][0]["message"]["content"]
    import json
    parsed = json.loads(content)  # raises if not valid JSON
    assert parsed["answer"] == "Paris"
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_structured_output_returns_valid_json_content -v -p no:pdb
```

**Step 3: No implementation change needed** — service already handles `isinstance(result.message.parsed, PydanticBaseModel)`.

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_structured_output_returns_valid_json_content -v -p no:pdb
```

Expected: `PASSED`

---

### TDD Cycle 18 — Fulfills AC18: `parsed=None` with `response_format` → HTTP 500

**Step 1: Write the failing test**

```python
def test_structured_output_parsed_none_returns_500(client):
    """AC18: response_format present but instructor returns parsed=None → HTTP 500"""
    mock_result = make_mock_result(parsed=None)  # parsed=None simulates instructor failure

    payload = {
        **VALID_PAYLOAD,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "my_schema",
                "schema": {"type": "object"},
            },
        },
    }
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="claude-sonnet-4-6"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/conduit/v1/chat/completions", json=payload)

    assert response.status_code == 500
    assert "Structured output failed" in response.json()["detail"]
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py::test_structured_output_parsed_none_returns_500 -v -p no:pdb
```

**Step 3: No implementation change needed.**

**Step 4: Run all service tests**

```bash
uv run pytest tests/conduit_service/test_conduit_openai_service.py -v -p no:pdb
```

Expected: all `PASSED`

**Step 5: Commit**

```bash
git add tests/conduit_service/test_conduit_openai_service.py
git commit -m "test: structured output success and failure paths (AC17, AC18)"
```

---

## Task 9: headwater-server — OpenAPI visibility

**Files:**
- Create: `headwater-server/tests/api/test_openapi.py`
- Create: `headwater-server/tests/api/__init__.py`

---

### TDD Cycle 19 — Fulfills AC6: `/openapi.json` contains the endpoint path

**Step 1: Write the failing test**

```python
# headwater-server/tests/api/test_openapi.py
def test_openapi_schema_contains_endpoint(client):
    """AC6: GET /openapi.json response contains /conduit/v1/chat/completions"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/conduit/v1/chat/completions" in response.json()["paths"]
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/api/test_openapi.py::test_openapi_schema_contains_endpoint -v -p no:pdb
```

Expected: `FAILED` if route not yet in OpenAPI, `PASSED` if it is (route is already registered)

**Step 3: No implementation change needed** — FastAPI auto-generates OpenAPI from registered routes.

**Step 4: Run to verify it passes**

```bash
uv run pytest tests/api/test_openapi.py -v -p no:pdb
```

Expected: `PASSED`

**Step 5: Run full server test suite**

```bash
uv run pytest tests/ -v -p no:pdb
```

Expected: all `PASSED`

**Step 6: Commit**

```bash
git add tests/api/__init__.py tests/api/test_openapi.py
git commit -m "test: verify endpoint appears in OpenAPI schema (AC6)"
```

---

## Task 10: headwater-client — `OpenAICompatAsyncAPI` and `HeadwaterAsyncClient` wiring

**Files:**
- Modify: `headwater-client/pyproject.toml` (add `openai`, `pytest`, `pytest-asyncio`)
- Create: `headwater-client/src/headwater_client/api/openai_async_api.py`
- Modify: `headwater-client/src/headwater_client/client/headwater_client_async.py`
- Create: `headwater-client/tests/__init__.py`
- Create: `headwater-client/tests/api/__init__.py`
- Create: `headwater-client/tests/api/test_openai_async_api.py`

---

### TDD Cycle 20 — Fulfills AC19: `chat_completions()` returns `openai.types.chat.ChatCompletion`

**Step 1: Add dependencies to `headwater-client/pyproject.toml`**

```toml
dependencies = [
    "dbclients",
    "headwater_api",
    "siphon_api",
    "httpx",
    "openai",
]
```

Also add a `[tool.pytest.ini_options]` section:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

And add test deps:

```toml
[project.optional-dependencies]
test = ["pytest", "pytest-asyncio"]
```

Then sync:

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-client
uv sync
```

**Step 2: Write the failing test**

```python
# headwater-client/tests/api/test_openai_async_api.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json


FAKE_CHAT_COMPLETION = {
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "headwater/claude-sonnet-4-6",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello!"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


async def test_chat_completions_returns_chat_completion_instance():
    """AC19: chat_completions() returns openai.types.chat.ChatCompletion"""
    from openai.types.chat import ChatCompletion
    from headwater_client.api.openai_async_api import OpenAICompatAsyncAPI
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest

    mock_transport = MagicMock()
    api = OpenAICompatAsyncAPI(mock_transport)
    api._request = AsyncMock(return_value=json.dumps(FAKE_CHAT_COMPLETION))

    request = OpenAIChatRequest(
        model="headwater/claude-sonnet-4-6",
        messages=[{"role": "user", "content": "Hello"}],
    )
    result = await api.chat_completions(request)

    assert isinstance(result, ChatCompletion)
    assert result.model == "headwater/claude-sonnet-4-6"
    assert result.choices[0].message.content == "Hello!"
```

**Step 3: Run to verify it fails**

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-client
uv run pytest tests/api/test_openai_async_api.py -v
```

Expected: `FAILED` — `openai_async_api.py` doesn't exist

**Step 4: Create `openai_async_api.py`**

```python
# headwater-client/src/headwater_client/api/openai_async_api.py
from __future__ import annotations
from headwater_client.api.base_async_api import BaseAsyncAPI
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from headwater_api.classes.conduit_classes.openai_compat import OpenAIChatRequest


class OpenAICompatAsyncAPI(BaseAsyncAPI):
    async def chat_completions(self, request: OpenAIChatRequest) -> object:
        from openai.types.chat import ChatCompletion  # lazy import
        response = await self._request(
            "POST",
            "/conduit/v1/chat/completions",
            json_payload=request.model_dump_json(by_alias=True),
        )
        return ChatCompletion.model_validate_json(response)
```

**Step 5: Run to verify it passes**

```bash
uv run pytest tests/api/test_openai_async_api.py -v
```

Expected: `PASSED`

**Step 6: Wire into `HeadwaterAsyncClient`**

Add to `headwater_client_async.py` imports:

```python
from headwater_client.api.openai_async_api import OpenAICompatAsyncAPI
```

Add to `__init__`:

```python
self.openai = OpenAICompatAsyncAPI(self._transport)
```

**Step 7: Verify client attribute accessible**

```bash
uv run python -c "
from headwater_client.client.headwater_client_async import HeadwaterAsyncClient
c = HeadwaterAsyncClient()
print(type(c.openai))
"
```

Expected: `<class 'headwater_client.api.openai_async_api.OpenAICompatAsyncAPI'>`

**Step 8: Run full client test suite**

```bash
uv run pytest tests/ -v
```

Expected: all `PASSED`

**Step 9: Commit**

```bash
git add pyproject.toml \
        src/headwater_client/api/openai_async_api.py \
        src/headwater_client/client/headwater_client_async.py \
        tests/__init__.py \
        tests/api/__init__.py \
        tests/api/test_openai_async_api.py
git commit -m "feat: add OpenAICompatAsyncAPI and wire into HeadwaterAsyncClient (AC19)"
```

---

## Final verification

Run all three packages' test suites:

```bash
cd /Users/bianders/Brian_Code/headwater/headwater-api && uv run pytest tests/ -v
cd /Users/bianders/Brian_Code/headwater/headwater-server && uv run pytest tests/ -v -p no:pdb
cd /Users/bianders/Brian_Code/headwater/headwater-client && uv run pytest tests/ -v
```

All expected: `PASSED`

---

## AC coverage index

| AC | Task | TDD Cycle |
|---|---|---|
| AC1 | 7 | 12 |
| AC2 | 7 | 13 |
| AC3 | 7 | 14 |
| AC4 | 7 | 15 |
| AC5 | 7 | 16 |
| AC6 | 9 | 19 |
| AC7 | 1 | 1 |
| AC8 | 2 | 2 |
| AC9 | 2 | 3 |
| AC10 | 5 | 10 |
| AC11 | 7 | 11 |
| AC12 | 2 | 4 |
| AC13 | 2 | 5 |
| AC14 | 3 | 6 |
| AC15 | 3 | 7 |
| AC16 | 3 | 8 |
| AC17 | 8 | 17 |
| AC18 | 8 | 18 |
| AC19 | 10 | 20 |
| AC20 | 3 | 9 |
