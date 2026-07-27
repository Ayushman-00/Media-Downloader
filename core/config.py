import json
import os
from pathlib import Path

from core.utils import get_default_download_folder
from core.paths import user_data_path

import yaml
from dotenv import load_dotenv

# Default configuration
DEFAULT_CONFIG = {
    "general": {
        "download_folder": get_default_download_folder(),
        "theme": "dark",
        "language": "en",
        "startup_behavior": "dashboard"
    },
    "downloads": {
        "default_mode": "Best Video + Best Audio",
        "default_quality": "Best Available",
        "default_format": "MP4",
        "auto_open_folder": False,
        "auto_delete_temp": True
    },
    "network": {
        "proxy": "",
        "timeout": 30,
        "concurrent_downloads": 3,
        "max_concurrent_downloads": 10,
        "retry_count": 5
    },
    "cookies": {
        "use_browser": "None",
        "cookie_file": "",
        "remember_choice": True
    },
    "naming": {
        "template": "%(title)s.%(ext)s"
    }
}

class ConfigManager:
    def __init__(self, config_file="settings.json"):
        # Always store settings next to the executable (PyInstaller-safe)
        self.config_file = user_data_path(config_file)
        self.config = self.load_config()

    def load_config(self):
        """Load config from JSON, falling back to defaults if missing or invalid."""
        if not self.config_file.exists():
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
        
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                
            # Merge user config with defaults to ensure all keys exist
            merged_config = DEFAULT_CONFIG.copy()
            for section, values in user_config.items():
                if section in merged_config:
                    merged_config[section].update(values)
                else:
                    merged_config[section] = values
            return merged_config
        except Exception as e:
            print(f"Error loading config: {e}. Using defaults.")
            return DEFAULT_CONFIG.copy()

    def save_config(self, config_data=None):
        """Save the current configuration to JSON."""
        if config_data is None:
            config_data = self.config
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, section, key=None):
        """Get a configuration section or specific key."""
        if section not in self.config:
            return None
        if key is None:
            return self.config[section]
        return self.config[section].get(key)

    def set(self, section, key, value):
        """Set a configuration value and save."""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
        self.save_config()

# Global config instance
config = ConfigManager()

class ShortsConfigManager:
    """Manages the configuration for the yt_shorts_automation pipeline."""
    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent
        self.shorts_root = self.project_root / "yt_shorts_automation"
        self.config = self.load_config()

    def load_config(self):
        env_path = self.shorts_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            
        yaml_path = self.shorts_root / "config" / "config.yaml"
        if not yaml_path.exists():
            return {}
            
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
            
        if "paths" in cfg:
            for key, rel in cfg["paths"].items():
                abs_path = self.shorts_root / rel
                cfg["paths"][key] = str(abs_path)
                os.makedirs(abs_path, exist_ok=True)
        return cfg

    def get_all(self):
        return self.config

# Global shorts config instance
shorts_config = ShortsConfigManager()
