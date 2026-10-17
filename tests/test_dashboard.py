import http.client
import threading
import time
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.dashboard.serve import start_server

class TestDashboardServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.thread = threading.Thread(target=start_server, daemon=True)
        cls.thread.start()
        time.sleep(1)

    def test_root_endpoint(self):
        conn = http.client.HTTPConnection("localhost", 8080)
        conn.request("GET", "/")
        res = conn.getresponse()
        self.assertEqual(res.status, 200)

    def test_api_notes_endpoint(self):
        conn = http.client.HTTPConnection("localhost", 8080)
        conn.request("GET", "/api/notes")
        res = conn.getresponse()
        self.assertEqual(res.status, 200)

    def test_api_approvals_endpoint(self):
        conn = http.client.HTTPConnection("localhost", 8080)
        conn.request("GET", "/api/approvals")
        res = conn.getresponse()
        self.assertEqual(res.status, 200)

if __name__ == "__main__":
    unittest.main()
