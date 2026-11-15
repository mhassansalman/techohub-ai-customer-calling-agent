"""Explicit local entry point, independent of deployment environment variables."""
from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    os.environ["TECHOHUB_RUNTIME"] = "local"
    os.environ.setdefault("TECHOHUB_CLOCK_MODE", "system")
    # Import only after selecting the runtime; backend.main constructs its app.
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
