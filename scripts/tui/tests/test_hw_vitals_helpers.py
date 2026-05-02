from __future__ import annotations
import hw_vitals


def test_temp_color_green():
    """AC-11: Temperature below 70°C is green."""
    assert hw_vitals.temp_color(50) == "#4ec9b0"
    assert hw_vitals.temp_color(69) == "#4ec9b0"


def test_temp_color_amber():
    """AC-11: Temperature 70–85°C is amber."""
    assert hw_vitals.temp_color(70) == "#e8c07d"
    assert hw_vitals.temp_color(85) == "#e8c07d"


def test_temp_color_red():
    """AC-11: Temperature above 85°C is red."""
    assert hw_vitals.temp_color(86) == "#f44747"
    assert hw_vitals.temp_color(95) == "#f44747"


def test_metric_color_gpu_green():
    """AC-11: GPU util below 60% is green."""
    assert hw_vitals.metric_color(50, "gpu") == "#4ec9b0"


def test_metric_color_gpu_amber():
    """AC-11: GPU util 60–85% is amber."""
    assert hw_vitals.metric_color(75, "gpu") == "#e8c07d"


def test_metric_color_gpu_red():
    """AC-11: GPU util above 85% is red."""
    assert hw_vitals.metric_color(90, "gpu") == "#f44747"


def test_metric_color_vram_thresholds():
    """AC-11: VRAM thresholds are 70/90."""
    assert hw_vitals.metric_color(65, "vram") == "#4ec9b0"
    assert hw_vitals.metric_color(80, "vram") == "#e8c07d"
    assert hw_vitals.metric_color(95, "vram") == "#f44747"


def test_metric_color_cpu_thresholds():
    """AC-11: CPU thresholds are 60/80."""
    assert hw_vitals.metric_color(50, "cpu") == "#4ec9b0"
    assert hw_vitals.metric_color(70, "cpu") == "#e8c07d"
    assert hw_vitals.metric_color(85, "cpu") == "#f44747"


def test_mb_to_gb():
    """GpuInfo uses MB; display in GB."""
    assert hw_vitals.mb_to_gb(4096) == pytest.approx(4.0, rel=0.01)
    assert hw_vitals.mb_to_gb(16384) == pytest.approx(16.0, rel=0.01)


def test_bytes_to_gb():
    """sysinfo returns bytes; display in GB."""
    assert hw_vitals.bytes_to_gb(17_179_869_184) == pytest.approx(16.0, rel=0.01)


def test_format_uptime_days_hours():
    assert hw_vitals.format_uptime(2 * 86400 + 4 * 3600) == "2d 4h"


def test_format_uptime_hours_only():
    assert hw_vitals.format_uptime(3 * 3600) == "0d 3h"


def test_compute_req_per_s_counts_matching_backend(monkeypatch):
    """AC-14: req/s counts proxy_response records for matching backend in last 60s."""
    now = 1000.0
    entries = [
        {"message": "proxy_response", "timestamp": 990.0, "extra": {"backend": "http://bw:8080"}},
        {"message": "proxy_response", "timestamp": 995.0, "extra": {"backend": "http://bw:8080"}},
        {"message": "proxy_response", "timestamp": 995.0, "extra": {"backend": "http://other:8080"}},
        {"message": "proxy_request", "timestamp": 998.0, "extra": {"backend": "http://bw:8080"}},
    ]
    rate = hw_vitals.compute_req_per_s(entries, "http://bw:8080", now, now - 60)
    assert rate == pytest.approx(2 / 60.0, rel=0.01)


def test_compute_error_count_counts_4xx_and_5xx():
    """AC-14: error count includes 4xx and 5xx upstream_status."""
    now = 1000.0
    entries = [
        {"message": "proxy_response", "timestamp": 999.0, "extra": {"backend": "http://bw:8080", "upstream_status": 200}},
        {"message": "proxy_response", "timestamp": 999.0, "extra": {"backend": "http://bw:8080", "upstream_status": 503}},
        {"message": "proxy_response", "timestamp": 999.0, "extra": {"backend": "http://bw:8080", "upstream_status": 400}},
    ]
    count = hw_vitals.compute_error_count(entries, "http://bw:8080", now)
    assert count == 2


import pytest
