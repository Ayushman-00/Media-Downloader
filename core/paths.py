"""
paths.py - PyInstaller-compatible path resolution.

When frozen with PyInstaller (--onefile or --onedir), the bundled resources
(assets, default configs etc.) live inside sys._MEIPASS. User-writable data
(settings.json, history.json, logs/) must stay next to the .exe or in AppData
so they persist across runs.

Usage:
    from core.paths import resource_path, user_data_path
"""

import sys
import os
from pathlib import Path


def _is_frozen() -> bool:
    """Return True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def resource_path(relative: str) -> Path:
    """
    Resolve path to a bundled read-only resource (icons, assets, …).
    - During development:  <project_root>/<relative>
    - PyInstaller frozen:  sys._MEIPASS/<relative>
    """
    if _is_frozen():
        base = Path(sys._MEIPASS)
    else:
        # __file__ is …/core/paths.py → go up two levels to project root
        base = Path(__file__).resolve().parent.parent
    return base / relative


def user_data_path(relative: str = "") -> Path:
    """
    Resolve path to user-writable data (settings.json, history.json, logs/).
    - Always lives next to the running executable (or main.py in dev mode).
    This ensures the file survives a PyInstaller --onefile extraction to temp.
    """
    if _is_frozen():
        # sys.executable is the .exe itself
        base = Path(sys.executable).parent
    else:
        # Running as plain python main.py – keep everything in project root
        base = Path(sys.argv[0]).resolve().parent
    
    return base / relative if relative else base
