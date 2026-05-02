from __future__ import annotations
import hw_log


def test_status_color_2xx():
    assert hw_log.status_color(200) == "#4ec9b0"
    assert hw_log.status_color(201) == "#4ec9b0"


def test_status_color_4xx():
    assert hw_log.status_color(400) == "#e8c07d"
    assert hw_log.status_color(404) == "#e8c07d"


def test_status_color_5xx():
    assert hw_log.status_color(500) == "#f44747"
    assert hw_log.status_color(503) == "#f44747"


def test_status_color_none():
    assert hw_log.status_color(None) == hw_log.MUTED


def test_via_color_standard():
    assert hw_log.via_color("conduit") == "#c586c0"
    assert hw_log.via_color("siphon") == "#c586c0"
    assert hw_log.via_color("embeddings") == "#c586c0"


def test_via_color_special():
    assert hw_log.via_color("heavy_inference") == "#e8c07d"
    assert hw_log.via_color("ambient_inference") == "#e8c07d"
    assert hw_log.via_color("reranker_heavy") == "#e8c07d"


def test_via_color_none_is_muted():
    assert hw_log.via_color(None) == hw_log.MUTED


def test_via_text_routed():
    assert hw_log.via_text("conduit") == "conduit"
    assert hw_log.via_text("heavy_inference") == "heavy_inference"


def test_via_text_direct():
    assert hw_log.via_text(None) == "direct"


def test_truncate_short_string():
    assert hw_log.truncate("hello", 10) == "hello"


def test_truncate_long_string():
    result = hw_log.truncate("conduit/generate_with_context", 20)
    assert len(result) == 20
    assert result.endswith("…")
