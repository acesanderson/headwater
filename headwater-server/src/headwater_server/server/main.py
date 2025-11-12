import logging
import os
from rich.logging import RichHandler

# Set up Rich logging
log_level = int(os.getenv("PYTHON_LOG_LEVEL", "2"))  # Default to INFO
levels = {1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}
logging.basicConfig(
    level=levels.get(log_level, logging.INFO),
    format="%(message)s",  # Let Rich handle layout (time, level, filename)
    datefmt="%Y-%m-%d %H:%M",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)],
)
logger = logging.getLogger(__name__)


def main():
    from headwater_server.server.logo import print_logo
    from pathlib import Path
    import uvicorn

    print_logo()

    uvicorn.run(
        "headwater_server.server.headwater:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        reload_dirs=[str(Path(__file__).parent.parent.parent)],
        log_level="info",
    )


if __name__ == "__main__":
    main()
