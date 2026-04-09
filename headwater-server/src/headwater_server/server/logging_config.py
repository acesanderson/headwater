"""
Configures centralized logging for the Headwater Server with three handlers:
- RichHandler: colorized console output, level controlled by PYTHON_LOG_LEVEL env var (1=WARNING, 2=INFO, 3=DEBUG)
- TimedRotatingFileHandler: DEBUG-level file logging to the XDG state directory, rotated daily, 30-day retention
- RingBufferHandler: in-memory ring buffer of the last 500 records, accessible via GET /logs/last

Request ID injection: Every LogRecord receives a request_id attribute via setLogRecordFactory,
which reads the current value from the request_id_var ContextVar (defaults to "system").

Log files are located in the XDG state directory under headwater_server/logs/server.log.
"""

from __future__ import annotations

import collections
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from xdg_base_dirs import (
    xdg_state_home,
)
from rich.console import Console
from rich.logging import RichHandler


_STANDARD_LOG_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName", "request_id",
    "root_package",  # added by PackagePathFilter
})


class PackagePathFilter(logging.Filter):
    """
    Prepends the root package name to record.pathname so Rich shows it in the right column.
    Example: my_app/utils/helpers.py -> my_app:helpers.py
    """

    def filter(self, record):
        record.root_package = record.name.split(".")[0]
        original_basename = os.path.basename(record.pathname)
        new_basename = f"{record.root_package}:{original_basename}"
        original_dirname = os.path.dirname(record.pathname)
        record.pathname = os.path.join(original_dirname, new_basename)
        return True


_orig_record_factory = logging.getLogRecordFactory()


def _request_id_record_factory(*args, **kwargs):
    record = _orig_record_factory(*args, **kwargs)
    from headwater_server.server.context import request_id_var
    record.request_id = request_id_var.get()
    return record


# --- Log level from env (still numeric, as you had) ---
log_level = int(os.getenv("PYTHON_LOG_LEVEL", "2"))  # 1=WARNING, 2=INFO, 3=DEBUG
levels = {1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}
root_level = levels.get(log_level, logging.INFO)

# --- Console handler (Rich) ---
console = Console(file=os.sys.stdout)  # force stdout instead of stderr if you care
rich_handler = RichHandler(
    rich_tracebacks=True,
    markup=True,
    console=console,
)
rich_handler.setFormatter(logging.Formatter("%(message)s"))
rich_handler.addFilter(PackagePathFilter())
rich_handler.setLevel(root_level)  # console level

# --- File handler (DEBUG) ---
log_dir = xdg_state_home() / "headwater_server" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "server.log"

file_handler = TimedRotatingFileHandler(
    log_file,
    when='midnight',
    backupCount=30,
    encoding='utf-8',
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(pathname)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M",
    )
)


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 500):
        super().__init__()
        self.capacity = capacity
        self._buffer: collections.deque = collections.deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        self._buffer.append(record)

    def get_records(self, n: int) -> list[dict]:
        if n <= 0:
            return []
        records = list(self._buffer)
        result = []
        for r in records[-n:]:
            extra = {
                k: v for k, v in r.__dict__.items()
                if k not in _STANDARD_LOG_ATTRS
                and isinstance(v, (str, int, float, bool, type(None)))
            }
            result.append({
                "timestamp": r.created,
                "level": r.levelname,
                "logger": r.name,
                "message": r.getMessage(),
                "pathname": r.pathname,
                "request_id": r.__dict__.get("request_id", None),
                "extra": extra if extra else None,
            })
        return result

    def get_response(self, n: int):
        from headwater_api.classes import LogsLastResponse, LogEntry
        entries = [LogEntry(**e) for e in self.get_records(n)]
        return LogsLastResponse(
            entries=entries,
            total_buffered=len(self._buffer),
            capacity=self.capacity,
        )


ring_buffer = RingBufferHandler(capacity=500)

# --- Root logger wiring ---
# Use explicit addHandler instead of basicConfig — basicConfig is a no-op when
# handlers already exist (e.g. when pytest has configured logging first).
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
for _handler in [rich_handler, file_handler, ring_buffer]:
    root_logger.addHandler(_handler)

# Inject request_id into every record via record factory (works for all loggers, including child loggers)
logging.setLogRecordFactory(_request_id_record_factory)

# Silence third-party loggers. Hardcoded — not configurable.
# uvicorn.error is intentionally excluded: it reports worker crashes.
SUPPRESSED_LOGGERS = [
    "httpx",
    "httpcore",
    "sentence_transformers",
    "conduit",
    "uvicorn.access",
]
for _name in SUPPRESSED_LOGGERS:
    logging.getLogger(_name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
