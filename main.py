"""
main.py - Application entry point.

Handles PyInstaller frozen-mode path bootstrapping so that 'core' and 'ui'
packages are importable whether running from source or as a packaged .exe.

Errors are written to:  logs/error.log   (next to main.py / the .exe)
Full debug log:          logs/app.log
"""

import sys
import os
import ctypes
from pathlib import Path

# Hide console window on Windows (desktop shortcut / no --noconsole needed)
if sys.platform == "win32":
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)




def _bootstrap_paths():
    """
    Ensure the project root is on sys.path.
    - When frozen (PyInstaller): the extracted temp dir (sys._MEIPASS) acts as root.
    - When run normally:         the directory containing main.py is the root.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        root = Path(sys._MEIPASS)
    else:
        root = Path(__file__).resolve().parent

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


_bootstrap_paths()

# ── Logger must be imported first so all subsequent errors are captured ────────
from core.logger import logger

logger.info("=" * 60)
logger.info("Media Downloader starting up")
logger.info(f"Python {sys.version}")
logger.info(f"Working dir: {Path.cwd()}")

# ── Rest of imports ────────────────────────────────────────────────────────────
try:
    from core.utils import is_ffmpeg_installed
    from ui.app import App
except Exception:
    logger.critical("Fatal import error — check logs/error.log", exc_info=True)
    sys.exit(1)


def check_dependencies():
    if not is_ffmpeg_installed():
        logger.warning("FFmpeg not found in PATH — merging/conversion will fail")
        print("WARNING: FFmpeg not found. Install from https://ffmpeg.org/download.html")


if __name__ == "__main__":
    try:
        check_dependencies()
        logger.info("Launching App window")
        app = App()
        app.mainloop()
        logger.info("App closed normally")
    except Exception:
        logger.critical("Unhandled exception in mainloop", exc_info=True)
        raise

