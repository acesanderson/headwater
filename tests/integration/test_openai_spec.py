"""
OpenAI Responses API spec compliance tests.

Covers the acceptance criteria from docs/plans and OpenAI Spec.md:
  HDR_01  — x-request-id header present on every response
  AUTH_01 — missing Authorization → 401 with OpenAI error schema
  AUTH_02 — openai-organization / openai-project headers accepted without error
  PARAM_01 — temperature bounds: 2.0 → 200, 2.1 → 400 with OpenAI error schema
  SHAPE   — response object shape (id, object, created_at, status, model, output, usage)
  USAGE   — usage field names use Responses API names (input_tokens, not prompt_tokens)
  ERR_MDL — unknown model → 404 with model_not_found code

Run:
    pytest -m integration tests/integration/test_openai_spec.py -v

Configure targets via env vars:
    BYWATER_URL      (default: http://172.16.0.4:8080)
    HEADWATER_MODEL  (default: gpt-oss:latest)
"""
from __future__ import annotations

import pytest

RESPONSES_PATH = "/v1/responses"


def _responses_payload(model: str, **overrides) -> dict:
    return {"model": model, "input": "Say hello.", "max_output_tokens": 10, **overrides}


def _has_openai_error_schema(body: dict) -> bool:
    error = body.get("error")
    if not isinstance(error, dict):
        return False
    return all(k in error for k in ("message", "type", "param", "code"))


# ---------------------------------------------------------------------------
# HDR_01 — x-request-id
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_hdr_01_request_id_present(client, auth, model):
    r = client.post(RESPONSES_PATH, json=_responses_payload(model), headers=auth)
    assert r.status_code == 200
    assert "x-request-id" in r.headers, "x-request-id header missing from response"


# ---------------------------------------------------------------------------
# AUTH_01 — missing Authorization → 401 + OpenAI error schema
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_auth_01_missing_auth_returns_401(client, model):
    r = client.post(RESPONSES_PATH, json=_responses_payload(model))
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text[:200]}"


@pytest.mark.integration
def test_auth_01_missing_auth_returns_openai_error_schema(client, model):
    r = client.post(RESPONSES_PATH, json=_responses_payload(model))
    body = r.json()
    assert _has_openai_error_schema(body), (
        f"Expected {{error: {{message, type, param, code}}}}, got: {body}"
    )


# ---------------------------------------------------------------------------
# AUTH_02 — openai-organization / openai-project headers accepted
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_auth_02_org_and_project_headers_accepted(client, auth, model):
    headers = {
        **auth,
        "openai-organization": "test-org",
        "openai-project": "test-project",
    }
    r = client.post(RESPONSES_PATH, json=_responses_payload(model), headers=headers)
    assert r.status_code == 200, f"Got {r.status_code}: {r.text[:200]}"


# ---------------------------------------------------------------------------
# PARAM_01 — temperature bounds
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_param_01_temperature_at_max_accepted(client, auth, model):
    r = client.post(
        RESPONSES_PATH,
        json=_responses_payload(model, temperature=2.0),
        headers=auth,
    )
    assert r.status_code == 200, f"temperature=2.0 should be accepted, got {r.status_code}"


@pytest.mark.integration
def test_param_01_temperature_above_max_rejected(client, auth, model):
    r = client.post(
        RESPONSES_PATH,
        json=_responses_payload(model, temperature=2.1),
        headers=auth,
    )
    assert r.status_code == 400, f"temperature=2.1 should be rejected with 400, got {r.status_code}"


@pytest.mark.integration
def test_param_01_temperature_above_max_returns_openai_error_schema(client, auth, model):
    r = client.post(
        RESPONSES_PATH,
        json=_responses_payload(model, temperature=2.1),
        headers=auth,
    )
    body = r.json()
    assert _has_openai_error_schema(body), (
        f"Expected OpenAI error schema, got: {body}"
    )
    assert body["error"].get("param") == "temperature", (
        f"Expected param='temperature', got: {body['error'].get('param')!r}"
    )


# ---------------------------------------------------------------------------
# SHAPE — response object fields
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_shape_top_level_fields(client, auth, model):
    r = client.post(RESPONSES_PATH, json=_responses_payload(model), headers=auth)
    assert r.status_code == 200
    body = r.json()
    for field in ("id", "object", "created_at", "status", "model", "output", "usage"):
        assert field in body, f"Missing top-level field: {field!r}"


@pytest.mark.integration
def test_shape_object_value(client, auth, model):
    r = client.post(RESPONSES_PATH, json=_responses_payload(model), headers=auth)
    body = r.json()
    assert body.get("object") == "response", f"object={body.get('object')!r}"


@pytest.mark.integration
def test_shape_output_message(client, auth, model):
    r = client.post(RESPONSES_PATH, json=_responses_payload(model), headers=auth)
    body = r.json()
    output = body.get("output", [])
    assert len(output) > 0, "output array is empty"
    msg = output[0]
    assert msg.get("type") == "message"
    assert msg.get("role") == "assistant"
    content = msg.get("content", [])
    assert len(content) > 0, "output[0].content is empty"
    assert content[0].get("type") == "output_text"
    assert isinstance(content[0].get("text"), str)


@pytest.mark.integration
def test_shape_status_completed(client, auth, model):
    r = client.post(RESPONSES_PATH, json=_responses_payload(model), headers=auth)
    body = r.json()
    assert body.get("status") == "completed"


# ---------------------------------------------------------------------------
# USAGE — Responses API field names (not Chat Completions names)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_usage_field_names(client, auth, model):
    r = client.post(RESPONSES_PATH, json=_responses_payload(model), headers=auth)
    usage = r.json().get("usage", {})
    assert "input_tokens" in usage, "usage.input_tokens missing"
    assert "output_tokens" in usage, "usage.output_tokens missing"
    assert "total_tokens" in usage, "usage.total_tokens missing"
    assert "prompt_tokens" not in usage, "usage.prompt_tokens should not be present (Chat Completions field)"
    assert "completion_tokens" not in usage, "usage.completion_tokens should not be present (Chat Completions field)"


@pytest.mark.integration
def test_usage_token_counts_are_positive(client, auth, model):
    r = client.post(RESPONSES_PATH, json=_responses_payload(model), headers=auth)
    usage = r.json().get("usage", {})
    assert usage.get("input_tokens", 0) > 0
    assert usage.get("output_tokens", 0) > 0
    assert usage.get("total_tokens", 0) == usage["input_tokens"] + usage["output_tokens"]


# ---------------------------------------------------------------------------
# ERR_MDL — unknown model → 404 + model_not_found
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_err_mdl_unknown_model_returns_404(client, auth):
    r = client.post(
        RESPONSES_PATH,
        json=_responses_payload("definitely-not-a-real-model"),
        headers=auth,
    )
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text[:200]}"


@pytest.mark.integration
def test_err_mdl_unknown_model_returns_model_not_found_code(client, auth):
    r = client.post(
        RESPONSES_PATH,
        json=_responses_payload("definitely-not-a-real-model"),
        headers=auth,
    )
    body = r.json()
    assert _has_openai_error_schema(body), f"Expected OpenAI error schema, got: {body}"
    assert body["error"].get("code") == "model_not_found", (
        f"Expected code='model_not_found', got: {body['error'].get('code')!r}"
    )
