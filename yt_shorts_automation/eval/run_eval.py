import os
import sys
import json
from pathlib import Path

# Ensure src/ modules can be imported
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src import highlight_engine
from src.utils import load_config

def calculate_iou(pred_start, pred_end, truth_start, truth_end):
    """Intersection over Union for 1D time segments."""
    intersection_start = max(pred_start, truth_start)
    intersection_end = min(pred_end, truth_end)
    intersection = max(0, intersection_end - intersection_start)
    
    union_start = min(pred_start, truth_start)
    union_end = max(pred_end, truth_end)
    union = max(0, union_end - union_start)
    
    if union == 0:
        return 0.0
    return intersection / union

def run_evaluation():
    print("Starting Golden Set Evaluation Harness...")
    dataset_path = os.path.join(PROJECT_ROOT, "eval", "golden_set", "dataset.json")
    
    if not os.path.exists(dataset_path):
        print(f"Dataset not found at {dataset_path}")
        return

    with open(dataset_path, "r") as f:
        dataset = json.load(f)

    cfg = load_config()

    total_iou = 0.0
    count = 0

    for item in dataset:
        video_path = os.path.join(PROJECT_ROOT, item["video_path"])
        segments_path = os.path.join(PROJECT_ROOT, item["segments_path"])
        
        print(f"\nEvaluating: {item['id']}")
        
        if not os.path.exists(video_path) or not os.path.exists(segments_path):
            print(f"  [SKIPPED] Missing media/transcript for {item['id']} (expected for placeholder)")
            continue

        with open(segments_path, "r") as f:
            segments = json.load(f)

        try:
            candidates = highlight_engine.run_engine(video_path, segments, cfg)
            if not candidates:
                print("  [FAIL] Engine returned no candidates")
                continue
                
            top_candidate = candidates[0]
            pred_start = top_candidate["start"]
            pred_end = top_candidate["end"]
            
            # Find best overlap with any golden bound
            best_iou = 0.0
            for truth in item["golden_bounds"]:
                iou = calculate_iou(pred_start, pred_end, truth["start"], truth["end"])
                if iou > best_iou:
                    best_iou = iou
            
            print(f"  Predicted: {pred_start:.1f}s - {pred_end:.1f}s")
            print(f"  Best Golden IoU: {best_iou:.2f}")
            
            total_iou += best_iou
            count += 1
            
        except Exception as e:
            print(f"  [ERROR] Engine failed on {item['id']}: {e}")

    if count > 0:
        print(f"\n--- Evaluation Complete ---")
        print(f"Average IoU: {total_iou / count:.2f} across {count} items")
    else:
        print(f"\n--- Evaluation Skipped ---")
        print("No valid source videos found in the golden dataset. Replace placeholder entries with real data.")

if __name__ == "__main__":
    run_evaluation()
