<div align="center">

# 🎬 Media Downloader & YT Shorts Automation Suite

**All-in-one desktop application for downloading media from 1000+ sites AND automated AI-powered YouTube Shorts creation.**

[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows)](https://github.com/Ayushman-00/Media-Downloader/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 🌟 Features Overview

- ⬇️ **Universal Media Downloader**: Download high-quality video and audio from 1000+ sites (YouTube, Instagram, X/Twitter, Reddit, TikTok, Facebook, Vimeo, Twitch, etc.).
- 🎬 **Integrated YouTube Shorts Wizard**: Turn long videos into 9:16 vertical Shorts directly inside the app GUI in 6 simple steps.
- 🤖 **AI Highlight Detection & Captions**: Automatic transcript extraction (Cloud APIs, WebVTT, or Whisper fallback) + LLM scoring (Groq, Ollama, or heuristic) to find viral moments.
- 🎵 **Royalty-Free Audio & Subtitles**: Mix custom background music from `/music` with automatic audio ducking and burn formatted `.ass` subtitles.
- 🚀 **Automated YouTube Uploading**: Direct YouTube Data API v3 integration to schedule and publish Shorts to your channel.
- 🍪 **Advanced Authentication**: Bypass login/age restrictions using browser cookies (Chrome, Firefox, Edge, Brave, or `cookies.txt`).

---

## 🚀 Getting Started

### 1. Requirements

- **Windows 10/11**
- **Python 3.10+** (if running from source)
- **FFmpeg** (Required for merging video/audio, clipping, and burning subtitles)
  1. Download FFmpeg from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
  2. Place `ffmpeg.exe` in the same directory as the app (or ensure it is added to your system `PATH`).

---

## 💻 Running the Desktop App

```bash
# Clone the repository
git clone https://github.com/Ayushman-00/Media-Downloader.git
cd Media-Downloader

# Install dependencies
pip install -r requirements.txt

# Launch the desktop GUI
python main.py
```

---

## 📖 How to Use

### 1️⃣ Universal Downloader
1. Copy a media URL from any supported website.
2. Paste it into the **URL field** on the **Dashboard**.
3. Select your **Mode** (`Best Video + Best Audio`, `MP3 Conversion`, `Thumbnail only`, etc.), **Quality** (`4K` down to `360p`), and **Format**.
4. Click **⬇ Download** — track live progress under the **Queue** tab.

### 2️⃣ YouTube Shorts Creator Wizard
Switch to the **Shorts** tab in the sidebar:
- **Step 1 (Download)**: Paste a YouTube URL, check rights, and download.
- **Step 2 (Analyze)**: Auto-extract transcripts and find the best 45-second viral window using AI scoring.
- **Step 3 (Adjust)**: Fine-tune clip start/end timestamps with live transcript preview.
- **Step 4 (Music & Captions)**: Pick a background track from `yt_shorts_automation/music`, adjust volume, and enable burned-in subtitles.
- **Step 5 (Build)**: Auto-crop to 9:16 vertical video, render audio, and burn `.ass` captions via FFmpeg.
- **Step 6 (Upload)**: Set Title, Description, Tags, Privacy, and schedule automatic publishing to YouTube!

---

## 🔑 YouTube API Setup (for Uploading Shorts)

To upload Shorts directly from the app or CLI:
1. Go to [Google Cloud Console](https://console.cloud.google.com) and create a project.
2. Enable the **YouTube Data API v3**.
3. Go to **Credentials** → Create **OAuth 2.0 Client ID** (Application type: **Desktop app**).
4. Download the JSON credential file and save it as:
   `yt_shorts_automation/credentials/client_secret.json`
5. On your first upload, a browser popup will ask for one-time YouTube account authorization (`token.json` will be saved locally for auto-refreshes).

---

## 🤖 AI Transcripts & Scoring Options

The pipeline supports both **free cloud APIs** and **100% local models**:

- **Captions / Transcripts**:
  - `youtube-transcript-api` (Free, instant)
  - Groq Whisper Large v3 (`GROQ_API_KEY` in `.env`)
  - Local `faster-whisper`
- **Highlight Scoring**:
  - Groq LLM (`llama-3.3-70b-versatile` / `gemini-2.5-flash`)
  - Local Ollama LLM (`ollama pull llama3.1:8b`)
  - Sound energy + speech density heuristic scorer

Configure your preferences in `yt_shorts_automation/config/config.yaml` or `.env`.

---

## 🛠️ CLI & Standalone Automation

For headless servers, cron jobs, or batch processing, you can also run the automation module via CLI or standalone Streamlit dashboard:

```bash
# Run via CLI with a job JSON file
python yt_shorts_automation/main.py --job yt_shorts_automation/config/job_template.json

# Run standalone Web UI (Streamlit)
streamlit run yt_shorts_automation/dashboard.py
```

---

## ⚙️ App Settings & Configuration

- **Download Folder**: Custom path for saved downloads (default: `Downloads`).
- **Theme**: Switch between Dark, Light, and System themes.
- **Network Settings**: Configure concurrent downloads (1–10) and retry attempts.
- **History**: View, filter, or clear download logs anytime.

---

## ⚖️ License & Legal Disclaimer

Distributed under the [MIT License](LICENSE).

> ⚠️ **Legal Notice**: Ensure you own or have explicit rights/licenses to any content you download or re-upload. Respect YouTube ToS and copyright guidelines.

---

<div align="center">

**Built with Python · CustomTkinter · yt-dlp · FFmpeg**

[⭐ Star this repository](https://github.com/Ayushman-00/Media-Downloader) if you find it useful!

</div>
