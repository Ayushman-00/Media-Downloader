"""
Entry point for the yt_shorts_automation CLI.

Usage:
  # Run full pipeline for a single job
  python main.py --job config/jobs/my_video.json

  # Run only a specific stage
  python main.py --job config/jobs/my_video.json --only download

  # Watch a directory for new job JSON files (batch mode)
  python main.py --watch config/jobs/

  # Launch the Streamlit dashboard
  python main.py --dashboard

Valid stages: download, transcript, highlight, clip, music, caption, upload
"""

import argparse
import glob
import os
import sys
import time

# Ensure the project root is on sys.path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.pipeline import run_pipeline
from src.utils import load_config, read_log


def main():
    parser = argparse.ArgumentParser(
        description="YT Shorts Automation — turn long videos into vertical Shorts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --job config/jobs/my_video.json
  python main.py --job config/jobs/my_video.json --only clip
  python main.py --watch config/jobs/
  python main.py --dashboard
        """,
    )
    parser.add_argument(
        "--job", type=str,
        help="Path to a job JSON file to process",
    )
    parser.add_argument(
        "--only", type=str, default=None,
        choices=["download", "transcript", "highlight", "clip", "music", "caption", "upload"],
        help="Run only this specific stage (requires --job)",
    )
    parser.add_argument(
        "--watch", type=str, default=None,
        help="Directory to watch for new job JSON files (batch mode)",
    )
    parser.add_argument(
        "--dashboard", action="store_true",
        help="Launch the Streamlit dashboard instead of CLI",
    )

    args = parser.parse_args()

    # --- Dashboard mode ---
    if args.dashboard:
        import subprocess
        dashboard_path = os.path.join(ROOT, "dashboard.py")
        print(f"Launching Streamlit dashboard: {dashboard_path}")
        subprocess.run([sys.executable, "-m", "streamlit", "run", dashboard_path], check=True)
        return

    # --- Single job mode ---
    if args.job:
        job_path = os.path.abspath(args.job)
        if not os.path.isfile(job_path):
            print(f"Error: job file not found: {job_path}", file=sys.stderr)
            sys.exit(1)
        run_pipeline(job_path, only_stage=args.only)
        return

    # --- Watch mode ---
    if args.watch:
        watch_dir = os.path.abspath(args.watch)
        if not os.path.isdir(watch_dir):
            print(f"Error: watch directory not found: {watch_dir}", file=sys.stderr)
            sys.exit(1)

        print(f"Watching {watch_dir} for job JSON files...")
        print("Press Ctrl+C to stop.\n")

        cfg = load_config()
        processed = set()

        try:
            while True:
                job_files = sorted(glob.glob(os.path.join(watch_dir, "*.json")))
                for job_path in job_files:
                    if job_path in processed:
                        continue

                    # Skip files that are fully done (have an upload stage)
                    log = read_log(job_path, cfg)
                    if "upload" in log.get("stages", {}):
                        processed.add(job_path)
                        continue

                    print(f"\n{'='*60}")
                    print(f"Processing: {os.path.basename(job_path)}")
                    print(f"{'='*60}")

                    try:
                        run_pipeline(job_path)
                        processed.add(job_path)
                    except Exception as e:
                        print(f"Error processing {job_path}: {e}", file=sys.stderr)
                        processed.add(job_path)  # Don't retry on error

                time.sleep(5)  # Poll every 5 seconds
        except KeyboardInterrupt:
            print("\nStopped watching.")
        return

    # --- No args: show help ---
    parser.print_help()


if __name__ == "__main__":
    main()