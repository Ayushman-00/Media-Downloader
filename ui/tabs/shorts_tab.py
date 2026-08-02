"""
Shorts tab — creates YouTube Shorts from the Media Downloader GUI.

Integrates the yt_shorts_automation pipeline into a step-by-step wizard
using the same CustomTkinter framework as the rest of the app.
"""

import customtkinter as ctk
import os
import sys
import subprocess
import threading
import tkinter.filedialog as filedialog
from typing import Optional, List, Dict

# ── Bootstrap yt_shorts_automation imports ──────────────────────────────────
_YT_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "yt_shorts_automation",
)
if _YT_ROOT not in sys.path:
    sys.path.insert(0, _YT_ROOT)

from src.utils import load_config as load_shorts_config
from src import (
    downloader as shorts_dl,
    transcript as transcript_mod,
    highlight_finder,
    clipper,
    music_selector,
    captioner,
)
from src.uploaders import get_uploader


class ShortsTab(ctk.CTkFrame):
    """Step-by-step wizard for the full Shorts pipeline."""

    def __init__(self, master, app, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app

        # ── State ─────────────────────────────────────────────────────────
        self._video_path: Optional[str] = None
        self._video_url: str = ""
        self._info: dict = {}
        self._segments: Optional[List[Dict]] = None
        self._highlight: Optional[Dict] = None
        self._highlights: List[Dict] = []    # top-ranked highlights for multi-clip
        self._final_path: Optional[str] = None
        self._final_paths: List[str] = []    # all built clip paths

        try:
            self._cfg = load_shorts_config()
        except Exception:
            self._cfg = {}

        # ── Scroll container ──────────────────────────────────────────────
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        self.scroll.grid_columnconfigure(1, weight=1)

        row = 0

        # ── Title ─────────────────────────────────────────────────────────
        ctk.CTkLabel(
            self.scroll,
            text="🎬  Create YouTube Short",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 15))
        row += 1

        # ══════════════════════════════════════════════════════════════════
        # STEP 1 — Download or Select
        # ══════════════════════════════════════════════════════════════════
        row = self._section_header("Step 1 — Download or Select Video", row)

        ctk.CTkLabel(self.scroll, text="YouTube URL:").grid(
            row=row, column=0, padx=10, pady=5, sticky="w"
        )
        self.url_entry = ctk.CTkEntry(
            self.scroll,
            placeholder_text="https://www.youtube.com/watch?v=...",
        )
        self.url_entry.grid(row=row, column=1, padx=10, pady=5, sticky="ew")
        row += 1

        self.rights_var = ctk.BooleanVar(value=False)
        self.rights_cb = ctk.CTkCheckBox(
            self.scroll,
            text="I own this video or have rights to reuse it",
            variable=self.rights_var,
        )
        self.rights_cb.grid(
            row=row, column=0, columnspan=2, padx=10, pady=5, sticky="w"
        )
        row += 1

        self.dl_btn = ctk.CTkButton(
            self.scroll, text="⬇  Download", height=38, command=self._on_download
        )
        self.dl_btn.grid(
            row=row, column=0, columnspan=2, padx=10, pady=5, sticky="ew"
        )
        row += 1

        ctk.CTkLabel(self.scroll, text="— OR —", font=("Arial", 11, "bold")).grid(
            row=row, column=0, columnspan=2, pady=(10, 0)
        )
        row += 1

        self.browse_btn = ctk.CTkButton(
            self.scroll, text="📂  Browse Local Video", height=38, fg_color="#455A64", hover_color="#37474F", command=self._on_browse_local
        )
        self.browse_btn.grid(
            row=row, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="ew"
        )
        row += 1

        self.dl_status = ctk.CTkLabel(self.scroll, text="", font=("Arial", 11))
        self.dl_status.grid(row=row, column=0, columnspan=2, padx=10, sticky="w")
        row += 1

        # ══════════════════════════════════════════════════════════════════
        # STEP 2 — Analyze
        # ══════════════════════════════════════════════════════════════════
        row = self._section_header("Step 2 — Find Best Part", row)

        self.analyze_btn = ctk.CTkButton(
            self.scroll,
            text="🔍  Analyze Video",
            height=38,
            command=self._on_analyze,
            state="disabled",
        )
        self.analyze_btn.grid(
            row=row, column=0, padx=10, pady=5, sticky="ew"
        )
        
        self.pre_short_var = ctk.BooleanVar(value=False)
        self.pre_short_cb = ctk.CTkCheckBox(
            self.scroll,
            text="Already a Short (Skip Crop/Analyze)",
            variable=self.pre_short_var,
            command=self._on_pre_short_toggle,
            state="disabled"
        )
        self.pre_short_cb.grid(
            row=row, column=1, padx=10, pady=5, sticky="w"
        )
        row += 1

        self.analyze_status = ctk.CTkLabel(
            self.scroll, text="", font=("Arial", 11)
        )
        self.analyze_status.grid(
            row=row, column=0, columnspan=2, padx=10, sticky="w"
        )
        row += 1

        # ══════════════════════════════════════════════════════════════════
        # STEP 3 — Adjust Clip Range
        # ══════════════════════════════════════════════════════════════════
        row = self._section_header("Step 3 — Adjust Clip Range", row)

        time_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        time_frame.grid(
            row=row, column=0, columnspan=2, padx=10, pady=5, sticky="ew"
        )

        ctk.CTkLabel(time_frame, text="Start (s):").grid(
            row=0, column=0, padx=(0, 5)
        )
        self.start_entry = ctk.CTkEntry(
            time_frame, width=80, placeholder_text="0.0"
        )
        self.start_entry.grid(row=0, column=1, padx=5)

        ctk.CTkLabel(time_frame, text="End (s):").grid(
            row=0, column=2, padx=(20, 5)
        )
        self.end_entry = ctk.CTkEntry(
            time_frame, width=80, placeholder_text="45.0"
        )
        self.end_entry.grid(row=0, column=3, padx=5)
        row += 1

        self.preview_text = ctk.CTkTextbox(self.scroll, height=80, state="disabled")
        self.preview_text.grid(
            row=row, column=0, columnspan=2, padx=10, pady=5, sticky="ew"
        )
        row += 1

        # ══════════════════════════════════════════════════════════════════
        # STEP 4 — Music & Captions
        # ══════════════════════════════════════════════════════════════════
        row = self._section_header("Step 4 — Music & Captions", row)

        ctk.CTkLabel(self.scroll, text="Music Track:").grid(
            row=row, column=0, padx=10, pady=5, sticky="w"
        )
        self.track_var = ctk.StringVar(value="(none)")
        self.track_combo = ctk.CTkOptionMenu(
            self.scroll, variable=self.track_var, values=["(none)"]
        )
        self.track_combo.grid(row=row, column=1, padx=10, pady=5, sticky="w")
        self._refresh_tracks()
        row += 1

        ctk.CTkLabel(self.scroll, text="Music Volume:").grid(
            row=row, column=0, padx=10, pady=5, sticky="w"
        )
        vol_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        vol_frame.grid(row=row, column=1, padx=10, pady=5, sticky="ew")
        vol_frame.grid_columnconfigure(0, weight=1)

        default_vol = self._cfg.get("music", {}).get("default_volume", 0.15)
        self.vol_var = ctk.DoubleVar(value=default_vol)
        self.vol_slider = ctk.CTkSlider(
            vol_frame,
            from_=0,
            to=1,
            variable=self.vol_var,
            command=self._on_vol_change,
        )
        self.vol_slider.grid(row=0, column=0, sticky="ew")
        self.vol_label = ctk.CTkLabel(
            vol_frame, text=f"{default_vol:.0%}", width=40
        )
        self.vol_label.grid(row=0, column=1, padx=(8, 0))
        row += 1

        # Caption Toggle
        self.captions_var = ctk.BooleanVar(
            value=self._cfg.get("captions", {}).get("enabled", True)
        )
        self.captions_cb = ctk.CTkCheckBox(
            self.scroll, text="Burn in captions", variable=self.captions_var,
            command=self._on_captions_toggle
        )
        self.captions_cb.grid(row=row, column=0, padx=10, pady=5, sticky="w")
        row += 1
        
        # Caption Source Radio
        self.caption_source_var = ctk.StringVar(value="auto")
        self.cap_source_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        
        ctk.CTkRadioButton(self.cap_source_frame, text="Auto (from transcript)", variable=self.caption_source_var, value="auto", command=self._on_captions_toggle).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkRadioButton(self.cap_source_frame, text="Custom Text", variable=self.caption_source_var, value="custom", command=self._on_captions_toggle).grid(row=0, column=1)
        
        self.cap_source_frame.grid(row=row, column=0, columnspan=2, padx=10, pady=2, sticky="w")
        row += 1
        
        # Custom Caption Textbox — editable, so DO NOT redirect its scroll
        self.custom_cap_text = ctk.CTkTextbox(self.scroll, height=120)
        # Hidden by default
        self._custom_cap_row = row
        row += 1

        self._on_captions_toggle()

        # ══════════════════════════════════════════════════════════════════
        # STEP 5 — Build
        # ══════════════════════════════════════════════════════════════════
        row = self._section_header("Step 5 — Build Short", row)

        clips_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        clips_frame.grid(
            row=row, column=0, columnspan=2, padx=10, pady=5, sticky="ew"
        )
        ctk.CTkLabel(clips_frame, text="Number of Clips:").grid(
            row=0, column=0, padx=(0, 10), sticky="w"
        )
        self.num_clips_var = ctk.StringVar(value="1")
        ctk.CTkOptionMenu(
            clips_frame,
            variable=self.num_clips_var,
            values=["1", "2", "3", "4", "5"],
            width=70,
        ).grid(row=0, column=1, sticky="w")
        row += 1

        self.build_btn = ctk.CTkButton(
            self.scroll,
            text="🔨  Build Short",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_build,
            state="disabled",
        )
        self.build_btn.grid(
            row=row, column=0, columnspan=2, padx=10, pady=5, sticky="ew"
        )
        row += 1

        self.build_status = ctk.CTkLabel(self.scroll, text="", font=("Arial", 11))
        self.build_status.grid(
            row=row, column=0, columnspan=2, padx=10, sticky="w"
        )
        row += 1

        # ══════════════════════════════════════════════════════════════════
        # STEP 6 — Upload
        # ══════════════════════════════════════════════════════════════════
        row = self._section_header("Step 6 — Post to YouTube", row)

        ctk.CTkLabel(self.scroll, text="Title:").grid(
            row=row, column=0, padx=10, pady=5, sticky="w"
        )
        self.title_entry = ctk.CTkEntry(
            self.scroll, placeholder_text="My Short #Shorts"
        )
        self.title_entry.grid(row=row, column=1, padx=10, pady=5, sticky="ew")
        row += 1

        ctk.CTkLabel(self.scroll, text="Description:").grid(
            row=row, column=0, padx=10, pady=(5, 0), sticky="nw"
        )
        self.desc_text = ctk.CTkTextbox(self.scroll, height=60)
        self.desc_text.grid(row=row, column=1, padx=10, pady=5, sticky="ew")
        self.desc_text.insert("1.0", "#Shorts")
        self._fix_mousewheel(self.desc_text)
        row += 1

        ctk.CTkLabel(self.scroll, text="Tags:").grid(
            row=row, column=0, padx=10, pady=5, sticky="w"
        )
        self.tags_entry = ctk.CTkEntry(
            self.scroll, placeholder_text="shorts, viral"
        )
        self.tags_entry.grid(row=row, column=1, padx=10, pady=5, sticky="ew")
        row += 1

        ctk.CTkLabel(self.scroll, text="Privacy:").grid(
            row=row, column=0, padx=10, pady=5, sticky="w"
        )
        self.privacy_var = ctk.StringVar(value="private")
        ctk.CTkOptionMenu(
            self.scroll,
            variable=self.privacy_var,
            values=["private", "public", "unlisted"],
        ).grid(row=row, column=1, padx=10, pady=5, sticky="w")
        row += 1

        self.upload_btn = ctk.CTkButton(
            self.scroll,
            text="🚀  Upload to YouTube",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#CC0000",
            hover_color="#AA0000",
            command=self._on_upload,
            state="disabled",
        )
        self.upload_btn.grid(
            row=row, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew"
        )
        row += 1

        self.upload_status = ctk.CTkLabel(
            self.scroll, text="", font=("Arial", 11)
        )
        self.upload_status.grid(
            row=row, column=0, columnspan=2, padx=10, pady=(0, 15), sticky="w"
        )

    # ══════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════



    def _section_header(self, title: str, row: int) -> int:
        """Draw a bold section header and return the next available row."""
        ctk.CTkLabel(
            self.scroll,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=(20, 5))
        return row + 1

    def _refresh_tracks(self):
        """Populate the music track dropdown from the /music folder."""
        music_dir = self._cfg.get("paths", {}).get("music", "")
        tracks = music_selector.list_available_tracks(music_dir) if music_dir else []
        values = ["(none)"] + tracks
        self.track_combo.configure(values=values)
        if tracks:
            self.track_var.set(tracks[0])

    def _on_vol_change(self, value):
        self.vol_label.configure(text=f"{value:.0%}")
        
    def _on_captions_toggle(self):
        if self.captions_var.get():
            self.cap_source_frame.grid(row=self.cap_source_frame.grid_info().get('row', 0), column=0, columnspan=2, padx=10, pady=2, sticky="w")
            if self.caption_source_var.get() == "custom":
                self.custom_cap_text.grid(row=self._custom_cap_row, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
            else:
                self.custom_cap_text.grid_forget()
        else:
            self.cap_source_frame.grid_forget()
            self.custom_cap_text.grid_forget()

    def _set_status(self, label, text, color="gray"):
        label.configure(text=text, text_color=color)

    def _run_threaded(self, func, status_label, working_msg="Working...", btn=None):
        """Run *func* in a daemon thread; disable *btn* while running."""
        if btn:
            btn.configure(state="disabled")
        self._set_status(status_label, working_msg)

        def wrapper():
            try:
                func()
            except Exception as e:
                self.after(
                    0, lambda: self._set_status(status_label, f"❌ {e}", "#C62828")
                )
                if btn:
                    self.after(0, lambda: btn.configure(state="normal"))

        threading.Thread(target=wrapper, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════
    # Step 1 — Download
    # ══════════════════════════════════════════════════════════════════════

    def _on_download(self):
        url = self.url_entry.get().strip()
        if not url:
            self._set_status(self.dl_status, "⚠ Enter a URL first.", "#FFA726")
            return
        if not self.rights_var.get():
            self._set_status(
                self.dl_status, "⚠ Confirm rights/ownership first.", "#FFA726"
            )
            return

        self._video_url = url

        def work():
            cfg = self._cfg
            dcfg = cfg.get("downloader", {})
            dl_dir = cfg.get("paths", {}).get("downloads", "")

            if dcfg.get("use_external_exe"):
                path, info = shorts_dl.download_via_exe(
                    url, dl_dir, dcfg["external_exe_path"]
                )
            else:
                path, info = shorts_dl.download_via_ytdlp(
                    url,
                    dl_dir,
                    dcfg.get("format", "bestvideo[height<=1080]+bestaudio/best"),
                )

            self._video_path = path
            self._info = info
            self._segments = None
            self._highlight = None
            self._final_path = None

            title = info.get("title", os.path.basename(path))
            dur = info.get("duration", "?")

            self.after(
                0,
                lambda: self._set_status(
                    self.dl_status, f"✅ {title} ({dur}s)", "#4CAF50"
                ),
            )
            self.after(0, lambda: self.analyze_btn.configure(state="normal"))
            self.after(0, lambda: self.dl_btn.configure(state="normal"))

        self._run_threaded(work, self.dl_status, "⬇ Downloading…", self.dl_btn)

    def _on_browse_local(self):
        file_path = filedialog.askopenfilename(
            title="Select Video",
            filetypes=[("Video Files", "*.mp4 *.mkv *.webm *.mov *.avi"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        self._video_path = file_path
        self._video_url = ""  # No URL
        
        # Get actual duration for the local file
        from src.music_selector import get_duration
        dur = get_duration(file_path)
        
        self._info = {
            "title": os.path.basename(file_path),
            "duration": dur
        }
        self._segments = None
        self._highlight = None
        self._final_path = None

        self._set_status(
            self.dl_status, f"✅ Local file selected: {os.path.basename(file_path)}", "#4CAF50"
        )
        self.analyze_btn.configure(state="normal")
        self.pre_short_cb.configure(state="normal")
        self.url_entry.delete(0, "end")

    def _on_pre_short_toggle(self):
        is_pre_short = self.pre_short_var.get()
        if is_pre_short:
            self.analyze_btn.configure(state="disabled")
            
            # Automatically populate start/end with full duration if known
            duration = self._info.get("duration", 0)
            self.start_entry.delete(0, "end")
            self.start_entry.insert(0, "0.0")
            if duration:
                self.end_entry.delete(0, "end")
                self.end_entry.insert(0, f"{float(duration):.1f}")
                
            self.preview_text.configure(state="normal")
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("1.0", "(Full short mode active. Run 'Get transcript' below if you want captions, or build directly.)")
            self.preview_text.configure(state="disabled")
            self.build_btn.configure(state="normal")
            
            # Optionally, we could kick off transcription here silently if they need captions,
            # but they can also just build.
        else:
            self.analyze_btn.configure(state="normal")
            self.build_btn.configure(state="disabled")

    # ══════════════════════════════════════════════════════════════════════
    # Step 2 — Analyze (transcript + highlight)
    # ══════════════════════════════════════════════════════════════════════

    def _on_analyze(self):
        def work():
            cfg = self._cfg
            tcfg = cfg.get("transcript", {})
            segments = None

            # ── Transcript waterfall ──────────────────────────────────────
            if tcfg.get("use_youtube_transcript_api") and self._video_url:
                segments = transcript_mod.fetch_youtube_captions(self._video_url)

            if not segments and tcfg.get("prefer_youtube_captions"):
                vtt = transcript_mod.find_existing_captions(self._video_path)
                if vtt:
                    segments = transcript_mod.parse_vtt(vtt)

            if not segments and tcfg.get("groq_whisper_fallback"):
                segments = transcript_mod.transcribe_with_groq(self._video_path)

            if not segments and tcfg.get("whisper_fallback"):
                segments = transcript_mod.transcribe_with_whisper(
                    self._video_path, tcfg.get("whisper_model", "base")
                )

            if not segments:
                segments = []
            self._segments = segments

            # ── Highlight scoring ─────────────────────────────────────────
            hcfg = cfg.get("highlight", {})
            total_dur = (
                segments[-1]["end"]
                if segments
                else self._info.get("duration", 45)
            )
            windows = highlight_finder.make_windows(
                segments,
                hcfg.get("window_sec", 45),
                hcfg.get("step_sec", 5),
                total_dur,
            )

            if not windows:
                best = {
                    "start": 0,
                    "end": min(45, total_dur),
                    "reason": "no windows",
                }
            else:
                ranked = highlight_finder.score_heuristic(
                    self._video_path, windows
                )
                best = {**ranked[0], "reason": "heuristic"}

                # Groq cloud LLM
                if hcfg.get("use_groq") and hcfg.get("method") in (
                    "groq",
                    "hybrid",
                ):
                    try:
                        shortlist = ranked[: hcfg.get("top_candidates", 5)]
                        gcfg = cfg.get("groq", {})
                        order = highlight_finder.score_groq(
                            shortlist,
                            gcfg.get("llm_model", "llama-3.3-70b-versatile"),
                        )
                        best = {**shortlist[order[0]], "reason": "groq_llm"}
                    except Exception:
                        pass

                # Ollama local LLM
                elif hcfg.get("use_ollama") and hcfg.get("method") in (
                    "ollama",
                    "hybrid",
                ):
                    try:
                        shortlist = ranked[: hcfg.get("top_candidates", 5)]
                        order = highlight_finder.score_llm(
                            shortlist,
                            hcfg["ollama_url"],
                            hcfg["ollama_model"],
                        )
                        best = {**shortlist[order[0]], "reason": "ollama_llm"}
                    except Exception:
                        pass

            self._highlight = best
            self._highlights = []  # store top N for multi-clip

            if windows and ranked:
                # Groq/Ollama may have re-ranked; store all candidates
                if hcfg.get("use_groq") and hcfg.get("method") in ("groq", "hybrid"):
                    try:
                        shortlist_all = ranked[: hcfg.get("top_candidates", 5)]
                        gcfg_all = cfg.get("groq", {})
                        order_all = highlight_finder.score_groq(
                            shortlist_all,
                            gcfg_all.get("llm_model", "llama-3.3-70b-versatile"),
                        )
                        self._highlights = [shortlist_all[i] for i in order_all]
                    except Exception:
                        self._highlights = ranked[:5]
                else:
                    self._highlights = ranked[:5]
            else:
                self._highlights = [best]

            # ── Update UI ─────────────────────────────────────────────────
            def update_ui():
                self.start_entry.delete(0, "end")
                self.start_entry.insert(0, f"{best['start']:.1f}")
                self.end_entry.delete(0, "end")
                self.end_entry.insert(0, f"{best['end']:.1f}")

                # Transcript preview
                self.preview_text.configure(state="normal")
                self.preview_text.delete("1.0", "end")
                if segments:
                    preview = " ".join(
                        s["text"]
                        for s in segments
                        if s["start"] < best["end"] and s["end"] > best["start"]
                    )
                    self.preview_text.insert("1.0", preview or "(no text in range)")
                else:
                    self.preview_text.insert("1.0", "(no transcript available)")
                self.preview_text.configure(state="disabled")

                reason = best.get("reason", "auto")
                self._set_status(
                    self.analyze_status,
                    f"✅ {best['start']:.1f}s – {best['end']:.1f}s ({reason})"
                    f" | {len(segments)} segments",
                    "#4CAF50",
                )
                self.build_btn.configure(state="normal")
                self.analyze_btn.configure(state="normal")

                # Pre-fill upload title
                title = self._info.get("title", "")
                if title:
                    self.title_entry.delete(0, "end")
                    self.title_entry.insert(0, f"{title} #Shorts")

            self.after(0, update_ui)

        self._run_threaded(
            work,
            self.analyze_status,
            "🔍 Analyzing (transcript + scoring)…",
            self.analyze_btn,
        )

    # ══════════════════════════════════════════════════════════════════════
    # Step 5 — Build (clip + music + captions)
    # ══════════════════════════════════════════════════════════════════════

    def _on_build(self):
        def work():
            cfg = self._cfg
            vcfg = cfg.get("video", {})
            num_clips = int(self.num_clips_var.get())

            # Determine which highlights to build
            highlights_to_build = []
            if num_clips == 1:
                # Single clip uses the user-edited start/end times
                if self.pre_short_var.get():
                    clip_start = 0.0
                    clip_end = self._info.get("duration", 0.0)
                    if not clip_end:
                        from src.music_selector import get_duration
                        clip_end = get_duration(self._video_path) or 1.0
                else:
                    try:
                        clip_start = float(self.start_entry.get())
                        clip_end = float(self.end_entry.get())
                    except ValueError:
                        raise ValueError("Enter valid start / end times")
                
                if clip_end <= clip_start:
                    raise ValueError("End time must be after start time")
                highlights_to_build = [{"start": clip_start, "end": clip_end}]
            else:
                # Multi-clip: use top N ranked highlights
                if len(self._highlights) < num_clips:
                    num_clips = len(self._highlights)
                highlights_to_build = self._highlights[:num_clips]
                if not highlights_to_build:
                    raise ValueError("No highlights found. Run Analyze first.")

            base = os.path.splitext(os.path.basename(self._video_path))[0]
            clips_dir = cfg.get("paths", {}).get("clips", "")
            final_dir = cfg.get("paths", {}).get("final", "")
            self._final_paths = []

            for clip_idx, hl in enumerate(highlights_to_build, start=1):
                clip_start = hl["start"]
                clip_end = hl["end"]
                suffix = f"_clip{clip_idx}" if num_clips > 1 else "_clip"
                final_suffix = f"_final{clip_idx}" if num_clips > 1 else "_final"

                self.after(
                    0,
                    lambda i=clip_idx, n=num_clips: self._set_status(
                        self.build_status,
                        f"✂ Clipping {i}/{n}…" if n > 1 else "✂ Clipping…",
                    ),
                )

                # 1. Clip & center-crop to 9:16 (skip if Already a Short)
                clip_out = os.path.join(clips_dir, f"{base}{suffix}.mp4")
                if self.pre_short_var.get():
                    import shutil
                    shutil.copy2(self._video_path, clip_out)
                else:
                    cmd = clipper.ffmpeg_center_crop_cmd(
                        self._video_path,
                        clip_out,
                        clip_start,
                        clip_end,
                        vcfg.get("target_width", 1080),
                        vcfg.get("target_height", 1920),
                        vcfg.get("fps", 30),
                    )
                    subprocess.run(cmd, check=True, capture_output=True)
                current = clip_out

                # 2. Mix music
                track = self.track_var.get()
                music_out = None
                if track and track != "(none)":
                    self.after(
                        0,
                        lambda i=clip_idx, n=num_clips: self._set_status(
                            self.build_status,
                            f"🎵 Mixing music {i}/{n}…" if n > 1 else "🎵 Mixing music…",
                        ),
                    )
                    music_dir = cfg.get("paths", {}).get("music", "")
                    track_path = os.path.join(music_dir, track)
                    music_out = os.path.splitext(clip_out)[0] + "_music.mp4"
                    music_selector.mix_music(
                        current,
                        track_path,
                        music_out,
                        self.vol_var.get(),
                        cfg.get("music", {}).get("duck_original", True),
                    )
                    current = music_out

                # 3. Burn captions
                ass_path = None
                if self.captions_var.get():
                    self.after(
                        0,
                        lambda i=clip_idx, n=num_clips: self._set_status(
                            self.build_status,
                            f"💬 Burning captions {i}/{n}…" if n > 1 else "💬 Burning captions…",
                        ),
                    )
                    ccfg = cfg.get("captions", {})
                    
                    caption_segments = []
                    if self.caption_source_var.get() == "custom":
                        custom_text = self.custom_cap_text.get("1.0", "end").strip()
                        if custom_text:
                            # Try structured parsing
                            parsed = captioner.parse_structured_script(custom_text, clip_start, clip_end, cfg)
                            if parsed:
                                caption_segments = parsed
                            else:
                                # Fallback static block
                                caption_segments = [{"start": clip_start, "end": clip_end, "text": custom_text}]
                            # Force static style for custom captions (no word-level)
                            ccfg = {**ccfg, "style": "static"}
                    else:
                        caption_segments = self._segments if self._segments else []
                        
                    if caption_segments:
                        ass_path = os.path.splitext(current)[0] + ".ass"
                        captioner.build_ass(
                            caption_segments, clip_start, clip_end, ass_path, ccfg
                        )
                        final_out = os.path.join(final_dir, f"{base}{final_suffix}.mp4")
                        rel_ass = os.path.relpath(ass_path).replace("\\", "/")
                        rel_ass_esc = rel_ass.replace("'", "'\\''")
                        sub_cmd = [
                            "ffmpeg", "-y", "-i", current,
                            "-vf", f"subtitles='{rel_ass_esc}'",
                            "-c:a", "copy",
                            final_out,
                        ]
                        subprocess.run(sub_cmd, check=True, capture_output=True)
                        current = final_out

                # Ensure final video is in the final_dir
                if not current.startswith(final_dir):
                    import shutil
                    final_out = os.path.join(final_dir, f"{base}{final_suffix}.mp4")
                    shutil.move(current, final_out)
                    current = final_out

                self._final_paths.append(current)

                # 4. Clean up intermediate files for this clip
                for fpath in [clip_out, music_out, ass_path]:
                    if fpath and os.path.exists(fpath) and fpath != current:
                        try:
                            os.remove(fpath)
                        except Exception:
                            pass
                # Clean cached .srt
                srt_cache = os.path.join(clips_dir, f"{base}.srt")
                if os.path.exists(srt_cache):
                    try:
                        os.remove(srt_cache)
                    except Exception:
                        pass

            self._final_path = self._final_paths[0] if self._final_paths else None

            if num_clips == 1:
                msg = f"✅ Short ready: {os.path.basename(self._final_paths[0])}"
            else:
                msg = f"✅ {len(self._final_paths)} shorts ready in output/final/"

            self.after(
                0,
                lambda: self._set_status(self.build_status, msg, "#4CAF50"),
            )
            self.after(0, lambda: self.upload_btn.configure(state="normal"))
            self.after(0, lambda: self.build_btn.configure(state="normal"))

        self._run_threaded(
            work, self.build_status, "🔨 Building short…", self.build_btn
        )

    # ══════════════════════════════════════════════════════════════════════
    # Step 6 — Upload to YouTube
    # ══════════════════════════════════════════════════════════════════════

    def _on_upload(self):
        def work():
            cfg = self._cfg

            title = self.title_entry.get().strip() or "My Short #Shorts"
            desc = self.desc_text.get("1.0", "end").strip() or "#Shorts"
            tags_raw = self.tags_entry.get().strip()
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()] or [
                "shorts"
            ]
            privacy = self.privacy_var.get()

            self.after(
                0,
                lambda: self._set_status(
                    self.upload_status, "🔑 Authenticating…"
                ),
            )
            up = get_uploader(cfg)

            self.after(
                0,
                lambda: self._set_status(self.upload_status, "🚀 Uploading…"),
            )
            metadata = {
                "title": title,
                "description": desc,
                "tags": tags,
                "category_id": cfg.get("upload", {}).get("category_id", "22"),
                "privacy_status": privacy,
                "made_for_kids": cfg.get("upload", {}).get("made_for_kids", False),
            }
            response = up.upload(self._final_path, metadata)

            vid_id = response.get("id", "unknown")
            self.after(
                0,
                lambda: self._set_status(
                    self.upload_status,
                    f"✅ Posted: https://youtube.com/watch?v={vid_id}",
                    "#4CAF50",
                ),
            )
            self.after(0, lambda: self.upload_btn.configure(state="normal"))

        self._run_threaded(
            work, self.upload_status, "🚀 Uploading…", self.upload_btn
        )
