"""
Uploads the final video to YouTube via Data API v3.

Two public functions (called by dashboard.py and pipeline.py):
  get_authenticated_service(cfg)  → youtube service object
  upload(youtube, file_path, ...)  → API response dict

OAuth flow adapted from:
  fralapo/clippyme  src/clippyme/domain/publish_service.py
  + Google's official upload_video.py sample
"""

import http.client
import json
import os
import random
import time
from typing import Dict, List, Optional

from src.utils import load_config


# ---------------------------------------------------------------------------
# OAuth 2.0 authentication
# ---------------------------------------------------------------------------

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

# Maximum number of retries on resumable upload
MAX_RETRIES = 5
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]


def get_authenticated_service(cfg: dict):
    """Authenticate with YouTube Data API v3 and return a service object.

    On first run, opens a browser for OAuth consent. The resulting token
    is cached in credentials/token.json for subsequent runs.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "YouTube upload requires: pip install google-api-python-client google-auth-oauthlib\n"
            "Uncomment these in requirements.txt and run pip install -r requirements.txt"
        )

    creds_dir = cfg["paths"]["credentials"]
    client_secret_path = os.path.join(creds_dir, "client_secret.json")
    token_path = os.path.join(creds_dir, "token.json")

    if not os.path.isfile(client_secret_path):
        raise FileNotFoundError(
            f"Missing {client_secret_path}.\n"
            "1. Go to https://console.cloud.google.com/apis/credentials\n"
            "2. Create an OAuth 2.0 'Desktop app' credential\n"
            "3. Download the JSON and save it as credentials/client_secret.json"
        )

    creds = None

    # Load existing token
    if os.path.isfile(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # Refresh or run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("[uploader] token refreshed", flush=True)
            except Exception:
                print("[uploader] token refresh failed, re-authenticating...", flush=True)
                creds = None

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
            print("[uploader] OAuth flow completed", flush=True)

        # Save token for next time
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build(API_SERVICE_NAME, API_VERSION, credentials=creds)


# ---------------------------------------------------------------------------
# Upload with resumable media
# ---------------------------------------------------------------------------

def upload(
    youtube,
    file_path: str,
    title: str = "My Short #Shorts",
    description: str = "#Shorts",
    tags: Optional[List[str]] = None,
    category_id: str = "22",
    privacy_status: str = "private",
    publish_at: Optional[str] = None,
    made_for_kids: bool = False,
) -> Dict:
    """Upload a video to YouTube with resumable upload and retry logic.

    Args:
        youtube: authenticated YouTube service object
        file_path: path to the video file
        title: video title
        description: video description
        tags: list of tags
        category_id: YouTube category (22 = People & Blogs)
        privacy_status: public, private, or unlisted
        publish_at: ISO 8601 datetime for scheduled publishing (requires private)
        made_for_kids: COPPA self-declaration

    Returns:
        YouTube API response dict containing the video 'id'.
    """
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        raise ImportError("Missing google-api-python-client")

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Video file not found: {file_path}")

    tags = tags or ["shorts"]

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    # Scheduled publishing requires privacy = private + publishAt
    if publish_at and privacy_status == "private":
        body["status"]["publishAt"] = publish_at

    media = MediaFileUpload(
        file_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10 MB chunks
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    print(f"[uploader] uploading {file_path} ({os.path.getsize(file_path) / 1e6:.1f} MB)...", flush=True)

    response = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"[uploader] progress: {pct}%", flush=True)
        except http.client.HTTPException as e:
            # Retriable network errors
            if retry < MAX_RETRIES:
                retry += 1
                sleep_secs = random.uniform(1, 2 ** retry)
                print(f"[uploader] retriable error ({e}), retry {retry}/{MAX_RETRIES} in {sleep_secs:.1f}s", flush=True)
                time.sleep(sleep_secs)
            else:
                raise
        except Exception as e:
            # Check if it's a retriable HTTP status
            err_str = str(e)
            if any(str(code) in err_str for code in RETRIABLE_STATUS_CODES) and retry < MAX_RETRIES:
                retry += 1
                sleep_secs = random.uniform(1, 2 ** retry)
                print(f"[uploader] retriable status ({e}), retry {retry}/{MAX_RETRIES} in {sleep_secs:.1f}s", flush=True)
                time.sleep(sleep_secs)
            else:
                raise

    video_id = response.get("id", "unknown")
    print(f"[uploader] upload complete: https://youtube.com/watch?v={video_id}", flush=True)
    return response