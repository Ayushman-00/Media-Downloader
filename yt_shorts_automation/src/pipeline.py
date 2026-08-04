"""
Orchestrates the entire 7-stage pipeline from URL → YouTube upload.

Called by main.py (CLI) and can also be imported for programmatic use.

Stages:
  1. download   → src/downloader.py
  2. transcript → src/transcript.py
  3. highlight  → src/highlight_finder.py
  4. clip       → src/clipper.py
  5. music      → src/music_selector.py
  6. caption    → src/captioner.py
  7. upload     → src/uploader.py

Each stage checks the job log to see if it already completed (idempotent).
"""

import os
import subprocess
from typing import Dict, List, Optional

from src.utils import load_config, load_job, mark_stage, get_stage_output, read_log, write_log
from src import downloader, transcript, highlight_finder, clipper, music_selector, captioner
from src.uploaders import get_uploader


# ---------------------------------------------------------------------------
# Individual stage runners
# ---------------------------------------------------------------------------

def stage_download(job: dict, cfg: dict, job_path: str) -> str:
    """Stage 1: Download the source video."""
    existing = get_stage_output(job_path, cfg, "download")
    if existing and os.path.isfile(existing):
        print(f"[pipeline] download already done: {existing}", flush=True)
        return existing

    if "source" in job and os.path.isfile(job["source"]):
        print(f"[pipeline] using local source: {job['source']}", flush=True)
        mark_stage(job_path, cfg, "download", job["source"])
        return job["source"]

    url = job.get("url")
    if not url:
        raise ValueError("Job must contain 'url' or a valid local 'source' file")
    dcfg = cfg["downloader"]

    if dcfg.get("use_external_exe"):
        video_path, info = downloader.download_via_exe(
            url, cfg["paths"]["downloads"], dcfg["external_exe_path"]
        )
    else:
        video_path, info = downloader.download_via_ytdlp(
            url, cfg["paths"]["downloads"], dcfg["format"]
        )

    mark_stage(job_path, cfg, "download", video_path, extra={"info": info})
    return video_path


def stage_transcript(job: dict, cfg: dict, job_path: str, video_path: str) -> List[Dict]:
    """Stage 2: Get transcript segments."""
    existing = get_stage_output(job_path, cfg, "transcript")
    if existing and os.path.isfile(existing):
        import json
        with open(existing, "r", encoding="utf-8") as f:
            segments = json.load(f)
        print(f"[pipeline] transcript already done: {len(segments)} segments", flush=True)
        return segments

    tcfg = cfg["transcript"]
    url = job.get("url", "")
    segments = None

    # Waterfall: youtube-transcript-api → local VTT → Groq Whisper → local Whisper
    method = None
    if tcfg.get("use_youtube_transcript_api") and url:
        segments = transcript.fetch_youtube_captions(url)
        if segments:
            method = "youtube_api"

    if not segments and tcfg.get("prefer_youtube_captions"):
        vtt = transcript.find_existing_captions(video_path)
        if vtt:
            segments = transcript.parse_vtt(vtt)
            if segments:
                method = "local_vtt"

    if not segments and tcfg.get("groq_whisper_fallback"):
        segments = transcript.transcribe_with_groq(video_path)
        if segments:
            method = "groq_whisper"

    if not segments and tcfg.get("whisper_fallback"):
        segments = transcript.transcribe_with_whisper(video_path, tcfg.get("whisper_model", "base"))
        if segments:
            method = "local_whisper"

    if not segments:
        segments = []
        method = "none"

    log = read_log(job_path, cfg)
    if "decisions" not in log:
        log["decisions"] = {}
    log["decisions"]["transcript"] = {"method": method}
    write_log(job_path, cfg, log)

    # Save to disk for idempotency
    import json
    seg_path = os.path.join(cfg["paths"]["clips"], os.path.splitext(os.path.basename(video_path))[0] + "_segments.json")
    with open(seg_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, indent=2)
    mark_stage(job_path, cfg, "transcript", seg_path, extra={"count": len(segments)})
    return segments


def stage_highlight(
    job: dict, cfg: dict, job_path: str, video_path: str, segments: List[Dict]
) -> Dict:
    """Stage 3: Find the best highlight window."""
    existing = get_stage_output(job_path, cfg, "highlight")
    if existing:
        log = read_log(job_path, cfg)
        hl = log["stages"].get("highlight", {})
        if "start" in hl and "end" in hl:
            print(f"[pipeline] highlight already done: {hl['start']:.1f}s-{hl['end']:.1f}s", flush=True)
            return {"start": hl["start"], "end": hl["end"]}
        elif existing == "pending_review":
            print(f"[pipeline] highlight pending review", flush=True)
            return None

    hcfg = cfg["highlight"]

    # Allow job-level overrides
    if "clip_start" in job and "clip_end" in job:
        best = {"start": job["clip_start"], "end": job["clip_end"], "reason": "job override"}
        mark_stage(job_path, cfg, "highlight", "manual", extra=best)
        return best

    if not segments:
        duration = job.get("duration", 45)
        best = {"start": 0, "end": min(45, duration), "reason": "no transcript"}
        mark_stage(job_path, cfg, "highlight", "fallback", extra=best)
        return best

    total_duration = segments[-1]["end"]
    
    log = read_log(job_path, cfg)
    if "decisions" not in log:
        log["decisions"] = {}

    engine = hcfg.get("engine", "heuristic_only")
    best = None
    all_candidates_for_log = []
    
    if engine == "propose_refine_judge":
        cached = log.get("decisions", {}).get("highlight", {})
        if cached.get("method") == "propose_refine_judge" and cached.get("candidates"):
            print("[pipeline] Using cached LLM propose_refine_judge candidates", flush=True)
            candidates = cached["candidates"]
            best = candidates[0]
            best["reason"] = "propose_refine_judge"
        else:
            try:
                from src import highlight_engine
                candidates = highlight_engine.run_engine(video_path, segments, cfg)
                best = candidates[0]
                
                # Log all candidates with their per-dimension scores
                all_candidates_for_log = [
                    {
                        "start": c["start"],
                        "end": c["end"],
                        "virality_score": c.get("virality_score", 0),
                        "scores": c.get("scores", {}),
                        "heuristic_scores": c.get("heuristic_scores", {}),
                        "llm_scores": c.get("llm_scores", {}),
                        "hook_line": c.get("hook_line", ""),
                        "hook_type": c.get("hook_type", ""),
                        "judge_rationale": c.get("judge_rationale", ""),
                    }
                    for c in candidates
                ]
                
                log["decisions"]["highlight"] = {
                    "method": "propose_refine_judge",
                    "candidates": all_candidates_for_log,
                }
                write_log(job_path, cfg, log)
                best["reason"] = "propose_refine_judge"
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[pipeline] propose_refine_judge failed: {e}. Falling back...", flush=True)
            log["decisions"]["highlight"] = {
                "method": "fallback_after_failure",
                "error": str(e)
            }
            write_log(job_path, cfg, log)

    if best is None:
        windows = highlight_finder.make_windows(
            segments, hcfg["window_sec"], hcfg["step_sec"], total_duration
        )

        if not windows:
            best = {"start": 0, "end": min(45, total_duration), "reason": "single window"}
            mark_stage(job_path, cfg, "highlight", "fallback", extra=best)
            return best

        ranked = highlight_finder.score_heuristic(video_path, windows, cfg)
        best = {**ranked[0], "reason": "heuristic"}

        # Log top candidates with per-dimension scores
        all_candidates_for_log = [
            {
                "start": r["start"],
                "end": r["end"],
                "virality_score": r.get("virality_score", r.get("score", 0)),
                "scores": r.get("scores", {}),
            }
            for r in ranked[:hcfg.get("top_candidates", 5)]
        ]

        # Cloud LLM re-ranking
        if hcfg.get("use_groq") and hcfg["method"] in ("groq", "hybrid"):
            try:
                shortlist = ranked[: hcfg["top_candidates"]]
                gcfg = cfg.get("groq", {})
                order = highlight_finder.score_groq(shortlist, gcfg.get("llm_model", "llama-3.3-70b-versatile"))
                best = {**shortlist[order[0]], "reason": "groq_llm"}
            except Exception as e:
                print(f"[pipeline] Groq scoring failed, using heuristic: {e}", flush=True)
        elif hcfg.get("use_ollama") and hcfg["method"] in ("ollama", "hybrid"):
            try:
                shortlist = ranked[: hcfg["top_candidates"]]
                order = highlight_finder.score_llm(shortlist, hcfg["ollama_url"], hcfg["ollama_model"])
                best = {**shortlist[order[0]], "reason": "ollama_llm"}
            except Exception as e:
                print(f"[pipeline] Ollama scoring failed, using heuristic: {e}", flush=True)
                
        if "highlight" not in log["decisions"] or log["decisions"]["highlight"].get("method") == "fallback_after_failure":
            log["decisions"]["highlight"] = {
                "method": best.get("reason", "heuristic"),
                "candidates": all_candidates_for_log,
            }
            write_log(job_path, cfg, log)

    if cfg.get("review", {}).get("enabled", False):
        log = read_log(job_path, cfg)
        # If it hasn't been approved yet (i.e. start and end are not in stages["highlight"])
        # We write output="pending_review" and stop here.
        mark_stage(job_path, cfg, "highlight", "pending_review")
        return None

    clean_best = {
        "start": best["start"],
        "end": best["end"],
        "reason": best.get("reason", "heuristic"),
    }
    if "hook_line" in best:
        clean_best["hook_line"] = best["hook_line"]
    if "virality_score" in best:
        clean_best["virality_score"] = best["virality_score"]
    if "scores" in best:
        clean_best["scores"] = best["scores"]
        
    mark_stage(job_path, cfg, "highlight", "scored", extra=clean_best)
    return best


def stage_clip(job: dict, cfg: dict, job_path: str, video_path: str, highlight: Dict) -> str:
    """Stage 4: Cut and crop the clip to 9:16."""
    existing = get_stage_output(job_path, cfg, "clip")
    if existing and os.path.isfile(existing):
        print(f"[pipeline] clip already done: {existing}", flush=True)
        return existing

    vcfg = cfg["video"]
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    clip_out = os.path.join(cfg["paths"]["clips"], f"{base_name}_clip.mp4")

    cmd = clipper.ffmpeg_center_crop_cmd(
        video_path, clip_out,
        highlight["start"], highlight["end"],
        vcfg["target_width"], vcfg["target_height"], vcfg["fps"],
    )
    print(f"[pipeline] clipping {highlight['start']:.1f}s-{highlight['end']:.1f}s...", flush=True)
    subprocess.run(cmd, check=True)

    mark_stage(job_path, cfg, "clip", clip_out)
    return clip_out


def stage_music(job: dict, cfg: dict, job_path: str, clip_path: str) -> dict:
    """Stage 5: Select background music (no encoding)."""
    existing = get_stage_output(job_path, cfg, "music")
    log = read_log(job_path, cfg)
    existing_extra = log.get("stages", {}).get("music", {}).get("extra", {})
    if existing and existing_extra.get("track_path"):
        print(f"[pipeline] music already selected: {existing_extra['track_path']}", flush=True)
        return existing_extra

    mcfg = cfg["music"]
    music_dir = cfg["paths"]["music"]
    
    volume = job.get("music_volume", mcfg["default_volume"])
    track_path = ""

    # Job can specify a track, otherwise pick the first available
    track_name = job.get("music_track", "")
    if track_name:
        track_path = os.path.join(music_dir, track_name)
    else:
        tracks = music_selector.list_available_tracks(music_dir)
        if not tracks:
            print("[pipeline] no music tracks available, skipping music", flush=True)
            mark_stage(job_path, cfg, "music", "skipped")
            return {"track_path": None, "volume": 0}
        track_path = os.path.join(music_dir, tracks[0])
        print(f"[pipeline] auto-selected track: {tracks[0]}", flush=True)

    music_meta = {"track_path": track_path, "volume": volume, "duck_original": mcfg.get("duck_original", True)}
    mark_stage(job_path, cfg, "music", "selected", extra=music_meta)
    return music_meta


def stage_caption(
    job: dict, cfg: dict, job_path: str, clip_path: str, music_meta: dict,
    segments: List[Dict], highlight: Dict,
) -> str:
    """Stage 6: Final consolidated pass (burn captions + mix music)."""
    existing = get_stage_output(job_path, cfg, "caption")
    if existing and os.path.isfile(existing):
        print(f"[pipeline] caption already done: {existing}", flush=True)
        return existing

    ccfg = cfg["captions"]
    final_out = os.path.join(
        cfg["paths"]["final"],
        os.path.basename(os.path.splitext(clip_path)[0]) + "_final.mp4",
    )

    # Check for custom caption text from the Script tab / job override
    log = read_log(job_path, cfg)
    hl_entry = log.get("stages", {}).get("highlight", {})
    custom_caption_text = hl_entry.get("custom_caption_text", "")

    if not ccfg.get("enabled", True):
        ass_path = None
    elif custom_caption_text:
        # Custom text — route through static fallback (no word-level data)
        ass_path = os.path.splitext(clip_path)[0] + ".ass"
        hook_line = highlight.get("hook_line", "")
        custom_segments = [{"start": highlight["start"], "end": highlight["end"], "text": custom_caption_text}]
        static_ccfg = {**ccfg, "style": "static"}
        captioner.build_ass(
            custom_segments,
            highlight["start"], highlight["end"],
            ass_path, static_ccfg,
            hook_line=hook_line
        )
    else:
        # Build .ass file from transcript segments
        ass_path = os.path.splitext(clip_path)[0] + ".ass"
        hook_line = highlight.get("hook_line", "")
        captioner.build_ass(
            segments,
            highlight["start"], highlight["end"],
            ass_path, ccfg,
            hook_line=hook_line
        )

    print("[pipeline] running consolidated ffmpeg pass (music + captions)...", flush=True)
    
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", clip_path]
    track_path = music_meta.get("track_path")
    
    if track_path and os.path.isfile(track_path):
        cmd.extend(["-i", track_path])
        volume = music_meta.get("volume", 0.3)
        filter_complex = f"[0:a]volume={volume}[a0]; [1:a]volume={volume}[a1]; [a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]"
        cmd.extend(["-filter_complex", filter_complex, "-map", "0:v", "-map", "[a]", "-c:a", "aac"])
    else:
        cmd.extend(["-c:a", "copy"])
        
    if ass_path:
        ass_for_filter = ass_path.replace("\\", "/").replace(":", "\\:")
        cmd.extend(["-vf", f"subtitles='{ass_for_filter}'", "-c:v", "libx264"])
    else:
        cmd.extend(["-c:v", "copy"])
        
    cmd.append(final_out)
    
    subprocess.run(cmd, check=True)

    mark_stage(job_path, cfg, "caption", final_out)
    return final_out


def stage_upload(job: dict, cfg: dict, job_path: str, final_path: str) -> Dict:
    """Stage 7: Upload to YouTube."""
    existing = get_stage_output(job_path, cfg, "upload")
    if existing:
        print(f"[pipeline] upload already done: {existing}", flush=True)
        return {"id": existing}

    uploader = get_uploader(cfg)
    response = uploader.upload(final_path, job)

    video_id = response.get("id", "unknown")
    mark_stage(job_path, cfg, "upload", video_id, extra={"url": f"https://youtube.com/watch?v={video_id}"})
    return response


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(job_path: str, only_stage: Optional[str] = None):
    """Run the full pipeline (or a single stage) for a job JSON file.

    Args:
        job_path: path to the job JSON file
        only_stage: if set, only run this specific stage
                    (download|transcript|highlight|clip|music|caption|upload)
    """
    job = load_job(job_path)
    preset = job.get("preset")
    cfg = load_config(preset=preset)

    print(f"[pipeline] starting job: {job_path}", flush=True)
    print(f"[pipeline] url: {job.get('url', 'N/A')}", flush=True)

    stages = ["download", "transcript", "highlight", "clip", "music", "caption", "upload"]

    if only_stage and only_stage not in stages:
        raise ValueError(f"Unknown stage '{only_stage}'. Valid: {stages}")

    # --- Download ---
    if only_stage in (None, "download"):
        video_path = stage_download(job, cfg, job_path)
    else:
        video_path = get_stage_output(job_path, cfg, "download")
        if not video_path:
            raise RuntimeError("Download stage has not been run yet")
    if only_stage == "download":
        return

    # --- Transcript ---
    if only_stage in (None, "transcript"):
        segments = stage_transcript(job, cfg, job_path, video_path)
    else:
        seg_output = get_stage_output(job_path, cfg, "transcript")
        if seg_output and os.path.isfile(seg_output):
            import json
            with open(seg_output, "r", encoding="utf-8") as f:
                segments = json.load(f)
        else:
            segments = []
    if only_stage == "transcript":
        return

    # --- Highlight ---
    if only_stage in (None, "highlight"):
        highlight = stage_highlight(job, cfg, job_path, video_path, segments)
    else:
        log = read_log(job_path, cfg)
        hl = log["stages"].get("highlight", {})
        if hl.get("output") == "pending_review":
            highlight = None
        else:
            highlight = {"start": hl.get("start", 0), "end": hl.get("end", 45), "hook_line": hl.get("hook_line", "")}

    if not highlight:
        print("[pipeline] Halting: Job is pending human review.", flush=True)
        return
        
    if only_stage == "highlight":
        return

    # --- Clip ---
    if only_stage in (None, "clip"):
        clip_path = stage_clip(job, cfg, job_path, video_path, highlight)
    else:
        clip_path = get_stage_output(job_path, cfg, "clip")
        if not clip_path:
            raise RuntimeError("Clip stage has not been run yet")
    if only_stage == "clip":
        return

    # --- Music ---
    if only_stage in (None, "music"):
        music_meta = stage_music(job, cfg, job_path, clip_path)
    else:
        log = read_log(job_path, cfg)
        music_meta = log.get("stages", {}).get("music", {}).get("extra", {})
    if only_stage == "music":
        return

    # --- Caption ---
    if only_stage in (None, "caption"):
        final_path = stage_caption(job, cfg, job_path, clip_path, music_meta, segments, highlight)
    else:
        final_path = get_stage_output(job_path, cfg, "caption") or clip_path
    if only_stage == "caption":
        return

    # --- Upload ---
    if only_stage in (None, "upload"):
        response = stage_upload(job, cfg, job_path, final_path)
        print(f"[pipeline] done! Video ID: {response.get('id', 'unknown')}", flush=True)