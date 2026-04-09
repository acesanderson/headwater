# /// script
# requires-python = ">=3.12"
# dependencies = ["rich>=13", "httpx>=0.27"]
# ///
from __future__ import annotations

import time
from datetime import datetime

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.columns import Columns

# ── Constants ─────────────────────────────────────────────────────────────────

ROUTER_URL = "http://172.16.0.4:8081"
POLL_INTERVAL = 1.0
HEADER_HEIGHT = 9  # 6 logo lines + 1 status + 1 col header + 1 panel border
MAX_PENDING_CYCLES = 3

INTERNAL_PREFIXES = frozenset([
    "/ping", "/status", "/metrics", "/logs/last", "/routes", "/gpu", "/sysinfo",
])
SPECIAL_ROUTES = frozenset(["heavy_inference", "ambient_inference", "reranker_heavy"])

GREEN  = "#4ec9b0"
AMBER  = "#e8c07d"
RED    = "#f44747"
PURPLE = "#c586c0"
BLUE   = "#6a9fb5"
ORANGE = "#ce9178"
YELLOW = "#dcdcaa"
MUTED  = "#333333"

LOGO_LINES = [
    "    ██╗  ██╗███████╗ █████╗ ██████╗ ██╗    ██╗ █████╗ ████████╗███████╗██████╗ ",
    "    ██║  ██║██╔════╝██╔══██╗██╔══██╗██║    ██║██╔══██╗╚══██╔══╝██╔════╝██╔══██╗",
    "    ███████║█████╗  ███████║██║  ██║██║ █╗ ██║███████║   ██║   █████╗  ██████╔╝",
    "    ██╔══██║██╔══╝  ██╔══██║██║  ██║██║███╗██║██╔══██║   ██║   ██╔══╝  ██╔══██╗",
    "    ██║  ██║███████╗██║  ██║██████╔╝╚███╔███╔╝██║  ██║   ██║   ███████╗██║  ██║",
    "    ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═════╝  ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝",
]

COL_WIDTHS = {"TIME": 8, "METH": 5, "PATH": 28, "ROUTE": 18, "BACKEND": 12, "MODEL": 16, "ST": 4, "DUR": 7}

# ── Pure helpers ───────────────────────────────────────────────────────────────

def truncate(s: str, width: int) -> str:
    if len(s) <= width:
        return s
    return s[:width - 1] + "…"


def is_internal_path(path: str) -> bool:
    normalized = "/" + path.lstrip("/")
    return any(normalized == p or normalized.startswith(p + "/") for p in INTERNAL_PREFIXES)


def status_color(code: int | None) -> str:
    if code is None:
        return MUTED
    if 200 <= code < 300:
        return GREEN
    if 400 <= code < 500:
        return AMBER
    if 500 <= code < 600:
        return RED
    return "#888888"


def route_color(route_key: str | None) -> str:
    if route_key in SPECIAL_ROUTES:
        return AMBER
    return PURPLE


def compute_row_cap(term_height: int, header_height: int) -> int:
    return max(1, term_height - header_height - 2)


def format_duration(ms: float | None) -> str:
    if ms is None:
        return "—"
    return f"{int(ms)}ms"

# ── Header rendering ───────────────────────────────────────────────────────────

def build_header(console: Console, router_status: str, backend_count: int, last_poll_s: float | None) -> Panel:
    logo_text = Text()
    for i, line in enumerate(LOGO_LINES):
        logo_text.append(line, style=f"bold {GREEN}")
        if i < len(LOGO_LINES) - 1:
            logo_text.append("\n")

    if console.size.width < 76:
        logo_text = Text("HEADWATER", style=f"bold {GREEN}")

    # Status subtitle
    if last_poll_s is None:
        staleness = "connecting…"
        staleness_style = MUTED
    else:
        age = int(time.time() - last_poll_s)
        staleness = f"last poll {age}s ago"
        staleness_style = AMBER if age > 5 else MUTED

    status_color_str = GREEN if router_status == "up" else RED
    status_line = Text()
    status_line.append("router · caruana:8081 · ", style=MUTED)
    status_line.append(router_status, style=status_color_str)
    status_line.append(f" · {backend_count} backends healthy · ", style=MUTED)
    status_line.append(staleness, style=staleness_style)

    combined = Text()
    combined.append_text(logo_text)
    combined.append("\n")
    combined.append_text(status_line)

    return Panel(combined, style="on #0a0a0a", border_style="#1a1a1a")


def main() -> None:
    console = Console()
    router_status = "connecting…"
    backend_count = 0
    last_successful_poll: float | None = None

    with Live(console=console, refresh_per_second=2, screen=False) as live:
        while True:
            header = build_header(console, router_status, backend_count, last_successful_poll)
            live.update(header)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
