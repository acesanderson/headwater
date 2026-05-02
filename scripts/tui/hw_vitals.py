# /// script
# requires-python = ">=3.12"
# dependencies = ["rich>=13", "httpx>=0.27"]
# ///
from __future__ import annotations

import time

import httpx
import rich.box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ── Constants ─────────────────────────────────────────────────────────────────

BYWATER_URL   = "http://172.16.0.4:8080"
DEEPWATER_URL = "http://172.16.0.2:8080"
BACKWATER_URL = "http://172.16.0.3:8080"
ROUTER_URL    = "http://172.16.0.4:8081"
POLL_INTERVAL = 2.0

GREEN  = "#4ec9b0"
AMBER  = "#e8c07d"
RED    = "#f44747"
BLUE   = "#9cdcfe"
ORANGE = "#ce9178"
MUTED  = "#ffffff"
DIM    = "#555555"

SERVER_COLORS = {
    "bywater":   "#dcdcaa",  # yellow  — matches logo.py \033[33m
    "deepwater": "#569cd6",  # blue    — matches logo.py \033[34m
    "backwater": "#4ec9b0",  # green   — matches logo.py \033[92m
}

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
        return Panel(t, title=f"[{RED}]{name}[/{RED}]", border_style=RED, box=rich.box.HEAVY, padding=(0, 2))

    tc = temp_color(temp_c)
    temp_str = f"{temp_c}C" if temp_c is not None else "—"
    uptime_str = format_uptime(uptime_s) if uptime_s is not None else "—"

    sc = SERVER_COLORS.get(name, BLUE)
    t.append(f"{name}  ", style=f"bold {sc}")
    t.append("* ", style=f"bold {tc}")
    t.append(f"{temp_str}\n", style=tc)
    t.append(f"{hostname} · {gpu_name} · up {uptime_str}\n", style=MUTED)
    t.append("\n")

    def metric_row(label: str, pct: float | None, used: str, total: str, kind: str) -> None:
        mc = metric_color(pct if pct is not None else 0, kind)
        t.append(f"{label:<10}", style=MUTED)
        bar_fill = int((pct if pct is not None else 0) / 100 * 20)
        t.append("█" * bar_fill, style=mc)
        t.append("░" * (20 - bar_fill), style=DIM)
        pct_str = f"{pct}%" if pct is not None else "—"
        t.append(f"  {pct_str}  {used}/{total}\n", style=mc)

    if gpu_pct is not None and vram_used_mb is not None and vram_total_mb is not None:
        metric_row("GPU UTIL", gpu_pct, f"{mb_to_gb(vram_used_mb):.1f}", f"{mb_to_gb(vram_total_mb):.0f}G", "gpu")
        vram_pct = int(vram_used_mb / vram_total_mb * 100) if vram_total_mb else 0
        metric_row("VRAM", vram_pct, f"{mb_to_gb(vram_used_mb):.1f}", f"{mb_to_gb(vram_total_mb):.0f}G", "vram")
    else:
        t.append("GPU  —\nVRAM  —\n", style=MUTED)

    if cpu_pct is not None and ram_used_bytes is not None and ram_total_bytes is not None:
        metric_row("CPU UTIL", cpu_pct, f"{bytes_to_gb(ram_used_bytes):.1f}", f"{bytes_to_gb(ram_total_bytes):.0f}G", "cpu")
        ram_pct = int(ram_used_bytes / ram_total_bytes * 100) if ram_total_bytes else 0
        metric_row("RAM", ram_pct, f"{bytes_to_gb(ram_used_bytes):.1f}", f"{bytes_to_gb(ram_total_bytes):.0f}G", "cpu")
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
            t.append(f"  {int(gpu)}% gpu\n", style=BLUE)
            err_style = RED if error_count > 0 else MUTED
            t.append(f"  {req_per_s:.1f} req/s · ", style=MUTED)
            t.append(f"{error_count} err\n", style=err_style)
    else:
        t.append("  no models loaded\n", style=MUTED)

    sc = SERVER_COLORS.get(name, BLUE)
    return Panel(t, title=f"[bold {sc}]{name}[/bold {sc}]", border_style=sc, box=rich.box.HEAVY, padding=(0, 2))


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


def main() -> None:
    console = Console()
    router_up = False
    last_successful_poll: float | None = None
    start_time = time.time()
    log_entries: list[dict] = []

    backends = {
        "bywater": BYWATER_URL,
        "deepwater": DEEPWATER_URL,
        "backwater": BACKWATER_URL,
    }

    with Live(console=console, refresh_per_second=1, screen=True) as live:
        while True:
            panels = []

            try:
                resp = httpx.get(f"{ROUTER_URL}/logs/last?n=500", timeout=3.0)
                resp.raise_for_status()
                log_entries = resp.json().get("entries", [])
                router_up = True
                last_successful_poll = time.time()
            except Exception:
                router_up = False

            for name, base_url in backends.items():
                offline = False
                gpu_data: dict | None = None
                sys_data: dict | None = None
                status_data: dict | None = None

                try:
                    r = httpx.get(f"{base_url}/gpu", timeout=5.0)
                    r.raise_for_status()
                    gpu_data = r.json()
                except Exception:
                    offline = True

                if not offline:
                    _sysinfo_404_warned: set[str] = getattr(main, "_sysinfo_404_warned", set())
                    try:
                        r = httpx.get(f"{base_url}/sysinfo", timeout=5.0)
                        if r.status_code == 404:
                            if name not in _sysinfo_404_warned:
                                import sys
                                print(f"WARNING: {name} /sysinfo returned 404 — CPU/RAM will show —", file=sys.stderr)
                                _sysinfo_404_warned.add(name)
                                main._sysinfo_404_warned = _sysinfo_404_warned
                            sys_data = None
                        else:
                            r.raise_for_status()
                            sys_data = r.json()
                    except httpx.HTTPStatusError:
                        sys_data = None
                    except Exception:
                        sys_data = None

                    try:
                        r = httpx.get(f"{base_url}/status", timeout=5.0)
                        r.raise_for_status()
                        status_data = r.json()
                    except Exception:
                        status_data = None

                now = time.time()
                rps = compute_req_per_s(log_entries, base_url, now, start_time)
                errs = compute_error_count(log_entries, base_url, now)

                if offline or gpu_data is None:
                    panels.append(build_backend_panel(
                        name=name, hostname="—", gpu_name="—", uptime_s=None,
                        gpu_pct=None, vram_used_mb=None, vram_total_mb=None, temp_c=None,
                        cpu_pct=None, ram_used_bytes=None, ram_total_bytes=None,
                        ollama_models=[], req_per_s=0.0, error_count=0, offline=True,
                    ))
                    continue

                gpus = gpu_data.get("gpus", [])
                gpu = gpus[0] if gpus else {}
                gpu_pct = gpu.get("utilization_pct")
                vram_used_mb = gpu.get("vram_used_mb")
                vram_total_mb = gpu.get("vram_total_mb")
                temp_c = gpu.get("temperature_c")
                hostname = gpu_data.get("server_name", name)
                gpu_name = gpu.get("name", "—")
                uptime_s = status_data.get("uptime") if status_data else None
                cpu_pct = sys_data.get("cpu_percent") if sys_data else None
                ram_used = sys_data.get("ram_used_bytes") if sys_data else None
                ram_total = sys_data.get("ram_total_bytes") if sys_data else None
                ollama_models = gpu_data.get("ollama_loaded_models", [])

                panels.append(build_backend_panel(
                    name=name, hostname=hostname, gpu_name=gpu_name, uptime_s=uptime_s,
                    gpu_pct=gpu_pct, vram_used_mb=vram_used_mb, vram_total_mb=vram_total_mb,
                    temp_c=temp_c, cpu_pct=cpu_pct, ram_used_bytes=ram_used, ram_total_bytes=ram_total,
                    ollama_models=ollama_models, req_per_s=rps, error_count=errs,
                    offline=False,
                ))

            # 2x2 grid: top row filled, bottom-left filled, bottom-right empty
            padded = panels + [""] * (4 - len(panels))
            grid = Table.grid(expand=True, padding=(0, 1))
            grid.add_column(ratio=1)
            grid.add_column(ratio=1)
            grid.add_row(padded[0], padded[1])
            grid.add_row(padded[2], padded[3])
            status_bar = build_router_status_bar(router_up, sum(1 for p in panels if True), len(backends), last_successful_poll)
            from rich.console import Group
            live.update(Group(grid, status_bar))

            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
