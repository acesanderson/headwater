"""
Regression test suite — shared fixtures and helpers.

All tests hit live servers via HeadwaterClient. No mocking.
"""

from __future__ import annotations

import pytest

from headwater_client.client.headwater_client import HeadwaterClient


# ---------------------------------------------------------------------------
# Module-scoped host fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def router() -> HeadwaterClient:
    """Router on caruana:8081 (host_alias='headwater')."""
    return HeadwaterClient(host_alias="headwater")


@pytest.fixture(scope="module")
def bywater() -> HeadwaterClient:
    """Bywater subserver on caruana:8080."""
    return HeadwaterClient(host_alias="bywater")


@pytest.fixture(scope="module")
def deepwater() -> HeadwaterClient:
    """Deepwater subserver on alphablue:8080."""
    return HeadwaterClient(host_alias="deepwater")


# ---------------------------------------------------------------------------
# Parametrized host fixture — covers all 3 hosts
# ---------------------------------------------------------------------------


@pytest.fixture(
    scope="module",
    params=["headwater", "bywater", "deepwater"],
    ids=["router", "bywater", "deepwater"],
)
def any_host(request) -> HeadwaterClient:
    """Parametrized fixture yielding a HeadwaterClient for each host."""
    return HeadwaterClient(host_alias=request.param)


@pytest.fixture(
    scope="module",
    params=["bywater", "deepwater"],
    ids=["bywater", "deepwater"],
)
def subserver(request) -> HeadwaterClient:
    """Parametrized fixture yielding a HeadwaterClient for each subserver."""
    return HeadwaterClient(host_alias=request.param)
