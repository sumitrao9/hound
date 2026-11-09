from .server import build_server, main

__all__ = ["build_server", "main"]

def serve_http():
    from .http import main
    main()
