"""
Downloader wrapper for the Shorts automation pipeline.
Delegates to the unified core.downloader module.
"""

import os
import sys

# Ensure the project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.downloader import download_for_shorts

def download_via_ytdlp(url: str, output_dir: str, fmt: str = "bestvideo[height<=1080]+bestaudio/best"):
    """Thin wrapper around core.downloader.download_for_shorts"""
    return download_for_shorts(url, output_dir, fmt)

def download_via_exe(url: str, output_dir: str, exe_path: str):
    """
    Deprecated: The standalone exe bridge is no longer needed since the
    domain logic is unified. Falls back to download_via_ytdlp.
    """
    print("[downloader] download_via_exe is deprecated. Using unified core downloader instead.", flush=True)
    return download_for_shorts(url, output_dir)