# Anthropic-Compatible API Endpoint Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan.

**Goal:** Add an Anthropic Messages API-compatible `POST /v1/messages` endpoint to headwater so Claude Code can route through it using `ANTHROPIC_BASE_URL`.

**Architecture:** Mirrors the existing OpenAI-compat layer exactly — Pydantic models in `headwater-api`, service logic in `headwater-server/services/conduit_service/`, route registration in `ConduitServerAPI`. Phase 1 is non-streaming (rejects `stream=true` with 400). Phase 2 replaces that rejection with fake SSE: full generation completes first, then the response is emitted as a valid Anthropic SSE event sequence in one burst using FastAPI `StreamingResponse`.

**Tech Stack:** FastAPI, Pydantic v2, conduit (`ModelAsync`, `GenerationRequest`), `fastapi.responses.StreamingResponse`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `headwater-api/src/headwater_api/classes/conduit_classes/anthropic_compat.py` | `AnthropicMessage`, `AnthropicRequest` Pydantic models |
| Modify | `headwater-api/src/headwater_api/classes/__init__.py` | Export new classes |
| Create | `headwater-server/src/headwater_server/services/conduit_service/conduit_anthropic_service.py` | Non-streaming service: translate conduit result → Anthropic Message dict |
| Create | `headwater-server/src/headwater_server/services/conduit_service/conduit_anthropic_stream_service.py` | Fake-SSE service: generates then emits Anthropic SSE event sequence |
| Modify | `headwater-server/src/headwater_server/api/conduit_server_api.py` | Register `POST /v1/messages` |
| Create | `headwater-server/tests/conduit_service/test_conduit_anthropic_service.py` | All tests for Phase 1 + Phase 2 |

---

## Task 1: Anthropic compat Pydantic models *(AC-1)*

**Files:**
- Create: `headwater-api/src/headwater_api/classes/conduit_classes/anthropic_compat.py`
- Modify: `headwater-api/src/headwater_api/classes/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `headwater-server/tests/conduit_service/test_conduit_anthropic_service.py`:

```python
from __future__ import annotations
import pytest
from headwater_api.classes import AnthropicMessage, AnthropicRequest


def test_anthropic_request_minimal():
    """AC-1: AnthropicRequest accepts model, max_tokens, messages"""
    req = AnthropicRequest(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[AnthropicMessage(role="user", content="Hello")],
    )
    assert req.model == "claude-sonnet-4-6"
    assert req.max_tokens == 1024
    assert req.stream is False


def test_anthropic_request_with_system():
    """AC-1: system is optional, defaults to None"""
    req = AnthropicRequest(
        model="gpt-oss:latest",
        max_tokens=512,
        messages=[AnthropicMessage(role="user", content="Hi")],
        system="You are a helpful assistant.",
    )
    assert req.system == "You are a helpful assistant."


def test_anthropic_message_content_as_blocks():
    """AC-1: content can be a list of content blocks"""
    msg = AnthropicMessage(
        role="user",
        content=[{"type": "text", "text": "Hello from block"}],
    )
    assert msg.content[0].text == "Hello from block"
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py::test_anthropic_request_minimal -v
```

Expected: `ImportError` — `AnthropicMessage` not in `headwater_api.classes`

- [ ] **Step 3: Write the models**

Create `headwater-api/src/headwater_api/classes/conduit_classes/anthropic_compat.py`:

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


__all__ = [
    "AnthropicContentBlock",
    "AnthropicMessage",
    "AnthropicRequest",
]


class AnthropicContentBlock(BaseModel):
    type: Literal["text"]
    text: str


class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[AnthropicContentBlock]


class AnthropicRequest(BaseModel):
    model: str
    max_tokens: int = Field(ge=1)
    messages: list[AnthropicMessage] = Field(min_length=1)
    system: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    stop_sequences: list[str] | None = None
    stream: bool = False
```

- [ ] **Step 4: Export from `__init__.py`**

In `headwater-api/src/headwater_api/classes/__init__.py`, add after the OpenAI compat block:

```python
# Anthropic compat
from headwater_api.classes.conduit_classes.anthropic_compat import (
    AnthropicContentBlock,
    AnthropicMessage,
    AnthropicRequest,
)
```

And add to `__all__`:
```python
    # Anthropic compat
    "AnthropicContentBlock",
    "AnthropicMessage",
    "AnthropicRequest",
```

- [ ] **Step 5: Run tests to verify passing**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py -v -k "AC-1 or anthropic_request or anthropic_message"
```

Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add headwater-api/src/headwater_api/classes/conduit_classes/anthropic_compat.py \
        headwater-api/src/headwater_api/classes/__init__.py \
        headwater-server/tests/conduit_service/test_conduit_anthropic_service.py
git commit -m "feat(AC-1): Anthropic compat Pydantic models"
```

---

## Task 2: Non-streaming service *(AC-2)*

**Files:**
- Create: `headwater-server/src/headwater_server/services/conduit_service/conduit_anthropic_service.py`
- Modify: `headwater-server/src/headwater_server/api/conduit_server_api.py`
- Modify: `headwater-server/tests/conduit_service/test_conduit_anthropic_service.py`

- [ ] **Step 1: Write the failing test**

Append to `headwater-server/tests/conduit_service/test_conduit_anthropic_service.py`:

```python
from unittest.mock import patch, MagicMock, AsyncMock
from tests.conftest import make_mock_result

VALID_ANTHROPIC_PAYLOAD = {
    "model": "gpt-oss:latest",
    "max_tokens": 512,
    "messages": [{"role": "user", "content": "Hello"}],
}


def test_anthropic_valid_request_returns_200(client):
    """AC-2: valid non-streaming request -> HTTP 200 with Anthropic Message shape"""
    mock_result = make_mock_result(content="Hi there!", input_tokens=10, output_tokens=5)
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=VALID_ANTHROPIC_PAYLOAD)
    assert response.status_code == 200


def test_anthropic_response_shape(client):
    """AC-2: response has type, role, content list, stop_reason, usage"""
    mock_result = make_mock_result(content="Hi there!", input_tokens=10, output_tokens=5)
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=VALID_ANTHROPIC_PAYLOAD)
    body = response.json()
    assert body["type"] == "message"
    assert body["role"] == "assistant"
    assert isinstance(body["content"], list)
    assert body["content"][0]["type"] == "text"
    assert body["content"][0]["text"] == "Hi there!"
    assert body["stop_reason"] == "end_turn"
    assert body["usage"]["input_tokens"] == 10
    assert body["usage"]["output_tokens"] == 5


def test_anthropic_response_model_echoes_request(client):
    """AC-2: response.model matches request.model"""
    mock_result = make_mock_result()
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=VALID_ANTHROPIC_PAYLOAD)
    assert response.json()["model"] == VALID_ANTHROPIC_PAYLOAD["model"]
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py::test_anthropic_valid_request_returns_200 -v
```

Expected: FAIL with 404 — route not registered yet

- [ ] **Step 3: Write the service**

Create `headwater-server/src/headwater_server/services/conduit_service/conduit_anthropic_service.py`:

```python
from __future__ import annotations
import logging
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from headwater_api.classes.conduit_classes.anthropic_compat import AnthropicRequest

logger = logging.getLogger(__name__)

_STOP_MAP = {
    "STOP": "end_turn",
    "LENGTH": "max_tokens",
    "TOOL_CALLS": "tool_use",
    "CONTENT_FILTER": "end_turn",
    "ERROR": "end_turn",
}


async def conduit_anthropic_service(request: AnthropicRequest) -> dict:
    from conduit.core.model.model_async import ModelAsync
    from conduit.core.model.models.modelstore import ModelStore
    from conduit.domain.config.conduit_options import ConduitOptions
    from conduit.domain.message.message import AssistantMessage, SystemMessage, UserMessage
    from conduit.domain.request.generation_params import GenerationParams
    from conduit.domain.request.request import GenerationRequest
    from conduit.utils.progress.verbosity import Verbosity
    from fastapi import HTTPException

    logger.info(
        "Anthropic-compat request: model=%s stream=%s",
        request.model,
        request.stream,
    )

    # 1. Validate model
    try:
        model_name = ModelStore.validate_model(request.model)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=502, detail="Model store unavailable.") from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unrecognized model: '{request.model}'.",
        ) from exc

    # 2. Build message list
    messages = []
    if request.system:
        messages.append(SystemMessage(content=request.system))
    for msg in request.messages:
        content = msg.content if isinstance(msg.content, str) else " ".join(
            b.text for b in msg.content if b.type == "text"
        )
        if msg.role == "user":
            messages.append(UserMessage(content=content))
        else:
            messages.append(AssistantMessage(content=content))

    # 3. Build params
    params_kwargs: dict = {"model": model_name}
    if request.temperature is not None:
        params_kwargs["temperature"] = request.temperature
    if request.top_p is not None:
        params_kwargs["top_p"] = request.top_p
    if request.max_tokens is not None:
        params_kwargs["max_tokens"] = request.max_tokens
    if request.stop_sequences:
        params_kwargs["stop"] = request.stop_sequences
    params = GenerationParams(**params_kwargs)

    # 4. Query
    options = ConduitOptions(
        project_name="headwater",
        verbosity=Verbosity.SILENT,
        include_history=False,
    )
    gen_request = GenerationRequest(
        messages=messages,
        params=params,
        options=options,
        include_history=False,
    )
    model = ModelAsync(model_name)
    result = await model.query(gen_request)

    # 5. Build response
    content_text = str(result.message)
    stop_reason = _STOP_MAP.get(result.metadata.stop_reason.name, "end_turn")

    logger.info(
        "Anthropic-compat response: model=%s stop_reason=%s input=%d output=%d",
        model_name, stop_reason,
        result.metadata.input_tokens, result.metadata.output_tokens,
    )

    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content_text}],
        "model": request.model,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": result.metadata.input_tokens,
            "output_tokens": result.metadata.output_tokens,
        },
    }
```

- [ ] **Step 4: Register the route**

In `headwater-server/src/headwater_server/api/conduit_server_api.py`, add the import and route:

```python
from headwater_api.classes import (
    GenerationRequest,
    GenerationResponse,
    BatchRequest,
    BatchResponse,
    TokenizationRequest,
    TokenizationResponse,
    OpenAIChatRequest,
    AnthropicRequest,
)
```

Add inside `register_routes()` **before** the end of the method:

```python
        @self.app.post("/v1/messages")
        async def conduit_anthropic_messages(request: AnthropicRequest) -> dict:
            from headwater_server.services.conduit_service.conduit_anthropic_service import (
                conduit_anthropic_service,
            )
            return await conduit_anthropic_service(request)
```

- [ ] **Step 5: Run tests to verify passing**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py -v -k "valid_request or response_shape or response_model"
```

Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add headwater-server/src/headwater_server/services/conduit_service/conduit_anthropic_service.py \
        headwater-server/src/headwater_server/api/conduit_server_api.py \
        headwater-server/tests/conduit_service/test_conduit_anthropic_service.py
git commit -m "feat(AC-2): non-streaming /v1/messages returns Anthropic Message shape"
```

---

## Task 3: Phase 1 — reject `stream=true` with 400 *(AC-3)*

**Files:**
- Modify: `headwater-api/src/headwater_api/classes/conduit_classes/anthropic_compat.py`
- Modify: `headwater-server/tests/conduit_service/test_conduit_anthropic_service.py`

- [ ] **Step 1: Write the failing test**

Append to `test_conduit_anthropic_service.py`:

```python
def test_stream_true_returns_400(client):
    """AC-3: stream=true rejected with 400 in Phase 1"""
    payload = {**VALID_ANTHROPIC_PAYLOAD, "stream": True}
    response = client.post("/v1/messages", json=payload)
    assert response.status_code == 422
    assert "Streaming" in response.text
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py::test_stream_true_returns_400 -v
```

Expected: FAIL — `stream=true` currently accepted and attempted

- [ ] **Step 3: Add validator to `AnthropicRequest`**

In `headwater-api/src/headwater_api/classes/conduit_classes/anthropic_compat.py`, add the import and validator:

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator


__all__ = [
    "AnthropicContentBlock",
    "AnthropicMessage",
    "AnthropicRequest",
]


class AnthropicContentBlock(BaseModel):
    type: Literal["text"]
    text: str


class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[AnthropicContentBlock]


class AnthropicRequest(BaseModel):
    model: str
    max_tokens: int = Field(ge=1)
    messages: list[AnthropicMessage] = Field(min_length=1)
    system: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    stop_sequences: list[str] | None = None
    stream: bool = False

    @model_validator(mode="after")
    def _validate_stream(self) -> AnthropicRequest:
        if self.stream:
            raise ValueError("Streaming is not supported on this endpoint.")
        return self
```

- [ ] **Step 4: Run to verify passing**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py::test_stream_true_returns_400 -v
```

Expected: PASSED

- [ ] **Step 5: Run full test file to check no regressions**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add headwater-api/src/headwater_api/classes/conduit_classes/anthropic_compat.py \
        headwater-server/tests/conduit_service/test_conduit_anthropic_service.py
git commit -m "feat(AC-3): reject stream=true with 422 in Phase 1"
```

---

## Task 4: Unknown model returns 400 *(AC-4)*

**Files:**
- Modify: `headwater-server/tests/conduit_service/test_conduit_anthropic_service.py`

- [ ] **Step 1: Write the failing test**

Append to `test_conduit_anthropic_service.py`:

```python
def test_unknown_model_returns_400(client):
    """AC-4: unrecognized model -> HTTP 400"""
    payload = {**VALID_ANTHROPIC_PAYLOAD, "model": "nonexistent-model-xyz"}
    with patch(
        "conduit.core.model.models.modelstore.ModelStore.validate_model",
        side_effect=ValueError("Model not found"),
    ):
        response = client.post("/v1/messages", json=payload)
    assert response.status_code == 400
    assert "nonexistent-model-xyz" in response.json()["detail"]


def test_model_store_unavailable_returns_502(client):
    """AC-4: missing model store -> HTTP 502"""
    with patch(
        "conduit.core.model.models.modelstore.ModelStore.validate_model",
        side_effect=FileNotFoundError("aliases.json not found"),
    ):
        response = client.post("/v1/messages", json=VALID_ANTHROPIC_PAYLOAD)
    assert response.status_code == 502
    assert "unavailable" in response.json()["detail"]
```

- [ ] **Step 2: Run to verify these tests fail**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py::test_unknown_model_returns_400 tests/conduit_service/test_conduit_anthropic_service.py::test_model_store_unavailable_returns_502 -v
```

Expected: FAIL — error handling already exists in service from Task 2, so these should actually pass. If they do, proceed to step 3 without writing any new code.

- [ ] **Step 3: Verify and commit**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py -v
```

Expected: all PASSED

```bash
git add headwater-server/tests/conduit_service/test_conduit_anthropic_service.py
git commit -m "test(AC-4): error handling tests for unknown model and unavailable store"
```

---

## Task 5: Fake SSE streaming service *(AC-5)*

**Files:**
- Create: `headwater-server/src/headwater_server/services/conduit_service/conduit_anthropic_stream_service.py`
- Modify: `headwater-api/src/headwater_api/classes/conduit_classes/anthropic_compat.py` (remove stream validator)
- Modify: `headwater-server/src/headwater_server/api/conduit_server_api.py` (dispatch on `stream`)
- Modify: `headwater-server/tests/conduit_service/test_conduit_anthropic_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_conduit_anthropic_service.py`:

```python
import json

def _parse_sse_events(body: str) -> list[dict]:
    """Parse raw SSE body into list of {event, data} dicts."""
    events = []
    for block in body.split("\n\n"):
        lines = [l for l in block.strip().split("\n") if l]
        if not lines:
            continue
        event_type = None
        data = None
        for line in lines:
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_type and data is not None:
            events.append({"event": event_type, "data": data})
    return events


def test_stream_true_returns_event_stream(client):
    """AC-5: stream=true -> Content-Type: text/event-stream"""
    mock_result = make_mock_result(content="Streaming response.", input_tokens=10, output_tokens=4)
    payload = {**VALID_ANTHROPIC_PAYLOAD, "stream": True}
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


def test_stream_sse_event_sequence(client):
    """AC-5: SSE body contains valid Anthropic event sequence in correct order"""
    mock_result = make_mock_result(content="Hello!", input_tokens=8, output_tokens=3)
    payload = {**VALID_ANTHROPIC_PAYLOAD, "stream": True}
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=payload)
    events = _parse_sse_events(response.text)
    event_types = [e["event"] for e in events]
    assert event_types == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]


def test_stream_content_block_delta_has_text(client):
    """AC-5: content_block_delta carries the full response text"""
    mock_result = make_mock_result(content="Hello!", input_tokens=8, output_tokens=3)
    payload = {**VALID_ANTHROPIC_PAYLOAD, "stream": True}
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=payload)
    events = _parse_sse_events(response.text)
    delta_event = next(e for e in events if e["event"] == "content_block_delta")
    assert delta_event["data"]["delta"]["text"] == "Hello!"


def test_stream_message_delta_has_stop_reason(client):
    """AC-5: message_delta carries stop_reason"""
    mock_result = make_mock_result(content="Done.", input_tokens=5, output_tokens=2)
    payload = {**VALID_ANTHROPIC_PAYLOAD, "stream": True}
    with patch("conduit.core.model.models.modelstore.ModelStore.validate_model", return_value="gpt-oss:latest"), \
         patch("conduit.core.model.model_async.ModelAsync") as MockModel:
        mock_instance = MagicMock()
        mock_instance.query = AsyncMock(return_value=mock_result)
        MockModel.return_value = mock_instance
        response = client.post("/v1/messages", json=payload)
    events = _parse_sse_events(response.text)
    msg_delta = next(e for e in events if e["event"] == "message_delta")
    assert msg_delta["data"]["delta"]["stop_reason"] == "end_turn"
    assert msg_delta["data"]["usage"]["output_tokens"] == 2
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py::test_stream_true_returns_event_stream -v
```

Expected: FAIL with 422 — stream=true still rejected

- [ ] **Step 3: Remove stream validator from `AnthropicRequest`**

In `headwater-api/src/headwater_api/classes/conduit_classes/anthropic_compat.py`, remove the `model_validator` and the `model_validator` import:

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


__all__ = [
    "AnthropicContentBlock",
    "AnthropicMessage",
    "AnthropicRequest",
]


class AnthropicContentBlock(BaseModel):
    type: Literal["text"]
    text: str


class AnthropicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[AnthropicContentBlock]


class AnthropicRequest(BaseModel):
    model: str
    max_tokens: int = Field(ge=1)
    messages: list[AnthropicMessage] = Field(min_length=1)
    system: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    stop_sequences: list[str] | None = None
    stream: bool = False
```

- [ ] **Step 4: Write the fake SSE service**

Create `headwater-server/src/headwater_server/services/conduit_service/conduit_anthropic_stream_service.py`:

```python
from __future__ import annotations
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from headwater_api.classes.conduit_classes.anthropic_compat import AnthropicRequest

logger = logging.getLogger(__name__)

_STOP_MAP = {
    "STOP": "end_turn",
    "LENGTH": "max_tokens",
    "TOOL_CALLS": "tool_use",
    "CONTENT_FILTER": "end_turn",
    "ERROR": "end_turn",
}


def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _sse_generator(request: AnthropicRequest) -> AsyncGenerator[str, None]:
    from conduit.core.model.model_async import ModelAsync
    from conduit.core.model.models.modelstore import ModelStore
    from conduit.domain.config.conduit_options import ConduitOptions
    from conduit.domain.message.message import AssistantMessage, SystemMessage, UserMessage
    from conduit.domain.request.generation_params import GenerationParams
    from conduit.domain.request.request import GenerationRequest
    from conduit.utils.progress.verbosity import Verbosity
    from fastapi import HTTPException

    try:
        model_name = ModelStore.validate_model(request.model)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    messages = []
    if request.system:
        messages.append(SystemMessage(content=request.system))
    for msg in request.messages:
        content = msg.content if isinstance(msg.content, str) else " ".join(
            b.text for b in msg.content if b.type == "text"
        )
        if msg.role == "user":
            messages.append(UserMessage(content=content))
        else:
            messages.append(AssistantMessage(content=content))

    params_kwargs: dict = {"model": model_name}
    if request.temperature is not None:
        params_kwargs["temperature"] = request.temperature
    if request.top_p is not None:
        params_kwargs["top_p"] = request.top_p
    if request.max_tokens is not None:
        params_kwargs["max_tokens"] = request.max_tokens
    if request.stop_sequences:
        params_kwargs["stop"] = request.stop_sequences

    params = GenerationParams(**params_kwargs)
    options = ConduitOptions(
        project_name="headwater",
        verbosity=Verbosity.SILENT,
        include_history=False,
    )
    gen_request = GenerationRequest(
        messages=messages,
        params=params,
        options=options,
        include_history=False,
    )
    model = ModelAsync(model_name)
    result = await model.query(gen_request)

    content_text = str(result.message)
    stop_reason = _STOP_MAP.get(result.metadata.stop_reason.name, "end_turn")
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    logger.info(
        "Anthropic-compat stream response: model=%s stop_reason=%s input=%d output=%d",
        model_name, stop_reason,
        result.metadata.input_tokens, result.metadata.output_tokens,
    )

    yield _sse("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": request.model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": result.metadata.input_tokens,
                "output_tokens": 0,
            },
        },
    })
    yield _sse("content_block_start", {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""},
    })
    yield _sse("content_block_delta", {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": content_text},
    })
    yield _sse("content_block_stop", {
        "type": "content_block_stop",
        "index": 0,
    })
    yield _sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": result.metadata.output_tokens},
    })
    yield _sse("message_stop", {"type": "message_stop"})


async def conduit_anthropic_stream_service(request: AnthropicRequest):
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        _sse_generator(request),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
```

- [ ] **Step 5: Update the route to dispatch on `stream`**

In `headwater-server/src/headwater_server/api/conduit_server_api.py`, replace the `conduit_anthropic_messages` route:

```python
        @self.app.post("/v1/messages")
        async def conduit_anthropic_messages(request: AnthropicRequest):
            if request.stream:
                from headwater_server.services.conduit_service.conduit_anthropic_stream_service import (
                    conduit_anthropic_stream_service,
                )
                return await conduit_anthropic_stream_service(request)
            from headwater_server.services.conduit_service.conduit_anthropic_service import (
                conduit_anthropic_service,
            )
            return await conduit_anthropic_service(request)
```

- [ ] **Step 6: Run the new streaming tests**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py -v -k "stream"
```

Expected: 4 PASSED (event_stream, event_sequence, delta_has_text, stop_reason)

- [ ] **Step 7: Run full test suite to check no regressions**

```bash
cd headwater-server && uv run pytest tests/conduit_service/test_conduit_anthropic_service.py -v
```

Expected: all PASSED (including Phase 1 tests)

> **Note:** The Phase 1 `test_stream_true_returns_400` test will now FAIL since we removed the stream validator. Delete that test or update it to `test_stream_true_no_longer_rejected` with an assertion that `stream=true` returns 200.

- [ ] **Step 8: Commit**

```bash
git add headwater-api/src/headwater_api/classes/conduit_classes/anthropic_compat.py \
        headwater-server/src/headwater_server/services/conduit_service/conduit_anthropic_stream_service.py \
        headwater-server/src/headwater_server/api/conduit_server_api.py \
        headwater-server/tests/conduit_service/test_conduit_anthropic_service.py
git commit -m "feat(AC-5): fake SSE streaming for /v1/messages with Anthropic event sequence"
```

---

## Claude Code wiring

Once deployed, point Claude Code at headwater:

```bash
export ANTHROPIC_BASE_URL="http://<caruana-ip>:8081"
export ANTHROPIC_API_KEY="headwater"
```

Or in `~/.claude/settings.json`:
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://<caruana-ip>:8081",
    "ANTHROPIC_API_KEY": "headwater"
  }
}
```

Claude Code will send the model name it's configured to use. Make sure the model exists in your ModelStore (e.g. `gpt-oss:latest`). You can override the model Claude Code uses with `ANTHROPIC_MODEL=gpt-oss:latest`.

---

## Self-review

**Spec coverage:**
- AC-1 (models) → Task 1
- AC-2 (non-streaming response shape) → Task 2
- AC-3 (stream=true Phase 1 rejection) → Task 3 (removed in Task 5 — note in Task 5 handles this)
- AC-4 (model validation errors) → Task 4
- AC-5 (fake SSE) → Task 5

**Placeholder scan:** None found. All tasks contain complete code.

**Type consistency:**
- `AnthropicRequest` used consistently across service, stream service, and route
- `_STOP_MAP` defined identically in both services — acceptable duplication for now, could be extracted to a shared module later if desired
- `_sse_generator` returns `AsyncGenerator[str, None]` — consistent with FastAPI `StreamingResponse` expectations
