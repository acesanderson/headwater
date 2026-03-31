from __future__ import annotations

from headwater_client.transport.headwater_transport import HeadwaterTransport
from dbclients.discovery.host import NetworkContext


def _fake_ctx(
    headwater="1.1.1.1",
    deepwater="9.9.9.9",
    bywater="2.2.2.2",
    backwater="3.3.3.3",
    stillwater="4.4.4.4",
) -> NetworkContext:
    return NetworkContext(
        local_hostname="test",
        is_on_vpn=False,
        is_local=False,
        is_database_server=False,
        is_siphon_server=False,
        preferred_host="",
        headwater_server=headwater,
        deepwater_server=deepwater,
        bywater_server=bywater,
        backwater_server=backwater,
        stillwater_server=stillwater,
    )


def test_sync_transport_headwater_alias_uses_headwater_server(monkeypatch):
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(headwater="1.1.1.1", bywater="2.2.2.2"),
    )
    t = HeadwaterTransport(host_alias="headwater")
    assert "1.1.1.1" in t.base_url
    assert "2.2.2.2" not in t.base_url


def test_sync_transport_bywater_alias_uses_bywater_server(monkeypatch):
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(headwater="1.1.1.1", bywater="2.2.2.2"),
    )
    t = HeadwaterTransport(host_alias="bywater")
    assert "2.2.2.2" in t.base_url
    assert "1.1.1.1" not in t.base_url


def test_sync_transport_default_alias_is_headwater(monkeypatch):
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(headwater="1.1.1.1"),
    )
    t = HeadwaterTransport()
    assert "1.1.1.1" in t.base_url


def test_sync_transport_explicit_base_url_ignores_alias(monkeypatch):
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(headwater="1.1.1.1", bywater="2.2.2.2"),
    )
    t = HeadwaterTransport(base_url="http://192.168.99.99:8080", host_alias="bywater")
    assert "192.168.99.99" in t.base_url
    assert "2.2.2.2" not in t.base_url


def test_sync_transport_get_url_emits_debug_log(monkeypatch, caplog):
    import logging
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(headwater="1.1.1.1", bywater="2.2.2.2"),
    )
    with caplog.at_level(logging.DEBUG, logger="headwater_client.transport.headwater_transport"):
        HeadwaterTransport(host_alias="bywater")
    assert any("bywater" in r.message and "2.2.2.2" in r.message for r in caplog.records)


def test_sync_transport_defers_resolution(monkeypatch):
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(headwater="9.8.7.6"),
    )
    t = HeadwaterTransport()
    assert "9.8.7.6" in t.base_url, (
        "base_url did not use the patched context — "
        "get_network_context() is likely still evaluated at module import"
    )


def test_headwater_alias_resolves_to_router_port_8081(monkeypatch):
    """AC-1: host_alias='headwater' resolves to base_url with port 8081."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(headwater="172.16.0.4"),
    )
    t = HeadwaterTransport(host_alias="headwater")
    assert t.base_url == "http://172.16.0.4:8081"


def test_deepwater_alias_resolves_to_alphablue(monkeypatch):
    """AC-2: host_alias='deepwater' resolves to AlphaBlue IP on port 8080."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(deepwater="172.16.0.2"),
    )
    t = HeadwaterTransport(host_alias="deepwater")
    assert t.base_url == "http://172.16.0.2:8080"


def test_stillwater_alias_resolves_to_botvinnik(monkeypatch):
    """AC-12: host_alias='stillwater' resolves to Botvinnik IP on port 8080."""
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(stillwater="172.16.0.3"),
    )
    t = HeadwaterTransport(host_alias="stillwater")
    assert t.base_url == "http://172.16.0.3:8080"
