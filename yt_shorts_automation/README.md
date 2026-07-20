# YT Shorts Automation Pipeline

End-to-end pipeline: Download → Find best segment → Clip to vertical Short →
Add your own royalty-free music → Burn captions → Upload to YouTube on a schedule.

Every stage is a standalone script in `src/`, chained together by `main.py`.
You can also run any stage individually for testing/debugging.

---

## 1. Folder structure

```
yt_shorts_automation/
├── config/
│   ├── config.yaml          # global settings (paths, model choice, crop mode, etc.)
│   └── job_template.json    # one job = one video to process
├── music/                   # <-- put your own royalty-free .mp3/.wav files here
├── downloads/                # raw downloaded videos land here
├── output/
│   ├── clips/                 # intermediate clipped segments
│   ├── final/                 # final rendered shorts (music + captions burned in)
│   └── logs/                  # per-job run logs (json)
├── credentials/
│   └── client_secret.json    # OAuth client from Google Cloud Console (you provide)
│   └── token.json             # auto-created after first YouTube login
├── src/
│   ├── downloader.py          # wraps yt-dlp (or calls your existing .exe)
│   ├── transcript.py          # gets transcript via yt-dlp captions or Whisper (local, free)
│   ├── highlight_finder.py    # scores segments, picks the "best part"
│   ├── clipper.py              # ffmpeg: cut + crop to 9:16 vertical
│   ├── music_selector.py       # lets you pick/mix music from /music
│   ├── captioner.py             # burns subtitles onto the clip
│   ├── uploader.py               # YouTube Data API v3 upload + schedule
│   └── pipeline.py               # orchestrates all stages in order
├── main.py                        # CLI entry point
├── requirements.txt
└── .env.example
```

---

## 2. What you need installed (all free)

| Tool | Why | Install |
|---|---|---|
| Python 3.10+ | runtime | python.org |
| ffmpeg | cutting, cropping, mixing audio, burning captions | `winget install ffmpeg` / `apt install ffmpeg` / `brew install ffmpeg` |
| yt-dlp | downloading (you already have a frontend for this — can reuse) | `pip install yt-dlp` |
| Whisper (openai-whisper) | local, free transcript generation if a video has no captions | `pip install openai-whisper` |
| Ollama + a local model (optional but recommended) | free local LLM to score "which part is the best part" | https://ollama.com then `ollama pull llama3.1:8b` |
| Google Cloud project + YouTube Data API v3 enabled | uploading/scheduling to YouTube (free quota: 10,000 units/day, an upload costs 1,600) | console.cloud.google.com |
| google-api-python-client, google-auth-oauthlib | talk to YouTube API | `pip install google-api-python-client google-auth-oauthlib` |

Everything above is free. The only "cost" is your own compute (Whisper/Ollama run locally on your CPU/GPU).

---

## 3. One-time setup

### 3.1 Python deps
```bash
cd yt_shorts_automation
python -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 3.2 YouTube API credentials (needed for uploading)
1. Go to https://console.cloud.google.com → create a project.
2. Enable **YouTube Data API v3**.
3. Create OAuth 2.0 Client ID → Application type: **Desktop app**.
4. Download the JSON → save it as `credentials/client_secret.json`.
5. First time you run `uploader.py`, a browser window opens to log into the YouTube
   account you want to post from. A `token.json` is saved so you won't need to log
   in again (auto-refreshes).

### 3.3 Add your music
Drop your royalty-free `.mp3`/`.wav` files into `/music`. Name them descriptively,
e.g. `music/upbeat_lofi.mp3`, `music/dramatic_build.mp3`. The pipeline reads
whatever's in that folder — you pick which one per job (see below).

### 3.4 Config
Edit `config/config.yaml` — crop mode, whisper model size, whether to use Ollama
scoring or the simpler heuristic scorer, output resolution, etc.

---

## 4. Running a job

A "job" is just a JSON file describing one video. Copy the template:

```bash
cp config/job_template.json config/jobs/my_job.json
```

```json
{
  "source_url": "https://www.youtube.com/watch?v=XXXXXXXX",
  "segment_length_sec": 45,
  "music_file": "upbeat_lofi.mp3",
  "music_volume": 0.25,
  "captions": true,
  "title": "This is insane 😳 #Shorts",
  "description": "Full video: <link> #Shorts",
  "schedule_time_utc": "2026-07-15T14:00:00Z",
  "privacy_status": "private"
}
```

- `music_file`: must match a filename inside `/music`. Leave `"auto"` to let the
  pipeline pick a track from `/music` based on tags in `config.yaml`.
- `schedule_time_utc`: ISO 8601. YouTube publishes automatically at this time.
- `segment_length_sec`: target length of the extracted highlight (YouTube Shorts ≤ 60s).

Run the full pipeline:
```bash
python main.py --job config/jobs/my_job.json
```

Run a single stage (useful for testing):
```bash
python main.py --job config/jobs/my_job.json --only download
python main.py --job config/jobs/my_job.json --only highlight
python main.py --job config/jobs/my_job.json --only clip
python main.py --job config/jobs/my_job.json --only music
python main.py --job config/jobs/my_job.json --only caption
python main.py --job config/jobs/my_job.json --only upload
```

Each stage writes its output path into the job's log file in `output/logs/`, so
stages downstream automatically pick up where the previous one left off.

---

## 5. Batch/scheduled automation

To run this unattended on new videos periodically:
- **Windows**: Task Scheduler → run `python main.py --watch config/jobs/` every N minutes
- **Linux/Mac**: cron entry, e.g. `*/30 * * * * cd /path/to/project && ./venv/bin/python main.py --watch config/jobs/`

Drop new job JSON files into `config/jobs/` and the watcher will process any that
don't yet have a completed log entry.

---

## 6. Dashboard (optional, easier than the CLI)

Instead of writing job JSON files by hand, run the Streamlit dashboard:

```bash
pip install -r requirements.txt   # now includes streamlit
streamlit run dashboard.py
```

This opens a browser tab at `http://localhost:8501` with:
1. A field to paste a YouTube link + a rights/ownership confirmation checkbox + **Download** button
2. **Analyze video** — runs transcript extraction + best-part detection, shown as an
   adjustable time-range slider (drag it if the auto-picked segment isn't right)
3. A dropdown of whatever tracks are sitting in your `/music` folder, a volume
   slider, and a **Build short** button (clip + music mix + optional captions)
4. Title/description/tags/privacy/schedule fields and a **Post to YouTube** button

It calls the exact same functions as the CLI stages (`src/downloader.py`,
`src/highlight_finder.py`, etc.) — it's just a UI layer on top, so behavior is
identical to running `main.py`. The first time you click "Post to YouTube" it
will open a browser window for Google OAuth login, same as the CLI version —
this needs to run on a machine where a browser can actually pop up (your own
computer, not a headless server).

## 7. Important legal note

This only produces something you're allowed to post if:
- you own the source video, OR
- you have explicit permission/license to reuse it, OR
- the source is under a license that permits derivative/reuse (e.g. Creative Commons)

Auto-downloading and re-uploading someone else's monetized YouTube video without
rights is copyright infringement and a ToS violation, regardless of automation.
The music-licensing side of this (using your own downloaded royalty-free tracks)
is fine as long as those tracks' license actually permits this use — check the
license terms of each track (some royalty-free licenses restrict monetized reuse
or require attribution).
