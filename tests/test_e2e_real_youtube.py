import http.client
import json
import socket
import socketserver
import sys
import threading
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import get_or_create_auth_token
from src.daemon import ElionDaemon
import src.dashboard.serve as serve_module
from src.dashboard.serve import JarvisHandler

class TestRealYouTubeShortEndToEnd(unittest.TestCase):
    """Real end-to-end integration test: phone endpoint -> background queue -> yt-dlp -> transcription -> classification -> vault."""

    def test_save_real_youtube_short_e2e(self):
        # 1. Allocate a local port
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        test_port = s.getsockname()[1]
        s.close()

        # 2. Start test daemon & server
        test_daemon = ElionDaemon()
        serve_module.daemon = test_daemon
        test_daemon.start_background_threads()

        socketserver.TCPServer.allow_reuse_address = True
        httpd = socketserver.TCPServer(('127.0.0.1', test_port), JarvisHandler)
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        try:
            real_short_url = "https://www.youtube.com/shorts/jNQXAC9IVRw"
            token = get_or_create_auth_token()
            test_daemon.state_mgr.processed_ids.discard("save_b0b3835ce5")
            test_daemon.queued_ids.discard("save_b0b3835ce5")

            # 3. Simulate phone share shortcut POST /api/save
            payload_bytes = json.dumps({
                "url": real_short_url,
                "title": "Me at the zoo",
                "creator": "@jawed"
            }).encode("utf-8")

            conn = http.client.HTTPConnection("127.0.0.1", test_port, timeout=15)
            headers = {
                "Content-Type": "application/json",
                "X-Elion-Token": token
            }

            conn.request("POST", "/api/save", body=payload_bytes, headers=headers)
            resp = conn.getresponse()
            resp_data = json.loads(resp.read().decode("utf-8"))
            conn.close()

            self.assertEqual(resp.status, 200)
            self.assertTrue(resp_data.get("success"))
            self.assertEqual(resp_data.get("platform"), "youtube")
            item_id = resp_data.get("id")
            self.assertTrue(bool(item_id))

            # 4. Wait for background worker to process real audio & create vault note
            timeout_sec = 45
            poll_start = time.time()
            created_note = None

            while time.time() - poll_start < timeout_sec:
                notes_dir = PROJECT_ROOT / "vault" / "notes"
                candidates = list(notes_dir.glob(f"*{item_id}*.md")) + list(notes_dir.glob("*jNQXAC9IVRw*.md"))
                if candidates and candidates[0].exists():
                    created_note = candidates[0]
                    break
                time.sleep(1.0)

            self.assertIsNotNone(created_note, f"Timed out waiting for vault note for {item_id}")

            # 5. Inspect note contents on disk
            note_content = created_note.read_text(encoding="utf-8")
            self.assertIn("type: ", note_content)
            self.assertIn("creator: ", note_content)
            self.assertIn("## Summary", note_content)
            self.assertIn("## Transcript", note_content)

            # 6. Verify INBOX.md
            inbox_path = PROJECT_ROOT / "vault" / "INBOX.md"
            self.assertTrue(inbox_path.exists())
            inbox_text = inbox_path.read_text(encoding="utf-8")
            self.assertTrue(created_note.name in inbox_text or item_id in inbox_text)

        finally:
            test_daemon.stop()
            httpd.shutdown()
            httpd.server_close()

if __name__ == "__main__":
    unittest.main()
