from __future__ import annotations

from headwater_api.classes.server_classes.exceptions import ErrorType


def test_routing_error_variant_exists():
    assert ErrorType.ROUTING_ERROR == "routing_error"


def test_backend_unavailable_variant_exists():
    assert ErrorType.BACKEND_UNAVAILABLE == "backend_unavailable"


def test_backend_timeout_variant_exists():
    assert ErrorType.BACKEND_TIMEOUT == "backend_timeout"
