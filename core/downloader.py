import threading
import yt_dlp
import traceback
import os
from core.config import config
from core.history import history_db

# Map display quality labels to max-height values for yt-dlp format strings
QUALITY_MAP = {
    "Best Available": None,
    "4K": "2160",
    "1440p": "1440",
    "1080p": "1080",
    "720p": "720",
    "480p": "480",
    "360p": "360",
}

# Map display browser names to yt-dlp cookiesfrombrowser keys
BROWSER_MAP = {
    "Chrome": "chrome",
    "Firefox": "firefox",
    "Edge": "edge",
    "Brave": "brave",
}

def download_video_sync(url: str, ydl_opts: dict) -> tuple[str, dict]:
    """Synchronously downloads a video using yt_dlp and returns the downloaded filepath and info dict."""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info and "entries" in info:
            info = info["entries"][0] if info["entries"] else info

        downloads = info.get("requested_downloads", [])
        if downloads:
            video_path = downloads[0]["filepath"]
        else:
            video_path = ydl.prepare_filename(info)
            if not os.path.exists(video_path):
                base = os.path.splitext(video_path)[0]
                video_path = base + ".mp4"
                
    return video_path, info

def download_for_shorts(url: str, output_dir: str, fmt: str = "bestvideo[height<=1080]+bestaudio/best") -> tuple[str, dict]:
    """Specific wrapper for the Shorts automation pipeline."""
    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, "%(title).200s [%(id)s].%(ext)s")
    outtmpl = outtmpl.replace("\\", "/")
    
    ydl_opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "writesubtitles": True,
        "subtitleslangs": ["en", "en-orig"],
        "writeinfojson": True,
        "quiet": False,
        "no_warnings": False,
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
        ],
    }
    
    video_path, info = download_video_sync(url, ydl_opts)
    
    slim_info = {
        "id": info.get("id", ""),
        "title": info.get("title", ""),
        "duration": info.get("duration", 0),
        "uploader": info.get("uploader", ""),
        "webpage_url": info.get("webpage_url", url),
    }
    print(f"[downloader] saved: {video_path}", flush=True)
    return video_path, slim_info


class DownloadTask:
    def __init__(self, url, options,
                 progress_callback=None,
                 completion_callback=None,
                 error_callback=None):
        self.url = url
        self.options = options
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback
        self.error_callback = error_callback
        self.is_cancelled = False
        self.thread = None
        self.history_id = None

    # ------------------------------------------------------------------ hooks
    def _hook(self, d):
        """Called by yt-dlp from the download thread."""
        if self.is_cancelled:
            raise Exception("Download cancelled by user")
        if self.progress_callback:
            try:
                self.progress_callback(d)
            except Exception:
                pass  # Never let UI errors kill the download thread

    # ------------------------------------------------------------------ run
    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        # Basic platform detection
        url_l = self.url.lower()
        if "youtube.com" in url_l or "youtu.be" in url_l:
            platform = "YouTube"
        elif "instagram.com" in url_l:
            platform = "Instagram"
        elif "twitter.com" in url_l or "x.com" in url_l:
            platform = "X (Twitter)"
        elif "reddit.com" in url_l or "redd.it" in url_l:
            platform = "Reddit"
        elif "tiktok.com" in url_l:
            platform = "TikTok"
        elif "facebook.com" in url_l or "fb.watch" in url_l:
            platform = "Facebook"
        elif "vimeo.com" in url_l:
            platform = "Vimeo"
        elif "twitch.tv" in url_l:
            platform = "Twitch"
        else:
            platform = "Unknown"

        out_location = self.options.get("outtmpl", "Unknown")
        if isinstance(out_location, dict):          # yt-dlp accepts dict form
            out_location = out_location.get("default", "Unknown")

        self.history_id = history_db.add_entry(
            url=self.url,
            platform=platform,
            output_location=out_location,
            status="Downloading…"
        )

        try:
            ydl_opts = dict(self.options)           # shallow copy
            ydl_opts["progress_hooks"] = [self._hook]

            video_path, info = download_video_sync(self.url, ydl_opts)

            file_size = 0
            if info:
                file_size = (
                    info.get("filesize_approx")
                    or info.get("filesize")
                    or 0
                )

            history_db.update_entry(
                self.history_id, status="Completed", file_size=file_size
            )

            if self.completion_callback:
                self.completion_callback(info)

        except Exception as e:
            if self.is_cancelled or "cancelled by user" in str(e).lower():
                history_db.update_entry(self.history_id, status="Cancelled")
                if self.error_callback:
                    self.error_callback("Cancelled")
            else:
                err_text = f"{e}\n\n{traceback.format_exc()}"
                history_db.update_entry(self.history_id, status="Failed")
                if self.error_callback:
                    self.error_callback(err_text)

    def cancel(self):
        self.is_cancelled = True


class Downloader:
    def __init__(self):
        self.active_tasks: list[DownloadTask] = []

    def build_ydl_opts(
        self,
        url: str,
        mode: str,
        quality: str,
        output_format: str,
        cookies_mode: str,
        cookies_file: str,
        naming_template: str,
        output_folder: str,
    ) -> dict:
        # Use forward-slash paths so yt-dlp handles them cross-platform
        outtmpl = output_folder.replace("\\", "/").rstrip("/") + "/" + naming_template

        opts: dict = {
            "outtmpl": outtmpl,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "retries": config.get("network", "retry_count") or 5,
            "concurrent_fragment_downloads": min(
                int(config.get("network", "concurrent_downloads") or 3),
                int(config.get("network", "max_concurrent_downloads") or 10),
            ),
        }

        # ---- Cookies -------------------------------------------------------
        if cookies_mode in BROWSER_MAP:
            # yt-dlp expects (browser_name,) or (browser_name, profile, keyring, container)
            opts["cookiesfrombrowser"] = (BROWSER_MAP[cookies_mode],)
        elif cookies_mode == "File" and cookies_file:
            opts["cookiefile"] = cookies_file

        # ---- Format / Quality ----------------------------------------------
        res = QUALITY_MAP.get(quality)  # None means "Best Available"

        if mode == "Best Video + Best Audio":
            if res is None:
                opts["format"] = "bestvideo+bestaudio/best"
            else:
                opts["format"] = (
                    f"bestvideo[height<={res}]+bestaudio/"
                    f"best[height<={res}]"
                )
            fmt = output_format.lower()
            if fmt in ("mp4", "mkv", "webm"):
                opts["merge_output_format"] = fmt

        elif mode == "Best Video Only":
            if res is None:
                opts["format"] = "bestvideo"
            else:
                opts["format"] = f"bestvideo[height<={res}]"

        elif mode == "Best Audio Only":
            opts["format"] = "bestaudio/best"

        elif mode == "MP3 Conversion":
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]

        elif mode == "Thumbnail only":
            opts["skip_download"] = True
            opts["writethumbnail"] = True

        elif mode == "Subtitle only":
            opts["skip_download"] = True
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True

        return opts

    def start_download(
        self,
        url: str,
        ydl_opts: dict,
        progress_cb,
        complete_cb,
        error_cb,
    ) -> DownloadTask:
        task = DownloadTask(
            url, ydl_opts,
            progress_callback=progress_cb,
            completion_callback=complete_cb,
            error_callback=error_cb,
        )
        self.active_tasks.append(task)
        # NOTE: start() is called by the caller AFTER setting callbacks
        return task

    def cancel_all(self):
        for t in self.active_tasks:
            t.cancel()


downloader = Downloader()
