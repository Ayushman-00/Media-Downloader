"""
Multi-phase highlight engine for yt_shorts_automation.

Phase A: Propose candidates via LLM (chunked for long videos).
Phase B: Refine boundaries (snap to word gaps or segment boundaries).
Phase C: Judge & diversify (LLM structured scoring + heuristic blend).

Phase C uses Opus Clips-style multi-dimensional scoring:
  5 dimensions (hook, flow, engagement, value, trend) each 0-100,
  blended between LLM judge and heuristic sanity-check scores.
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional

from src.utils import load_config
from src.highlight_finder import (
    score_heuristic,
    compute_virality_score,
    blend_scores,
    _get_scoring_config,
    _parse_dimension_scores,
    DEFAULT_WEIGHTS,
)

PROPOSE_PROMPT = """You are an expert short-form video editor. Your task is to find the most viral, engaging moments in the provided transcript and propose them as short-form video clips (YouTube Shorts / TikTok).

Guidelines:
1. Each clip must be self-contained and make complete sense with zero prior context.
2. Boundaries should land on natural sentence or pause boundaries visible in the transcript.
3. The opening line MUST work as a strong, standalone hook to grab attention immediately.
4. Aim for clip durations between 20s and 60s.

For each candidate, also provide a quick self-assessment on these virality dimensions (0-100):
- hook: How attention-grabbing is the opening line?
- flow: Does the clip have a complete narrative arc?
- engagement: Emotional peaks, conflict, humor, surprise?
- value: Actionable tips, insights, quotable lines?
- trend: Topic relevance, shareability, platform fit?

Propose up to {max_candidates} candidates.
Respond ONLY with a JSON array of objects. Example:
[
  {{
    "start": 132.4,
    "end": 178.9,
    "hook_line": "The first sentence of the clip",
    "hook_type": "question|bold_claim|contrarian|story_open|stat",
    "payoff_type": "insight|punchline|reveal|actionable_tip|emotional_beat",
    "rationale": "One sentence explaining why this clip is highly engaging.",
    "self_contained": true,
    "self_scores": {{"hook": 85, "flow": 75, "engagement": 80, "value": 70, "trend": 65}}
  }}
]

Transcript:
{transcript}
"""

JUDGE_PROMPT = """You are an expert viral content analyst. Score each candidate video clip on these 5 virality dimensions (each 0-100).

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


def _parse_candidate_list(raw: str) -> List[Dict]:
    """Parse an LLM response into a list of candidate dicts.
    Uses defensive parsing (strip fences -> json.loads -> regex fallback).
    """
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract the JSON array via regex
        match = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except Exception as e:
                raise ValueError(f"Could not parse candidate list from regex match: {e}")
        else:
            raise ValueError(f"Could not parse candidate list from: {text!r}")

    if not isinstance(parsed, list):
        raise ValueError(f"Expected a list of objects, got: {type(parsed)}")

    # Basic validation
    valid_candidates = []
    for c in parsed:
        if isinstance(c, dict) and "start" in c and "end" in c and "hook_line" in c:
            try:
                c["start"] = float(c["start"])
                c["end"] = float(c["end"])

                # Parse self_scores if present (from updated Phase A prompt)
                if "self_scores" in c and isinstance(c["self_scores"], dict):
                    for dim in DEFAULT_WEIGHTS:
                        try:
                            c["self_scores"][dim] = max(0, min(100, int(c["self_scores"].get(dim, 50))))
                        except (ValueError, TypeError):
                            c["self_scores"][dim] = 50

                valid_candidates.append(c)
            except (ValueError, TypeError):
                continue
    return valid_candidates


def _chunk_transcript(segments: List[Dict], chunk_sec: float = 600, overlap_sec: float = 60) -> List[List[Dict]]:
    """Chunk the transcript into ~10-15 minute overlapping windows."""
    if not segments:
        return []
    
    total_duration = segments[-1]["end"]
    if total_duration <= chunk_sec:
        return [segments]
        
    chunks = []
    pos = 0.0
    while pos < total_duration:
        end = pos + chunk_sec
        chunk_segs = [s for s in segments if s["start"] < end and s["end"] > pos]
        if chunk_segs:
            chunks.append(chunk_segs)
        pos += (chunk_sec - overlap_sec)
        
    return chunks


def _call_groq(prompt: str, model: str, temperature: float = 0.2) -> str:
    """Call Groq chat completions API."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in .env")

    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
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

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]


# --- Phase A: Propose ---
def propose_candidates(segments: List[Dict], cfg: dict) -> List[Dict]:
    """Phase A: Chunk transcript, propose candidates via LLM, dedupe."""
    hcfg = cfg.get("highlight", {})
    max_cands = hcfg.get("max_candidates", 10)
    
    # 10 minute chunks with 1 minute overlap
    chunks = _chunk_transcript(segments, chunk_sec=600, overlap_sec=60)
    
    all_candidates = []
    model = cfg.get("groq", {}).get("llm_model", "llama-3.3-70b-versatile")
    
    for i, chunk in enumerate(chunks):
        # Format transcript for prompt
        transcript_text = ""
        for s in chunk:
            transcript_text += f"[{s['start']:.1f}s - {s['end']:.1f}s] {s['text']}\n"
            
        prompt = PROPOSE_PROMPT.format(max_candidates=max_cands, transcript=transcript_text)
        
        try:
            start_t = time.time()
            raw_response = _call_groq(prompt, model, temperature=0.2)
            latency = time.time() - start_t
            
            cands = _parse_candidate_list(raw_response)
            for c in cands:
                c["_llm_latency"] = latency
            all_candidates.extend(cands)
            print(f"[highlight_engine] Chunk {i+1}/{len(chunks)}: proposed {len(cands)} candidates", flush=True)
        except Exception as e:
            print(f"[highlight_engine] Chunk {i+1} proposal failed: {e}", flush=True)
            
    if not all_candidates:
        raise ValueError("LLM proposed zero valid candidates across all chunks.")
        
    # Dedupe by time-overlap (if overlap > 50% of the shorter clip)
    all_candidates.sort(key=lambda c: c["start"])
    deduped = []
    for c in all_candidates:
        overlap = False
        for d in deduped:
            start_max = max(c["start"], d["start"])
            end_min = min(c["end"], d["end"])
            if start_max < end_min:
                overlap_dur = end_min - start_max
                min_dur = min(c["end"]-c["start"], d["end"]-d["start"])
                if overlap_dur > 0.5 * min_dur:
                    overlap = True
                    break
        if not overlap:
            deduped.append(c)
            
    print(f"[highlight_engine] Phase A complete: {len(deduped)} candidates after deduping.", flush=True)
    return deduped


# --- Phase B: Refine boundaries ---
def refine_boundaries(candidates: List[Dict], segments: List[Dict]) -> List[Dict]:
    """Phase B: Snap proposed start/end to nearest safe boundary (word gap >300ms or segment).
    Cap correction at ±3s.
    """
    # Build a flat list of safe boundary timestamps
    safe_boundaries = []
    
    # Check if we have word-level timestamps
    has_words = any(getattr(s, "words", None) or s.get("words") for s in segments)
    
    if has_words:
        # Collect word gaps > 300ms
        all_words = []
        for s in segments:
            words = s.get("words") or getattr(s, "words", [])
            for w in words:
                all_words.append(w)
                
        if all_words:
            safe_boundaries.append(all_words[0]["start"])
            for i in range(len(all_words)-1):
                gap = all_words[i+1]["start"] - all_words[i]["end"]
                if gap > 0.3:
                    # Gap > 300ms is a safe boundary
                    safe_boundaries.append(all_words[i+1]["start"])
                    safe_boundaries.append(all_words[i]["end"])
            safe_boundaries.append(all_words[-1]["end"])
    
    if not safe_boundaries:
        # Fallback to segment boundaries
        for s in segments:
            safe_boundaries.append(s["start"])
            safe_boundaries.append(s["end"])
            
    safe_boundaries = sorted(list(set(safe_boundaries)))
    
    def snap_time(t: float, max_correction: float = 3.0) -> float:
        if not safe_boundaries:
            return t
        # Find nearest boundary
        nearest = min(safe_boundaries, key=lambda x: abs(x - t))
        if abs(nearest - t) <= max_correction:
            return nearest
        return t

    refined = []
    for c in candidates:
        r = c.copy()
        r["original_start"] = c["start"]
        r["original_end"] = c["end"]
        r["start"] = snap_time(c["start"])
        r["end"] = snap_time(c["end"])
        
        # Ensure it doesn't snap to 0 duration or negative
        if r["end"] <= r["start"]:
            r["start"] = c["start"]
            r["end"] = c["end"]
            
        refined.append(r)
        
    return refined


# --- Phase C: Judge & diversify (Opus Clips-style multi-dimensional scoring) ---
def judge_and_diversify(candidates: List[Dict], video_path: str, cfg: dict) -> List[Dict]:
    """Phase C: Score candidates using LLM structured judge + heuristic blend.

    Scoring pipeline:
    1. Run heuristic scorer on all candidates → per-dimension scores
    2. Call LLM judge for structured per-dimension scoring
    3. Blend LLM + heuristic scores (configurable ratio, default 60/40)
    4. Compute composite virality score
    5. Greedy diversify selection (min time separation)
    """
    hcfg = cfg.get("highlight", {})
    scoring_cfg = _get_scoring_config(cfg)
    weights = scoring_cfg["weights"]
    llm_weight = scoring_cfg["llm_weight"]
    min_separation = hcfg.get("min_candidate_separation_sec", 20)
    top_k = hcfg.get("top_candidates", 5)
    
    # 1. Run heuristic score on all candidates
    windows = []
    for c in candidates:
        windows.append({
            "start": c["start"],
            "end": c["end"],
            "text": c.get("hook_line", "") + " " + c.get("rationale", ""),
            "segments": c.get("segments", []),
        })
        
    scored_heuristics = score_heuristic(video_path, windows, cfg)
    
    # Map heuristic scores by start time
    heuristic_map = {}
    for sh in scored_heuristics:
        heuristic_map[round(sh["start"], 1)] = sh.get("scores", {})

    # 2. Call LLM judge for structured scoring
    llm_dim_scores = {}
    model = cfg.get("groq", {}).get("llm_model", "llama-3.3-70b-versatile")
    
    try:
        # Build candidate descriptions for the judge
        candidates_text = ""
        for i, c in enumerate(candidates):
            hook = c.get("hook_line", "")
            text_preview = c.get("rationale", "")
            candidates_text += (
                f"\n[{i}] {c['start']:.1f}s–{c['end']:.1f}s\n"
                f"  Hook: \"{hook}\"\n"
                f"  Context: {text_preview}\n"
                f"  Hook type: {c.get('hook_type', 'unknown')}\n"
                f"  Payoff: {c.get('payoff_type', 'unknown')}\n"
            )

        judge_prompt = JUDGE_PROMPT.format(candidates=candidates_text)

        start_t = time.time()
        raw_response = _call_groq(judge_prompt, model, temperature=0.0)
        judge_latency = time.time() - start_t

        dim_results = _parse_dimension_scores(raw_response, max_idx=len(candidates) - 1)
        for ds in dim_results:
            idx = ds["index"]
            llm_dim_scores[idx] = {
                dim: ds.get(dim, 50) for dim in DEFAULT_WEIGHTS
            }
            llm_dim_scores[idx]["rationale"] = ds.get("rationale", "")
            llm_dim_scores[idx]["_judge_latency"] = judge_latency

        print(f"[highlight_engine] Phase C: LLM judged {len(dim_results)} candidates in {judge_latency:.1f}s", flush=True)
    except Exception as e:
        print(f"[highlight_engine] Phase C: LLM judge failed ({e}), using heuristic-only scoring", flush=True)
        llm_weight = 0.0  # Fall back to pure heuristic

    # 3. Blend scores and compute composite
    judged = []
    for i, c in enumerate(candidates):
        # Get heuristic scores for this candidate
        h_scores = heuristic_map.get(round(c["start"], 1), {
            "hook": 50, "flow": 50, "engagement": 50, "value": 50, "trend": 50
        })
        
        # Get LLM scores (or fall back to self_scores from Phase A, or defaults)
        if i in llm_dim_scores:
            l_scores = {dim: llm_dim_scores[i].get(dim, 50) for dim in DEFAULT_WEIGHTS}
        elif "self_scores" in c and isinstance(c["self_scores"], dict):
            l_scores = {dim: c["self_scores"].get(dim, 50) for dim in DEFAULT_WEIGHTS}
        else:
            l_scores = {dim: 50 for dim in DEFAULT_WEIGHTS}
        
        # Blend
        virality, blended = blend_scores(h_scores, l_scores, llm_weight, weights)
        
        j = c.copy()
        j["scores"] = blended
        j["heuristic_scores"] = h_scores
        j["llm_scores"] = l_scores
        j["virality_score"] = virality
        j["final_score"] = virality  # backward compat
        j["score"] = virality  # backward compat
        
        # Include LLM rationale if available
        if i in llm_dim_scores:
            j["judge_rationale"] = llm_dim_scores[i].get("rationale", "")
            j["_judge_latency"] = llm_dim_scores[i].get("_judge_latency", 0)
        
        judged.append(j)
        
    # Sort by virality score
    judged.sort(key=lambda x: x["virality_score"], reverse=True)
    
    # 4. Diversify (respect min_candidate_separation_sec)
    selected = []
    for j in judged:
        if len(selected) >= top_k:
            break
            
        too_close = False
        for s in selected:
            # Check distance between centers to see if they are too close
            center_j = (j["start"] + j["end"]) / 2
            center_s = (s["start"] + s["end"]) / 2
            if abs(center_j - center_s) < min_separation:
                too_close = True
                break
                
        if not too_close:
            selected.append(j)

    # Log summary
    for rank, s in enumerate(selected):
        dims = s.get("scores", {})
        print(
            f"[highlight_engine]   #{rank+1}: {s['start']:.1f}s-{s['end']:.1f}s "
            f"VS={s['virality_score']} "
            f"[H:{dims.get('hook',0)} F:{dims.get('flow',0)} "
            f"E:{dims.get('engagement',0)} V:{dims.get('value',0)} T:{dims.get('trend',0)}]",
            flush=True,
        )

    return selected


def run_engine(video_path: str, segments: List[Dict], cfg: dict) -> List[Dict]:
    """Run the full multi-phase highlight engine. 
    Raises Exception on failure so the pipeline can fallback.
    """
    print("[highlight_engine] Starting Phase A (Propose)...", flush=True)
    candidates = propose_candidates(segments, cfg)
    
    print(f"[highlight_engine] Starting Phase B (Refine) on {len(candidates)} candidates...", flush=True)
    refined = refine_boundaries(candidates, segments)
    
    print(f"[highlight_engine] Starting Phase C (Judge & Diversify) on {len(refined)} candidates...", flush=True)
    final_candidates = judge_and_diversify(refined, video_path, cfg)
    
    if not final_candidates:
        raise ValueError("Engine produced zero candidates after filtering.")
        
    print(f"[highlight_engine] Engine complete: selected {len(final_candidates)} diverse candidates.", flush=True)
    return final_candidates
