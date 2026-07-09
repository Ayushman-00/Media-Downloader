
import sys
import os
from pathlib import Path


def _is_frozen() -> bool:

    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def resource_path(relative: str) -> Path:
 
    if _is_frozen():
        base = Path(sys._MEIPASS)
    else:

        base = Path(__file__).resolve().parent.parent
    return base / relative


def user_data_path(relative: str = "") -> Path:
  
    if _is_frozen():
   
        base = Path(sys.executable).parent
    else:
     
        base = Path(sys.argv[0]).resolve().parent
    
    return base / relative if relative else base
