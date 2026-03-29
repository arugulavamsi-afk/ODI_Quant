"""
ODI Quant - Auto-start Setup
Adds ODI Quant to Windows startup so it launches automatically on login.
Also creates a desktop shortcut.

Run once:  python setup_autostart.py
Remove:    python setup_autostart.py --remove
"""
import os
import sys
import argparse
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = sys.executable
TRAY_SCRIPT = os.path.join(BASE_DIR, "tray_app.py")

STARTUP_FOLDER = os.path.join(
    os.environ.get("APPDATA", ""),
    r"Microsoft\Windows\Start Menu\Programs\Startup"
)

SHORTCUT_NAME = "ODI Quant.lnk"
STARTUP_SHORTCUT = os.path.join(STARTUP_FOLDER, SHORTCUT_NAME)
DESKTOP_SHORTCUT = os.path.join(os.path.expanduser("~"), "Desktop", SHORTCUT_NAME)


def create_shortcut(target_path: str, shortcut_path: str, description: str,
                    icon_path: str = None, window_style: int = 7):
    """Create a Windows .lnk shortcut using PowerShell."""
    icon_line = f'$s.IconLocation = "{icon_path}"' if icon_path else ""
    ps_script = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("{shortcut_path}")
$s.TargetPath = "{PYTHON_EXE}"
$s.Arguments = '"{TRAY_SCRIPT}"'
$s.WorkingDirectory = "{BASE_DIR}"
$s.WindowStyle = {window_style}
$s.Description = "{description}"
{icon_line}
$s.Save()
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  Warning: {result.stderr.strip()}")
    return result.returncode == 0


def remove_shortcut(path: str):
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def setup():
    print("\n ODI Quant - Auto-start Setup")
    print("=" * 42)

    # 1. Startup folder shortcut (hidden window = style 7)
    print(f"\n[1] Adding to Windows Startup...")
    ok = create_shortcut(
        target_path=PYTHON_EXE,
        shortcut_path=STARTUP_SHORTCUT,
        description="ODI Quant NSE Trading Scanner",
        window_style=7,  # 7 = minimized (no console window)
    )
    if ok and os.path.exists(STARTUP_SHORTCUT):
        print(f"    OK  {STARTUP_SHORTCUT}")
    else:
        print(f"    FAIL — try running as Administrator")

    # 2. Desktop shortcut
    print(f"\n[2] Creating Desktop shortcut...")
    ok = create_shortcut(
        target_path=PYTHON_EXE,
        shortcut_path=DESKTOP_SHORTCUT,
        description="ODI Quant NSE Trading Scanner",
        window_style=7,
    )
    if ok and os.path.exists(DESKTOP_SHORTCUT):
        print(f"    OK  {DESKTOP_SHORTCUT}")
    else:
        print(f"    FAIL")

    # 3. Also create a browser shortcut to open the dashboard directly
    browser_shortcut_path = os.path.join(os.path.expanduser("~"), "Desktop", "ODI Quant Dashboard.url")
    with open(browser_shortcut_path, "w") as f:
        f.write("[InternetShortcut]\nURL=http://localhost:8000\nIconIndex=0\n")
    print(f"\n[3] Browser shortcut created:")
    print(f"    OK  {browser_shortcut_path}")

    print("\n" + "=" * 42)
    print(" Setup complete!")
    print()
    print(" On next Windows login, ODI Quant will:")
    print("  - Start automatically (no window)")
    print("  - Show a tray icon (bottom-right)")
    print("  - Open the dashboard in your browser")
    print()
    print(" Desktop shortcuts:")
    print("  - 'ODI Quant.lnk'           -> starts the tray app")
    print("  - 'ODI Quant Dashboard.url'  -> opens browser directly")
    print()
    print(" To start right now:  python tray_app.py")
    print()


def remove():
    print("\n ODI Quant - Removing Auto-start")
    print("=" * 42)

    for path, label in [
        (STARTUP_SHORTCUT, "Startup shortcut"),
        (DESKTOP_SHORTCUT, "Desktop shortcut (app)"),
        (os.path.join(os.path.expanduser("~"), "Desktop", "ODI Quant Dashboard.url"), "Desktop shortcut (browser)"),
    ]:
        if remove_shortcut(path):
            print(f"  Removed: {label}")
        else:
            print(f"  Not found: {label}")

    print("\n Auto-start removed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--remove", action="store_true", help="Remove auto-start")
    args = parser.parse_args()

    if args.remove:
        remove()
    else:
        setup()
