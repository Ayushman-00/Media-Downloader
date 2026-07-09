import customtkinter as ctk
import tkinter.filedialog as filedialog
from core.config import config
from core.downloader import downloader


class DashboardTab(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app
        self.cookie_file: str = config.get("cookies", "cookie_file") or ""

        self.grid_columnconfigure(1, weight=1)

        # ── Row 0: URL Input ───────────────────────────────────────────────
        ctk.CTkLabel(self, text="Media URL:", font=("Arial", 14, "bold")).grid(
            row=0, column=0, padx=20, pady=(20, 5), sticky="w"
        )
        self.url_entry = ctk.CTkEntry(
            self,
            placeholder_text="Paste YouTube, X, Instagram, TikTok, Reddit … link here",
        )
        self.url_entry.grid(row=0, column=1, padx=(0, 20), pady=(20, 5), sticky="ew")

        # ── Row 1: Download Mode ───────────────────────────────────────────
        ctk.CTkLabel(self, text="Mode:").grid(row=1, column=0, padx=20, pady=5, sticky="w")
        self.mode_var = ctk.StringVar(value=config.get("downloads", "default_mode") or "Best Video + Best Audio")
        self.mode_combo = ctk.CTkOptionMenu(
            self,
            variable=self.mode_var,
            values=[
                "Best Video + Best Audio",
                "Best Video Only",
                "Best Audio Only",
                "MP3 Conversion",
                "Thumbnail only",
                "Subtitle only",
            ],
        )
        self.mode_combo.grid(row=1, column=1, padx=(0, 20), pady=5, sticky="w")

        # ── Row 2: Quality ─────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Quality:").grid(row=2, column=0, padx=20, pady=5, sticky="w")
        self.quality_var = ctk.StringVar(value=config.get("downloads", "default_quality") or "Best Available")
        self.quality_combo = ctk.CTkOptionMenu(
            self,
            variable=self.quality_var,
            values=["Best Available", "4K", "1440p", "1080p", "720p", "480p", "360p"],
        )
        self.quality_combo.grid(row=2, column=1, padx=(0, 20), pady=5, sticky="w")

        # ── Row 3: Output Format ───────────────────────────────────────────
        ctk.CTkLabel(self, text="Format:").grid(row=3, column=0, padx=20, pady=5, sticky="w")
        self.format_var = ctk.StringVar(value=config.get("downloads", "default_format") or "MP4")
        self.format_combo = ctk.CTkOptionMenu(
            self,
            variable=self.format_var,
            values=["MP4", "MKV", "WEBM", "MP3", "M4A", "FLAC", "WAV"],
        )
        self.format_combo.grid(row=3, column=1, padx=(0, 20), pady=5, sticky="w")

        # ── Row 4: Cookies / Auth ──────────────────────────────────────────
        ctk.CTkLabel(self, text="Authentication:").grid(row=4, column=0, padx=20, pady=5, sticky="w")
        self.cookie_var = ctk.StringVar(value=config.get("cookies", "use_browser") or "None")
        self.cookie_combo = ctk.CTkOptionMenu(
            self,
            variable=self.cookie_var,
            values=["None", "Chrome", "Firefox", "Edge", "Brave", "File"],
            command=self.on_cookie_change,
        )
        self.cookie_combo.grid(row=4, column=1, padx=(0, 20), pady=5, sticky="w")

        # Cookie-file picker (only shown when mode == "File")
        self.cookie_label = ctk.CTkLabel(self, text="", text_color="gray", font=("Arial", 11))
        self.cookie_label.grid(row=5, column=1, padx=(0, 20), pady=(0, 5), sticky="w")

        self.cookie_btn = ctk.CTkButton(
            self, text="Select cookies.txt", width=140, command=self.select_cookie_file
        )
        self.cookie_btn.grid(row=5, column=0, columnspan=2, padx=20, pady=(0, 5), sticky="w")
        if self.cookie_var.get() != "File":
            self.cookie_btn.grid_remove()
            self.cookie_label.grid_remove()

        # ── Row 6: Download Button ─────────────────────────────────────────
        self.download_btn = ctk.CTkButton(
            self,
            text="⬇  Download",
            font=("Arial", 16, "bold"),
            height=50,
            command=self.start_download,
        )
        self.download_btn.grid(row=6, column=0, columnspan=2, padx=20, pady=(30, 20), sticky="ew")

        # ── Row 7: Status / error label ────────────────────────────────────
        self.status_label = ctk.CTkLabel(self, text="", font=("Arial", 12))
        self.status_label.grid(row=7, column=0, columnspan=2, padx=20, pady=5, sticky="w")

    # ------------------------------------------------------------------ helpers
    def on_cookie_change(self, choice: str):
        if choice == "File":
            self.cookie_btn.grid()
            self.cookie_label.grid()
        else:
            self.cookie_btn.grid_remove()
            self.cookie_label.grid_remove()

    def select_cookie_file(self):
        file = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt"), ("All files", "*.*")])
        if file:
            self.cookie_file = file
            config.set("cookies", "cookie_file", file)
            self.cookie_label.configure(text=f"📄 {file}")

    def _show_status(self, msg: str, color: str = "gray"):
        self.status_label.configure(text=msg, text_color=color)

    # ------------------------------------------------------------------ download
    def start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            self._show_status("⚠  Please enter a URL first.", color="#FFA726")
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            self._show_status("⚠  URL must start with http:// or https://", color="#FFA726")
            return

        mode = self.mode_var.get()
        quality = self.quality_var.get()
        fmt = self.format_var.get()
        cookie_mode = self.cookie_var.get()
        folder = config.get("general", "download_folder") or ""
        template = config.get("naming", "template") or "%(title)s.%(ext)s"

        opts = downloader.build_ydl_opts(
            url, mode, quality, fmt,
            cookie_mode, self.cookie_file,
            template, folder,
        )

        # Build the task (start() is called AFTER callbacks are attached)
        task = downloader.start_download(
            url=url,
            ydl_opts=opts,
            progress_cb=None,   # set below
            complete_cb=None,
            error_cb=None,
        )

        # Switch to queue tab and create the progress row
        self.app.show_tab("queue")
        row = self.app.queue_tab.add_download(task)

        # Wire callbacks (must happen before task.start())
        task.progress_callback = lambda d: self.app.after(0, row.update_progress, d)

        def on_complete(info):
            self.app.after(0, row.mark_completed)
            self.app.after(0, self.app.history_tab.load_history)

        def on_error(err: str):
            self.app.after(0, row.mark_error, err)
            self.app.after(0, self.app.history_tab.load_history)

        task.completion_callback = on_complete
        task.error_callback = on_error

        # Now it is safe to start the thread
        task.start()

        self.url_entry.delete(0, "end")
        self._show_status(f"▶  Queued: {url[:60]}…" if len(url) > 60 else f"▶  Queued: {url}", color="#4CAF50")
