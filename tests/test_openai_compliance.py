#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
OpenAI API compliance checker for Bywater / Headwater.

Usage:
    uv run tests/test_openai_compliance.py [BASE_URL] [MODEL]

Defaults:
    BASE_URL = http://172.16.0.4:8080
    MODEL    = gpt-oss:latest

Exit code: 0 if all required checks pass, 1 otherwise.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass

import httpx

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://172.16.0.4:8080"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "gpt-oss:latest"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"


@dataclass
class Result:
    name: str
    passed: bool
    required: bool
    detail: str = ""
    response_snippet: str = ""


results: list[Result] = []


def check(name: str, required: bool = True):
    def decorator(fn):
        try:
            r = fn()
            results.append(r if isinstance(r, Result) else Result(name, r, required))
        except Exception as exc:
            results.append(Result(name, False, required, detail=str(exc)))
        return fn
    return decorator


def get(path: str, **kwargs) -> httpx.Response:
    return httpx.get(f"{BASE_URL}{path}", timeout=10, **kwargs)


def post(path: str, payload: dict, **kwargs) -> httpx.Response:
    return httpx.post(f"{BASE_URL}{path}", json=payload, timeout=30, **kwargs)


def chat_payload(**overrides) -> dict:
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Say hello."}],
        "max_tokens": 16,
        **overrides,
    }


# ---------------------------------------------------------------------------
# 1. Basic connectivity
# ---------------------------------------------------------------------------

@check("GET /ping")
def _():
    r = get("/ping")
    return Result("GET /ping", r.status_code == 200, True, detail=f"HTTP {r.status_code}")


@check("GET /status", required=False)
def _():
    r = get("/status")
    return Result("GET /status", r.status_code == 200, False, detail=f"HTTP {r.status_code}")


# ---------------------------------------------------------------------------
# 2. Required OpenAI-compatible endpoints
# ---------------------------------------------------------------------------

@check("GET /v1/models returns 200 with model list")
def _():
    r = get("/v1/models")
    if r.status_code != 200:
        return Result("GET /v1/models returns 200 with model list", False, True,
                      detail=f"HTTP {r.status_code}",
                      response_snippet=r.text[:300])
    body = r.json()
    ok = body.get("object") == "list" and isinstance(body.get("data"), list)
    detail = f"object={body.get('object')!r}, {len(body.get('data', []))} models" if ok else "unexpected shape"
    return Result("GET /v1/models returns 200 with model list", ok, True,
                  detail=detail,
                  response_snippet="" if ok else json.dumps(body)[:300])


@check("POST /v1/chat/completions returns 200")
def _():
    r = post("/v1/chat/completions", chat_payload())
    ok = r.status_code == 200
    return Result("POST /v1/chat/completions returns 200", ok, True,
                  detail=f"HTTP {r.status_code}",
                  response_snippet=r.text[:300] if not ok else "")


# ---------------------------------------------------------------------------
# 3. Response shape
# ---------------------------------------------------------------------------

@check("Response is valid JSON with required fields")
def _():
    r = post("/v1/chat/completions", chat_payload())
    if r.status_code != 200:
        return Result("Response is valid JSON with required fields", False, True,
                      detail="Skipped — endpoint returned non-200")
    try:
        body = r.json()
    except Exception:
        return Result("Response is valid JSON with required fields", False, True,
                      detail="Response is not valid JSON")

    missing = [f for f in ["id", "object", "created", "model", "choices"] if f not in body]
    choices_ok = (
        isinstance(body.get("choices"), list)
        and len(body["choices"]) > 0
        and "message" in body["choices"][0]
    )
    passed = not missing and choices_ok
    if missing:
        detail = f"Missing top-level fields: {missing}"
    elif not choices_ok:
        detail = "choices[0].message missing or choices is empty"
    else:
        detail = "All required fields present"
    return Result("Response is valid JSON with required fields", passed, True,
                  detail=detail,
                  response_snippet=json.dumps(body, indent=2)[:400] if not passed else "")


@check("object == 'chat.completion'")
def _():
    r = post("/v1/chat/completions", chat_payload())
    if r.status_code != 200:
        return Result("object == 'chat.completion'", False, True, detail="Skipped — non-200")
    obj = r.json().get("object", "")
    return Result("object == 'chat.completion'", obj == "chat.completion", True,
                  detail=f"object={obj!r}")


@check("model echoed in response")
def _():
    r = post("/v1/chat/completions", chat_payload())
    if r.status_code != 200:
        return Result("model echoed in response", False, True, detail="Skipped — non-200")
    got = r.json().get("model", "")
    passed = got == MODEL
    return Result("model echoed in response", passed, True,
                  detail=f"sent={MODEL!r} got={got!r}")


@check("choices[0].finish_reason present", required=False)
def _():
    r = post("/v1/chat/completions", chat_payload())
    if r.status_code != 200:
        return Result("choices[0].finish_reason present", False, False, detail="Skipped — non-200")
    choices = r.json().get("choices", [])
    passed = bool(choices) and "finish_reason" in choices[0]
    return Result("choices[0].finish_reason present", passed, False,
                  detail=f"finish_reason={choices[0].get('finish_reason')!r}" if choices else "no choices")


@check("usage block has prompt/completion/total_tokens", required=False)
def _():
    r = post("/v1/chat/completions", chat_payload())
    if r.status_code != 200:
        return Result("usage block has prompt/completion/total_tokens", False, False, detail="Skipped — non-200")
    usage = r.json().get("usage", {})
    missing = {"prompt_tokens", "completion_tokens", "total_tokens"} - set(usage.keys())
    passed = not missing
    return Result("usage block has prompt/completion/total_tokens", passed, False,
                  detail=f"Missing: {missing}" if missing else "All usage fields present")


# ---------------------------------------------------------------------------
# 4. Error handling
# ---------------------------------------------------------------------------

@check("Unknown model returns 4xx")
def _():
    r = post("/v1/chat/completions", chat_payload(model="definitely-not-a-real-model-xyz"))
    passed = 400 <= r.status_code < 500
    return Result("Unknown model returns 4xx", passed, True,
                  detail=f"HTTP {r.status_code}",
                  response_snippet=r.text[:200] if not passed else "")


@check("Empty messages rejected", required=False)
def _():
    r = post("/v1/chat/completions", {"model": MODEL, "messages": []})
    passed = r.status_code in (400, 422)
    return Result("Empty messages rejected", passed, False,
                  detail=f"HTTP {r.status_code}")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def report() -> int:
    print(f"\nOpenAI Compliance Check — {BASE_URL}")
    print(f"Model under test: {MODEL}")
    print("=" * 70)

    required_failures = 0
    for r in results:
        if r.passed:
            status = PASS
        elif r.required:
            status = FAIL
            required_failures += 1
        else:
            status = WARN

        tag = "[required]" if r.required else "[optional]"
        print(f"  {status}  {tag:10s}  {r.name}")
        if r.detail:
            print(f"             {r.detail}")
        if r.response_snippet:
            for line in r.response_snippet.splitlines():
                print(f"             > {line}")

    print("=" * 70)
    passed = sum(1 for r in results if r.passed)
    print(f"\n{passed}/{len(results)} checks passed. Required failures: {required_failures}")

    if required_failures:
        print("\nDiagnosis:")
        for r in results:
            if not r.passed and r.required:
                print(f"  - {r.name}: {r.detail}")
        print()

    return required_failures


if __name__ == "__main__":
    sys.exit(0 if report() == 0 else 1)
