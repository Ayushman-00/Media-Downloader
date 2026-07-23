"""
Music selection and mixing module for yt_shorts_automation.

Custom — no open-source repo equivalent found. Most repos either:
  - Skip background music entirely
  - Use paid APIs (Epidemic Sound, etc.)

This module provides:
  list_available_tracks(music_dir) — scan a local folder for audio files
  mix_music(clip, track, out, volume, duck) — overlay music via ffmpeg

All processing is done through ffmpeg (no Python audio libraries required
for the mixing itself). The user drops .mp3/.wav/.ogg files into the
/music folder and picks one from the dashboard.
"""

import os
import subprocess
from typing import List


# Supported audio extensions for music tracks
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}


def list_available_tracks(music_dir: str) -> List[str]:
    """Scan music_dir for audio files and return their filenames (sorted).

    Returns an empty list if the directory doesn't exist or has no audio files.
    """
    if not os.path.isdir(music_dir):
        return []

    tracks = [
        f for f in os.listdir(music_dir)
        if os.path.isfile(os.path.join(music_dir, f))
        and os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS
    ]
    tracks.sort()
    return tracks


def get_duration(file_path: str) -> float:
    """Get the duration of an audio/video file in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError):
        return 0.0


def mix_music(
    clip_path: str,
    track_path: str,
    output_path: str,
    volume: float = 0.15,
    duck_original: bool = True,
) -> str:
    """Overlay a music track onto a video clip using ffmpeg.

    Args:
        clip_path: Path to the video clip (with original audio).
        track_path: Path to the music file (.mp3/.wav etc).
        output_path: Where to write the mixed result.
        volume: Music volume relative to original (0.0 - 1.0).
        duck_original: If True, slightly lower original audio when music plays.

    The music track is:
      - Trimmed to match the clip duration (if longer)
      - Faded out over the last 2 seconds
      - Mixed at the specified volume level
    """
    clip_duration = get_duration(clip_path)
    if clip_duration <= 0:
        # Can't determine duration — just copy the clip
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", clip_path,
             "-c", "copy", output_path],
            check=True,
        )
        return output_path

    # Fade-out duration for music (last 2 seconds, or less if clip is very short)
    fade_dur = min(2.0, clip_duration * 0.1)
    fade_start = max(0, clip_duration - fade_dur)

    # Build the audio filter graph:
    #   [1:a] = music track: trim to clip length, apply volume, fade out
    #   [0:a] = original audio: optionally duck (lower volume slightly)
    #   amix both together
    original_vol = 0.85 if duck_original else 1.0

    filter_complex = (
        f"[1:a]atrim=0:{clip_duration:.3f},asetpts=PTS-STARTPTS,"
        f"volume={volume:.3f},"
        f"afade=t=out:st={fade_start:.3f}:d={fade_dur:.3f}[music];"
        f"[0:a]volume={original_vol:.3f}[orig];"
        f"[orig][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", clip_path,
        "-i", track_path,
        "-filter_complex", filter_complex,
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    subprocess.run(cmd, check=True)
    return output_path