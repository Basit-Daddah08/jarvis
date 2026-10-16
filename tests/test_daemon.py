import shutil
import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.daemon import ElionDaemon
from src.fetch.base import VideoItem
from src.fetch.clipboard_watcher import VIDEO_URL_PATTERN
from src.fetch.media_extractor import MediaExtractor

class TestElionDaemon(unittest.TestCase):

    def test_video_url_regex_detection(self):
        ig_match = VIDEO_URL_PATTERN.search("Check this out https://www.instagram.com/reel/C89xYz12345/?igsh=abc")
        self.assertIsNotNone(ig_match)
        self.assertIn("instagram.com/reel/C89xYz12345", ig_match.group(0))

        tt_match = VIDEO_URL_PATTERN.search("https://www.tiktok.com/@dev/video/7123456789")
        self.assertIsNotNone(tt_match)

        yt_match = VIDEO_URL_PATTERN.search("Watch https://youtube.com/shorts/dQw4w9WgXcQ")
        self.assertIsNotNone(yt_match)

    def test_platform_detection(self):
        self.assertEqual(MediaExtractor._detect_platform("https://www.instagram.com/reel/123"), "instagram")
        self.assertEqual(MediaExtractor._detect_platform("https://www.tiktok.com/@user/video/1"), "tiktok")
        self.assertEqual(MediaExtractor._detect_platform("https://youtube.com/shorts/abc"), "youtube")

    def test_daemon_enqueue_and_background_process(self):
        daemon = ElionDaemon()
        item_id = daemon.enqueue_url(
            url="https://www.instagram.com/reel/test_bg_daemon/",
            creator="@elion_dev",
            title="Background Daemon Test Reel",
            caption="Step 1 install ollama. Step 2 run whisper.cpp in the background.",
            source="mobile_in_app_share"
        )
        self.assertTrue(item_id.startswith("save_"))
        self.assertGreaterEqual(daemon.work_queue.qsize(), 1)

if __name__ == "__main__":
    unittest.main()
