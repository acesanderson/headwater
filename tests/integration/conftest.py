from __future__ import annotations

import os

import httpx
import pytest

BYWATER_URL = os.getenv("BYWATER_URL", "http://172.16.0.4:8080").rstrip("/")
HEADWATER_MODEL = os.getenv("HEADWATER_MODEL", "gpt-oss:latest")


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=BYWATER_URL, timeout=30) as c:
        yield c


@pytest.fixture(scope="module")
def auth() -> dict[str, str]:
    return {"Authorization": "Bearer headwater"}


@pytest.fixture(scope="module")
def model() -> str:
    return HEADWATER_MODEL
