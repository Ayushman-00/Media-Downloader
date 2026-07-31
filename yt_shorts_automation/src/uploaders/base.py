from abc import ABC, abstractmethod

class Uploader(ABC):
    """Protocol for multi-platform uploaders."""
    
    @abstractmethod
    def upload(self, file_path: str, metadata: dict) -> dict:
        """
        Upload a file to the platform.
        
        Args:
            file_path (str): The absolute path to the local video file.
            metadata (dict): Job metadata (title, description, tags, etc.)
            
        Returns:
            dict: The API response, typically containing the video ID or URL.
        """
        pass
