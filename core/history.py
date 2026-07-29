import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from core.paths import user_data_path

class HistoryManager:
    """Manages persistent JSON history for downloads."""

    def __init__(self, history_file: str = "history.json"):
        # Always store history next to the executable (PyInstaller-safe)
        self.history_file: Path = user_data_path(history_file)
        self.history: List[Dict[str, Any]] = self.load_history()

    def load_history(self) -> List[Dict[str, Any]]:
        """Load history entries from JSON storage."""
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading history: {e}")
            return []

    def save_history(self) -> None:
        """Save current history entries to JSON storage."""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=4)
        except Exception as e:
            print(f"Error saving history: {e}")

    def add_entry(self, url: str, platform: str, output_location: str, status: str, file_size: int = 0) -> str:
        """Add a new download entry to history and return its entry ID."""
        entry = {
            "id": str(datetime.now().timestamp()),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "platform": platform,
            "output_location": output_location,
            "status": status,
            "file_size": file_size
        }
        self.history.insert(0, entry)  # Add to beginning
        self.save_history()
        return entry["id"]

    def update_entry(self, entry_id: str, status: Optional[str] = None, file_size: Optional[int] = None) -> None:
        """Update status or file size for an existing history entry."""
        for entry in self.history:
            if entry["id"] == entry_id:
                if status is not None:
                    entry["status"] = status
                if file_size is not None:
                    entry["file_size"] = file_size
                self.save_history()
                break

    def delete_entry(self, entry_id: str) -> None:
        """Delete a specific entry from history by ID."""
        self.history = [e for e in self.history if e["id"] != entry_id]
        self.save_history()

    def clear_history(self) -> None:
        """Clear all history entries."""
        self.history = []
        self.save_history()

    def get_all(self) -> List[Dict[str, Any]]:
        """Return all history entries."""
        return self.history

# Global history instance
history_db = HistoryManager()

