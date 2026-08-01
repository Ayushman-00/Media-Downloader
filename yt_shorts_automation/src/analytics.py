import os
import sys
import glob
import json
import csv
from datetime import datetime

# Ensure src/ modules can be imported
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.utils import load_config
from src.uploaders.youtube import get_authenticated_service

def fetch_metrics(youtube, video_id: str) -> dict:
    """Fetch metrics from YouTube Data API.
    
    Note on deviation from spec (§3.9):
    Average view duration and view percentage are NOT available via the standard 
    YouTube Data API v3 (videos.list). They require the separate YouTube Analytics API
    (yt-analytics.readonly scope) and a channel with sufficient traffic to generate reports.
    Since this is an offline tuning script meant for broad usage without complex
    Analytics API setup, we omit those fields here (returning None).
    If they become available or if the user sets up Analytics API, they can be added.
    """
    try:
        # Fetch basic stats from Data API
        request = youtube.videos().list(
            part="statistics",
            id=video_id
        )
        response = request.execute()
        
        if not response.get("items"):
            return {"views": 0, "likes": 0, "comments": 0, "average_view_duration": None, "average_view_percentage": None}
            
        stats = response["items"][0]["statistics"]
        return {
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "average_view_duration": None,  # Not exposed in Data API v3
            "average_view_percentage": None # Not exposed in Data API v3
        }
    except Exception as e:
        print(f"[analytics] Failed to fetch metrics for {video_id}: {e}")
        return {"views": 0, "likes": 0, "comments": 0, "average_view_duration": None, "average_view_percentage": None}

def build_dataset():
    """
    Scans all completed jobs in output/logs/, fetches YouTube metrics for
    uploaded videos, and builds a flat CSV dataset for offline tuning.
    """
    cfg = load_config()
    logs_dir = cfg["paths"]["logs"]
    dataset_path = os.path.join(cfg["paths"]["root"], "eval", "analytics_dataset.csv")
    
    os.makedirs(os.path.dirname(dataset_path), exist_ok=True)
    
    # Try to authenticate, but continue with mock metrics if auth fails (e.g. CI)
    try:
        youtube = get_authenticated_service(cfg)
    except Exception as e:
        print(f"[analytics] Auth failed ({e}). Proceeding with empty metrics.")
        youtube = None

    rows = []
    
    for log_file in glob.glob(os.path.join(logs_dir, "*.json")):
        with open(log_file, "r") as f:
            log_data = json.load(f)
            
        stages = log_data.get("stages", {})
        decisions = log_data.get("decisions", {})
        
        # Only process jobs that actually uploaded
        if "upload" not in stages or "output" not in stages["upload"]:
            continue
            
        video_id = stages["upload"]["output"]
        if video_id == "unknown":
            continue
            
        # Get decisions for the selected highlight
        hl_decisions = decisions.get("highlight", {})
        method = hl_decisions.get("method", "heuristic")
        
        # Default empty values
        hook_type = ""
        payoff_type = ""
        score = 0.0
        
        # If the LLM was used, try to extract the chosen candidate's features
        if "candidates" in hl_decisions:
            # The chosen candidate should match the bounds in the highlight stage
            start = stages.get("highlight", {}).get("start", -1)
            for c in hl_decisions["candidates"]:
                if abs(float(c.get("start", -1)) - float(start)) < 0.1:
                    hook_type = c.get("hook_type", "")
                    payoff_type = c.get("payoff_type", "")
                    score = c.get("final_score", 0.0)
                    break
        
        metrics = {"views": 0, "likes": 0, "comments": 0, "average_view_duration": None, "average_view_percentage": None}
        if youtube:
            metrics = fetch_metrics(youtube, video_id)
            
        rows.append({
            "job_id": log_data.get("job_id", os.path.basename(log_file)),
            "video_id": video_id,
            "method": method,
            "hook_type": hook_type,
            "payoff_type": payoff_type,
            "score": round(score, 2),
            "views": metrics["views"],
            "likes": metrics["likes"],
            "comments": metrics["comments"],
            "average_view_duration": metrics.get("average_view_duration"),
            "average_view_percentage": metrics.get("average_view_percentage"),
            "processed_at": datetime.now().isoformat()
        })
        
    if not rows:
        print("[analytics] No uploaded jobs found to process.")
        return
        
    # Write to CSV
    fieldnames = ["job_id", "video_id", "method", "hook_type", "payoff_type", "score", "views", "likes", "comments", "average_view_duration", "average_view_percentage", "processed_at"]
    
    file_exists = os.path.isfile(dataset_path)
    with open(dataset_path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            
    print(f"[analytics] Successfully exported {len(rows)} rows to {dataset_path}")
    print("[analytics] This dataset is intended for future offline prompt/weight tuning.")

if __name__ == "__main__":
    build_dataset()
