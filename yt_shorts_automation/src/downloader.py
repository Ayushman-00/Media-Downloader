"""
Downloads a YouTube video using yt-dlp or an external Media Downloader .exe.

Two public functions (called by dashboard.py and pipeline.py):
  download_via_ytdlp(url, output_dir, fmt)       → (video_path, info_dict)
  download_via_exe(url, output_dir, exe_path)     → (video_path, info_dict)

Includes custom external-exe bridge for the parent Media Downloader suite.
"""

import glob
import json
import os
import re
import subprocess
from typing import Dict, Optional, Tuple

from src.utils import load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_downloaded_video(output_dir: str, title_hint: str = "") -> Optional[str]:
    """Return the most recently modified video file in output_dir."""
    exts = ("*.mp4", "*.mkv", "*.webm", "*.mov")
    candidates = []
    for ext in exts:
        candidates.extend(glob.glob(os.path.join(output_dir, ext)))
    if not candidates:
        return None
    # Sort by modification time, newest first
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


def _sanitize_filename(name: str) -> str:
    """Remove characters that are unsafe in filenames."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip(". ")
    return name[:200] if name else "video"


# ---------------------------------------------------------------------------
# yt-dlp native download
# ---------------------------------------------------------------------------

def download_via_ytdlp(
    url: str,
    output_dir: str,
    fmt: str = "bestvideo[height<=1080]+bestaudio/best",
) -> Tuple[str, Dict]:
    """Download a video via yt-dlp and return (video_path, info_dict).

    Uses yt-dlp as a Python library (yt_dlp) if installed, otherwise falls
    back to shelling out to the yt-dlp CLI binary.
    """
    os.makedirs(output_dir, exist_ok=True)

    # --- Try the Python library first ---
    try:
        import yt_dlp

        outtmpl = os.path.join(output_dir, "%(title).200s [%(id)s].%(ext)s")
        ydl_opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "writesubtitles": True,
            "subtitleslangs": ["en", "en-orig"],
            "writeinfojson": True,
            "quiet": False,
            "no_warnings": False,
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
            ],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # yt_dlp fills 'requested_downloads' with actual output paths
            downloads = info.get("requested_downloads", [])
            if downloads:
                video_path = downloads[0]["filepath"]
            else:
                video_path = ydl.prepare_filename(info)
                # After merge the extension may have changed
                if not os.path.exists(video_path):
                    base = os.path.splitext(video_path)[0]
                    video_path = base + ".mp4"

        slim_info = {
            "id": info.get("id", ""),
            "title": info.get("title", ""),
            "duration": info.get("duration", 0),
            "uploader": info.get("uploader", ""),
            "webpage_url": info.get("webpage_url", url),
        }
        print(f"[downloader] saved: {video_path}", flush=True)
        return video_path, slim_info

    except ImportError:
        print("[downloader] yt_dlp library not found, falling back to CLI", flush=True)

    # --- CLI fallback ---
    outtmpl = os.path.join(output_dir, "%(title).200s [%(id)s].%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", fmt,
        "-o", outtmpl,
        "--merge-output-format", "mp4",
        "--write-sub", "--sub-langs", "en,en-orig",
        "--write-info-json",
        url,
    ]
    print(f"[downloader] running: {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)

    video_path = _find_downloaded_video(output_dir)
    if not video_path:
        raise FileNotFoundError(f"No video file found in {output_dir} after download")

    # Try to load the info json
    info_json_path = os.path.splitext(video_path)[0] + ".info.json"
    info = {}
    if os.path.exists(info_json_path):
        with open(info_json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        info = {
            "id": raw.get("id", ""),
            "title": raw.get("title", ""),
            "duration": raw.get("duration", 0),
            "uploader": raw.get("uploader", ""),
            "webpage_url": raw.get("webpage_url", url),
        }

    print(f"[downloader] saved: {video_path}", flush=True)
    return video_path, info


# ---------------------------------------------------------------------------
# External Media Downloader .exe bridge
# ---------------------------------------------------------------------------

def download_via_exe(
    url: str,
    output_dir: str,
    exe_path: str,
) -> Tuple[str, Dict]:
    """Download using the parent Media Downloader executable.

    The Media Downloader .exe accepts:
        MediaDownloader.exe --url <url> --output <dir> [--format mp4]
    It writes the file into output_dir and prints the filename to stdout.
    """
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.isfile(exe_path):
        raise FileNotFoundError(
            f"External exe not found at {exe_path}. "
            "Set downloader.use_external_exe to false or fix the path in config.yaml"
        )

    cmd = [exe_path, "--url", url, "--output", output_dir, "--format", "mp4"]
    print(f"[downloader] running external exe: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    # Try to find the downloaded file
    video_path = _find_downloaded_video(output_dir)
    if not video_path:
        # Check stdout for a filename hint
        stdout_lines = result.stdout.strip().split("\n")
        for line in reversed(stdout_lines):
            candidate = os.path.join(output_dir, line.strip())
            if os.path.isfile(candidate):
                video_path = candidate
                break

    if not video_path:
        raise FileNotFoundError(
            f"No video file found in {output_dir} after external exe download"
        )

    info = {"title": os.path.splitext(os.path.basename(video_path))[0], "webpage_url": url}
    print(f"[downloader] saved: {video_path}", flush=True)
    return video_path, info