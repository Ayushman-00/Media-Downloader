---
name: yt-shorts-automation
description: End-to-end local automated pipeline that transforms long videos (YouTube URLs or local MP4 files) into 9:16 vertical Shorts with custom background music from /music, burned .ass captions, and automated upload/scheduling via YouTube Data API v3.
---

# YT Shorts Automation Skill

## 1. Skill Metadata & Overview
- **Name:** `yt-shorts-automation`
- **Description:** End-to-end local automated pipeline that transforms long videos (YouTube URLs or local MP4 files) into 9:16 vertical Shorts with custom background music from `/music`, burned `.ass` captions, and automated upload/scheduling via YouTube Data API v3.
- **Ecosystem Sync:** This tool functions within the `Media Downloader` suite and can seamlessly reuse an external Media Downloader `.exe` binary (`use_external_exe: true` in `config/config.yaml`) or run natively via `yt-dlp`.

## 2. Execution Interfaces & Triggers

**When to trigger this skill:**
- "Download and make a short from this YouTube URL"
- "Process this MP4 with Media Downloader"
- "Launch Streamlit GUI dashboard"

**Execution Entry Points:**
1. **Interactive Streamlit GUI Dashboard:** `streamlit run dashboard.py` (provides UI for link input, video sliders, music selector, subtitle toggles, and one-click YouTube posting).
2. **CLI Job Pipeline:** `python main.py --job config/jobs/<job>.json` (supports individual stage execution via `--only [download|highlight|clip|music|caption|upload]`).
3. **Automated Batch Watcher:** `python main.py --watch config/jobs/` (processes pending job JSONs unattended).

## 3. Modular 7-Stage Pipeline
The pipeline consists of 7 modular stages, each powered by a corresponding `src/` module:

- **Download (`src/downloader.py`):** Downloads via `yt-dlp` or external Media Downloader binary into `downloads/`.
- **Transcript (`src/transcript.py`):** Fetches captions via `youtube-transcript-api` (fast/free), falls back to Groq Cloud Whisper API, then local `openai-whisper` / `faster-whisper`.
- **Highlight Finder (`src/highlight_finder.py`):** Scores segment windows via heuristics; optionally picks top candidate via cloud Groq Llama 3.3 70B or local `Ollama` (`llama3.1:8b`).
- **Clipper (`src/clipper.py`):** Uses FFmpeg for 9:16 vertical center-cropping (1080x1920).
- **Music Mixer (`src/music_selector.py`):** Mixes audio tracks from `/music` with configurable volume and original audio ducking.
- **Subtitle Burner (`src/captioner.py`):** Builds `.ass` subtitle files and burns them into the final clip.
- **Publisher (`src/uploader.py`):** Handles Google Cloud OAuth2 authentication (`credentials/client_secret.json`) to upload and schedule videos on YouTube.

## 4. Local System Requirements & Fail-Safes

**Mandatory Local Dependencies:**
- Python 3.10+
- FFmpeg (must be on system PATH)
- YouTube OAuth secret (placed in `credentials/client_secret.json`)
- Local music files (.mp3/.wav, etc.) in the `music/` directory
- `GROQ_API_KEY` in `.env` (optional, for free cloud transcription/scoring)

**Failure Modes and Resolution Steps:**
- **FFmpeg path issues:** Ensure FFmpeg is installed and properly added to the environment variables/PATH, or placed next to the executable if running compiled.
- **Missing audio tracks in `music/`:** The pipeline will fail or skip the music mixing stage. Ensure valid audio files exist in the `/music` folder before running the mixer.
- **Whisper transcript fallbacks:** If YouTube captions and Groq API fail (or API key is missing), ensure `faster-whisper` and its dependencies (like PyTorch) are correctly installed for local transcription fallback.
- **OAuth token refresh handling:** If upload fails due to an expired token, delete `credentials/token.json` and re-authenticate via the interactive browser prompt to generate a new token.
