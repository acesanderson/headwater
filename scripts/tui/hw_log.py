# /// script
# requires-python = ">=3.12"
# dependencies = ["rich>=13", "httpx>=0.27"]
# ///
from __future__ import annotations

import collections
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

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
MUTED  = "#808080"

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

# ── Row assembly ──────────────────────────────────────────────────────────────

@dataclass
class PendingRow:
    timestamp: float
    path: str
    service: str
    backend: str
    model: str | None
    route: str | None
    upstream_status: int | None = None
    method: str | None = None
    duration_ms: float | None = None
    cycles: int = 0


def process_entries(
    entries: list[dict],
    pending: dict[str, PendingRow],
    seen: set[str],
    completed: list[PendingRow],
) -> None:
    """Process new log entries; update pending rows; emit completed or timed-out rows."""
    for entry in entries:
        req_id = entry.get("request_id")
        msg = entry.get("message")
        extra = entry.get("extra") or {}

        if msg == "proxy_request" and req_id and req_id not in seen and req_id not in pending:
            path = extra.get("path", "")
            if is_internal_path(path):
                continue
            pending[req_id] = PendingRow(
                timestamp=entry["timestamp"],
                path=path,
                service=extra.get("service", ""),
                backend=extra.get("backend", ""),
                model=extra.get("model"),
                route=extra.get("route"),
            )

        elif msg == "proxy_response" and req_id and req_id in pending:
            status = extra.get("upstream_status")
            if status is not None:
                pending[req_id].upstream_status = int(status)

        elif msg == "request_finished" and req_id and req_id in pending:
            pending[req_id].method = extra.get("method")
            dur = extra.get("duration_ms")
            if dur is not None:
                pending[req_id].duration_ms = float(dur)

    to_complete = [rid for rid, row in pending.items()
                   if row.upstream_status is not None and row.method is not None]
    for rid in to_complete:
        row = pending.pop(rid)
        seen.add(rid)
        completed.append(row)

    for row in pending.values():
        row.cycles += 1

    timed_out = [rid for rid, row in pending.items() if row.cycles >= MAX_PENDING_CYCLES]
    for rid in timed_out:
        row = pending.pop(rid)
        seen.add(rid)
        completed.append(row)


# ── Table rendering ───────────────────────────────────────────────────────────

def build_log_table(rows: list[PendingRow]) -> Table:
    table = Table(
        show_header=True,
        header_style=f"dim {MUTED}",
        box=None,
        padding=(0, 1, 0, 0),
        expand=True,
    )
    table.add_column("TIME",         style=MUTED,   width=COL_WIDTHS["TIME"],    no_wrap=True)
    table.add_column("METH",         style=GREEN,   width=COL_WIDTHS["METH"],    no_wrap=True)
    table.add_column("SERVICE/PATH", style=YELLOW,  width=COL_WIDTHS["PATH"],    no_wrap=True)
    table.add_column("ROUTE",                       width=COL_WIDTHS["ROUTE"],   no_wrap=True)
    table.add_column("BACKEND",      style=BLUE,    width=COL_WIDTHS["BACKEND"], no_wrap=True)
    table.add_column("MODEL",        style=ORANGE,  width=COL_WIDTHS["MODEL"],   no_wrap=True)
    table.add_column("ST",                          width=COL_WIDTHS["ST"],      no_wrap=True)
    table.add_column("DUR",          style=MUTED,   width=COL_WIDTHS["DUR"],     no_wrap=True)

    for row in rows:
        ts = datetime.fromtimestamp(row.timestamp).strftime("%H:%M:%S")
        route_str = truncate(row.route or "—", COL_WIDTHS["ROUTE"])
        rc = route_color(row.route)
        st_str = str(row.upstream_status) if row.upstream_status is not None else "—"
        sc = status_color(row.upstream_status)
        backend_short = row.backend.split("//")[-1].split(":")[0]

        table.add_row(
            ts,
            row.method or "—",
            truncate(row.path, COL_WIDTHS["PATH"]),
            f"[{rc}]{route_str}[/{rc}]",
            f"→ {backend_short}",
            truncate(row.model or "—", COL_WIDTHS["MODEL"]),
            f"[{sc}]{st_str}[/{sc}]",
            format_duration(row.duration_ms),
        )
    return table


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
    router_status = "UNREACHABLE"
    backend_count = 0
    last_successful_poll: float | None = None

    pending: dict[str, PendingRow] = {}
    seen: set[str] = set()
    row_deque: collections.deque[PendingRow] = collections.deque()
    last_seen_ts: float = 0.0

    with Live(console=console, refresh_per_second=2, screen=True) as live:
        while True:
            term_height = console.size.height
            row_cap = compute_row_cap(term_height, HEADER_HEIGHT)

            try:
                resp = httpx.get(f"{ROUTER_URL}/logs/last?n=100", timeout=3.0)
                resp.raise_for_status()
                data = resp.json()
                router_status = "up"
                last_successful_poll = time.time()

                try:
                    s = httpx.get(f"{ROUTER_URL}/status", timeout=2.0)
                    status_data = s.json()
                    backend_count = status_data.get("backend_count", backend_count)
                except Exception:
                    pass

                entries = data.get("entries", [])
                new_entries = [e for e in entries if e.get("timestamp", 0) > last_seen_ts]
                if new_entries:
                    last_seen_ts = max(e["timestamp"] for e in new_entries)

                completed: list[PendingRow] = []
                process_entries(new_entries, pending, seen, completed)

                for row in completed:
                    row_deque.append(row)

            except Exception:
                router_status = "UNREACHABLE"

            while len(row_deque) > row_cap:
                row_deque.popleft()

            header = build_header(console, router_status, backend_count, last_successful_poll)
            table = build_log_table(list(row_deque))
            live.update(Group(header, table))

            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
