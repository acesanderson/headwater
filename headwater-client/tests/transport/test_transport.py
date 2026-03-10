from __future__ import annotations

from headwater_client.transport.headwater_transport import HeadwaterTransport
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


def test_sync_transport_defers_resolution(monkeypatch):
    """AC-3: get_network_context() is called at instantiation, not at import.
    Proof: a monkeypatch applied after import still takes effect for new instances.
    If get_network_context() were evaluated at module import, the patch would
    arrive too late and base_url would contain the real IP, not '9.8.7.6'.
    """
    monkeypatch.setattr(
        "headwater_client.transport.headwater_transport.get_network_context",
        lambda: _fake_ctx(siphon="9.8.7.6"),
    )
    t = HeadwaterTransport()
    assert "9.8.7.6" in t.base_url, (
        "base_url did not use the patched context — "
        "get_network_context() is likely still evaluated at module import"
    )
