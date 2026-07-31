from src.uploaders.base import Uploader

def get_uploader(cfg: dict) -> Uploader:
    """Factory to get the correct Uploader implementation based on config."""
    platform = cfg.get("upload", {}).get("platform", "youtube").lower()
    
    if platform == "youtube":
        from src.uploaders.youtube import YouTubeUploader
        return YouTubeUploader(cfg)
    else:
        raise ValueError(f"Unknown upload platform: {platform}")
