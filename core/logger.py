
import logging
import sys
from core.paths import user_data_path

LOG_DIR = user_data_path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE  = LOG_DIR / "app.log"
ERR_FILE  = LOG_DIR / "error.log"

FMT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(FMT, datefmt=DATE_FMT)

logger = logging.getLogger("media_downloader")
logger.setLevel(logging.DEBUG)

_console = logging.StreamHandler(sys.stdout)
_console.setLevel(logging.INFO)
_console.setFormatter(formatter)
logger.addHandler(_console)

_file_all = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_all.setLevel(logging.DEBUG)
_file_all.setFormatter(formatter)
logger.addHandler(_file_all)

_file_err = logging.FileHandler(ERR_FILE, encoding="utf-8")
_file_err.setLevel(logging.WARNING)
_file_err.setFormatter(formatter)
logger.addHandler(_file_err)

def _handle_exception(exc_type, exc_value, exc_tb):
    """Write any unhandled exception to error.log before the app dies."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))

sys.excepthook = _handle_exception
