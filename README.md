<div align="center">

# 🎬 Media Downloader

**Download videos, audio, and more from hundreds of websites — no command line needed.**

[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows)](https://github.com/Ayushman-00/Media-Downloader/releases)
[![Powered by yt-dlp](https://img.shields.io/badge/Powered%20by-yt--dlp-red?logo=youtube&logoColor=white)](https://github.com/yt-dlp/yt-dlp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## ⬇️ Download

**[→ Download the latest MediaDownloader.exe from Releases](https://github.com/Ayushman-00/Media-Downloader/releases)**

No installation required. Just download and run.

---

## 🌐 Supported Sites

YouTube · Instagram · X (Twitter) · Reddit · TikTok · Facebook · Vimeo · Twitch · and **1000+ more**

---

## 🚀 Getting Started

### 1. Install FFmpeg (Required)

FFmpeg is needed to merge video and audio, and to convert formats (MP3, MP4, etc.).

1. Download FFmpeg from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html) → Windows builds
2. Extract the zip and place `ffmpeg.exe` in the **same folder as `MediaDownloader.exe`**
3. That's it — no PATH setup needed

> ⚠️ Without FFmpeg, downloads will still work but video+audio merging and MP3 conversion will fail.

### 2. Run the App

Double-click **`MediaDownloader.exe`** — the app will open directly, no console window.

---

## 📖 How to Use

### Basic Download
1. Copy a video/audio URL from any supported site
2. Paste it into the **URL field** on the Dashboard
3. Choose your **Mode**, **Quality**, and **Format**
4. Click **⬇ Download**
5. The app switches to the **Queue** tab and shows live progress

### Download Modes

| Mode | What it does |
|---|---|
| Best Video + Best Audio | Downloads and merges the highest quality video and audio |
| Best Video Only | Video stream only, no audio |
| Best Audio Only | Audio stream only |
| MP3 Conversion | Downloads audio and converts to MP3 |
| Thumbnail only | Saves the video thumbnail as an image |
| Subtitle only | Downloads subtitles/captions |

### Quality Options
`Best Available` · `4K` · `1440p` · `1080p` · `720p` · `480p` · `360p`

> If your selected quality isn't available, the app automatically falls back to the next best option.

### Output Formats
`MP4` · `MKV` · `WEBM` · `MP3` · `M4A` · `FLAC` · `WAV`

---

## 🍪 Private / Age-Restricted / Login-Required Videos

Go to the **Authentication** dropdown on the Dashboard:

| Option | When to use |
|---|---|
| **None** | Public YouTube, Reddit, free content |
| **Chrome / Firefox / Edge / Brave** | Uses cookies from your logged-in browser |
| **Cookie File** | Browse for a `cookies.txt` file exported from your browser |

---

## ⚙️ Settings

Click **Settings** in the sidebar to configure:

- **Download Folder** — where files are saved (default: `Downloads`)
- **Theme** — Dark · Light · System
- **Concurrent Downloads** — 1 to 10 simultaneous fragment downloads (default: 3)
- **Retry Count** — how many times to retry on network failure

---

## 📋 History

The **History** tab keeps a log of every download including date, site, status, and file size. You can delete individual entries or clear all history.

---

## 🐛 Troubleshooting

| Problem | Fix |
|---|---|
| Nothing downloads / merge fails | Install FFmpeg and place it next to the `.exe` |
| Age-restricted video fails | Use Browser Cookies in the Authentication dropdown |
| Private / login-required video fails | Export `cookies.txt` from your browser and select it |
| App doesn't open | Right-click → **Run as administrator** |
| Download stuck at 0% | Check your internet connection; try again |

**Logs** are saved automatically next to the `.exe` in `logs/error.log` — check this file if something goes wrong.

---

## ❓ FAQ

**Does this store my data or send anything online?**
No. Everything runs locally. No accounts, no telemetry, no cloud.

**Can I download playlists?**
Yes — paste a playlist URL and it will download all available videos.

**Where are my downloaded files?**
In your `Downloads` folder by default. You can change this in Settings.

**Can I use this on Mac or Linux?**
The `.exe` is Windows-only. Mac/Linux users can run from source — see below.

---

## 🛠️ Running from Source (Developers)

```bash
git clone https://github.com/Ayushman-00/Media-Downloader.git
cd Media-Downloader
pip install -r requirements.txt
python main.py
```

---

## 📄 License

[MIT License](LICENSE) — free to use, modify, and distribute.

---

<div align="center">

**Built with Python 

[⭐ Star this repo](https://github.com/Ayushman-00/Media-Downloader) if you find it useful!

</div>
