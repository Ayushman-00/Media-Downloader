"""
logger.py - Centralised logging setup.

All modules should import `logger` from here:
    from core.logger import logger

Log files are written next to the executable (PyInstaller-safe via user_data_path).
"""

import logging
import sys
from core.paths import user_data_path

# ── Paths ─────────────────────────────────────────────────────────────────────
LOG_DIR = user_data_path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE  = LOG_DIR / "app.log"
ERR_FILE  = LOG_DIR / "error.log"

# ── Formatter ─────────────────────────────────────────────────────────────────
FMT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(FMT, datefmt=DATE_FMT)

# ── Root logger ───────────────────────────────────────────────────────────────
logger = logging.getLogger("media_downloader")
logger.setLevel(logging.DEBUG)

# Console handler (INFO+)
_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.INFO)
_console.setFormatter(formatter)
logger.addHandler(_console)

# Full log file (DEBUG+)
_file_all = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_all.setLevel(logging.DEBUG)
_file_all.setFormatter(formatter)
logger.addHandler(_file_all)

# Error-only log file (WARNING+)
_file_err = logging.FileHandler(ERR_FILE, encoding="utf-8")
_file_err.setLevel(logging.WARNING)
_file_err.setFormatter(formatter)
logger.addHandler(_file_err)

# ── Uncaught exception hook ───────────────────────────────────────────────────
def _handle_exception(exc_type, exc_value, exc_tb):
    """Write any unhandled exception to error.log before the app dies."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))

sys.excepthook = _handle_exception

# ── Redirect stdout / stderr ──────────────────────────────────────────────────
class StreamToLogger:
    def __init__(self, logger_obj, log_level):
        self.logger = logger_obj
        self.log_level = log_level
        self.linebuf = ""

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            if line.strip():
                self.logger.log(self.log_level, line.strip())

    def flush(self):
        pass

# Hijack standard prints so yt_shorts_automation logs are captured in app.log
sys.stdout = StreamToLogger(logger, logging.INFO)
sys.stderr = StreamToLogger(logger, logging.ERROR)
