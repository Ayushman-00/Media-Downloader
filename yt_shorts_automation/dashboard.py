"""
Streamlit dashboard for the yt_shorts_automation pipeline.

Run with:
    streamlit run dashboard.py

This is a thin UI layer over the existing src/ modules - it does not
reimplement download/highlight/clip/music/caption/upload logic, it just
calls the same functions those CLI stages use, so behavior stays identical
to running main.py directly.

Flow:
  1. Paste a YouTube link -> Download
  2. Auto-detect transcript + suggested "best part" (adjustable)
  3. Pick a music track from /music
  4. Build the short (clip + music + captions)
  5. Fill title/description/schedule -> Post to YouTube
"""
import os
import json
import glob
import streamlit as st

from src.utils import load_config
from src import downloader, transcript as transcript_mod, highlight_finder, clipper, music_selector, captioner, uploader

st.set_page_config(page_title="YT Shorts Automation", layout="wide")
cfg = load_config()

if "video_path" not in st.session_state:
    st.session_state.video_path = None
if "info" not in st.session_state:
    st.session_state.info = {}
if "segments" not in st.session_state:
    st.session_state.segments = None
if "highlight" not in st.session_state:
    st.session_state.highlight = None
if "clip_path" not in st.session_state:
    st.session_state.clip_path = None
if "music_path" not in st.session_state:
    st.session_state.music_path = None
if "final_path" not in st.session_state:
    st.session_state.final_path = None

st.title("YT Shorts Automation Dashboard")

# ---------------------------------------------------------------
# Step 1 - Download
# ---------------------------------------------------------------
st.header("1. Download")
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
                st.session_state.segments = None
                st.session_state.highlight = None
                st.session_state.clip_path = None
                st.session_state.music_path = None
                st.session_state.final_path = None
                st.success(f"Downloaded: {video_path}")
            except Exception as e:
                st.error(f"Download failed: {e}")

if st.session_state.video_path:
    st.video(st.session_state.video_path)
    st.caption(f"Title: {st.session_state.info.get('title', 'n/a')} | "
               f"Duration: {st.session_state.info.get('duration', 'n/a')}s")

# ---------------------------------------------------------------
# Step 2 - Transcript + Highlight (best part)
# ---------------------------------------------------------------
if st.session_state.video_path:
    st.header("2. Find the best part")

    if st.button("Analyze video"):
        with st.spinner("Getting transcript..."):
            tcfg = cfg["transcript"]
            vtt = transcript_mod.find_existing_captions(st.session_state.video_path)
            if tcfg.get("prefer_youtube_captions") and vtt:
                segments = transcript_mod.parse_vtt(vtt)
            elif tcfg.get("whisper_fallback"):
                segments = transcript_mod.transcribe_with_whisper(
                    st.session_state.video_path, tcfg.get("whisper_model", "base")
                )
            else:
                segments = []
            st.session_state.segments = segments

        with st.spinner("Scoring segments for the best clip..."):
            hcfg = cfg["highlight"]
            total_duration = segments[-1]["end"] if segments else st.session_state.info.get("duration", 45)
            windows = highlight_finder.make_windows(
                segments, hcfg["window_sec"], hcfg["step_sec"], total_duration
            )
            if not windows:
                best = {"start": 0, "end": min(45, total_duration), "reason": "video shorter than window"}
            else:
                ranked = highlight_finder.score_heuristic(st.session_state.video_path, windows)
                best = {**ranked[0], "reason": "heuristic pick"}
                if hcfg.get("use_ollama") and hcfg["method"] in ("llm", "hybrid"):
                    try:
                        shortlist = ranked[: hcfg["top_candidates"]]
                        order = highlight_finder.score_llm(shortlist, hcfg["ollama_url"], hcfg["ollama_model"])
                        best = {**shortlist[order[0]], "reason": "hybrid LLM pick"}
                    except Exception as e:
                        st.warning(f"Ollama scoring unavailable, used heuristic instead ({e})")
            st.session_state.highlight = best
        st.success(f"Suggested segment: {best['start']:.1f}s - {best['end']:.1f}s ({best['reason']})")

    if st.session_state.highlight:
        h = st.session_state.highlight
        duration = st.session_state.info.get("duration", h["end"] + 60)
        start, end = st.slider(
            "Adjust clip range (seconds)",
            min_value=0.0, max_value=float(duration),
            value=(float(h["start"]), float(h["end"])),
            step=1.0,
        )
        st.session_state.highlight = {"start": start, "end": end, "reason": h.get("reason", "manual adjust")}
        if st.session_state.segments:
            preview_text = " ".join(
                s["text"] for s in st.session_state.segments if s["start"] < end and s["end"] > start
            )
            st.text_area("Transcript preview for this range", preview_text, height=100)

# ---------------------------------------------------------------
# Step 3 - Music
# ---------------------------------------------------------------
if st.session_state.highlight:
    st.header("3. Choose music")
    music_dir = cfg["paths"]["music"]
    tracks = music_selector.list_available_tracks(music_dir)

    if not tracks:
        st.warning(f"No music files found in {music_dir}. Add .mp3/.wav files there first.")
    else:
        chosen_track = st.selectbox("Pick a track from your /music folder", tracks)
        volume = st.slider("Music volume (relative to original audio)", 0.0, 1.0,
                            cfg["music"]["default_volume"], 0.05)
        add_captions = st.checkbox("Burn in captions", value=cfg["captions"]["enabled"])

        if st.button("Build short"):
            with st.spinner("Cutting and cropping clip..."):
                vcfg = cfg["video"]
                base_name = os.path.splitext(os.path.basename(st.session_state.video_path))[0]
                clip_out = os.path.join(cfg["paths"]["clips"], f"{base_name}_clip.mp4")
                cmd = clipper.ffmpeg_center_crop_cmd(
                    st.session_state.video_path, clip_out,
                    st.session_state.highlight["start"], st.session_state.highlight["end"],
                    vcfg["target_width"], vcfg["target_height"], vcfg["fps"],
                )
                import subprocess
                subprocess.run(cmd, check=True)
                st.session_state.clip_path = clip_out

            with st.spinner(f"Mixing in '{chosen_track}'..."):
                track_path = os.path.join(music_dir, chosen_track)
                music_out = os.path.splitext(clip_out)[0] + "_music.mp4"
                music_selector.mix_music(clip_out, track_path, music_out, volume,
                                          cfg["music"].get("duck_original", True))
                st.session_state.music_path = music_out

            final_path = music_out
            if add_captions and st.session_state.segments:
                with st.spinner("Burning captions..."):
                    ccfg = cfg["captions"]
                    ass_path = os.path.splitext(music_out)[0] + ".ass"
                    captioner.build_ass(
                        st.session_state.segments,
                        st.session_state.highlight["start"], st.session_state.highlight["end"],
                        ass_path, ccfg,
                    )
                    final_out = os.path.join(
                        cfg["paths"]["final"],
                        os.path.basename(os.path.splitext(music_out)[0]) + "_final.mp4",
                    )
                    ass_for_filter = ass_path.replace("\\", "/").replace(":", "\\:")
                    cmd = ["ffmpeg", "-y", "-i", music_out, "-vf",
                           f"subtitles='{ass_for_filter}'", "-c:a", "copy", final_out]
                    subprocess.run(cmd, check=True)
                    final_path = final_out

            st.session_state.final_path = final_path
            st.success(f"Short ready: {final_path}")

    if st.session_state.final_path:
        st.video(st.session_state.final_path)

# ---------------------------------------------------------------
# Step 4 - Post to YouTube
# ---------------------------------------------------------------
if st.session_state.final_path:
    st.header("4. Post to YouTube")

    title = st.text_input("Title", value=(st.session_state.info.get("title", "") + " #Shorts"))
    description = st.text_area("Description", value="#Shorts")
    tags = st.text_input("Tags (comma separated)", value="shorts")
    privacy = st.selectbox("Privacy status", ["private", "public", "unlisted"])
    schedule_enabled = st.checkbox("Schedule for later (requires privacy = private)")
    schedule_time = None
    if schedule_enabled:
        sched_date = st.date_input("Publish date (UTC)")
        sched_time = st.time_input("Publish time (UTC)")
        schedule_time = f"{sched_date}T{sched_time}Z"

    if st.button("Post to YouTube"):
        client_secret = os.path.join(cfg["paths"]["credentials"], "client_secret.json")
        if not os.path.exists(client_secret):
            st.error(f"Missing {client_secret}. Add your Google Cloud OAuth 'Desktop app' JSON there first.")
        else:
            with st.spinner("Authenticating + uploading (a browser window may open for login)..."):
                try:
                    youtube = uploader.get_authenticated_service(cfg)
                    response = uploader.upload(
                        youtube, st.session_state.final_path,
                        title=title, description=description,
                        tags=[t.strip() for t in tags.split(",") if t.strip()],
                        category_id=cfg["upload"]["category_id"],
                        privacy_status=privacy,
                        publish_at=schedule_time,
                        made_for_kids=cfg["upload"].get("made_for_kids", False),
                    )
                    video_id = response.get("id")
                    st.success(f"Posted: https://youtube.com/watch?v={video_id}")
                except Exception as e:
                    st.error(f"Upload failed: {e}")
