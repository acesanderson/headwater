from __future__ import annotations

from headwater_server.server.headwater import HeadwaterServer

_server = HeadwaterServer(name="Bywater API Server")
app = _server.app
