#!/usr/bin/env python3
"""
ODI Quant — Single-command launcher.
Usage:
    python run.py            # Start server + open browser
    python run.py --no-browser  # Start server only
"""
import subprocess
import sys
import os
import webbrowser
import time
import threading
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")

BANNER = """
╔══════════════════════════════════════════════════════════╗
║          ODI QUANT — NSE Day Trading Scanner             ║
║          Next-Day Setup Probability Engine v1.0          ║
╚══════════════════════════════════════════════════════════╝

  📊  Dashboard  :  http://localhost:8000
  🔌  API Docs   :  http://localhost:8000/docs
  ❤️   Health     :  http://localhost:8000/api/health

  Press Ctrl+C to stop.
"""


def check_dependencies():
    """Check that required packages are installed."""
    missing = []
    required = ["fastapi", "uvicorn", "yfinance", "pandas", "numpy"]
    for pkg in required:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print(f"Run: pip install -r {os.path.join(BACKEND_DIR, 'requirements.txt')}\n")
        sys.exit(1)


def open_browser_delayed(url: str, delay: float = 3.0):
    """Open browser after a short delay to let server start."""
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(description="ODI Quant Trading System")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    parser.add_argument("--port", type=int, default=8000, help="Port number (default: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    args = parser.parse_args()

    check_dependencies()
    print(BANNER)

    if not args.no_browser:
        open_browser_delayed(f"http://localhost:{args.port}", delay=3.5)

    # Build uvicorn command
    cmd = [
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", args.host,
        "--port", str(args.port),
        "--log-level", "info",
    ]
    if args.reload:
        cmd.append("--reload")

    # Run from backend directory
    os.chdir(BACKEND_DIR)
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n\n👋  ODI Quant stopped. Good trading!")


if __name__ == "__main__":
    main()
