"""
Highlight detection module for yt_shorts_automation.

Provides three detection strategies:
  1. Heuristic — sliding-window scoring based on audio energy + transcript
     density. Pure local, no LLM needed. (custom — no direct repo equivalent)
  2. LLM (Ollama) — sends top heuristic candidates to a local Ollama model
     for re-ranking by virality potential.
  3. Hybrid — heuristic first, then LLM re-rank on the shortlist.

The dashboard calls:
  make_windows(segments, window_sec, step_sec, total_duration) → [windows]
  score_heuristic(video_path, windows) → ranked windows
  score_llm(shortlist, ollama_url, ollama_model) → reordered indices
"""

import json
import re
import subprocess
import struct
import wave
from typing import Dict, List, Optional

from src.utils import load_config


# ---------------------------------------------------------------------------
# Window generation
# ---------------------------------------------------------------------------

def make_windows(
    segments: List[Dict],
    window_sec: float = 45,
    step_sec: float = 5,
    total_duration: float = 0,
) -> List[Dict]:
    """Slide a fixed-size window across the transcript timeline.

    Returns a list of dicts:
      {start, end, segments: [{start, end, text}, ...], text: str}
    """
    if not segments:
        return []

    if total_duration <= 0:
        total_duration = segments[-1]["end"]

    if total_duration <= window_sec:
        # Entire video fits in one window
        text = " ".join(s["text"] for s in segments)
        return [{
            "start": 0,
            "end": total_duration,
            "segments": segments,
            "text": text,
        }]

    windows: List[Dict] = []
    pos = 0.0
    while pos + window_sec <= total_duration + step_sec:
        end = min(pos + window_sec, total_duration)
        win_segs = [
            s for s in segments
            if s["start"] < end and s["end"] > pos
        ]
        text = " ".join(s["text"] for s in win_segs)
        windows.append({
            "start": pos,
            "end": end,
            "segments": win_segs,
            "text": text,
        })
        pos += step_sec
        if end >= total_duration:
            break

    return windows


# ---------------------------------------------------------------------------
# Heuristic scoring  (custom — no repo equivalent)
# ---------------------------------------------------------------------------

def _word_density(window: Dict) -> float:
    """Words per second in the window."""
    duration = window["end"] - window["start"]
    if duration <= 0:
        return 0.0
    word_count = len(window["text"].split())
    return word_count / duration


def _has_question(text: str) -> bool:
    return "?" in text


def _has_hook_words(text: str) -> bool:
    """Check for common viral hook patterns."""
    hooks = [
        "secret", "nobody", "wrong", "actually", "truth",
        "crazy", "insane", "amazing", "shocking", "never",
        "biggest", "worst", "best", "mistake", "hack",
        "discovered", "revealed", "finally", "imagine",
    ]
    lower = text.lower()
    return any(h in lower for h in hooks)


def _audio_energy_score(video_path: str, start: float, end: float) -> float:
    """Extract audio energy for a time range using ffmpeg + raw PCM.

    Returns a normalized RMS energy value (0.0 - 1.0).
    Higher energy ≈ more animated speech / less dead air.
    """
    try:
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-i", video_path,
            "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le",
            "-acodec", "pcm_s16le",
            "pipe:1",
        ]
        result = subprocess.run(
            cmd, capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            return 0.5  # fallback neutral score

        raw = result.stdout
        if len(raw) < 2:
            return 0.0

        # Parse raw 16-bit PCM samples
        n_samples = len(raw) // 2
        samples = struct.unpack(f"<{n_samples}h", raw[:n_samples * 2])

        # RMS energy
        rms = (sum(s * s for s in samples) / n_samples) ** 0.5
        # Normalize to 0-1 (16-bit max is 32767)
        return min(1.0, rms / 32767.0 * 5)  # scale up since speech is usually quiet

    except Exception:
        return 0.5  # neutral on failure


def score_heuristic(
    video_path: str,
    windows: List[Dict],
) -> List[Dict]:
    """Score windows using local heuristics and return sorted (best first).

    Scoring factors:
      - Word density (more words = more engaging content)
      - Questions (engagement hooks)
      - Hook words (viral language patterns)
      - Audio energy (animated speech > silence)
    """
    scored = []
    for w in windows:
        density = _word_density(w)
        question_bonus = 10 if _has_question(w["text"]) else 0
        hook_bonus = 15 if _has_hook_words(w["text"]) else 0
        energy = _audio_energy_score(video_path, w["start"], w["end"])

        # Weighted score (0-100 range roughly)
        score = (
            density * 15        # speech density (0-~4 wps → 0-60)
            + energy * 25       # audio energy (0-1 → 0-25)
            + question_bonus    # +10 for questions
            + hook_bonus        # +15 for hook words
        )

        scored.append({**w, "score": round(score, 2)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# LLM scoring via Ollama
# ---------------------------------------------------------------------------

VIRALITY_PROMPT = """You are an expert short-form video editor. Given these candidate
video segments (each with a start time, end time, and transcript text),
rank them by viral potential for YouTube Shorts / TikTok.

Virality signals to prioritize:
1. HOOK MOMENTS — statements that create immediate curiosity
2. EMOTIONAL PEAKS — surprise, laughter, anger, vulnerability
3. OPINION BOMBS — strong, polarizing or counter-intuitive statements
4. REVELATION MOMENTS — surprising facts or confessions
5. CONFLICT/TENSION — disagreement or a problem confronted head-on
6. QUOTABLE ONE-LINERS — standalone quote-worthy sentences
7. STORY PEAKS — climax or twist of an anecdote
8. PRACTICAL VALUE — a concrete tip or hack

Candidates:
{candidates}

Respond ONLY with a JSON array of the candidate indices (0-based) ranked
from most viral to least viral. Example: [2, 0, 4, 1, 3]
"""


def _parse_index_list(raw: str, max_idx: int) -> List[int]:
    """Parse an LLM response into a list of valid indices."""
    text = raw.strip()
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON array in the text
        match = re.search(r"\[[\d\s,]+\]", text)
        if match:
            parsed = json.loads(match.group())
        else:
            raise ValueError(f"Could not parse index list from: {text!r}")

    if not isinstance(parsed, list):
        raise ValueError(f"Expected a list, got: {type(parsed)}")

    # Filter to valid indices
    return [int(i) for i in parsed if 0 <= int(i) <= max_idx]


def score_llm(
    shortlist: List[Dict],
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3",
) -> List[int]:
    """Send the heuristic shortlist to Ollama for viral re-ranking.

    Returns a list of indices (into shortlist) ordered best-first.
    Falls back to original order on failure.
    """
    import urllib.request
    import urllib.error

    # Build candidate descriptions
    candidates = ""
    for i, w in enumerate(shortlist):
        preview = w.get("text", "")[:300]
        candidates += f"\n[{i}] {w['start']:.1f}s–{w['end']:.1f}s: {preview}\n"

    prompt = VIRALITY_PROMPT.format(candidates=candidates)

    # Call Ollama API
    url = f"{ollama_url.rstrip('/')}/api/generate"
    payload = json.dumps({
        "model": ollama_model,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        raw_text = result.get("response", "")
        indices = _parse_index_list(raw_text, max_idx=len(shortlist) - 1)
        if indices:
            print(f"[highlight] LLM re-ranked: {indices}", flush=True)
            return indices
    except (urllib.error.URLError, json.JSONDecodeError, ValueError) as e:
        print(f"[highlight] Ollama call failed: {e}", flush=True)

    # Fallback: original order
    return list(range(len(shortlist)))


def score_groq(
    shortlist: List[Dict],
    model: str = "llama-3.3-70b-versatile",
) -> List[int]:
    """Send the heuristic shortlist to Groq for viral re-ranking."""
    import os
    import urllib.request
    import urllib.error

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        print("[highlight] GROQ_API_KEY not set in .env", flush=True)
        return list(range(len(shortlist)))

    # Build candidate descriptions
    candidates = ""
    for i, w in enumerate(shortlist):
        preview = w.get("text", "")[:300]
        candidates += f"\n[{i}] {w['start']:.1f}s–{w['end']:.1f}s: {preview}\n"

    prompt = VIRALITY_PROMPT.format(candidates=candidates)
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        
        raw_text = result["choices"][0]["message"]["content"]
        indices = _parse_index_list(raw_text, max_idx=len(shortlist) - 1)
        if indices:
            print(f"[highlight] Groq re-ranked: {indices}", flush=True)
            return indices
    except (urllib.error.URLError, json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"[highlight] Groq call failed: {e}", flush=True)

    # Fallback: original order
    return list(range(len(shortlist)))