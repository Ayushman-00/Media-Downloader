"""
Streamlit dashboard for the yt_shorts_automation pipeline.

Run with:
    streamlit run dashboard.py

Flow (Phase 3.5):
  1. Source   — Paste a YouTube link or browse a local file
  2. Script   — Auto-Analyze or manually define clip range + captions
  3. Captions — Preview & configure caption settings
  4. Music    — Pick a track from /music, set volume
  5. Build    — Render the short (clip + music + captions) + upload
"""
import os
import json
import re
import glob
import subprocess
import streamlit as st

from src.utils import load_config
from src import downloader, transcript as transcript_mod, highlight_finder, clipper, music_selector, captioner
from src.uploaders import get_uploader

st.set_page_config(page_title="YT Shorts Automation", layout="wide")
cfg = load_config()

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
_defaults = {
    "video_path": None,
    "info": {},
    "segments": None,
    "highlight": None,
    "clip_path": None,
    "final_path": None,
    "job": {},
    # Script tab state
    "script_mode": cfg.get("script", {}).get("default_mode", "full_auto"),
    "caption_source": "auto",
    "custom_caption_text": "",
    "hook_line_override": "",
    "script_saved": False,
    "candidates": None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.title("YT Shorts Automation Dashboard")

# ---------------------------------------------------------------
# Pending Reviews Panel (unchanged from Phase 2)
# ---------------------------------------------------------------
logs_dir = cfg["paths"]["logs"]
pending_logs = []
if os.path.exists(logs_dir):
    for f in glob.glob(os.path.join(logs_dir, "*.json")):
        try:
            with open(f, "r") as lf:
                log_data = json.load(lf)
                if log_data.get("stages", {}).get("highlight", {}).get("output") == "pending_review":
                    pending_logs.append((f, log_data))
        except:
            pass

if pending_logs:
    with st.expander(f"Pending Reviews ({len(pending_logs)})", expanded=True):
        for path, log_data in pending_logs:
            st.subheader(f"Job: {log_data.get('job_id', os.path.basename(path))}")
            cands = log_data.get("decisions", {}).get("highlight", {}).get("candidates", [])

            if not cands:
                st.warning("No candidates found in log.")
                continue

            selected_idx = st.selectbox(
                "Select candidate to approve",
                range(len(cands)),
                format_func=lambda i: f"[{cands[i].get('final_score', 0):.1f}] {cands[i].get('hook_line', 'No hook')}",
                key=f"sel_{log_data.get('job_id', path)}"
            )

            cand = cands[selected_idx]
            st.write(f"**Rationale:** {cand.get('rationale')}")
            st.write(f"**Hook Type:** {cand.get('hook_type')} | **Payoff Type:** {cand.get('payoff_type')}")

            col1, col2 = st.columns(2)
            with col1:
                adj_start = st.number_input("Start time", value=float(cand.get("start", 0)), step=0.1, key=f"start_{log_data.get('job_id', path)}")
            with col2:
                adj_end = st.number_input("End time", value=float(cand.get("end", 0)), step=0.1, key=f"end_{log_data.get('job_id', path)}")

            if st.button("Approve", key=f"btn_{log_data.get('job_id', path)}"):
                log_data["stages"]["highlight"]["start"] = adj_start
                log_data["stages"]["highlight"]["end"] = adj_end
                log_data["stages"]["highlight"]["output"] = "scored"
                log_data["stages"]["highlight"]["reason"] = "human_approved"
                if "decisions" not in log_data:
                    log_data["decisions"] = {}
                log_data["decisions"]["review_approved"] = True

                with open(path, "w") as lf:
                    json.dump(log_data, lf, indent=2)
                st.success("Approved! The pipeline can now be resumed for this job.")
                st.rerun()

st.divider()

# ===============================================================
# Section 1 — SOURCE
# ===============================================================
st.header("1. Source")
url = st.text_input("YouTube link")
rights_confirmed = st.checkbox(
    "I own this video or have explicit rights/license to reuse it"
)

if st.button("Download", disabled=not url):
    if not rights_confirmed:
        st.error("You must confirm rights/ownership before downloading and processing this video.")
    else:
        with st.spinner("Downloading (yt-dlp)..."):
            try:
                dcfg = cfg["downloader"]
                if dcfg.get("use_external_exe"):
                    video_path, info = downloader.download_via_exe(
                        url, cfg["paths"]["downloads"], dcfg["external_exe_path"]
                    )
                else:
                    video_path, info = downloader.download_via_ytdlp(
                        url, cfg["paths"]["downloads"], dcfg["format"]
                    )
                st.session_state.video_path = video_path
                st.session_state.info = info
                # Reset downstream state
                st.session_state.segments = None
                st.session_state.highlight = None
                st.session_state.clip_path = None
                st.session_state.final_path = None
                st.session_state.script_saved = False
                st.session_state.candidates = None
                st.success(f"Downloaded: {video_path}")
            except Exception as e:
                st.error(f"Download failed: {e}")

if st.session_state.video_path:
    st.video(st.session_state.video_path)
    st.caption(f"Title: {st.session_state.info.get('title', 'n/a')} | "
               f"Duration: {st.session_state.info.get('duration', 'n/a')}s")


# ===============================================================
# Section 2 — SCRIPT
# ===============================================================
if st.session_state.video_path:
    st.header("2. Script")

    script_mode = st.radio(
        "Mode",
        ["Auto-Analyze", "Skip Analyze (manual)", "Already a Short (Full Video)"],
        index=0 if st.session_state.script_mode == "full_auto" else 1,
        horizontal=True,
        key="script_mode_radio",
    )
    is_auto = script_mode == "Auto-Analyze"
    is_pre_short = script_mode == "Already a Short (Full Video)"

    # --- Transcript (needed for both modes — runs once) ---
    if st.session_state.segments is None:
        if st.button("Get transcript"):
            with st.spinner("Getting transcript..."):
                tcfg = cfg["transcript"]
                segments = []
                if tcfg.get("use_youtube_transcript_api") and not segments:
                    segments = transcript_mod.fetch_youtube_captions(url)
                if tcfg.get("prefer_youtube_captions") and not segments:
                    vtt = transcript_mod.find_existing_captions(st.session_state.video_path)
                    if vtt:
                        segments = transcript_mod.parse_vtt(vtt)
                if tcfg.get("groq_whisper_fallback") and not segments:
                    segments = transcript_mod.transcribe_with_groq(st.session_state.video_path)
                if tcfg.get("whisper_fallback") and not segments:
                    segments = transcript_mod.transcribe_with_whisper(
                        st.session_state.video_path, tcfg.get("whisper_model", "base")
                    )
                if not segments:
                    segments = []
                st.session_state.segments = segments
                st.success(f"Transcript ready: {len(segments)} segments")
                st.rerun()
    else:
        st.success(f"Transcript loaded: {len(st.session_state.segments)} segments")

    # --- Auto-Analyze ---
    if is_auto and st.session_state.segments is not None:
        if st.session_state.candidates is None:
            if st.button("Run Auto-Analyze"):
                with st.spinner("Running highlight engine (LLM)..."):
                    try:
                        from src import highlight_engine
                        candidates = highlight_engine.run_engine(
                            st.session_state.video_path, st.session_state.segments, cfg
                        )
                        st.session_state.candidates = candidates
                        # Set highlight to top candidate
                        top = candidates[0]
                        st.session_state.highlight = {
                            "start": top["start"],
                            "end": top["end"],
                            "hook_line": top.get("hook_line", ""),
                            "reason": "propose_refine_judge",
                        }
                        st.session_state.hook_line_override = top.get("hook_line", "")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Auto-Analyze failed: {e}")
                        import traceback
                        traceback.print_exc()

        if st.session_state.candidates:
            cands = st.session_state.candidates
            # Candidate card — reusing the same layout as Pending Reviews
            selected_idx = st.selectbox(
                "Select candidate",
                range(len(cands)),
                format_func=lambda i: f"[{cands[i].get('final_score', 0):.1f}] {cands[i].get('hook_line', 'No hook')}",
                key="script_cand_sel",
            )
            cand = cands[selected_idx]
            st.write(f"**Rationale:** {cand.get('rationale', 'n/a')}")
            st.write(f"**Hook Type:** {cand.get('hook_type', 'n/a')} | "
                     f"**Payoff Type:** {cand.get('payoff_type', 'n/a')} | "
                     f"**Score:** {cand.get('final_score', 0):.1f}")

            # Update highlight to selected candidate
            st.session_state.highlight = {
                "start": cand["start"],
                "end": cand["end"],
                "hook_line": cand.get("hook_line", ""),
                "reason": "propose_refine_judge",
            }
            st.session_state.hook_line_override = cand.get("hook_line", "")

    # --- Manual / Skip Analyze / Already a Short defaults ---
    if not is_auto and st.session_state.highlight is None:
        duration = st.session_state.info.get("duration", 30)
        st.session_state.highlight = {
            "start": 0,
            "end": float(duration) if is_pre_short else min(30.0, duration),
            "hook_line": "",
            "reason": "manual" if not is_pre_short else "full_video",
        }

    # --- Overridable fields ---
    if st.session_state.highlight:
        h = st.session_state.highlight
        duration = st.session_state.info.get("duration", h["end"] + 60)

        if is_pre_short:
            st.info("Full video mode active. Clip range is locked to the entire video length.")
            start_val, end_val = 0.0, float(duration)
            st.session_state.highlight["start"] = start_val
            st.session_state.highlight["end"] = end_val
        else:
            st.subheader("Clip range")
            col_s, col_e = st.columns(2)
            with col_s:
                start_val = st.number_input("Start (s)", value=float(h["start"]), min_value=0.0,
                                            max_value=float(duration), step=0.1, key="script_start")
            with col_e:
                end_val = st.number_input("End (s)", value=float(h["end"]), min_value=0.0,
                                          max_value=float(duration), step=0.1, key="script_end")
    
            # Snap to sentence boundary
            if st.session_state.segments and st.button("Snap to sentence boundary"):
                from src.highlight_engine import refine_boundaries
                temp_cand = [{"start": start_val, "end": end_val, "hook_line": ""}]
                refined = refine_boundaries(temp_cand, st.session_state.segments)
                if refined:
                    start_val = refined[0]["start"]
                    end_val = refined[0]["end"]
                    st.success(f"Snapped to: {start_val:.1f}s – {end_val:.1f}s")
                    st.session_state.highlight["start"] = start_val
                    st.session_state.highlight["end"] = end_val
                    st.rerun()
    
            st.session_state.highlight["start"] = start_val
            st.session_state.highlight["end"] = end_val

        # Transcript preview for selected range
        if st.session_state.segments:
            preview_text = " ".join(
                s["text"] for s in st.session_state.segments
                if s["start"] < end_val and s["end"] > start_val
            )
            if preview_text:
                st.text_area("Transcript preview for this range", preview_text, height=80, disabled=True)

        st.subheader("Captions")
        caption_source = st.radio(
            "Caption source",
            ["Auto (from transcript)", "Custom text"],
            index=0 if st.session_state.caption_source == "auto" else 1,
            horizontal=True,
            key="caption_source_radio",
        )
        st.session_state.caption_source = "auto" if caption_source == "Auto (from transcript)" else "custom"

        if st.session_state.caption_source == "custom":
            custom_text = st.text_area(
                "Paste your script or caption text",
                value=st.session_state.custom_caption_text,
                height=200,
                placeholder=(
                    "[0:00–0:06]\nHOOK VO: \"...\"\nON-SCREEN: \"text to burn\"\nVISUAL: \"...\"\n\n"
                    "[0:06–0:12]\nON-SCREEN: \"next caption\"\n\n"
                    "— or just paste plain text for a single static caption."
                ),
                key="custom_text_area",
            )
            st.session_state.custom_caption_text = custom_text

        st.subheader("Hook overlay")
        hook_line = st.text_input(
            "Hook text (shown at top of video for ~2s)",
            value=st.session_state.hook_line_override,
            key="hook_line_input",
        )
        st.session_state.hook_line_override = hook_line
        st.session_state.highlight["hook_line"] = hook_line

        # --- Save / Continue ---
        if st.button("Save & Continue", type="primary"):
            st.session_state.script_saved = True
            st.success("Script saved. Proceed to Captions / Music / Build below.")
            st.rerun()


# ===============================================================
# Section 3 — CAPTIONS (preview + settings)
# ===============================================================
if st.session_state.script_saved and st.session_state.highlight:
    st.header("3. Captions")
    h = st.session_state.highlight

    if st.session_state.caption_source == "auto":
        if st.session_state.segments:
            preview = " ".join(
                s["text"] for s in st.session_state.segments
                if s["start"] < h["end"] and s["end"] > h["start"]
            )
            st.text_area("Caption preview (auto from transcript)", preview, height=80, disabled=True)
        else:
            st.info("No transcript segments available — captions will be skipped.")
    else:
        st.text_area("Caption preview (custom text)", st.session_state.custom_caption_text, height=80, disabled=True)

    add_captions = st.checkbox("Burn in captions", value=cfg["captions"]["enabled"], key="add_captions_cb")
    st.session_state["add_captions"] = add_captions


# ===============================================================
# Section 4 — MUSIC
# ===============================================================
if st.session_state.script_saved and st.session_state.highlight:
    st.header("4. Music")
    music_dir = cfg["paths"]["music"]
    tracks = music_selector.list_available_tracks(music_dir)

    if not tracks:
        st.warning(f"No music files found in {music_dir}. Add .mp3/.wav files there first.")
        st.session_state["chosen_track"] = None
        st.session_state["music_volume"] = cfg["music"]["default_volume"]
    else:
        chosen_track = st.selectbox("Pick a track from your /music folder", tracks, key="music_track_sel")
        volume = st.slider("Music volume (relative to original audio)", 0.0, 1.0,
                           cfg["music"]["default_volume"], 0.05, key="music_vol_slider")
        st.session_state["chosen_track"] = chosen_track
        st.session_state["music_volume"] = volume


# ===============================================================
# Section 5 — BUILD
# ===============================================================
if st.session_state.script_saved and st.session_state.highlight:
    st.header("5. Build")

    if st.button("Build Short", type="primary"):
        h = st.session_state.highlight

        # --- Clip ---
        with st.spinner("Cutting and cropping clip..."):
            vcfg = cfg["video"]
            base_name = os.path.splitext(os.path.basename(st.session_state.video_path))[0]
            clip_out = os.path.join(cfg["paths"]["clips"], f"{base_name}_clip.mp4")
            
            # Use original script_mode to check if we skip crop
            if st.session_state.get("script_mode_radio") == "Already a Short (Full Video)":
                import shutil
                shutil.copy2(st.session_state.video_path, clip_out)
            else:
                cmd = clipper.ffmpeg_center_crop_cmd(
                    st.session_state.video_path, clip_out,
                    h["start"], h["end"],
                    vcfg["target_width"], vcfg["target_height"], vcfg["fps"],
                )
                subprocess.run(cmd, check=True)
                
            st.session_state.clip_path = clip_out

        # --- Resolve caption segments ---
        caption_segments = []
        add_captions = st.session_state.get("add_captions", cfg["captions"]["enabled"])
        ccfg = cfg["captions"]

        if add_captions:
            if st.session_state.caption_source == "custom" and st.session_state.custom_caption_text.strip():
                custom_text = st.session_state.custom_caption_text.strip()
                # Try structured parsing for bracketed-timestamp scripts
                parsed = _parse_structured_script(custom_text, h["start"], h["end"], cfg)
                if parsed:
                    caption_segments = parsed
                else:
                    # Fallback: single static block
                    caption_segments = [{"start": h["start"], "end": h["end"], "text": custom_text}]
                # Force static style for custom captions (no word-level timing data)
                ccfg = {**ccfg, "style": "static"}
            elif st.session_state.segments:
                caption_segments = st.session_state.segments
            # else: no segments, captions will be empty

        # --- Build ASS + music + render in one pass ---
        final_path = clip_out
        track_path = None
        chosen = st.session_state.get("chosen_track")
        volume = st.session_state.get("music_volume", cfg["music"]["default_volume"])
        if chosen:
            track_path = os.path.join(cfg["paths"]["music"], chosen)

        ass_path = None
        if add_captions and caption_segments:
            with st.spinner("Building captions..."):
                ass_path = os.path.splitext(clip_out)[0] + ".ass"
                captioner.build_ass(
                    caption_segments,
                    h["start"], h["end"],
                    ass_path, ccfg,
                    hook_line=h.get("hook_line", ""),
                )

        # Consolidated FFmpeg pass (music + captions)
        final_out = os.path.join(
            cfg["paths"]["final"],
            os.path.basename(os.path.splitext(clip_out)[0]) + "_final.mp4",
        )
        with st.spinner("Rendering final video..."):
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", clip_out]

            if track_path and os.path.isfile(track_path):
                cmd.extend(["-i", track_path])
                fc = (f"[0:a]volume={volume}[a0]; [1:a]volume={volume}[a1]; "
                      f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]")
                cmd.extend(["-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-c:a", "aac"])
            else:
                cmd.extend(["-c:a", "copy"])

            if ass_path:
                ass_for_filter = ass_path.replace("\\", "/").replace(":", "\\:")
                cmd.extend(["-vf", f"subtitles='{ass_for_filter}'", "-c:v", "libx264"])
            else:
                cmd.extend(["-c:v", "copy"])

            cmd.append(final_out)
            subprocess.run(cmd, check=True)
            final_path = final_out

        st.session_state.final_path = final_path
        st.success(f"Short ready: {final_path}")

    # --- Preview ---
    if st.session_state.final_path:
        st.video(st.session_state.final_path)

    # --- Upload ---
    if st.session_state.final_path:
        st.subheader("Post to YouTube")

        title = st.text_input("Title", value=(st.session_state.info.get("title", "") + " #Shorts"), key="upload_title")
        description = st.text_area("Description", value="#Shorts", key="upload_desc")
        tags = st.text_input("Tags (comma separated)", value="shorts", key="upload_tags")
        privacy = st.selectbox("Privacy status", ["private", "public", "unlisted"], key="upload_privacy")
        schedule_enabled = st.checkbox("Schedule for later (requires privacy = private)", key="upload_sched_cb")
        schedule_time = None
        if schedule_enabled:
            sched_date = st.date_input("Publish date (UTC)", key="upload_sched_date")
            sched_time = st.time_input("Publish time (UTC)", key="upload_sched_time")
            schedule_time = f"{sched_date}T{sched_time}Z"

        if st.button("Post to YouTube"):
            client_secret = os.path.join(cfg["paths"]["credentials"], "client_secret.json")
            if not os.path.exists(client_secret):
                st.error(f"Missing {client_secret}. Add your Google Cloud OAuth 'Desktop app' JSON there first.")
            else:
                with st.spinner("Authenticating + uploading (a browser window may open for login)..."):
                    try:
                        uploader = get_uploader(cfg)
                        metadata = {
                            "title": title,
                            "description": description,
                            "tags": [t.strip() for t in tags.split(",") if t.strip()],
                            "category_id": cfg["upload"]["category_id"],
                            "privacy_status": privacy,
                            "publish_at": schedule_time,
                            "made_for_kids": cfg["upload"].get("made_for_kids", False)
                        }
                        response = uploader.upload(st.session_state.final_path, metadata)
                        st.success(f"Uploaded! Video ID: {response.get('id')}")
                        st.markdown(f"**Link:** [youtu.be/{response.get('id')}](https://youtu.be/{response.get('id')})")
                    except Exception as e:
                        st.error(f"Upload failed: {e}")


# ===============================================================
# Structured script parsing (Addendum B)
# ===============================================================

def _parse_structured_script(raw_text: str, clip_start: float, clip_end: float, cfg: dict) -> list:
    """Parse a bracketed-timestamp script into caption segments.

    If the text matches the structured format ([MM:SS–MM:SS] blocks with ON-SCREEN lines),
    sends it to Groq for strict JSON extraction. Falls back to None on failure
    (caller uses single static block).
    """
    # Quick check: does this look like a structured script?
    if not re.search(r'\[\d+:\d+', raw_text):
        return None  # Plain text — caller handles fallback

    prompt = f"""You are a precise JSON extractor. The user has written a structured video script with timestamped blocks. Extract ONLY the ON-SCREEN caption lines with their timestamps.

Rules:
1. Parse each [MM:SS–MM:SS] block and find the ON-SCREEN line.
2. Convert timestamps to seconds (e.g. 1:30 = 90.0).
3. Return the ON-SCREEN text EXACTLY as written — do NOT paraphrase, summarize, or alter it in any way.
4. Ignore VO, VISUAL, and any other non-ON-SCREEN lines. Do not include them in output.
5. If a block has no ON-SCREEN line, skip it entirely.

Respond ONLY with a JSON array of objects. Example:
[
  {{"start": 0.0, "end": 6.0, "text": "exact ON-SCREEN text here"}}
]

Script:
{raw_text}"""

    try:
        from src.highlight_engine import _call_groq, _parse_candidate_list
        model = cfg.get("groq", {}).get("llm_model", "llama-3.3-70b-versatile")
        raw_response = _call_groq(prompt, model, temperature=0.0)

        # Defensive parsing — same pattern as _parse_candidate_list
        text = raw_response.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
            else:
                print("[dashboard] Structured script parse failed (no JSON array found), falling back.", flush=True)
                return None

        if not isinstance(parsed, list):
            return None

        # Validate and clamp segments to clip range
        clip_duration = clip_end - clip_start
        valid = []
        for seg in parsed:
            if not isinstance(seg, dict) or "start" not in seg or "end" not in seg or "text" not in seg:
                continue
            try:
                s = float(seg["start"])
                e = float(seg["end"])
            except (ValueError, TypeError):
                continue
            # Clamp to clip range (these are relative to clip start=0)
            s = max(0, s)
            e = min(clip_duration, e)
            if e <= s:
                continue
            # Offset to original video time for build_ass
            valid.append({
                "start": clip_start + s,
                "end": clip_start + e,
                "text": str(seg["text"]),
            })

        if not valid:
            print("[dashboard] Structured script produced zero valid segments, falling back.", flush=True)
            return None

        print(f"[dashboard] Structured script parsed: {len(valid)} caption segments.", flush=True)
        return valid

    except Exception as e:
        print(f"[dashboard] Structured script parse error: {e}. Falling back.", flush=True)
        return None
