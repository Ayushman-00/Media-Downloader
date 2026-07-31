"""
Multi-phase highlight engine for yt_shorts_automation.

Phase A: Propose candidates via LLM (chunked for long videos).
Phase B: Refine boundaries (snap to word gaps or segment boundaries).
Phase C: Judge & diversify (score using LLM signal + heuristic sanity check).
"""

import json
import os
import re
import urllib.request
import urllib.error
from typing import Dict, List, Optional

from src.utils import load_config
from src.highlight_finder import score_heuristic

PROPOSE_PROMPT = """You are an expert short-form video editor. Your task is to find the most viral, engaging moments in the provided transcript and propose them as short-form video clips (YouTube Shorts / TikTok).

Guidelines:
1. Each clip must be self-contained and make complete sense with zero prior context.
2. Boundaries should land on natural sentence or pause boundaries visible in the transcript.
3. The opening line MUST work as a strong, standalone hook to grab attention immediately.
4. Aim for clip durations between 20s and 60s.

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
    "self_contained": true
  }}
]

Transcript:
{transcript}
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
    import time
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


# --- Phase C: Judge & diversify ---
def judge_and_diversify(candidates: List[Dict], video_path: str, cfg: dict) -> List[Dict]:
    """Phase C: Score candidates using heuristic + LLM signal, and select top-K."""
    hcfg = cfg.get("highlight", {})
    min_separation = hcfg.get("min_candidate_separation_sec", 20)
    top_k = hcfg.get("top_candidates", 5)
    
    # 1. Run heuristic score as a sanity check
    # Convert candidates to 'windows' format for heuristic function
    windows = []
    for c in candidates:
        windows.append({
            "start": c["start"],
            "end": c["end"],
            "text": c.get("hook_line", "") # Only needed for hook/question bonus
        })
        
    scored_heuristics = score_heuristic(video_path, windows)
    
    # 2. Combine scores
    judged = []
    for i, c in enumerate(candidates):
        # Find its heuristic score
        h_score = 0.0
        for sh in scored_heuristics:
            if abs(sh["start"] - c["start"]) < 0.1:
                h_score = sh["score"]
                break
                
        # LLM signal is inherent since the LLM proposed it.
        # We could prompt the LLM again to judge, but for determinism (temp=0) 
        # and efficiency, we will blend the heuristic score with its order of proposal.
        # The earlier it was proposed (or the better its hook_type), the higher its intrinsic LLM score.
        
        # Simple blend: heuristic score + bonus for being self_contained + bonus for hook type
        llm_bonus = 0
        if c.get("self_contained"):
            llm_bonus += 10
        if c.get("hook_type") in ["question", "bold_claim", "contrarian", "story_open"]:
            llm_bonus += 15
            
        final_score = h_score + llm_bonus
        
        j = c.copy()
        j["heuristic_score"] = h_score
        j["llm_bonus"] = llm_bonus
        j["final_score"] = final_score
        judged.append(j)
        
    # Sort by final score
    judged.sort(key=lambda x: x["final_score"], reverse=True)
    
    # 3. Diversify (respect min_candidate_separation_sec)
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
            
    return selected


def run_engine(video_path: str, segments: List[Dict], cfg: dict) -> List[Dict]:
    """Run the full multi-phase highlight engine. 
    Raises Exception on failure so the pipeline can fallback.
    """
    print("[highlight_engine] Starting Phase A (Propose)...", flush=True)
    candidates = propose_candidates(segments, cfg)
    
    print(f"[highlight_engine] Starting Phase B (Refine) on {len(candidates)} candidates...", flush=True)
    refined = refine_boundaries(candidates, segments)
    
    print(f"[highlight_engine] Starting Phase C (Judge) on {len(refined)} candidates...", flush=True)
    final_candidates = judge_and_diversify(refined, video_path, cfg)
    
    if not final_candidates:
        raise ValueError("Engine produced zero candidates after filtering.")
        
    print(f"[highlight_engine] Engine complete: selected {len(final_candidates)} diverse candidates.", flush=True)
    return final_candidates
