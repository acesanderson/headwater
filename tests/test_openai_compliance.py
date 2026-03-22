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
from dataclasses import dataclass, field

import httpx

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://172.16.0.4:8080"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "gpt-oss:latest"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"
INFO = "\033[34mINFO\033[0m"


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


# ---------------------------------------------------------------------------
# 1. Basic connectivity
# ---------------------------------------------------------------------------

@check("GET /ping (server alive)", required=True)
def _():
    r = get("/ping")
    ok = r.status_code == 200
    return Result("GET /ping (server alive)", ok, True,
                  detail=f"HTTP {r.status_code}")


@check("GET /status (server status)", required=False)
def _():
    r = get("/status")
    ok = r.status_code == 200
    return Result("GET /status (server status)", ok, False,
                  detail=f"HTTP {r.status_code}")


# ---------------------------------------------------------------------------
# 2. Standard OpenAI paths (what clients like OpenClaw probe)
# ---------------------------------------------------------------------------

@check("GET /v1/models (OpenAI standard path)", required=True)
def _():
    r = get("/v1/models")
    ok = r.status_code == 200
    snippet = r.text[:200] if not ok else ""
    return Result("GET /v1/models (OpenAI standard path)", ok, True,
                  detail=f"HTTP {r.status_code}",
                  response_snippet=snippet)


@check("POST /v1/chat/completions (OpenAI standard path)", required=True)
def _():
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Say hello."}],
        "max_tokens": 16,
    }
    r = post("/v1/chat/completions", payload)
    ok = r.status_code == 200
    snippet = r.text[:300] if not ok else r.text[:300]
    return Result("POST /v1/chat/completions (OpenAI standard path)", ok, True,
                  detail=f"HTTP {r.status_code}",
                  response_snippet=snippet)


# ---------------------------------------------------------------------------
# 3. Actual Bywater/Headwater paths
# ---------------------------------------------------------------------------

@check("POST /v1/chat/completions with headwater/ prefix (Headwater model naming)", required=False)
def _():
    payload = {
        "model": f"headwater/{MODEL}",
        "messages": [{"role": "user", "content": "Say hello."}],
        "max_tokens": 16,
    }
    r = post("/v1/chat/completions", payload)
    ok = r.status_code == 200
    snippet = r.text[:300]
    return Result("POST /v1/chat/completions with headwater/ prefix (Headwater model naming)", ok, False,
                  detail=f"HTTP {r.status_code}",
                  response_snippet=snippet)


# ---------------------------------------------------------------------------
# 4. Response shape validation (if /v1/chat/completions returned 200)
# ---------------------------------------------------------------------------

@check("Response has required OpenAI fields", required=True)
def _():
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Say hello."}],
        "max_tokens": 16,
    }
    r = post("/v1/chat/completions", payload)
    if r.status_code != 200:
        return Result("Response has required OpenAI fields", False, True,
                      detail="Skipped — endpoint returned non-200")
    try:
        body = r.json()
    except Exception:
        return Result("Response has required OpenAI fields", False, True,
                      detail="Response is not valid JSON")

    required_fields = ["id", "object", "created", "model", "choices"]
    missing = [f for f in required_fields if f not in body]
    choices_ok = (
        isinstance(body.get("choices"), list)
        and len(body["choices"]) > 0
        and "message" in body["choices"][0]
    )
    passed = not missing and choices_ok
    detail = f"Missing: {missing}" if missing else ("choices[0].message missing" if not choices_ok else "All required fields present")
    return Result("Response has required OpenAI fields", passed, True,
                  detail=detail,
                  response_snippet=json.dumps(body, indent=2)[:400] if not passed else "")


@check("Response object type is 'chat.completion'", required=True)
def _():
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Say hello."}],
        "max_tokens": 16,
    }
    r = post("/v1/chat/completions", payload)
    if r.status_code != 200:
        return Result("Response object type is 'chat.completion'", False, True,
                      detail="Skipped — endpoint returned non-200")
    body = r.json()
    obj = body.get("object", "")
    passed = obj == "chat.completion"
    return Result("Response object type is 'chat.completion'", passed, True,
                  detail=f"object={obj!r}")


@check("choices[0].finish_reason is present", required=False)
def _():
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Say hello."}],
        "max_tokens": 16,
    }
    r = post("/v1/chat/completions", payload)
    if r.status_code != 200:
        return Result("choices[0].finish_reason is present", False, False,
                      detail="Skipped — endpoint returned non-200")
    body = r.json()
    choices = body.get("choices", [])
    if not choices:
        return Result("choices[0].finish_reason is present", False, False, detail="No choices")
    passed = "finish_reason" in choices[0]
    return Result("choices[0].finish_reason is present", passed, False,
                  detail=f"finish_reason={choices[0].get('finish_reason')!r}")


@check("usage block present (prompt/completion/total tokens)", required=False)
def _():
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Say hello."}],
        "max_tokens": 16,
    }
    r = post("/v1/chat/completions", payload)
    if r.status_code != 200:
        return Result("usage block present", False, False,
                      detail="Skipped — endpoint returned non-200")
    body = r.json()
    usage = body.get("usage", {})
    required = {"prompt_tokens", "completion_tokens", "total_tokens"}
    missing = required - set(usage.keys())
    passed = not missing
    return Result("usage block present (prompt/completion/total tokens)", passed, False,
                  detail=f"Missing usage fields: {missing}" if missing else "All usage fields present")


# ---------------------------------------------------------------------------
# 5. Model name handling
# ---------------------------------------------------------------------------

@check("Plain model name accepted (no 'headwater/' prefix)", required=True)
def _():
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 8,
    }
    r = post("/v1/chat/completions", payload)
    passed = r.status_code == 200
    return Result("Plain model name accepted (no 'headwater/' prefix)", passed, True,
                  detail=f"HTTP {r.status_code} for model={MODEL!r}",
                  response_snippet=r.text[:200] if not passed else "")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def report():
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
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    print(f"\n{passed}/{total} checks passed. Required failures: {required_failures}")

    if required_failures:
        print("\nDiagnosis:")
        for r in results:
            if not r.passed and r.required:
                print(f"  - {r.name}: {r.detail}")
        print()

    return required_failures


if __name__ == "__main__":
    sys.exit(0 if report() == 0 else 1)
