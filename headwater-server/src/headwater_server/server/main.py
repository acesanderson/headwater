"""
Main entry point for the headwater server. Detects the host machine and starts the server with appropriate configuration, for either:
- Headwater (alphablue)
- Bywater (caruana)
- Backwater (cheet)
"""

import headwater_server.server.logging_config
from dbclients.discovery.host import get_network_context

# To comfort my IDE
_ = headwater_server.server.logging_config

# Servers
hosts = {
    "alphablue": "headwater",
    "caruana": "bywater",
    "cheet": "backwater",
}


def run_server(mode: str = "headwater"):
    from headwater_server.server.logo import print_logo
    from pathlib import Path
    import uvicorn
    import sys

    # 1. Clear screen and move cursor to top-left
    sys.stdout.write("\033[2J\033[H")

    # 2. Print your logo
    print_logo(mode)

    # 3. Determine how many lines the logo takes (e.g., 10 lines)
    # You may need to adjust this number based on your actual FIGlet height
    header_height = 10

    # 4. Set scrolling region: Top margin is header_height + 1, bottom is end of screen
    # Syntax: \033[<top>;<bottom>r
    # Note: Leaving bottom empty usually defaults to the screen edge
    sys.stdout.write(f"\033[{header_height + 1};r")

    # 5. Move cursor to the start of the scrolling region
    sys.stdout.write(f"\033[{header_height + 1};1H")
    sys.stdout.flush()

    try:
        uvicorn.run(
            "headwater_server.server.headwater:app",
            host="0.0.0.0",
            port=8080,
            reload=True,
            reload_dirs=[str(Path(__file__).parent.parent.parent)],
            log_config=None,
            log_level="info",
        )
    finally:
        # Reset scrolling region to default when exiting
        sys.stdout.write("\033[r")
        sys.stdout.flush()


def main():
    # Detect host
    network_context = get_network_context()
    hostname = network_context.local_hostname
    mode = hosts.get(
        hostname, "headwater"
    )  # Default to headwater if hostname not recognized
    run_server(mode)


if __name__ == "__main__":
    main()
