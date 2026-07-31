import unittest
from unittest.mock import patch, MagicMock

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.uploaders.youtube import YouTubeUploader

class TestUploaderEquivalence(unittest.TestCase):
    @patch('src.uploaders.youtube.get_authenticated_service')
    @patch('src.uploaders.youtube.upload')
    def test_youtube_uploader_translates_metadata_correctly(self, mock_upload, mock_get_auth):
        mock_auth = MagicMock()
        mock_get_auth.return_value = mock_auth
        mock_upload.return_value = {"id": "test_id123"}
        
        cfg = {"upload": {"category_id": "22", "made_for_kids": False}}
        uploader = YouTubeUploader(cfg)
        
        metadata = {
            "title": "Test Title #Shorts",
            "description": "Test Desc",
            "tags": ["shorts", "test"],
            "category_id": "24",
            "privacy_status": "unlisted",
            "publish_at": "2024-01-01T00:00:00Z",
            "made_for_kids": True
        }
        
        result = uploader.upload("fake_path.mp4", metadata)
        
        self.assertEqual(result, {"id": "test_id123"})
        mock_upload.assert_called_once_with(
            mock_auth,
            "fake_path.mp4",
            title="Test Title #Shorts",
            description="Test Desc",
            tags=["shorts", "test"],
            category_id="24",
            privacy_status="unlisted",
            publish_at="2024-01-01T00:00:00Z",
            made_for_kids=True
        )

if __name__ == '__main__':
    unittest.main()
