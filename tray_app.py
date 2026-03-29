"""
ODI Quant — System Tray Application
Runs the FastAPI server silently in the background.
Tray icon gives quick access to the dashboard and controls.
"""
import sys
import os
import threading
import webbrowser
import time
import logging

# ── Bootstrap path ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

# ── Suppress console window output ──────────────────────────────────────────
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "odi_quant.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    import uvicorn
except ImportError as e:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("ODI Quant", f"Missing dependency: {e}\nRun: pip install pystray pillow fastapi uvicorn")
    sys.exit(1)

PORT = 8000
HOST = "127.0.0.1"
DASHBOARD_URL = f"http://{HOST}:{PORT}"
_server_started = threading.Event()
_pipeline_running = False


# ── Tray Icon Image ──────────────────────────────────────────────────────────
def create_icon_image(color="#00c896"):
    """Create a simple circular icon with 'OQ' text."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle
    draw.ellipse([2, 2, size - 2, size - 2], fill="#12121a", outline=color, width=3)

    # Text "OQ"
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), "OQ", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 - 2), "OQ", fill=color, font=font)

    return img


def create_busy_icon():
    """Pulsing amber icon when pipeline is running."""
    return create_icon_image("#ffd700")


# ── FastAPI Server Thread ────────────────────────────────────────────────────
def start_server():
    os.chdir(BACKEND_DIR)
    try:
        from storage.db import initialize_db
        initialize_db()
    except Exception as e:
        logger.error(f"DB init failed: {e}")

    config = uvicorn.Config(
        "main:app",
        host=HOST,
        port=PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    _server_started.set()
    logger.info(f"Starting ODI Quant server on {DASHBOARD_URL}")
    server.run()


# ── Tray Menu Actions ────────────────────────────────────────────────────────
def open_dashboard(icon=None, item=None):
    webbrowser.open(DASHBOARD_URL)


def run_analysis(icon=None, item=None):
    global _pipeline_running
    if _pipeline_running:
        return

    def _run():
        global _pipeline_running
        _pipeline_running = True
        if icon:
            icon.icon = create_busy_icon()
            icon.title = "ODI Quant — Running analysis..."

        try:
            import urllib.request
            req = urllib.request.urlopen(f"{DASHBOARD_URL}/api/run", timeout=180)
            data = req.read()
            logger.info("Pipeline completed successfully")
            if icon:
                icon.title = "ODI Quant — Analysis done! ✓"
        except Exception as e:
            logger.error(f"Pipeline request failed: {e}")
            if icon:
                icon.title = "ODI Quant — Analysis failed"
        finally:
            _pipeline_running = False
            if icon:
                time.sleep(3)
                icon.icon = create_icon_image()
                icon.title = "ODI Quant"

    threading.Thread(target=_run, daemon=True).start()


def open_api_docs(icon=None, item=None):
    webbrowser.open(f"{DASHBOARD_URL}/docs")


def view_logs(icon=None, item=None):
    log_path = os.path.join(BASE_DIR, "odi_quant.log")
    os.startfile(log_path) if os.path.exists(log_path) else None


def quit_app(icon, item):
    logger.info("ODI Quant exiting via tray")
    icon.stop()
    os._exit(0)


# ── Build Tray Menu ──────────────────────────────────────────────────────────
def build_menu():
    return pystray.Menu(
        pystray.MenuItem("📊 Open Dashboard", open_dashboard, default=True),
        pystray.MenuItem("▶  Run Analysis", run_analysis),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("📖 API Docs", open_api_docs),
        pystray.MenuItem("📋 View Logs", view_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ Exit ODI Quant", quit_app),
    )


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    # Start FastAPI server in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait for server to initialize (max 15s)
    _server_started.wait(timeout=15)
    time.sleep(1.5)  # Give uvicorn a moment to bind the port

    # Open dashboard on first launch
    threading.Thread(
        target=lambda: (time.sleep(2), webbrowser.open(DASHBOARD_URL)),
        daemon=True
    ).start()

    # Create and run tray icon
    icon_img = create_icon_image()
    tray = pystray.Icon(
        name="ODI Quant",
        icon=icon_img,
        title="ODI Quant — NSE Scanner",
        menu=build_menu(),
    )

    logger.info("Tray app started")
    tray.run()


if __name__ == "__main__":
    main()
