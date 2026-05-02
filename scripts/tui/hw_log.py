# /// script
# requires-python = ">=3.12"
# dependencies = ["rich>=13", "httpx>=0.27"]
# ///
from __future__ import annotations

import collections
import os
import select
import shutil
import subprocess
import sys
import termios
import time
import tty
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

# ── Constants ─────────────────────────────────────────────────────────────────

ROUTER_URL = "http://172.16.0.4:8081"
SUBSERVER_URLS = {
    "bywater":   "http://172.16.0.4:8080",
    "deepwater":  "http://172.16.0.2:8080",
    "backwater":  "http://172.16.0.3:8080",
}
IP_TO_HOST = {
    "172.16.0.4": "caruana",
    "172.16.0.2": "alphablue",
    "172.16.0.3": "botvinnik",
    "172.16.0.11": "lasker",
}
POLL_INTERVAL = 1.0
HEADER_HEIGHT = 9  # 6 logo lines + 1 status + 1 col header + 1 panel border
MAX_PENDING_CYCLES = 3
BACKEND_CHECK_INTERVAL = 10

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

COL_WIDTHS = {"TIME": 8, "CNT": 5, "METH": 5, "PATH": 26, "VIA": 16, "BACKEND": 20, "MODEL": 22, "ST": 4, "DUR": 7}

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


def via_text(route_key: str | None) -> str:
    return route_key if route_key is not None else "direct"


def via_color(route_key: str | None) -> str:
    if route_key is None:
        return MUTED
    if route_key in SPECIAL_ROUTES:
        return AMBER
    return PURPLE


def compute_row_cap(term_height: int, header_height: int) -> int:
    return max(1, term_height - header_height - 2)


def format_duration(ms: float | None) -> str:
    if ms is None:
        return "—"
    return f"{int(ms)}ms"

# ── Row compression ───────────────────────────────────────────────────────────

def _row_signature(row: "PendingRow") -> tuple:
    return (row.path, row.method, row.route, row.backend, row.model, row.upstream_status)


def compress_rows(rows: list["PendingRow"]) -> list[tuple["PendingRow", int]]:
    """Collapse consecutive rows with identical signatures into (row, count) pairs."""
    if not rows:
        return []
    result: list[tuple[PendingRow, int]] = []
    current, count = rows[0], 1
    for row in rows[1:]:
        if _row_signature(row) == _row_signature(current):
            count += 1
            current = row  # keep latest timestamp
        else:
            result.append((current, count))
            current, count = row, 1
    result.append((current, count))
    return result


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
            path = "/" + extra.get("path", "").lstrip("/")
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


def process_subserver_entries(
    entries: list[dict],
    backend_url: str,
    seen: set[str],
    completed: list[PendingRow],
) -> None:
    """Extract direct (non-routed) requests from a subserver's ring buffer.

    Router-proxied requests share the same request_id and will already be in
    `seen` after process_entries() runs. We skip those and only emit rows for
    requests that arrived at the subserver directly.
    """
    for entry in entries:
        if entry.get("message") != "request_finished":
            continue
        req_id = entry.get("request_id")
        if req_id and req_id in seen:
            continue
        extra = entry.get("extra") or {}
        path = "/" + extra.get("path", "").lstrip("/")
        if is_internal_path(path):
            continue
        completed.append(PendingRow(
            timestamp=entry["timestamp"],
            path=path,
            service=path.lstrip("/").split("/")[0],
            backend=backend_url,
            model=extra.get("model"),
            route=None,
            upstream_status=extra.get("status_code"),
            method=extra.get("method"),
            duration_ms=extra.get("duration_ms"),
        ))
        if req_id:
            seen.add(req_id)


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
    table.add_column("CNT",                        width=COL_WIDTHS["CNT"],     no_wrap=True)
    table.add_column("METH",         style=GREEN,   width=COL_WIDTHS["METH"],    no_wrap=True)
    table.add_column("SERVICE/PATH", style=YELLOW,  width=COL_WIDTHS["PATH"],    no_wrap=True)
    table.add_column("VIA",                         width=COL_WIDTHS["VIA"],     no_wrap=True)
    table.add_column("BACKEND",      style=BLUE,    width=COL_WIDTHS["BACKEND"], no_wrap=True)
    table.add_column("MODEL",        style=ORANGE,  width=COL_WIDTHS["MODEL"],   no_wrap=True)
    table.add_column("ST",                          width=COL_WIDTHS["ST"],      no_wrap=True)
    table.add_column("DUR",          style=MUTED,   width=COL_WIDTHS["DUR"],     no_wrap=True)

    for row, count in compress_rows(rows):
        ts = datetime.fromtimestamp(row.timestamp).strftime("%H:%M:%S")
        cnt_str = f"[{AMBER}]×{count}[/{AMBER}]" if count > 1 else ""
        via_str = truncate(via_text(row.route), COL_WIDTHS["VIA"])
        vc = via_color(row.route)
        st_str = str(row.upstream_status) if row.upstream_status is not None else "—"
        sc = status_color(row.upstream_status)
        ip = row.backend.split("//")[-1].split(":")[0]
        host = IP_TO_HOST.get(ip, ip)
        backend_str = truncate(f"{host} ({ip})", COL_WIDTHS["BACKEND"])

        table.add_row(
            ts,
            cnt_str,
            row.method or "—",
            truncate(row.path, COL_WIDTHS["PATH"]),
            f"[{vc}]{via_str}[/{vc}]",
            backend_str,
            truncate((row.model.split("/")[-1] if row.model else "—"), COL_WIDTHS["MODEL"]),
            f"[{sc}]{st_str}[/{sc}]",
            format_duration(row.duration_ms),
        )
    return table


# ── Header rendering ───────────────────────────────────────────────────────────

def build_header(console: Console, router_status: str, backend_count: int, last_poll_s: float | None, blast_state: dict | None = None) -> Panel:
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

    blast_ts = (blast_state or {}).get("ts")
    if blast_ts and (time.time() - blast_ts) < _BLAST_INDICATOR_SECS:
        status_line.append(" · blasting…", style=AMBER)
    else:
        status_line.append(" · [b] blast", style=MUTED)

    combined = Text()
    combined.append_text(logo_text)
    combined.append("\n")
    combined.append_text(status_line)

    return Panel(combined, style="on #0a0a0a", border_style="#1a1a1a")


def count_healthy_backends(backend_urls: list[str]) -> int:
    count = 0
    for url in backend_urls:
        try:
            r = httpx.get(f"{url}/ping", timeout=2.0)
            if r.status_code == 200:
                count += 1
        except Exception:
            pass
    return count


# ── Blast integration ─────────────────────────────────────────────────────────

_BLAST_SCRIPT = Path(__file__).parent / "hw_blast.py"
_BLAST_INDICATOR_SECS = 5


def _fire_blast(blast_state: dict) -> None:
    uv = shutil.which("uv") or "uv"
    blast_state["ts"] = time.time()
    subprocess.Popen(
        [uv, "run", str(_BLAST_SCRIPT), "--n", "30", "--delay", "0.3"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    console = Console()
    router_status = "UNREACHABLE"
    backend_count = 0
    last_successful_poll: float | None = None
    backend_urls: list[str] = []
    poll_tick = 0

    pending: dict[str, PendingRow] = {}
    seen: set[str] = set()
    row_deque: collections.deque[PendingRow] = collections.deque()
    last_seen_ts: dict[str, float] = {"router": 0.0} | {k: 0.0 for k in SUBSERVER_URLS}
    blast_state: dict = {}

    fd = sys.stdin.fileno()
    old_term = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        with Live(console=console, refresh_per_second=2, screen=True) as live:
            while True:
                term_height = console.size.height
                row_cap = compute_row_cap(term_height, HEADER_HEIGHT)
                completed: list[PendingRow] = []

                # ── router ────────────────────────────────────────────────────────
                try:
                    resp = httpx.get(f"{ROUTER_URL}/logs/last?n=100", timeout=3.0)
                    resp.raise_for_status()
                    data = resp.json()
                    router_status = "up"
                    last_successful_poll = time.time()

                    if poll_tick % BACKEND_CHECK_INTERVAL == 0:
                        try:
                            s = httpx.get(f"{ROUTER_URL}/routes/", timeout=2.0)
                            backend_urls = list(s.json().get("backends", {}).values())
                        except Exception:
                            pass
                        backend_count = count_healthy_backends(backend_urls)

                    entries = data.get("entries", [])
                    new_entries = [e for e in entries if e.get("timestamp", 0) > last_seen_ts["router"]]
                    if new_entries:
                        last_seen_ts["router"] = max(e["timestamp"] for e in new_entries)
                    process_entries(new_entries, pending, seen, completed)

                except Exception:
                    router_status = "UNREACHABLE"

                # ── subservers (direct traffic only) ──────────────────────────────
                for name, url in SUBSERVER_URLS.items():
                    try:
                        resp = httpx.get(f"{url}/logs/last?n=100", timeout=2.0)
                        resp.raise_for_status()
                        entries = resp.json().get("entries", [])
                        new_entries = [e for e in entries if e.get("timestamp", 0) > last_seen_ts[name]]
                        if new_entries:
                            last_seen_ts[name] = max(e["timestamp"] for e in new_entries)
                        process_subserver_entries(new_entries, url, seen, completed)
                    except Exception:
                        pass

                poll_tick += 1
                for row in completed:
                    row_deque.append(row)

                while len(row_deque) > row_cap:
                    row_deque.popleft()

                header = build_header(console, router_status, backend_count, last_successful_poll, blast_state)
                table = build_log_table(list(row_deque))
                live.update(Group(header, table))

                # Sleep for POLL_INTERVAL but wake immediately on keypress
                rlist, _, _ = select.select([sys.stdin], [], [], POLL_INTERVAL)
                if rlist:
                    ch = os.read(fd, 1)
                    if ch == b"b":
                        _fire_blast(blast_state)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_term)


if __name__ == "__main__":
    main()
