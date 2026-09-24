"""Prepare the optional model download, then start the local web server."""

from __future__ import annotations

import os
import sys

from model_setup import ensure_model


if __name__ == "__main__":
    try:
        ensure_model()
    except Exception as exc:
        print(f"Model setup failed: {exc}", flush=True)
        print("Place a compatible model at model/best.pt and restart the container.", flush=True)
    os.execv(sys.executable, [sys.executable, "web_server.py", "--host", "0.0.0.0", "--port", "8000"])
