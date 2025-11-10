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
