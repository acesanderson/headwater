def test_openai_chat_endpoint_is_registered(client):
    """AC6: /v1/chat/completions is registered as a route.

    Note: GET /openapi.json fails with 500 on this server due to a pre-existing
    issue (ConduitOptions.cache: ConduitCache | None is not JSON-schema-serializable).
    That bug predates this feature and affects all conduit routes. We verify route
    registration directly via app.routes instead.
    """
    from headwater_server.server.headwater import app
    paths = [getattr(r, "path", None) for r in app.routes]
    assert "/v1/chat/completions" in paths
