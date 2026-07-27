import json
import os
import sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.config import shorts_config
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    return shorts_config.get_all()


def load_job(job_path):
    with open(job_path, "r") as f:
        return json.load(f)


def log_path_for(job_path, cfg):
    job_id = os.path.splitext(os.path.basename(job_path))[0]
    return os.path.join(cfg["paths"]["logs"], f"{job_id}.json")


def read_log(job_path, cfg):
    lp = log_path_for(job_path, cfg)
    if os.path.exists(lp):
        with open(lp, "r") as f:
            return json.load(f)
    return {"job_id": os.path.splitext(os.path.basename(job_path))[0], "stages": {}}


def write_log(job_path, cfg, log):
    log["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(log_path_for(job_path, cfg), "w") as f:
        json.dump(log, f, indent=2)


def mark_stage(job_path, cfg, stage_name, output_path, extra=None):
    log = read_log(job_path, cfg)
    entry = {"output": output_path, "completed_at": datetime.now(timezone.utc).isoformat()}
    if extra:
        entry.update(extra)
    log["stages"][stage_name] = entry
    write_log(job_path, cfg, log)
    return log


def get_stage_output(job_path, cfg, stage_name):
    log = read_log(job_path, cfg)
    stage = log["stages"].get(stage_name)
    return stage["output"] if stage else None
