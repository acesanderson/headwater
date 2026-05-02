# /// script
# requires-python = ">=3.12"
# dependencies = ["rich>=13", "httpx>=0.27"]
# ///
from __future__ import annotations

import time

import httpx
from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

# ── Constants ─────────────────────────────────────────────────────────────────

BYWATER_URL   = "http://172.16.0.4:8080"
DEEPWATER_URL = "http://172.16.0.2:8080"
ROUTER_URL    = "http://172.16.0.4:8081"
POLL_INTERVAL = 2.0

GREEN  = "#4ec9b0"
AMBER  = "#e8c07d"
RED    = "#f44747"
BLUE   = "#9cdcfe"
ORANGE = "#ce9178"
MUTED  = "#555555"
DIM    = "#333333"

_GPU_THRESHOLDS  = (60, 85)
_VRAM_THRESHOLDS = (70, 90)
_CPU_THRESHOLDS  = (60, 80)
_TEMP_THRESHOLDS = (70, 85)

# ── Pure helpers ───────────────────────────────────────────────────────────────

def temp_color(celsius: int | None) -> str:
    if celsius is None:
        return MUTED
    if celsius > _TEMP_THRESHOLDS[1]:
        return RED
    if celsius >= _TEMP_THRESHOLDS[0]:
        return AMBER
    return GREEN


def metric_color(pct: float, kind: str) -> str:
    thresholds = {
        "gpu": _GPU_THRESHOLDS,
        "vram": _VRAM_THRESHOLDS,
        "cpu": _CPU_THRESHOLDS,
    }.get(kind, (60, 80))
    if pct > thresholds[1]:
        return RED
    if pct >= thresholds[0]:
        return AMBER
    return GREEN


def mb_to_gb(mb: int) -> float:
    return mb / 1024.0


def bytes_to_gb(b: int) -> float:
    return b / (1024 ** 3)


def format_uptime(seconds: float) -> str:
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    return f"{days}d {hours}h"


def compute_req_per_s(
    entries: list[dict],
    backend_url: str,
    now: float,
    start_time: float,
) -> float:
    window = 60.0
    cutoff = now - window
    count = sum(
        1 for e in entries
        if e.get("message") == "proxy_response"
        and (e.get("extra") or {}).get("backend") == backend_url
        and e.get("timestamp", 0) > cutoff
    )
    elapsed = min(window, now - start_time)
    return count / elapsed if elapsed > 0 else 0.0


def compute_error_count(
    entries: list[dict],
    backend_url: str,
    now: float,
) -> int:
    cutoff = now - 60.0
    return sum(
        1 for e in entries
        if e.get("message") == "proxy_response"
        and (e.get("extra") or {}).get("backend") == backend_url
        and (e.get("extra") or {}).get("upstream_status", 0) >= 400
        and e.get("timestamp", 0) > cutoff
    )


# ── Panel builders ─────────────────────────────────────────────────────────────

def build_backend_panel(
    name: str,
    hostname: str,
    gpu_name: str,
    uptime_s: float | None,
    gpu_pct: int | None,
    vram_used_mb: int | None,
    vram_total_mb: int | None,
    temp_c: int | None,
    cpu_pct: float | None,
    ram_used_bytes: int | None,
    ram_total_bytes: int | None,
    ollama_models: list[dict],
    req_per_s: float,
    error_count: int,
    offline: bool = False,
) -> Panel:
    t = Text()

    if offline:
        t.append(f"{name}  X  OFFLINE\n", style=f"bold {RED}")
        t.append(f"{hostname}\n", style=MUTED)
        t.append("GPU  —\nVRAM  —\nCPU  —\nRAM  —\n", style=MUTED)
        t.append("OLLAMA  —\n", style=MUTED)
        return Panel(t, title=f"[{RED}]{name}[/{RED}]", border_style=RED)

    tc = temp_color(temp_c)
    temp_str = f"{temp_c}C" if temp_c is not None else "—"
    uptime_str = format_uptime(uptime_s) if uptime_s is not None else "—"

    t.append(f"{name}  ", style=f"bold {BLUE}")
    t.append("* ", style=f"bold {tc}")
    t.append(f"{temp_str}\n", style=tc)
    t.append(f"{hostname} · {gpu_name} · up {uptime_str}\n", style=MUTED)
    t.append("\n")

    def metric_row(label: str, pct: float | None, used: str, total: str, kind: str) -> None:
        mc = metric_color(pct or 0, kind)
        t.append(f"{label:<10}", style=MUTED)
        bar_fill = int((pct or 0) / 100 * 20)
        t.append("█" * bar_fill, style=mc)
        t.append("░" * (20 - bar_fill), style=DIM)
        t.append(f"  {pct or '—'}%  {used}/{total}\n", style=mc)

    if gpu_pct is not None and vram_used_mb is not None and vram_total_mb is not None:
        metric_row("GPU UTIL", gpu_pct, f"{mb_to_gb(vram_used_mb):.1f}", f"{mb_to_gb(vram_total_mb):.1f} GB", "gpu")
        vram_pct = int(vram_used_mb / vram_total_mb * 100) if vram_total_mb else 0
        metric_row("VRAM", vram_pct, f"{mb_to_gb(vram_used_mb):.1f}", f"{mb_to_gb(vram_total_mb):.1f} GB", "vram")
    else:
        t.append("GPU  —\nVRAM  —\n", style=MUTED)

    if cpu_pct is not None and ram_used_bytes is not None and ram_total_bytes is not None:
        metric_row("CPU UTIL", cpu_pct, f"{bytes_to_gb(ram_used_bytes):.1f}", f"{bytes_to_gb(ram_total_bytes):.1f} GB", "cpu")
        ram_pct = int(ram_used_bytes / ram_total_bytes * 100) if ram_total_bytes else 0
        metric_row("RAM", ram_pct, f"{bytes_to_gb(ram_used_bytes):.1f}", f"{bytes_to_gb(ram_total_bytes):.1f} GB", "cpu")
    else:
        t.append("CPU  —\nRAM  —\n", style=MUTED)

    t.append("\n")
    t.append("OLLAMA\n", style=MUTED)
    if ollama_models:
        for m in ollama_models:
            model_name = m.get("name", "—")
            size_gb = mb_to_gb(m.get("size_mb", 0))
            cpu = m.get("cpu_pct", 0)
            gpu = m.get("vram_pct", 0)
            t.append(f"  {model_name}  {size_gb:.1f} GB", style=ORANGE)
            if cpu >= 1:
                t.append(f"  {int(cpu)}% cpu", style=AMBER)
            t.append(f"  {int(gpu)}% gpu\n", style=metric_color(gpu, "gpu"))
            err_style = RED if error_count > 0 else MUTED
            t.append(f"  {req_per_s:.1f} req/s · ", style=MUTED)
            t.append(f"{error_count} err\n", style=err_style)
    else:
        t.append("  no models loaded\n", style=MUTED)

    return Panel(t, title=f"[{BLUE}]{name}[/{BLUE}]", border_style="#2a2a2a")


def build_router_status_bar(router_up: bool, backend_count: int, total_backends: int, last_poll_s: float | None) -> Text:
    t = Text()
    if last_poll_s is None:
        age = "—"
        age_style = MUTED
    else:
        age = f"{time.time() - last_poll_s:.1f}s ago"
        age_style = AMBER if (time.time() - last_poll_s) > 10 else MUTED

    line_style = AMBER if not router_up else MUTED
    t.append(f"ROUTER · caruana:8081 · ", style=line_style)
    t.append("up" if router_up else "UNREACHABLE", style=GREEN if router_up else RED)
    t.append(f" · {backend_count}/{total_backends} backends healthy · ", style=line_style)
    t.append(f"last poll {age}", style=age_style)
    return t


# ── Hardcoded mock data for Gate 4 visual review ───────────────────────────────

_MOCK_BYWATER = dict(
    name="bywater", hostname="caruana", gpu_name="RTX 4090M", uptime_s=2 * 86400 + 4 * 3600,
    gpu_pct=8, vram_used_mb=4096, vram_total_mb=16384, temp_c=54,
    cpu_pct=12.0, ram_used_bytes=5_798_205_440, ram_total_bytes=17_179_869_184,
    ollama_models=[{"name": "gpt-oss:latest", "size_mb": 3276, "vram_pct": 8, "cpu_pct": 0}],
    req_per_s=1.2, error_count=0, offline=False,
)
_MOCK_DEEPWATER = dict(
    name="deepwater", hostname="alphablue", gpu_name="RTX 3090", uptime_s=2 * 86400 + 4 * 3600,
    gpu_pct=91, vram_used_mb=40755, vram_total_mb=49152, temp_c=81,
    cpu_pct=5.0, ram_used_bytes=24_000_000_000, ram_total_bytes=68_719_476_736,
    ollama_models=[{"name": "qwq:latest", "size_mb": 34918, "vram_pct": 91, "cpu_pct": 18}],
    req_per_s=0.1, error_count=0, offline=False,
)


def main() -> None:
    console = Console()

    with Live(console=console, refresh_per_second=1, screen=False) as live:
        while True:
            bw_panel = build_backend_panel(**_MOCK_BYWATER)
            dw_panel = build_backend_panel(**_MOCK_DEEPWATER)

            layout = Layout()
            layout.split_row(Layout(bw_panel, name="bywater"), Layout(dw_panel, name="deepwater"))

            status_bar = build_router_status_bar(True, 2, 2, time.time())
            from rich.console import Group
            live.update(Group(layout, status_bar))
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
