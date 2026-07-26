<div align="center">

# 🎬 Media Downloader & YT Shorts Automation Suite

**An all-in-one desktop suite and AI-powered pipeline for downloading media from 1000+ sites and converting long videos into vertical YouTube Shorts.**

[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-0078D6?logo=windows)](https://github.com/Ayushman-00/Media-Downloader)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Framework](https://img.shields.io/badge/GUI-CustomTkinter-blue)](https://github.com/TomSchimansky/CustomTkinter)

---

### 🚀 **Three Ways to Run**
**1. Desktop App (CustomTkinter GUI)** • **2. Web Dashboard (Streamlit)** • **3. Headless CLI & Watcher**

</div>

---

## 📖 Table of Contents

- [🌟 Key Features](#-key-features)
- [📁 Project Structure](#-project-structure)
- [💻 Prerequisites & System Requirements](#-prerequisites--system-requirements)
- [⚙️ Installation & Setup](#%EF%B8%8F-installation--setup)
- [🔑 Credentials & API Setup](#-credentials--api-setup)
- [🚀 Quick Start & Usage](#-quick-start--usage)
  - [1. Desktop GUI App (`python main.py`)](#1-desktop-gui-app-python-mainpy)
  - [2. YouTube Shorts Wizard (6-Step Flow)](#2-youtube-shorts-wizard-6-step-flow)
  - [3. Standalone Web UI (`streamlit`)](#3-standalone-web-ui-streamlit)
  - [4. Headless CLI & Automated Watcher](#4-headless-cli--automated-watcher)
- [⚙️ Configuration Reference](#%EF%B8%8F-configuration-reference)
- [⚖️ License & Legal Notice](#%EF%B8%8F-license--legal-notice)

---

## 🌟 Key Features

### ⬇️ 1. Universal Media Downloader
- **1000+ Supported Sites**: Download video/audio from YouTube, Instagram, X/Twitter, TikTok, Facebook, Reddit, Twitch, Vimeo, and more via `yt-dlp`.
- **Quality & Format Controls**: Select resolutions from **4K down to 360p**, extract audio as **MP3**, or download thumbnails directly.
- **Bypass Login & Age Restrictions**: Export and load browser cookies (Chrome, Firefox, Edge, Brave, or custom `cookies.txt`) for restricted videos.
- **Queue & History Management**: Live download progress, concurrent task queuing, error retries, and searchable download history.

### 🎬 2. AI-Powered YouTube Shorts Creator
- **6-Step Interactive GUI Wizard**: Complete end-to-end workflow built directly inside the desktop app.
- **Smart Highlight Detection**:
  - Cloud LLM scoring via **Groq** (`llama-3.3-70b-versatile` / `gemini-2.5-flash`).
  - 100% free local scoring via **Ollama** (`llama3.1:8b`).
  - Audio speech density & energy heuristic fallback.
- **Flexible Transcripts & Captions**:
  - Instant transcript retrieval using `youtube-transcript-api` or WebVTT captions.
  - Automatic fallback to **Groq Whisper** or **Local Whisper** (`faster-whisper`).
  - Formatted burned `.ass` subtitle rendering.
- **Background Music & Audio Mixing**: Select royalty-free tracks from `/music`, adjust background music levels, and apply original audio ducking.
- **Smart 9:16 Vertical Cropping**: Automatic center-cropping or face/object detection using FFmpeg and OpenCV.
- **Automated YouTube API Publishing**: Direct YouTube Data API v3 integration with ISO 8601 release scheduling.

---

## 📁 Project Structure

```
Media-Downloader/
├── main.py                        # Desktop application entry point (CustomTkinter)
├── requirements.txt               # Main application dependencies
├── settings.json                  # Application settings (theme, paths, concurrency)
├── history.json                   # Download history log
│
├── core/                          # Core downloading & configuration engines
│   ├── config.py                  # App configuration manager
│   ├── downloader.py              # yt-dlp download wrapper & progress tracker
│   ├── history.py                 # Persistent download history manager
│   ├── logger.py                  # Application logging
│   └── paths.py                   # Path resolution utilities
│
├── ui/                            # CustomTkinter GUI components & views
│   ├── app.py                     # Main window & navigation sidebar
│   ├── components/                # Reusable UI widgets
│   └── tabs/                      # Application tab views
│       ├── dashboard.py           # Universal Downloader view
│       ├── shorts_tab.py          # 6-step YouTube Shorts creation wizard
│       ├── queue.py               # Download queue manager
│       ├── history_tab.py         # Download history viewer
│       └── settings_tab.py        # Settings & preferences tab
│
└── yt_shorts_automation/          # Standalone & CLI Shorts processing engine
    ├── main.py                    # Headless CLI entry point & watcher
    ├── dashboard.py               # Standalone Web UI (Streamlit)
    ├── requirements.txt           # Pipeline specific dependencies
    ├── .env.example               # Environment template (API keys)
    │
    ├── config/                    # Pipeline configuration & job templates
    │   ├── config.yaml            # Pipeline settings (Whisper, Groq, Ollama, FFmpeg)
    │   └── job_template.json      # Job schema for automated pipeline execution
    │
    ├── src/                       # Modular pipeline stages
    │   ├── downloader.py          # Video fetcher stage
    │   ├── transcript.py          # Transcript & subtitle extraction
    │   ├── highlight_finder.py    # AI & heuristic moment scoring
    │   ├── clipper.py             # FFmpeg 9:16 vertical crop & trim
    │   ├── music_selector.py      # Background audio mixing & ducking
    │   ├── captioner.py           # ASS subtitle burning engine
    │   ├── uploader.py            # YouTube Data API v3 uploader & scheduler
    │   └── pipeline.py            # End-to-end stage orchestrator
    │
    ├── music/                     # Drop royalty-free .mp3/.wav files here
    ├── downloads/                 # Downloaded source videos storage
    ├── output/                    # Pipeline outputs (clips, final shorts, run logs)
    └── credentials/               # OAuth credentials (client_secret.json, token.json)
```

---

## 💻 Prerequisites & System Requirements

- **Operating System**: Windows 10/11, macOS, or Linux.
- **Python**: Version **3.10+** (64-bit recommended).
- **FFmpeg**: Required for audio/video merging, clipping, music mixing, and subtitle burning.
  - **Windows**: `winget install ffmpeg` (or download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH).
  - **macOS**: `brew install ffmpeg`
  - **Linux**: `sudo apt install ffmpeg`

---

## ⚙️ Installation & Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/Ayushman-00/Media-Downloader.git
   cd Media-Downloader
   ```

2. **Create a Virtual Environment**:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   # Install desktop app requirements
   pip install -r requirements.txt

   # Install YouTube Shorts automation requirements
   pip install -r yt_shorts_automation/requirements.txt
   ```

---

## 🔑 Credentials & API Setup

### 1. YouTube Data API v3 (For Direct Uploading)
To schedule and upload Shorts directly to YouTube from the GUI, Web UI, or CLI:
1. Open the [Google Cloud Console](https://console.cloud.google.com) and create a project.
2. Enable the **YouTube Data API v3**.
3. Go to **Credentials** → **Create Credentials** → **OAuth Client ID**.
4. Select **Desktop Application** as the application type.
5. Download the JSON file and save it to:
   ```
   yt_shorts_automation/credentials/client_secret.json
   ```
6. Upon your first upload attempt, a browser window will open requesting one-time authorization. The authentication token will be cached at `credentials/token.json` for seamless background refreshes.

### 2. AI Transcripts & Highlight Scoring Keys
Copy `yt_shorts_automation/.env.example` to `.env`:
```bash
cp yt_shorts_automation/.env.example yt_shorts_automation/.env
```

- **Groq Cloud API** (Recommended for instant transcript + fast scoring):
  Add your API key inside `yt_shorts_automation/.env`:
  ```env
  GROQ_API_KEY="gsk_your_groq_api_key_here"
  ```
- **Local Ollama LLM** (Free local scoring):
  Install [Ollama](https://ollama.com) and pull a model:
  ```bash
  ollama pull llama3.1:8b
  ```
  Set `highlight.method: ollama` in `yt_shorts_automation/config/config.yaml`.

### 3. Background Music
Place your royalty-free `.mp3` or `.wav` tracks into `yt_shorts_automation/music/`. They will automatically appear in the GUI dropdown and CLI music selector.

---

## 🚀 Quick Start & Usage

### 1. Desktop GUI App (`python main.py`)
Launch the primary desktop app containing both the **Universal Downloader** and the **Shorts Wizard**:
```bash
python main.py
```

### 2. YouTube Shorts Wizard (6-Step Flow)
Inside the desktop app, click on the **Shorts** tab on the left sidebar:

| Step | Action | Description |
|---|---|---|
| **Step 1: Download** | Input YouTube URL | Paste URL, confirm content rights, and fetch high-res source video. |
| **Step 2: Analyze** | AI Moment Finder | Extract transcript & run LLM/heuristic scoring to find top viral moments. |
| **Step 3: Adjust** | Timestamp Trimming | Fine-tune start/end trim points (e.g. 30-60s) with live transcript preview. |
| **Step 4: Music & Subtitles** | Audio & Captions | Select track from `/music`, adjust volume/ducking, enable ASS subtitles. |
| **Step 5: Build** | FFmpeg Rendering | Render 9:16 vertical crop, merge audio track, and burn subtitles. |
| **Step 6: Upload** | YouTube Publisher | Fill title, description, tags, privacy mode, and schedule automatic publishing. |

---

### 3. Standalone Web UI (`streamlit`)
If you prefer a browser-based dashboard interface:
```bash
streamlit run yt_shorts_automation/dashboard.py
```
Access the interactive web UI at `http://localhost:8501`.

---

### 4. Headless CLI & Automated Watcher
For headless servers, background cron jobs, or batch rendering:

#### Run a Single Job File
Create a job JSON file based on `yt_shorts_automation/config/job_template.json`:
```json
{
  "source_url": "https://www.youtube.com/watch?v=EXAMPLE",
  "segment_length_sec": 45,
  "music_file": "upbeat_lofi.mp3",
  "music_volume": 0.20,
  "captions": true,
  "title": "Unbelievable Moment! 😳 #Shorts",
  "description": "Watch full clip here. #Shorts",
  "privacy_status": "private",
  "schedule_time_utc": "2026-08-01T14:00:00Z"
}
```

Run the pipeline execution:
```bash
python yt_shorts_automation/main.py --job yt_shorts_automation/config/job_template.json
```

#### Run Specific Pipeline Stages
```bash
python yt_shorts_automation/main.py --job config/jobs/my_job.json --only download
python yt_shorts_automation/main.py --job config/jobs/my_job.json --only highlight
python yt_shorts_automation/main.py --job config/jobs/my_job.json --only clip
python yt_shorts_automation/main.py --job config/jobs/my_job.json --only music
python yt_shorts_automation/main.py --job config/jobs/my_job.json --only caption
python yt_shorts_automation/main.py --job config/jobs/my_job.json --only upload
```

#### Automated Job Folder Watcher
Watch a folder for incoming job files continuously:
```bash
python yt_shorts_automation/main.py --watch yt_shorts_automation/config/jobs/
```

---

## ⚙️ Configuration Reference

### Pipeline Settings (`yt_shorts_automation/config/config.yaml`)

```yaml
downloader:
  format: "bestvideo[height<=1080]+bestaudio/best"

transcript:
  prefer_youtube_captions: true
  use_youtube_transcript_api: true
  groq_whisper_fallback: true
  whisper_fallback: true
  whisper_model: base

highlight:
  window_sec: 45
  method: groq   # Options: groq | ollama | heuristic | hybrid
  top_candidates: 5

video:
  target_width: 1080
  target_height: 1920
  fps: 30

music:
  default_volume: 0.15
  duck_original: true

captions:
  enabled: true
  font: "Arial"
  font_size: 48
  position: "bottom"
```

---

## ⚖️ License & Legal Notice

Distributed under the **MIT License**. See `LICENSE` for details.

> ⚠️ **Disclaimer**: Please ensure you own or hold appropriate rights, licenses, or permissions before downloading, editing, or re-uploading content from external platforms. Always respect YouTube Terms of Service, copyright laws, and music licensing guidelines.

---

<div align="center">

**Built with Python • CustomTkinter • Streamlit • yt-dlp • FFmpeg • Groq • Whisper**

[⭐ Star on GitHub](https://github.com/Ayushman-00/Media-Downloader)

</div>
