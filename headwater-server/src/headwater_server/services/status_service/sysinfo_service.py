from __future__ import annotations
import logging
import psutil

logger = logging.getLogger(__name__)


async def get_sysinfo_service() -> dict:
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    logger.debug(
        "sysinfo",
        extra={"cpu_percent": cpu_percent, "ram_used_bytes": ram.used},
    )
    return {
        "cpu_percent": float(cpu_percent),
        "ram_used_bytes": int(ram.used),
        "ram_total_bytes": int(ram.total),
    }
