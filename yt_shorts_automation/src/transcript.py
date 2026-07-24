"""
Transcription module for yt_shorts_automation.


"""

import glob
import os
import re
import urllib.request
import urllib.error
import json
from pathlib import Path
from typing import Dict, List, Optional

from src.utils import load_config

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

_cfg_cache: Optional[dict] = None


def _cfg() -> dict:
    """Lazy-load config.yaml once."""
    global _cfg_cache
    if _cfg_cache is None:
        _cfg_cache = load_config()
    return _cfg_cache


def _output_dir() -> str:
    return _cfg()["paths"].get("clips", "output/clips")


def _whisper_model() -> str:
    return _cfg().get("transcript", {}).get("whisper_model", "base")


def _whisper_device() -> str:
    return _cfg().get("transcript", {}).get("whisper_device", "auto")


def _vad_enabled() -> bool:
    return _cfg().get("transcript", {}).get("vad_filter", False)


def _vad_parameters() -> dict:
    return _cfg().get("transcript", {}).get("vad_parameters", {
        "threshold": 0.5,
        "min_speech_duration_ms": 250,
        "max_speech_duration_s": float("inf"),
        "min_silence_duration_ms": 2000,
        "speech_pad_ms": 400,
    })


# ---------------------------------------------------------------------------
# Existing-caption discovery  (custom — no repo equivalent)
# ---------------------------------------------------------------------------

def find_existing_captions(video_path: str) -> Optional[str]:
    """Check if yt-dlp already downloaded a .vtt or .srt alongside the video.

    Returns the path to the first caption file found, or None.
    yt-dlp typically saves captions as  <video_stem>.<lang>.vtt  or  .srt.
    """
    stem = os.path.splitext(video_path)[0]
    directory = os.path.dirname(video_path)
    base = os.path.basename(stem)

    # Patterns yt-dlp uses:  name.en.vtt, name.en.srt, name.vtt, name.srt
    for ext in ("vtt", "srt"):
        # With language code
        matches = glob.glob(os.path.join(directory, f"{base}.*.{ext}"))
        if matches:
            return matches[0]
        # Without language code
        plain = os.path.join(directory, f"{base}.{ext}")
        if os.path.isfile(plain):
            return plain

    return None


def fetch_youtube_captions(video_url: str) -> Optional[List[Dict]]:
    """Fetch captions directly from YouTube using youtube-transcript-api.
    Fast and free, requires no API key.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("[transcript] youtube-transcript-api not installed", flush=True)
        return None

    # Extract video ID
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", video_url)
    if not match:
        print(f"[transcript] Could not extract video ID from {video_url}", flush=True)
        return None
    video_id = match.group(1)

    try:
        print(f"[transcript] fetching captions via API for {video_id}...", flush=True)
        # Try both the new API (v1.x) and the old API
        api_instance = YouTubeTranscriptApi()
        if hasattr(api_instance, "fetch"):
            transcript_obj = api_instance.fetch(video_id)
            items = getattr(transcript_obj, 'snippets', transcript_obj)
        else:
            items = YouTubeTranscriptApi.get_transcript(video_id)
            
        segments = []
        for item in items:
            start = getattr(item, 'start', item.get("start") if isinstance(item, dict) else 0)
            duration = getattr(item, 'duration', item.get("duration") if isinstance(item, dict) else 0)
            text = getattr(item, 'text', item.get("text") if isinstance(item, dict) else "")
            
            segments.append({
                "start": start,
                "end": start + duration,
                "text": text
            })
        print(f"[transcript] successfully fetched {len(segments)} segments via API", flush=True)
        return segments
    except Exception as e:
        print(f"[transcript] API fetch failed: {e}", flush=True)
        return None



# ---------------------------------------------------------------------------
# VTT parsing
# ---------------------------------------------------------------------------

def parse_vtt(vtt_path: str) -> List[Dict]:
    """Parse a WebVTT file into a list of {start, end, text} dicts.

    WebVTT timestamps look like:  00:00:01.230 --> 00:00:04.560
    """
    content = Path(vtt_path).read_text(encoding="utf-8-sig").strip()
    segments: List[Dict] = []

    # Split on blank lines
    blocks = re.split(r"\n\s*\n", content)
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        # Find the line with the --> arrow
        arrow_idx = None
        for i, line in enumerate(lines):
            if "-->" in line:
                arrow_idx = i
                break
        if arrow_idx is None:
            continue

        # Parse timestamps
        ts_line = lines[arrow_idx]
        # Remove position/alignment metadata after timestamps
        ts_parts = ts_line.split("-->")
        if len(ts_parts) != 2:
            continue

        start_str = ts_parts[0].strip().split()[0] if ts_parts[0].strip() else ""
        end_str = ts_parts[1].strip().split()[0] if ts_parts[1].strip() else ""

        try:
            start = _parse_vtt_timestamp(start_str)
            end = _parse_vtt_timestamp(end_str)
        except ValueError:
            continue

        # Text is everything after the timestamp line
        text = " ".join(lines[arrow_idx + 1:]).strip()
        # Strip VTT styling tags like <c>, </c>, <b>, etc.
        text = re.sub(r"<[^>]+>", "", text).strip()

        if text:
            segments.append({"start": start, "end": end, "text": text})

    return segments


def _parse_vtt_timestamp(value: str) -> float:
    """Parse  HH:MM:SS.mmm  or  MM:SS.mmm  into seconds."""
    # HH:MM:SS.mmm
    match = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{3})", value)
    if match:
        h, m, s, ms = map(int, match.groups())
        return h * 3600 + m * 60 + s + ms / 1000.0

    # MM:SS.mmm  (some VTTs omit hours)
    match = re.fullmatch(r"(\d{1,2}):(\d{2})[.,](\d{3})", value)
    if match:
        m, s, ms = map(int, match.groups())
        return m * 60 + s + ms / 1000.0

    raise ValueError(f"Invalid VTT timestamp: {value!r}")


# ---------------------------------------------------------------------------
# SRT helpers
# ---------------------------------------------------------------------------

def _format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _parse_srt_timestamp(value: str) -> float:
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", value.strip())
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value!r}")
    hours, minutes, seconds, millis = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + (millis / 1000.0)


# ---------------------------------------------------------------------------
# SRT cache
# ---------------------------------------------------------------------------

def _transcript_cache_path(media_path: str) -> Path:
    """Return the .srt cache path for a media file."""
    cache_dir = Path(_output_dir())
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / (Path(media_path).stem + ".srt")


def _write_srt_cache(media_path: str, transcript: Dict) -> Path:
    cache_path = _transcript_cache_path(media_path)
    lines = []
    for idx, segment in enumerate(transcript.get("segments", []), start=1):
        start = _format_srt_timestamp(float(segment["start"]))
        end = _format_srt_timestamp(float(segment["end"]))
        text = str(segment.get("text", "")).strip().replace("\r", "").replace("\n", " ")
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")

    cache_path.write_text("\n".join(lines), encoding="utf-8")
    return cache_path


def _load_srt_cache(cache_path: Path) -> Dict:
    content = cache_path.read_text(encoding="utf-8-sig").strip()
    if not content:
        return {"duration": 0.0, "segments": []}

    segments = []
    for block in re.split(r"\n\s*\n", content):
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        # Skip the numeric index line
        if "-->" not in lines[0] and len(lines) > 1 and "-->" in lines[1]:
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[0].split("-->", 1)]
        text = "\n".join(lines[1:]).strip()
        segments.append({
            "start": _parse_srt_timestamp(start_raw),
            "end": _parse_srt_timestamp(end_raw),
            "text": text,
        })

    duration = segments[-1]["end"] if segments else 0.0
    return {"duration": duration, "segments": segments}


# ---------------------------------------------------------------------------
# Device detection
# ---------------------------------------------------------------------------

def _resolve_device() -> str:
    """Auto-detect CUDA availability, fall back to CPU."""
    device = _whisper_device()
    if device != "auto":
        return device
    try:
        import torch
        if torch.cuda.is_available():
            # Verify CUDA actually works (catches missing cuBLAS/cuDNN)
            torch.zeros(1, device="cuda")
            return "cuda"
    except (ImportError, OSError, RuntimeError):
        pass
    return "cpu"


# ---------------------------------------------------------------------------
# Groq Whisper API (custom — cloud fallback)
# ---------------------------------------------------------------------------

def transcribe_with_groq(media_path: str, language: Optional[str] = None) -> Optional[List[Dict]]:
    """Transcribe using Groq's fast cloud Whisper endpoint."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        print("[transcript] GROQ_API_KEY not set in .env", flush=True)
        return None

    model = _cfg().get("groq", {}).get("whisper_model", "whisper-large-v3-turbo")
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    
    import subprocess
    audio_path = os.path.splitext(media_path)[0] + "_temp_audio.mp3"
    
    try:
        # Extract audio using FFmpeg to avoid 25MB limit and format rejection
        print(f"[transcript] extracting audio for Groq API...", flush=True)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", media_path, "-vn", "-acodec", "libmp3lame", "-q:a", "5", audio_path],
                check=True,
                capture_output=True
            )
        except Exception as e:
            print(f"[transcript] Audio extraction failed: {e}", flush=True)
            return None

        # We must use multipart/form-data for the file upload
        import io
        import mimetypes
        import uuid
        
        boundary = uuid.uuid4().hex
        
        def form_field(name, value):
            return f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode('utf-8')
        
        filename = os.path.basename(audio_path)
        mime_type = 'audio/mpeg'
        
        with open(audio_path, "rb") as f:
            file_data = f.read()
            
        file_header = f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {mime_type}\r\n\r\n".encode('utf-8')
        
        body = bytearray()
        body.extend(form_field("model", model))
        body.extend(form_field("response_format", "verbose_json"))
        if language:
            body.extend(form_field("language", language))
        body.extend(file_header)
        body.extend(file_data)
        body.extend(f"\r\n--{boundary}--\r\n".encode('utf-8'))
        
        req = urllib.request.Request(
            url,
            data=bytes(body),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            },
            method="POST"
        )
        
        print(f"[transcript] transcribing with Groq ({model})...", flush=True)
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            
            segments = []
            for item in result.get("segments", []):
                segments.append({
                    "start": item["start"],
                    "end": item["end"],
                    "text": item["text"].strip()
                })
            print(f"[transcript] Groq success: {len(segments)} segments", flush=True)
            return segments
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode('utf-8', errors='ignore')
        except Exception:
            err_body = ""
        print(f"[transcript] Groq transcription failed ({e.code} {e.reason}): {err_body}", flush=True)
        return None
    except Exception as e:
        print(f"[transcript] Groq transcription failed: {e}", flush=True)
        return None
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


# ---------------------------------------------------------------------------
# Main transcription
# ---------------------------------------------------------------------------

def transcribe_with_whisper(
    media_path: str,
    model_name: Optional[str] = None,
    language: Optional[str] = None,
) -> List[Dict]:
    """Run faster-whisper on a local file, with SRT caching.

    Returns a list of {start, end, text} segment dicts (the format
    dashboard.py and highlight_finder.py expect).
    """
    if model_name is None:
        model_name = _whisper_model()

    # --- Check cache ---
    cache_path = _transcript_cache_path(media_path)
    if cache_path.exists():
        source_mtime = os.path.getmtime(media_path)
        cache_mtime = cache_path.stat().st_mtime
        if cache_mtime >= source_mtime:
            print(f"[transcript] reusing cached transcript: {cache_path}", flush=True)
            cached = _load_srt_cache(cache_path)
            if cached["segments"] and cached["duration"] > 0.0:
                print(
                    f"[transcript] {len(cached['segments'])} cached segments, "
                    f"{cached['duration']:.0f}s of audio",
                    flush=True,
                )
                return cached["segments"]
            else:
                print(f"[transcript] cache empty/invalid, re-transcribing", flush=True)
                cache_path.unlink(missing_ok=True)

    # --- Load faster-whisper ---
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper is required for transcription. Install with:\n"
            "    pip install faster-whisper"
        ) from e

    device = _resolve_device()
    compute_type = "float16" if device == "cuda" else "int8"
    print(f"[transcript] faster-whisper model={model_name} device={device}", flush=True)

    model = WhisperModel(model_name, device=device, compute_type=compute_type)

    transcribe_kwargs = {
        "audio": media_path,
        "language": language,
        "beam_size": 5,
        "condition_on_previous_text": False,
    }

    if _vad_enabled():
        transcribe_kwargs["vad_filter"] = True
        transcribe_kwargs["vad_parameters"] = _vad_parameters()
    else:
        transcribe_kwargs["vad_filter"] = False

    segments_iter, info = model.transcribe(**transcribe_kwargs)

    segments = []
    for s in segments_iter:
        segments.append({
            "start": float(s.start),
            "end": float(s.end),
            "text": (s.text or "").strip(),
        })

    duration = float(getattr(info, "duration", 0.0)) or (
        segments[-1]["end"] if segments else 0.0
    )
    print(f"[transcript] {len(segments)} segments, {duration:.0f}s of audio", flush=True)

    # --- Write cache ---
    transcript = {"duration": duration, "segments": segments}
    written = _write_srt_cache(media_path, transcript)
    print(f"[transcript] wrote cache: {written}", flush=True)

    return segments