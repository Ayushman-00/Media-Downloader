import json
import os
from datetime import datetime
from pathlib import Path
from core.paths import user_data_path

class HistoryManager:
    def __init__(self, history_file="history.json"):
        # Always store history next to the executable (PyInstaller-safe)
        self.history_file = user_data_path(history_file)
        self.history = self.load_history()

    def load_history(self):
        """Load history from JSON."""
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading history: {e}")
            return []

    def save_history(self):
        """Save current history to JSON."""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=4)
        except Exception as e:
            print(f"Error saving history: {e}")

    def add_entry(self, url, platform, output_location, status, file_size=0):
        """Add a new download entry to history."""
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

    def update_entry(self, entry_id, status=None, file_size=None):
        """Update an existing history entry."""
        for entry in self.history:
            if entry["id"] == entry_id:
                if status is not None:
                    entry["status"] = status
                if file_size is not None:
                    entry["file_size"] = file_size
                self.save_history()
                break

    def delete_entry(self, entry_id):
        """Delete an entry from history."""
        self.history = [e for e in self.history if e["id"] != entry_id]
        self.save_history()

    def clear_history(self):
        """Clear all history."""
        self.history = []
        self.save_history()

    def get_all(self):
        """Return all history entries."""
        return self.history

# Global history instance
history_db = HistoryManager()
