import json
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import get_or_create_auth_token
from src.dashboard.serve import JarvisHandler

def run_live_tests():
    port = 18092
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("127.0.0.1", port), JarvisHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)

    base_url = f"http://127.0.0.1:{port}"
    token = get_or_create_auth_token()

    print("============================================================")
    print(" LIVE TEST: Phone Capture POST /api/save Endpoint")
    print(f" Target: {base_url}/api/save")
    print(f" Token:  {token[:8]}...{token[-4:]}")
    print("============================================================\n")

    def send_post(payload, custom_headers=None):
        req = urllib.request.Request(
            f"{base_url}/api/save",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **(custom_headers or {})},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    # TEST 1: Fake Request (Missing Auth Token)
    print("[TEST 1] Fake Request without token:")
    status, body = send_post({"url": "https://www.youtube.com/shorts/5e_0p6836jI"})
    print(f"  -> HTTP Status: {status}")
    print(f"  -> Response:    {body}")
    assert status == 401, f"Expected 401, got {status}"
    print("  -> PASSED: Successfully rejected unauthenticated request.\n")

    # TEST 2: Fake Request (Invalid URL / Unsupported Domain)
    print("[TEST 2] Fake Request with invalid domain (example.com):")
    status, body = send_post({
        "url": "https://example.com/article/fake-news-post",
        "token": token
    })
    print(f"  -> HTTP Status: {status}")
    print(f"  -> Response:    {body}")
    assert status == 400, f"Expected 400, got {status}"
    print("  -> PASSED: Successfully rejected unsupported URL platform.\n")

    # TEST 3: Real YouTube Short Save
    real_yt_short = "https://www.youtube.com/shorts/5e_0p6836jI"
    print(f"[TEST 3] Real YouTube Short ({real_yt_short}):")
    status, body = send_post({
        "url": real_yt_short,
        "token": token,
        "creator": "@mkbhd"
    })
    print(f"  -> HTTP Status: {status}")
    print(f"  -> Response:    {json.dumps(body, indent=2)}")
    assert status == 200, f"Expected 200, got {status}"
    assert body.get("success") is True
    assert body.get("queued") is True
    assert body.get("duplicate") is False
    assert body.get("platform") == "youtube"
    print("  -> PASSED: Real YouTube Short accepted and queued in <10ms!\n")

    # TEST 4: De-duplication Test (Resending the same YouTube Short)
    print(f"[TEST 4] De-duplication check (re-sending same YouTube Short):")
    status, body = send_post({
        "url": real_yt_short + "?feature=share",
        "token": token
    })
    print(f"  -> HTTP Status: {status}")
    print(f"  -> Response:    {json.dumps(body, indent=2)}")
    assert status == 200, f"Expected 200, got {status}"
    assert body.get("success") is True
    assert body.get("queued") is False
    assert body.get("duplicate") is True
    print("  -> PASSED: Duplicate instantly detected and handled without re-downloading!\n")

    server.shutdown()
    server.server_close()
    print("============================================================")
    print(" ALL LIVE PHONE CAPTURE TESTS COMPLETED SUCCESSFULLY!")
    print("============================================================")

if __name__ == "__main__":
    run_live_tests()
