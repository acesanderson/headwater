from __future__ import annotations

from headwater_client.client.headwater_client import HeadwaterClient
from dbclients.discovery.host import NetworkContext


def _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2") -> NetworkContext:
    # Inline helper — no conftest.py. Each test file is self-contained.
    return NetworkContext(
        local_hostname="test",
        is_on_vpn=False,
        is_local=False,
        is_database_server=False,
        is_siphon_server=False,
        preferred_host="",
        siphon_server=siphon,
        bywater_server=bywater,
    )


def test_headwater_client_default_routes_to_headwater(monkeypatch):
    """AC-6: HeadwaterClient() defaults to headwater host."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2"),
    )
    client = HeadwaterClient()
    assert "1.1.1.1" in client._transport.base_url


def test_headwater_client_bywater_alias_routes_to_bywater(monkeypatch):
    """AC-6: HeadwaterClient(host_alias='bywater') routes to bywater_server."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2"),
    )
    client = HeadwaterClient(host_alias="bywater")
    assert "2.2.2.2" in client._transport.base_url


from headwater_client.client.headwater_client_async import HeadwaterAsyncClient


def test_async_client_default_routes_to_headwater(monkeypatch):
    """AC-7: HeadwaterAsyncClient() defaults to headwater host."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_async_transport.get_network_context",
        lambda: _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2"),
    )
    client = HeadwaterAsyncClient()
    assert "1.1.1.1" in client._transport.base_url


def test_async_client_bywater_alias_routes_to_bywater(monkeypatch):
    """AC-7: HeadwaterAsyncClient(host_alias='bywater') routes to bywater_server."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_async_transport.get_network_context",
        lambda: _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2"),
    )
    client = HeadwaterAsyncClient(host_alias="bywater")
    assert "2.2.2.2" in client._transport.base_url


def test_async_client_explicit_base_url_takes_precedence(monkeypatch):
    """AC-7: Explicit base_url overrides host_alias='headwater' (default)."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_async_transport.get_network_context",
        lambda: _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2"),
    )
    client = HeadwaterAsyncClient(base_url="http://10.0.0.99:8080")
    assert "10.0.0.99" in client._transport.base_url
    assert "1.1.1.1" not in client._transport.base_url


def test_async_client_explicit_base_url_takes_precedence_over_bywater_alias(monkeypatch):
    """AC-7: Explicit base_url overrides host_alias='bywater' too.
    Both non-default args specified simultaneously; base_url must win.
    """
    monkeypatch.setattr(
        "headwater_client.transport.headwater_async_transport.get_network_context",
        lambda: _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2"),
    )
    client = HeadwaterAsyncClient(base_url="http://10.0.0.99:8080", host_alias="bywater")
    assert "10.0.0.99" in client._transport.base_url
    assert "2.2.2.2" not in client._transport.base_url
