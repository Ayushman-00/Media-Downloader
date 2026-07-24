import shutil
import math
from pathlib import Path

def format_size(bytes_size: int) -> str:
    """Format bytes to a human readable string."""
    if bytes_size == 0 or bytes_size is None:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB")
    i = int(math.floor(math.log(bytes_size, 1024)))
    p = math.pow(1024, i)
    s = round(bytes_size / p, 2)
    return f"{s} {size_name[i]}"

def format_speed(speed: float) -> str:
    """Format speed in bytes/s to a human readable string."""
    if speed is None:
        return "N/A"
    return f"{format_size(speed)}/s"

def format_time(seconds: int) -> str:
    """Format seconds into HH:MM:SS."""
    if seconds is None:
        return "N/A"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def is_ffmpeg_installed() -> bool:
    """Check if FFmpeg is installed and accessible in the system path."""
    return shutil.which("ffmpeg") is not None

def get_default_download_folder() -> str:
    """Get the default downloads folder for the current user."""
    return str(Path.home() / "Downloads")

def validate_url(url: str) -> bool:
    """Basic validation for URL."""
    return url.startswith("http://") or url.startswith("https://")
