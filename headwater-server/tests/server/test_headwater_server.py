from __future__ import annotations

from headwater_server.server.headwater import HeadwaterServer


def test_headwater_server_default_title():
    """AC-8: Default title is 'Headwater API Server'."""
    server = HeadwaterServer()
    assert server.app.title == "Headwater API Server"


def test_headwater_server_custom_title():
    """AC-8: HeadwaterServer accepts a name parameter that sets the FastAPI app title."""
    server = HeadwaterServer(name="Bywater API Server")
    assert server.app.title == "Bywater API Server"
