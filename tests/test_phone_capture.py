import json
import socketserver
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from src.auth import get_or_create_auth_token
from src.dashboard.rate_limiter import RateLimiter
from src.dashboard.serve import JarvisHandler, is_localhost
from src.daemon import ElionDaemon
from src.fetch.clipboard_watcher import ClipboardWatcher
from src.fetch.url_validator import (
    extract_video_url_from_text,
    normalize_video_url,
    validate_video_url,
)

class TestPhoneCaptureLogic(unittest.TestCase):
    """Unit tests for phone capture validator, rate limiter, de-duplication, and clipboard."""

    def setUp(self):
        self.token = get_or_create_auth_token()
        self.daemon = ElionDaemon()
        self.limiter = RateLimiter(max_requests=5, window_seconds=10)

    def test_url_validator_platforms(self):
        # 1. Instagram URLs
        valid_ig, platform_ig, norm_ig = validate_video_url("https://www.instagram.com/reel/DC_12345/?igsh=xyz")
        self.assertTrue(valid_ig)
        self.assertEqual(platform_ig, "instagram")
        self.assertEqual(norm_ig, "https://www.instagram.com/reel/DC_12345")

        # 2. TikTok URLs
        valid_tt, platform_tt, norm_tt = validate_video_url("https://www.tiktok.com/@creator/video/7123456789012345678")
        self.assertTrue(valid_tt)
        self.assertEqual(platform_tt, "tiktok")

        valid_tt_vm, platform_tt_vm, _ = validate_video_url("https://vm.tiktok.com/ZMh123456/")
        self.assertTrue(valid_tt_vm)
        self.assertEqual(platform_tt_vm, "tiktok")

        # 3. YouTube Shorts and Links
        valid_yt_short, platform_yt_short, norm_yt = validate_video_url("https://www.youtube.com/shorts/dQw4w9WgXcQ?si=abcdef")
        self.assertTrue(valid_yt_short)
        self.assertEqual(platform_yt_short, "youtube")
        self.assertEqual(norm_yt, "https://www.youtube.com/shorts/dQw4w9WgXcQ")

        valid_yt_short_alt, _, _ = validate_video_url("https://youtube.com/shorts/dQw4w9WgXcQ")
        self.assertTrue(valid_yt_short_alt)

        valid_yt_be, platform_yt_be, _ = validate_video_url("https://youtu.be/dQw4w9WgXcQ")
        self.assertTrue(valid_yt_be)
        self.assertEqual(platform_yt_be, "youtube")

        # 4. Invalid / Unsupported URLs
        invalid_fb, _, _ = validate_video_url("https://www.facebook.com/watch/?v=12345")
        self.assertFalse(invalid_fb)

        invalid_twitter, _, _ = validate_video_url("https://x.com/user/status/123456789")
        self.assertFalse(invalid_twitter)

        invalid_general, _, _ = validate_video_url("https://example.com/article/test")
        self.assertFalse(invalid_general)

        invalid_empty, _, _ = validate_video_url("")
        self.assertFalse(invalid_empty)

    def test_extract_video_url_from_share_text(self):
        share_text = "Check out this reel! https://www.instagram.com/reel/C_test123/?igsh=abc so cool!"
        extracted = extract_video_url_from_text(share_text)
        self.assertIsNotNone(extracted)
        platform, canonical = extracted
        self.assertEqual(platform, "instagram")
        self.assertEqual(canonical, "https://www.instagram.com/reel/C_test123")

    def test_deduplication_logic(self):
        test_url = "https://youtube.com/shorts/abc123unique"

        # First enqueue
        queued1, dup1, item_id1 = self.daemon.enqueue_url_safe(test_url, source="test")
        self.assertTrue(queued1)
        self.assertFalse(dup1)

        # Second enqueue of the exact same URL (or with query param)
        queued2, dup2, item_id2 = self.daemon.enqueue_url_safe(test_url + "?si=tracker", source="test")
        self.assertFalse(queued2)
        self.assertTrue(dup2)
        self.assertEqual(item_id1, item_id2)

    def test_rate_limiter(self):
        client_key = "100.85.1.2:my_token"
        limiter = RateLimiter(max_requests=3, window_seconds=5)

        self.assertTrue(limiter.is_allowed(client_key))
        self.assertTrue(limiter.is_allowed(client_key))
        self.assertTrue(limiter.is_allowed(client_key))
        # 4th request must be rejected
        self.assertFalse(limiter.is_allowed(client_key))

    def test_clipboard_watcher_validation_and_toggle(self):
        detected_urls = []
        watcher = ClipboardWatcher(on_url_detected=lambda u: detected_urls.append(u))

        # Mock _read_clipboard_text to simulate user copying a YouTube Short
        watcher._read_clipboard_text = MagicMock(return_value="https://youtube.com/shorts/dQw4w9WgXcQ")
        url = watcher.check_once()
        self.assertEqual(url, "https://youtube.com/shorts/dQw4w9WgXcQ")
        self.assertIn("https://youtube.com/shorts/dQw4w9WgXcQ", detected_urls)

        # Copying an unsupported link (e.g. news article) should be ignored
        watcher._read_clipboard_text = MagicMock(return_value="https://nytimes.com/article/tech")
        url_unsupported = watcher.check_once()
        self.assertIsNone(url_unsupported)

        # Toggle OFF: watcher must do nothing when disabled
        watcher.enabled = False
        watcher._read_clipboard_text = MagicMock(return_value="https://www.instagram.com/reel/C_newreel/")
        url_when_disabled = watcher.check_once()
        self.assertIsNone(url_when_disabled)
        self.assertNotIn("https://www.instagram.com/reel/C_newreel", detected_urls)

        # Toggle ON
        watcher.enabled = True
        url_when_enabled = watcher.check_once()
        self.assertEqual(url_when_enabled, "https://www.instagram.com/reel/C_newreel")
        self.assertIn("https://www.instagram.com/reel/C_newreel", detected_urls)

    def test_daemon_toggle_clipboard(self):
        initial = self.daemon.clipboard_enabled
        new_state = self.daemon.toggle_clipboard()
        self.assertEqual(new_state, not initial)
        self.assertEqual(self.daemon.clipboard_watcher.enabled, new_state)

        # Toggle back
        restored = self.daemon.toggle_clipboard()
        self.assertEqual(restored, initial)
        self.assertEqual(self.daemon.clipboard_watcher.enabled, initial)


class TestPhoneCaptureLiveHttpServer(unittest.TestCase):
    """End-to-end integration tests on live HTTP server for POST /api/save."""

    @classmethod
    def setUpClass(cls):
        socketserver.TCPServer.allow_reuse_address = True
        cls.port = 18099
        cls.server = socketserver.TCPServer(("127.0.0.1", cls.port), JarvisHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.token = get_or_create_auth_token()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _post(self, path: str, data: dict, headers: dict = None):
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode("utf-8")
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_post_save_missing_token_returns_401(self):
        status, res = self._post("/api/save", {"url": "https://youtube.com/shorts/dQw4w9WgXcQ"})
        self.assertEqual(status, 401)
        self.assertEqual(res.get("error"), "Unauthorized")

    def test_post_save_invalid_token_returns_401(self):
        status, res = self._post("/api/save", {
            "url": "https://youtube.com/shorts/dQw4w9WgXcQ",
            "token": "wrong_token_12345"
        })
        self.assertEqual(status, 401)
        self.assertEqual(res.get("error"), "Unauthorized")

    def test_post_save_invalid_url_returns_400(self):
        # Fake request with non-Instagram/TikTok/YouTube link
        status, res = self._post("/api/save", {
            "url": "https://example.com/fake_page",
            "token": self.token
        })
        self.assertEqual(status, 400)
        self.assertEqual(res.get("error"), "Invalid URL")
        self.assertIn("Only Instagram, TikTok, and YouTube", res.get("message", ""))

    def test_post_save_valid_url_queues_successfully(self):
        # Real format YouTube Short
        yt_url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        status, res = self._post("/api/save", {
            "url": yt_url,
            "token": self.token
        })
        self.assertEqual(status, 200)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("platform"), "youtube")
        self.assertIn("id", res)

    def test_post_save_duplicate_returns_instant_duplicate_flag(self):
        yt_url = "https://www.youtube.com/shorts/dupTest123"
        # First save
        status1, res1 = self._post("/api/save", {"url": yt_url, "token": self.token})
        self.assertEqual(status1, 200)
        self.assertTrue(res1.get("queued"))
        self.assertFalse(res1.get("duplicate"))

        # Second save of the exact same video
        status2, res2 = self._post("/api/save", {"url": yt_url, "token": self.token})
        self.assertEqual(status2, 200)
        self.assertTrue(res2.get("success"))
        self.assertFalse(res2.get("queued"))
        self.assertTrue(res2.get("duplicate"))


if __name__ == "__main__":
    unittest.main()
