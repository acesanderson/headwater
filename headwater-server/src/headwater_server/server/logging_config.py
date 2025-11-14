"""
This module configures centralized logging for the Headwater Server with dual output handlers and environment-based log level control. It establishes a Rich console handler for colorized terminal output and a file handler for persistent DEBUG-level logging to the XDG state directory, while the PackagePathFilter enhances readability by reformatting log records to show package names alongside filenames.

The configuration wires both handlers into the root logger at initialization time, allowing the console output to respect the PYTHON_LOG_LEVEL environment variable (1=WARNING, 2=INFO, 3=DEBUG) while the file handler independently captures all DEBUG and above messages. This dual-level approach enables developers to control verbosity interactively while maintaining detailed audit trails on disk.

Log files are located in the XDG state directory under `headwater_server/logs/server.log`.

Usage:
```python
# Simply import to activate logging configuration
import headwater_server.server.logging_config
logger = logging.getLogger(__name__)  # Use in any module
logger.info("Server processing request")  # Appears in console and file
```
"""

import logging
import os
from xdg_base_dirs import (
    xdg_state_home,
)
from rich.console import Console
from rich.logging import RichHandler


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
rich_handler.addFilter(PackagePathFilter())
rich_handler.setLevel(root_level)  # console level

# --- File handler (DEBUG) ---
log_dir = xdg_state_home() / "headwater_server" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "server.log"

file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(pathname)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M",
    )
)

# --- Root logger wiring ---
logging.basicConfig(
    level=logging.DEBUG,  # allow DEBUG to reach handlers; handlers filter individually
    handlers=[rich_handler, file_handler],
)

logger = logging.getLogger(__name__)
