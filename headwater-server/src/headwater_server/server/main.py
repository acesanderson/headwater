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


def main():
    # Detect host
    network_context = get_network_context()
    hostname = network_context.local_hostname
    mode = hosts.get(
        hostname, "headwater"
    )  # Default to headwater if hostname not recognized

    from headwater_server.server.logo import print_logo
    from pathlib import Path
    import uvicorn

    print_logo(mode)

    uvicorn.run(
        "headwater_server.server.headwater:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        reload_dirs=[str(Path(__file__).parent.parent.parent)],
        log_config=None,
        log_level="info",
    )


if __name__ == "__main__":
    main()
