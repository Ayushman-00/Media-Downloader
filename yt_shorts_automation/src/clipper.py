"""
Video clipping module for yt_shorts_automation.

Two approaches:
  1. ffmpeg_center_crop_cmd() — builds a pure-ffmpeg command that cuts a time
     range and crops to vertical (9:16) in one pass. Fast, no Python deps
     beyond subprocess. This is what dashboard.py calls directly.

  2. crop_clip_with_face_tracking() — cuts first, then uses OpenCV Haar
     cascade to track the largest face and slide the crop window to follow it.

Both produce a vertical .mp4 ready for music overlay / captioning.
"""

import os
import subprocess
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Pure-ffmpeg center crop  (what dashboard.py calls)
# ---------------------------------------------------------------------------

def ffmpeg_center_crop_cmd(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
    target_width: int = 1080,
    target_height: int = 1920,
    fps: int = 30,
) -> List[str]:
    """Build an ffmpeg command that cuts [start, end] and center-crops to vertical.

    Returns the command as a list (ready for subprocess.run(cmd, check=True)).
    The filter chain:
      1. Scale so the shorter dimension fills the target
      2. Center-crop to exact target_width × target_height
      3. Set output FPS
    """
    # Ensure even dimensions
    tw = target_width - (target_width % 2)
    th = target_height - (target_height % 2)

    # Video filter: scale to fill, then crop center
    vf = (
        f"fps={fps},"
        f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
        f"crop={tw}:{th}"
    )

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]
    return cmd


# ---------------------------------------------------------------------------
# Face-tracking vertical crop
# ---------------------------------------------------------------------------

def _cut_subclip(source_path: str, start: float, end: float, out_path: str) -> str:
    """ffmpeg cut to [start, end] — re-encoded mp4 with audio."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", source_path,
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def _ratio(aspect_ratio: str) -> float:
    """Parse '9:16' → 9/16."""
    try:
        w, h = aspect_ratio.split(":")
        return float(w) / float(h)
    except (ValueError, ZeroDivisionError):
        return 9.0 / 16.0


def smooth_trajectory(raw_centers: List[Optional[Tuple[int, int]]], src_w: int, src_h: int) -> List[Tuple[int, int]]:
    """Fill Nones and apply exponential smoothing with max pan clamping."""
    smoothed_centers = []
    last_valid = (src_w // 2, src_h // 2)
    
    # Fill Nones
    for c in raw_centers:
        if c is not None:
            last_valid = c
        smoothed_centers.append(last_valid)
        
    # Apply exponential smoothing and clamp pan speed
    if smoothed_centers:
        smoothing = 0.15
        max_pan = src_w * 0.05  # max 5% pan per frame
        
        for i in range(1, len(smoothed_centers)):
            lx, ly = smoothed_centers[i-1]
            cx, cy = smoothed_centers[i]
            
            dx = cx - lx
            dy = cy - ly
            
            sx = lx + dx * smoothing
            sy = ly + dy * smoothing
            
            # Clamp speed
            if abs(sx - lx) > max_pan:
                sx = lx + (max_pan if sx > lx else -max_pan)
            if abs(sy - ly) > max_pan:
                sy = ly + (max_pan if sy > ly else -max_pan)
                
            smoothed_centers[i] = (int(sx), int(sy))
            
    return smoothed_centers


def _reframe_vertical(in_path: str, out_path: str, aspect_ratio: str = "9:16") -> str:
    """Crop the clip to target aspect ratio, tracking faces if possible.

    Uses OpenCV Haar cascade to find the largest face per frame and smoothly
    slide the crop window to keep it centered.
    """
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError(
            "opencv-python is required for face-tracking crop. Install with:\n"
            "    pip install opencv-python"
        ) from e

    target_ratio = _ratio(aspect_ratio)
    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {in_path}")

    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    # Compute the largest crop that fits inside the frame at target ratio
    if target_ratio < src_w / src_h:
        crop_h = src_h
        crop_w = int(crop_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = int(crop_w / target_ratio)
    crop_w = max(2, crop_w - (crop_w % 2))
    crop_h = max(2, crop_h - (crop_h % 2))

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    silent_path = out_path + ".silent.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(silent_path, fourcc, fps, (crop_w, crop_h))

    # Pass 1: Collect raw centers
    raw_centers = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
        )

        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            cx = x + w // 2
            cy = y + h // 2
            raw_centers.append((cx, cy))
        else:
            raw_centers.append(None)
            
    # Process trajectory
    smoothed_centers = smooth_trajectory(raw_centers, src_w, src_h)
            
    # Pass 2: Write cropped frames
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        if frame_idx < len(smoothed_centers):
            cx, cy = smoothed_centers[frame_idx]
        else:
            cx, cy = smoothed_centers[-1] if smoothed_centers else (src_w // 2, src_h // 2)

        x0 = max(0, min(src_w - crop_w, int(cx) - crop_w // 2))
        y0 = max(0, min(src_h - crop_h, int(cy) - crop_h // 2))
        cropped = frame[y0:y0 + crop_h, x0:x0 + crop_w]
        writer.write(cropped)
        frame_idx += 1

    cap.release()
    writer.release()

    # Mux audio from the cut clip back onto the silent reframed video
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", silent_path,
        "-i", in_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-map", "0:v:0", "-map", "1:a:0?",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    os.remove(silent_path)
    return out_path


def crop_clip_with_face_tracking(
    source_path: str,
    start: float,
    end: float,
    output_path: str,
    aspect_ratio: str = "9:16",
) -> str:
    """Cut + face-tracking reframe in two stages. Returns the output path.

    This is the higher-quality alternative to ffmpeg_center_crop_cmd —
    it follows faces instead of blindly center-cropping.
    Requires: opencv-python
    """
    cut_path = output_path + ".cut.mp4"
    try:
        _cut_subclip(source_path, start, end, cut_path)
        _reframe_vertical(cut_path, output_path, aspect_ratio)
    finally:
        if os.path.exists(cut_path):
            os.remove(cut_path)
    return output_path