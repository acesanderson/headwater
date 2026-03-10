from __future__ import annotations

import logging
from headwater_client.transport.headwater_async_transport import HeadwaterAsyncTransport
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


def test_async_transport_defers_resolution(monkeypatch):
    """AC-5 / AC-3: get_network_context() called at instantiation, not import."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_async_transport.get_network_context",
        lambda: _fake_ctx(siphon="9.8.7.6"),
    )
    t = HeadwaterAsyncTransport()
    assert "9.8.7.6" in t.base_url


def test_async_transport_headwater_alias(monkeypatch):
    """AC-5: host_alias='headwater' routes to siphon_server IP."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_async_transport.get_network_context",
        lambda: _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2"),
    )
    t = HeadwaterAsyncTransport(host_alias="headwater")
    assert "1.1.1.1" in t.base_url
    assert "2.2.2.2" not in t.base_url


def test_async_transport_bywater_alias(monkeypatch):
    """AC-5: host_alias='bywater' routes to bywater_server IP."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_async_transport.get_network_context",
        lambda: _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2"),
    )
    t = HeadwaterAsyncTransport(host_alias="bywater")
    assert "2.2.2.2" in t.base_url
    assert "1.1.1.1" not in t.base_url


def test_async_transport_default_alias_is_headwater(monkeypatch):
    """AC-5: Default host_alias is 'headwater'."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_async_transport.get_network_context",
        lambda: _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2"),
    )
    t = HeadwaterAsyncTransport()
    assert "1.1.1.1" in t.base_url


def test_async_transport_explicit_base_url_ignores_alias(monkeypatch):
    """AC-5: Explicit base_url overrides host_alias."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_async_transport.get_network_context",
        lambda: _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2"),
    )
    t = HeadwaterAsyncTransport(base_url="http://192.168.99.99:8080", host_alias="bywater")
    assert "192.168.99.99" in t.base_url
    assert "2.2.2.2" not in t.base_url


def test_async_transport_get_url_emits_debug_log(monkeypatch, caplog):
    """AC-5: _get_url() logs the resolved alias and IP at DEBUG level."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_async_transport.get_network_context",
        lambda: _fake_ctx(siphon="1.1.1.1", bywater="2.2.2.2"),
    )
    with caplog.at_level(logging.DEBUG, logger="headwater_client.transport.headwater_async_transport"):
        HeadwaterAsyncTransport(host_alias="bywater")
    assert any("bywater" in r.message and "2.2.2.2" in r.message for r in caplog.records)
