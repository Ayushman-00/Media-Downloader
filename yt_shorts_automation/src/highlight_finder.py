"""
Highlight detection module for yt_shorts_automation.

Provides three detection strategies:
  1. Heuristic — multi-dimensional scoring across 5 virality dimensions
     (hook, flow, engagement, value, trend). Pure local, no LLM needed.
  2. LLM (Ollama/Groq) — structured multi-dimensional re-ranking via LLM.
  3. Hybrid — heuristic first, then LLM structured judge on the shortlist.

Scoring mirrors Opus Clips' virality scoring system:
  - Each dimension scored 0-100
  - Weighted composite → "Virality Score" (0-100)
  - Configurable weights via config.yaml

The dashboard calls:
  make_windows(segments, window_sec, step_sec, total_duration) → [windows]
  score_heuristic(video_path, windows, cfg) → ranked windows with per-dimension scores
  score_llm(shortlist, ollama_url, ollama_model) → reordered indices
"""

import json
import math
import re
import subprocess
import struct
from typing import Dict, List, Optional, Tuple

from src.utils import load_config


# ---------------------------------------------------------------------------
# Default scoring weights (Opus Clips-inspired)
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "hook": 0.30,
    "flow": 0.20,
    "engagement": 0.20,
    "value": 0.15,
    "trend": 0.15,
}


def _get_scoring_config(cfg: Optional[dict] = None) -> dict:
    """Extract scoring config with defaults."""
    if cfg is None:
        return {"weights": DEFAULT_WEIGHTS.copy(), "llm_weight": 0.60}
    scoring = cfg.get("highlight", {}).get("scoring", {})
    weights = scoring.get("weights", DEFAULT_WEIGHTS.copy())
    # Ensure all keys exist
    for k, v in DEFAULT_WEIGHTS.items():
        weights.setdefault(k, v)
    return {
        "weights": weights,
        "llm_weight": scoring.get("llm_weight", 0.60),
    }


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
# Audio energy extraction (shared utility)
# ---------------------------------------------------------------------------

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


def _audio_energy_dynamic_range(video_path: str, start: float, end: float) -> float:
    """Measure audio dynamic range (peaks vs valleys) for engagement scoring.

    Returns 0.0 (flat/monotone) to 1.0 (highly dynamic).
    """
    try:
        duration = end - start
        if duration <= 0:
            return 0.5

        # Sample 4 sub-windows and compare their energies
        chunk = duration / 4.0
        energies = []
        for i in range(4):
            e = _audio_energy_score(video_path, start + i * chunk, start + (i + 1) * chunk)
            energies.append(e)

        if not energies or max(energies) == 0:
            return 0.0

        # Dynamic range = (max - min) / max
        return min(1.0, (max(energies) - min(energies)) / max(max(energies), 0.01))

    except Exception:
        return 0.5


# ---------------------------------------------------------------------------
# Dimension 1: HOOK SCORE (0-100)
# "How strong is the first 1-3 seconds as a standalone attention-grabber?"
# ---------------------------------------------------------------------------

_HOOK_WORDS = [
    "secret", "nobody", "wrong", "actually", "truth",
    "crazy", "insane", "amazing", "shocking", "never",
    "biggest", "worst", "best", "mistake", "hack",
    "discovered", "revealed", "finally", "imagine",
    "unbelievable", "mindblowing", "controversial", "banned",
    "hidden", "exposed", "warning", "urgent", "breaking",
    "impossible", "legendary", "genius", "terrible", "ruined",
]

_HOOK_OPENERS = [
    "here's why", "here's what", "here's how", "the reason",
    "what if", "did you know", "let me tell you", "stop doing",
    "you need to", "this is why", "i can't believe",
    "nobody talks about", "the truth is", "fun fact",
    "unpopular opinion", "hot take", "plot twist",
]


def _score_hook(window: Dict, video_path: Optional[str] = None) -> int:
    """Score the hook quality of a window (0-100).

    Signals:
    - First sentence is short and punchy (< 15 words)
    - Starts with a question
    - Contains hook words / opener patterns
    - First-segment audio energy (if video_path provided)
    """
    text = window.get("text", "")
    segments = window.get("segments", [])
    if not text:
        return 0

    score = 0.0

    # --- First sentence analysis ---
    # Extract the first sentence (up to first period, question mark, or exclamation)
    first_sentence_match = re.match(r"^(.*?[.?!])", text)
    first_sentence = first_sentence_match.group(1) if first_sentence_match else text[:100]
    first_words = first_sentence.split()

    # Short, punchy opening (< 15 words = strong, < 8 = very strong)
    if len(first_words) <= 8:
        score += 30
    elif len(first_words) <= 15:
        score += 20
    elif len(first_words) <= 25:
        score += 10

    # Starts with a question
    if "?" in first_sentence:
        score += 20

    # Hook words in first sentence
    lower_first = first_sentence.lower()
    hook_hits = sum(1 for h in _HOOK_WORDS if h in lower_first)
    score += min(25, hook_hits * 10)

    # Hook opener patterns
    opener_hits = sum(1 for o in _HOOK_OPENERS if o in lower_first)
    score += min(20, opener_hits * 15)

    # Audio energy in first 3 seconds (animated opening)
    if video_path and segments:
        first_end = min(window["start"] + 3.0, window["end"])
        energy = _audio_energy_score(video_path, window["start"], first_end)
        score += energy * 15  # 0-15 points

    return min(100, max(0, int(score)))


# ---------------------------------------------------------------------------
# Dimension 2: FLOW SCORE (0-100)
# "Does the clip have a clear beginning, middle, end? No mid-sentence cuts?"
# ---------------------------------------------------------------------------

def _score_flow(window: Dict) -> int:
    """Score narrative flow / completeness (0-100).

    Signals:
    - Starts near a segment boundary (not mid-sentence)
    - Ends near a segment boundary
    - Consistent word density (steady pacing, no dead air)
    - Has enough text content (not mostly silence)
    """
    segments = window.get("segments", [])
    text = window.get("text", "")
    w_start = window["start"]
    w_end = window["end"]
    duration = w_end - w_start

    if duration <= 0 or not segments:
        return 0

    score = 0.0

    # --- Boundary alignment ---
    # Does the window start near a segment boundary?
    if segments:
        first_seg_start = segments[0]["start"]
        start_offset = abs(w_start - first_seg_start)
        if start_offset < 0.5:
            score += 20  # clean start
        elif start_offset < 2.0:
            score += 10
        # else: starts mid-sentence, no bonus

        # Does the window end near a segment boundary?
        last_seg_end = segments[-1]["end"]
        end_offset = abs(w_end - last_seg_end)
        if end_offset < 0.5:
            score += 20  # clean end
        elif end_offset < 2.0:
            score += 10

    # --- Pacing consistency ---
    # Measure word density across 3 sub-sections (start/middle/end)
    if len(segments) >= 3:
        third = duration / 3.0
        densities = []
        for i in range(3):
            sec_start = w_start + i * third
            sec_end = sec_start + third
            sec_segs = [s for s in segments if s["start"] < sec_end and s["end"] > sec_start]
            sec_words = sum(len(s["text"].split()) for s in sec_segs)
            densities.append(sec_words / third if third > 0 else 0)

        if densities and max(densities) > 0:
            # Low variance = consistent pacing
            mean_d = sum(densities) / len(densities)
            variance = sum((d - mean_d) ** 2 for d in densities) / len(densities)
            std_dev = variance ** 0.5
            # Coefficient of variation (lower = more consistent)
            cv = std_dev / mean_d if mean_d > 0 else 1.0
            if cv < 0.3:
                score += 25  # very consistent
            elif cv < 0.6:
                score += 15
            elif cv < 1.0:
                score += 5
            # high cv = dead-air sections, penalty (no bonus)

    # --- Content density ---
    # Has enough speech content (not mostly silence)
    words = len(text.split())
    wps = words / duration if duration > 0 else 0
    if wps >= 2.5:
        score += 20  # good speech density
    elif wps >= 1.5:
        score += 12
    elif wps >= 0.8:
        score += 5
    # Below 0.8 wps = too much silence

    # --- Text completeness ---
    # Penalize if text starts with lowercase (mid-sentence cut)
    stripped = text.strip()
    if stripped and stripped[0].isupper():
        score += 10
    # Penalize if text doesn't end with sentence-ending punctuation
    if stripped and stripped[-1] in ".!?\"'":
        score += 5

    return min(100, max(0, int(score)))


# ---------------------------------------------------------------------------
# Dimension 3: ENGAGEMENT SCORE (0-100)
# "Emotional peaks, conflict, humor, surprise, strong opinions?"
# ---------------------------------------------------------------------------

_EMOTION_WORDS = [
    "love", "hate", "angry", "furious", "hilarious", "funny",
    "terrified", "scared", "excited", "thrilled", "devastated",
    "heartbroken", "disgusted", "outraged", "ecstatic", "miserable",
    "obsessed", "passionate", "frustrated", "overwhelmed",
    "speechless", "stunned", "blown away", "can't believe",
]

_CONFLICT_WORDS = [
    "disagree", "wrong", "fight", "argue", "debate", "conflict",
    "controversial", "problem", "issue", "crisis", "failure",
    "disaster", "confronted", "challenged", "attacked", "defended",
    "versus", "vs", "but", "however", "despite", "although",
]

_SURPRISE_WORDS = [
    "surprising", "unexpected", "shocked", "twist", "plot twist",
    "turns out", "actually", "wait", "hold on", "what",
    "oh my", "no way", "are you serious", "really",
    "didn't expect", "never thought", "who knew",
]


def _score_engagement(
    window: Dict,
    video_path: Optional[str] = None,
) -> int:
    """Score emotional engagement potential (0-100).

    Signals:
    - Emotion/conflict/surprise word density
    - Question density (drives comments)
    - Exclamation marks (emphasis)
    - Audio dynamic range (peaks = animated, interesting)
    """
    text = window.get("text", "")
    if not text:
        return 0

    lower = text.lower()
    word_count = len(text.split())
    score = 0.0

    # --- Emotional language ---
    emotion_hits = sum(1 for w in _EMOTION_WORDS if w in lower)
    score += min(25, emotion_hits * 8)

    # --- Conflict / tension ---
    conflict_hits = sum(1 for w in _CONFLICT_WORDS if w in lower)
    score += min(20, conflict_hits * 7)

    # --- Surprise / revelation ---
    surprise_hits = sum(1 for w in _SURPRISE_WORDS if w in lower)
    score += min(20, surprise_hits * 8)

    # --- Question density (drives comments) ---
    question_count = text.count("?")
    if question_count >= 3:
        score += 15
    elif question_count >= 1:
        score += 10

    # --- Exclamation emphasis ---
    exclamation_count = text.count("!")
    if exclamation_count >= 2:
        score += 10
    elif exclamation_count >= 1:
        score += 5

    # --- Audio dynamic range (animated peaks vs valleys) ---
    if video_path:
        dyn_range = _audio_energy_dynamic_range(
            video_path, window["start"], window["end"]
        )
        score += dyn_range * 15  # 0-15 points

    return min(100, max(0, int(score)))


# ---------------------------------------------------------------------------
# Dimension 4: VALUE SCORE (0-100)
# "Actionable tips, insights, quotable lines, educational substance?"
# ---------------------------------------------------------------------------

_LIST_PATTERNS = [
    r"\b\d+\s+(?:things?|ways?|tips?|steps?|reasons?|mistakes?|rules?|hacks?|secrets?|facts?)\b",
    r"\b(?:first|second|third|step\s*\d|number\s*\d|#\d)\b",
    r"\b(?:firstly|secondly|thirdly|lastly|finally|next|then)\b",
]

_INSTRUCTIONAL_PHRASES = [
    "how to", "here's how", "here's why", "the key is",
    "the trick is", "pro tip", "quick tip", "important",
    "you should", "you need to", "make sure", "don't forget",
    "the secret", "the answer", "the solution", "in other words",
    "for example", "specifically", "the reason", "because",
    "lesson learned", "takeaway", "bottom line", "key point",
]


def _score_value(window: Dict) -> int:
    """Score practical/educational value (0-100).

    Signals:
    - List/number patterns ("3 things", "step 1")
    - Instructional phrases ("how to", "here's why")
    - Quote-worthy sentence structure (short, punchy declarations)
    - Information density (unique words / total words)
    """
    text = window.get("text", "")
    if not text:
        return 0

    lower = text.lower()
    words = text.split()
    word_count = len(words)
    score = 0.0

    # --- List / number patterns ---
    list_hits = sum(
        1 for pattern in _LIST_PATTERNS
        if re.search(pattern, lower)
    )
    score += min(25, list_hits * 12)

    # --- Instructional phrases ---
    instruction_hits = sum(1 for p in _INSTRUCTIONAL_PHRASES if p in lower)
    score += min(30, instruction_hits * 8)

    # --- Quote-worthy sentences ---
    # Short, declarative sentences (< 12 words, ends with period) = quotable
    sentences = re.split(r"[.!?]+", text)
    quotable_count = sum(
        1 for s in sentences
        if 3 <= len(s.split()) <= 12 and s.strip()
    )
    score += min(20, quotable_count * 5)

    # --- Information density ---
    # Unique words ratio (higher = more information, lower = repetitive)
    if word_count > 0:
        unique_ratio = len(set(w.lower() for w in words)) / word_count
        if unique_ratio > 0.7:
            score += 15
        elif unique_ratio > 0.5:
            score += 10
        elif unique_ratio > 0.35:
            score += 5

    # --- Numbers / data (concrete facts) ---
    number_count = len(re.findall(r"\b\d+(?:\.\d+)?%?\b", text))
    score += min(10, number_count * 3)

    return min(100, max(0, int(score)))


# ---------------------------------------------------------------------------
# Dimension 5: TREND SCORE (0-100)
# "Topic relevance, shareability, platform fit for Shorts/TikTok?"
# ---------------------------------------------------------------------------

_SHAREABILITY_PATTERNS = [
    "tag someone", "share this", "send this to",
    "you won't believe", "save this", "bookmark",
    "everyone needs to", "spread the word",
]

_TRENDING_TOPICS = [
    "ai", "artificial intelligence", "chatgpt", "gpt",
    "crypto", "bitcoin", "investing", "money",
    "productivity", "mindset", "motivation", "success",
    "health", "fitness", "mental health", "anxiety",
    "relationship", "dating", "social media", "algorithm",
    "side hustle", "passive income", "entrepreneur",
    "psychology", "brain", "science", "technology",
    "lifestyle", "minimalism", "stoicism",
]


def _score_trend(window: Dict) -> int:
    """Score trend alignment and shareability (0-100).

    Signals:
    - Hook word density (expanded viral vocabulary)
    - Topic match against trending/evergreen categories
    - Shareability language patterns
    - Unique noun density (topic richness)
    """
    text = window.get("text", "")
    if not text:
        return 0

    lower = text.lower()
    words = text.split()
    word_count = len(words)
    score = 0.0

    # --- Viral vocabulary (hook words from expanded list) ---
    hook_hits = sum(1 for h in _HOOK_WORDS if h in lower)
    score += min(25, hook_hits * 6)

    # --- Trending topic match ---
    topic_hits = sum(1 for t in _TRENDING_TOPICS if t in lower)
    score += min(30, topic_hits * 8)

    # --- Shareability language ---
    share_hits = sum(1 for p in _SHAREABILITY_PATTERNS if p in lower)
    score += min(20, share_hits * 10)

    # --- Topic density (unique nouns → content richness) ---
    # Simple proxy: ratio of capitalized words (likely proper nouns/topics)
    if word_count > 5:
        # Exclude first word of sentences
        mid_words = words[1:]
        cap_words = sum(1 for w in mid_words if w and w[0].isupper())
        cap_ratio = cap_words / len(mid_words) if mid_words else 0
        score += min(15, int(cap_ratio * 60))

    # --- Conciseness for platform fit ---
    # Shorts/TikTok favors dense, fast content
    duration = window["end"] - window["start"]
    if duration > 0:
        wps = word_count / duration
        if 2.5 <= wps <= 4.0:
            score += 15  # ideal pacing for short-form
        elif 2.0 <= wps <= 4.5:
            score += 8

    return min(100, max(0, int(score)))


# ---------------------------------------------------------------------------
# Composite Virality Score
# ---------------------------------------------------------------------------

def compute_virality_score(
    dimension_scores: Dict[str, int],
    weights: Optional[Dict[str, float]] = None,
) -> int:
    """Compute weighted composite virality score (0-100) from dimension scores.

    Args:
        dimension_scores: dict with keys hook/flow/engagement/value/trend, each 0-100
        weights: optional custom weights (must sum to ~1.0)

    Returns:
        Composite score 0-100
    """
    w = weights or DEFAULT_WEIGHTS
    composite = sum(
        dimension_scores.get(dim, 0) * w.get(dim, 0)
        for dim in DEFAULT_WEIGHTS
    )
    return min(100, max(0, int(round(composite))))


def blend_scores(
    heuristic_scores: Dict[str, int],
    llm_scores: Dict[str, int],
    llm_weight: float = 0.60,
    weights: Optional[Dict[str, float]] = None,
) -> Tuple[int, Dict[str, int]]:
    """Blend heuristic and LLM dimension scores into a final virality score.

    Args:
        heuristic_scores: per-dimension scores from heuristic scorer
        llm_scores: per-dimension scores from LLM judge
        llm_weight: weight for LLM scores (0.0 = pure heuristic, 1.0 = pure LLM)
        weights: dimension weights for composite

    Returns:
        (composite_score, blended_dimension_scores)
    """
    h_weight = 1.0 - llm_weight
    blended = {}
    for dim in DEFAULT_WEIGHTS:
        h = heuristic_scores.get(dim, 0)
        l = llm_scores.get(dim, 0)
        blended[dim] = int(round(h * h_weight + l * llm_weight))

    composite = compute_virality_score(blended, weights)
    return composite, blended


# ---------------------------------------------------------------------------
# Heuristic scoring (multi-dimensional, Opus Clips-style)
# ---------------------------------------------------------------------------

def score_heuristic(
    video_path: str,
    windows: List[Dict],
    cfg: Optional[dict] = None,
) -> List[Dict]:
    """Score windows using multi-dimensional heuristics and return sorted (best first).

    Each window gets per-dimension scores (0-100) and a weighted composite
    "virality_score" (0-100), mimicking Opus Clips' ranking system.

    Scoring dimensions:
      - hook: First-impression strength (opening line punch, hook words)
      - flow: Narrative completeness (clean boundaries, consistent pacing)
      - engagement: Emotional peaks (conflict, surprise, dynamic audio)
      - value: Practical substance (tips, lists, quotable lines)
      - trend: Platform fit (viral vocab, trending topics, shareability)
    """
    scoring_cfg = _get_scoring_config(cfg)
    weights = scoring_cfg["weights"]

    scored = []
    for w in windows:
        # Score each dimension
        hook = _score_hook(w, video_path)
        flow = _score_flow(w)
        engagement = _score_engagement(w, video_path)
        value = _score_value(w)
        trend = _score_trend(w)

        dimensions = {
            "hook": hook,
            "flow": flow,
            "engagement": engagement,
            "value": value,
            "trend": trend,
        }

        virality = compute_virality_score(dimensions, weights)

        scored.append({
            **w,
            "virality_score": virality,
            "scores": dimensions,
            "score": virality,  # backward compat
        })

    scored.sort(key=lambda x: x["virality_score"], reverse=True)
    return scored


# ---------------------------------------------------------------------------
# LLM structured scoring prompt
# ---------------------------------------------------------------------------

VIRALITY_PROMPT = """You are an expert short-form video editor and viral content analyst.
Score each candidate video segment on these 5 virality dimensions (each 0-100):

**Scoring Rubric:**
- **hook** (0-100): How strong is the opening line as a standalone attention-grabber?
  90-100: Irresistible curiosity gap or bold statement that demands attention
  70-89: Strong opener that creates clear interest
  50-69: Decent opener but not immediately compelling
  0-49: Weak or generic opening

- **flow** (0-100): Does the clip have a clear beginning, middle, and end?
  90-100: Perfect narrative arc, completely self-contained
  70-89: Good structure, minor rough edges
  50-69: Somewhat complete but feels cut short or starts abruptly
  0-49: Feels like a random excerpt, no clear arc

- **engagement** (0-100): Emotional peaks, conflict, humor, surprise, strong opinions?
  90-100: Multiple strong emotional moments, highly compelling
  70-89: Clear emotional content that drives reaction
  50-69: Some interesting moments but mostly flat
  0-49: Monotone, no emotional peaks

- **value** (0-100): Actionable tips, insights, quotable lines, educational substance?
  90-100: Highly actionable, memorable takeaway
  70-89: Solid insight or useful information
  50-69: Some value but not particularly memorable
  0-49: No clear takeaway

- **trend** (0-100): Topic relevance, shareability, platform fit for YouTube Shorts / TikTok?
  90-100: Highly shareable, perfect for short-form, trending topic
  70-89: Good platform fit, likely to get engagement
  50-69: Adequate for short-form but not exceptional
  0-49: Poor fit for short-form or niche/dated topic

Candidates:
{candidates}

Respond ONLY with a JSON array of objects, one per candidate:
[{{"index": 0, "hook": 85, "flow": 72, "engagement": 80, "value": 65, "trend": 70, "rationale": "Strong opening question creates curiosity gap..."}}]
"""


def _parse_dimension_scores(raw: str, max_idx: int) -> List[Dict]:
    """Parse an LLM response into a list of per-candidate dimension scores.

    Expected format: [{"index": 0, "hook": 85, "flow": 72, ...}, ...]
    Falls back to index-list parsing for backward compat.
    """
    text = raw.strip()
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON array of objects in the text
        match = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                pass

        if parsed is None:
            # Last resort: try old-style index list [2, 0, 4, 1, 3]
            match = re.search(r"\[[\d\s,]+\]", text)
            if match:
                try:
                    indices = json.loads(match.group())
                    return _indices_to_dimension_scores(indices, max_idx)
                except (json.JSONDecodeError, TypeError):
                    pass
            raise ValueError(f"Could not parse dimension scores from: {text!r}")

    if not isinstance(parsed, list):
        raise ValueError(f"Expected a list, got: {type(parsed)}")

    # Check if this is a plain index list (e.g. [2, 0, 1]) rather than dicts
    if parsed and isinstance(parsed[0], (int, float)):
        return _indices_to_dimension_scores(parsed, max_idx)

    # Validate and normalize structured dimension scores
    dimensions = ["hook", "flow", "engagement", "value", "trend"]
    valid = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if idx is None:
            continue
        try:
            idx = int(idx)
        except (ValueError, TypeError):
            continue
        if not (0 <= idx <= max_idx):
            continue

        scores = {"index": idx}
        for dim in dimensions:
            try:
                scores[dim] = max(0, min(100, int(item.get(dim, 50))))
            except (ValueError, TypeError):
                scores[dim] = 50
        scores["rationale"] = item.get("rationale", "")
        valid.append(scores)

    return valid


def _indices_to_dimension_scores(indices: list, max_idx: int) -> List[Dict]:
    """Convert a plain index ranking list to dimension score dicts.

    Earlier-ranked indices get higher scores (descending from 90).
    """
    result = []
    for rank, idx in enumerate(indices):
        try:
            idx = int(idx)
        except (ValueError, TypeError):
            continue
        if 0 <= idx <= max_idx:
            fake_score = max(10, 90 - rank * 10)
            result.append({
                "index": idx,
                "hook": fake_score,
                "flow": fake_score,
                "engagement": fake_score,
                "value": fake_score,
                "trend": fake_score,
                "rationale": f"Ranked #{rank + 1} by LLM",
            })
    return result


def _parse_index_list(raw: str, max_idx: int) -> List[int]:
    """Parse an LLM response into a list of valid indices.
    
    Kept for backward compatibility with code that calls this directly.
    """
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


# ---------------------------------------------------------------------------
# LLM scoring via Ollama
# ---------------------------------------------------------------------------

def score_llm(
    shortlist: List[Dict],
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3",
) -> List[int]:
    """Send the heuristic shortlist to Ollama for structured viral re-ranking.

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

        # Try structured dimension parsing first
        dim_scores = _parse_dimension_scores(raw_text, max_idx=len(shortlist) - 1)
        if dim_scores:
            # Enrich shortlist items with LLM scores
            for ds in dim_scores:
                idx = ds["index"]
                if 0 <= idx < len(shortlist):
                    shortlist[idx]["llm_scores"] = {
                        k: ds[k] for k in DEFAULT_WEIGHTS
                    }
                    shortlist[idx]["llm_rationale"] = ds.get("rationale", "")

            # Sort by composite LLM score
            scored_indices = []
            for ds in dim_scores:
                composite = compute_virality_score(
                    {k: ds[k] for k in DEFAULT_WEIGHTS}
                )
                scored_indices.append((ds["index"], composite))
            scored_indices.sort(key=lambda x: x[1], reverse=True)
            indices = [si[0] for si in scored_indices]
            print(f"[highlight] LLM re-ranked (structured): {indices}", flush=True)
            return indices

        # Fallback to simple index parsing
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
    """Send the heuristic shortlist to Groq for structured viral re-ranking."""
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

        # Try structured dimension parsing first
        dim_scores = _parse_dimension_scores(raw_text, max_idx=len(shortlist) - 1)
        if dim_scores:
            # Enrich shortlist items with LLM scores
            for ds in dim_scores:
                idx = ds["index"]
                if 0 <= idx < len(shortlist):
                    shortlist[idx]["llm_scores"] = {
                        k: ds[k] for k in DEFAULT_WEIGHTS
                    }
                    shortlist[idx]["llm_rationale"] = ds.get("rationale", "")

            # Sort by composite LLM score
            scored_indices = []
            for ds in dim_scores:
                composite = compute_virality_score(
                    {k: ds[k] for k in DEFAULT_WEIGHTS}
                )
                scored_indices.append((ds["index"], composite))
            scored_indices.sort(key=lambda x: x[1], reverse=True)
            indices = [si[0] for si in scored_indices]
            print(f"[highlight] Groq re-ranked (structured): {indices}", flush=True)
            return indices

        # Fallback to simple index parsing
        indices = _parse_index_list(raw_text, max_idx=len(shortlist) - 1)
        if indices:
            print(f"[highlight] Groq re-ranked: {indices}", flush=True)
            return indices
    except (urllib.error.URLError, json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"[highlight] Groq call failed: {e}", flush=True)

    # Fallback: original order
    return list(range(len(shortlist)))