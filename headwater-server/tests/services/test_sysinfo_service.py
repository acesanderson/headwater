from __future__ import annotations
import pytest


@pytest.mark.asyncio
async def test_sysinfo_returns_required_keys():
    """AC-1: get_sysinfo_service() returns cpu_percent, ram_used_bytes, ram_total_bytes."""
    from headwater_server.services.status_service.sysinfo_service import get_sysinfo_service
    result = await get_sysinfo_service()
    assert "cpu_percent" in result
    assert "ram_used_bytes" in result
    assert "ram_total_bytes" in result


@pytest.mark.asyncio
async def test_sysinfo_cpu_percent_is_float():
    """AC-1: cpu_percent is a float in range [0.0, 100.0]."""
    from headwater_server.services.status_service.sysinfo_service import get_sysinfo_service
    result = await get_sysinfo_service()
    assert isinstance(result["cpu_percent"], float)
    assert 0.0 <= result["cpu_percent"] <= 100.0


@pytest.mark.asyncio
async def test_sysinfo_ram_values_are_positive_ints():
    """AC-1: ram_used_bytes and ram_total_bytes are positive integers."""
    from headwater_server.services.status_service.sysinfo_service import get_sysinfo_service
    result = await get_sysinfo_service()
    assert isinstance(result["ram_used_bytes"], int)
    assert isinstance(result["ram_total_bytes"], int)
    assert result["ram_used_bytes"] > 0
    assert result["ram_total_bytes"] >= result["ram_used_bytes"]
