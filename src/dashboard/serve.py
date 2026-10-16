import hashlib
import http.server
import json
import re
import socketserver
import sys
import urllib.parse
from datetime import date
from pathlib import Path

PORT = 8080
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.daemon import ElionDaemon
from src.mcp.server import list_saved_notes, search_vault_notes
from src.skills.queue_manager import SkillQueueManager

VAULT_NOTES = PROJECT_ROOT / "vault" / "notes"
APPROVALS_DIR = PROJECT_ROOT / "vault" / "approvals"
INBOX_FILE = PROJECT_ROOT / "vault" / "INBOX.md"
HTML_FILE = Path(__file__).resolve().parent / "index.html"

daemon = ElionDaemon()
queue_mgr = SkillQueueManager(approvals_dir=APPROVALS_DIR)

def parse_markdown_note(file_path: Path) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    front_matter = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1]
            body = parts[2]
            for line in fm_text.strip().split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    k = key.strip()
                    v = val.strip().strip('"').strip("'")
                    if v.startswith("[") and v.endswith("]"):
                        front_matter[k] = [i.strip().strip('"').strip("'") for i in v[1:-1].split(",") if i.strip()]
                    else:
                        front_matter[k] = v

    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else file_path.stem

    summary_match = re.search(r"##\s+Summary\s*\n([\s\S]*?)(?=##|$)", body)
    summary = summary_match.group(1).strip() if summary_match else ""

    steps_match = re.search(r"##\s+Steps\s*\n([\s\S]*?)(?=##|$)", body)
    steps_raw = steps_match.group(1).strip() if steps_match else ""
    steps = [line.strip() for line in steps_raw.split("\n") if line.strip()]

    transcript_match = re.search(r"##\s+Transcript\s*\n([\s\S]*?)(?=##|$)", body)
    transcript = transcript_match.group(1).strip() if transcript_match else body.strip()

    return {
        "id": front_matter.get("id", file_path.stem),
        "title": title,
        "creator": front_matter.get("creator", "@unknown"),
        "type": front_matter.get("type", "other"),
        "saved_at": front_matter.get("saved_at", ""),
        "tools": front_matter.get("tools", []),
        "links": front_matter.get("links", []),
        "summary": summary,
        "steps": steps,
        "transcript": transcript
    }

def get_approval_details():
    approvals = []
    if APPROVALS_DIR.exists():
        for d in sorted(APPROVALS_DIR.iterdir()):
            if d.is_dir():
                req_file = d / "APPROVAL_REQUEST.md"
                risk_level = "HIGH"
                has_code = True
                reasons = ["Contains executable scripts/dependencies"]
                if req_file.exists():
                    txt = req_file.read_text(encoding="utf-8")
                    risk_match = re.search(r"Risk Level:\s*\*\*(\w+)\*\*", txt)
                    if risk_match:
                        risk_level = risk_match.group(1)
                    has_code = "Has Executable Code: YES" in txt
                approvals.append({
                    "name": d.name,
                    "risk_level": risk_level,
                    "has_code": has_code,
                    "reasons": reasons
                })
    return approvals

class JarvisHandler(http.server.SimpleHTTPRequestHandler):

    def log_message(self, format, *args):
        # Keep console output clean for background daemon
        pass

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def read_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        return json.loads(body) if body else {}

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        route = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        if route == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            with open(HTML_FILE, "rb") as f:
                self.wfile.write(f.read())
            return

        # Zero-Interruption Mobile Share GET Webhook (for iOS Shortcuts / Android Share URL)
        if route == "/api/webhook/save":
            url = (query_params.get("url", [""])[0]).strip()
            caption = (query_params.get("caption", [""])[0]).strip()
            creator = (query_params.get("creator", ["@mobile_share"])[0]).strip()
            if not url and not caption:
                self.send_json({"error": "Missing url parameter"}, status=400)
                return
            item_id = daemon.enqueue_url(url=url, creator=creator, caption=caption, source="mobile_in_app_share")
            self.send_json({"queued": True, "id": item_id, "message": "Queued silently in ELION background daemon."})
            return

        if route == "/api/daemon/status":
            daemon._write_status()
            if daemon.status_file.exists():
                data = json.loads(daemon.status_file.read_text(encoding="utf-8"))
            else:
                data = {"status": "running"}
            self.send_json(data)
            return

        if route == "/api/notes":
            notes = []
            if VAULT_NOTES.exists():
                for p in sorted(VAULT_NOTES.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
                    try:
                        notes.append(parse_markdown_note(p))
                    except Exception as e:
                        print(f"Error reading {p.name}: {e}")
            self.send_json(notes)
            return

        if route == "/api/approvals":
            self.send_json(get_approval_details())
            return

        super().do_GET()

    def do_POST(self):
        try:
            # 1. Silent Mobile Share Webhook & Background Queue Ingest
            if self.path in ["/api/webhook/save", "/api/ingest"]:
                payload = self.read_json_body()
                url = payload.get("url", "").strip()
                title = payload.get("title", "").strip()
                creator = payload.get("creator", "@mobile_share").strip()
                caption = payload.get("caption", "").strip()

                if not url and not caption:
                    self.send_json({"error": "Provide a URL or caption"}, status=400)
                    return

                item_id = daemon.enqueue_url(
                    url=url,
                    creator=creator,
                    title=title,
                    caption=caption,
                    source="mobile_webhook" if "webhook" in self.path else "control_panel"
                )
                self.send_json({
                    "success": True,
                    "queued": True,
                    "id": item_id,
                    "message": "Video queued in background daemon for local Whisper transcription."
                })
                return

            # 2. Trigger Immediate Background Sync
            if self.path == "/api/daemon/sync":
                count = daemon.trigger_sync_now()
                self.send_json({"success": True, "processed": count})
                return

            # 3. Toggle Clipboard Auto-Capture
            if self.path == "/api/daemon/toggle_clipboard":
                daemon.clipboard_enabled = not daemon.clipboard_enabled
                daemon.log_event(f"Clipboard auto-watcher {'enabled' if daemon.clipboard_enabled else 'paused'}.")
                self.send_json({"success": True, "clipboard_watcher_active": daemon.clipboard_enabled})
                return

            # 4. Approve Skill
            if self.path == "/api/approvals/approve":
                payload = self.read_json_body()
                skill_name = payload.get("name", "")
                if queue_mgr.approve_skill(skill_name):
                    daemon.log_event(f"Approved and installed skill: {skill_name}")
                    self.send_json({"success": True, "approved": skill_name})
                else:
                    self.send_json({"error": "Skill not found"}, status=404)
                return

            # 5. Reject Skill
            if self.path == "/api/approvals/reject":
                payload = self.read_json_body()
                skill_name = payload.get("name", "")
                if queue_mgr.reject_skill(skill_name):
                    daemon.log_event(f"Rejected and removed quarantined skill: {skill_name}")
                    self.send_json({"success": True, "rejected": skill_name})
                else:
                    self.send_json({"error": "Skill not found"}, status=404)
                return

            # 6. Ask Vault (Local MCP Query)
            if self.path == "/api/ask":
                payload = self.read_json_body()
                query = payload.get("query", "").strip()
                if not query:
                    self.send_json({"error": "No query provided"}, status=400)
                    return

                q_lower = query.lower()
                if any(w in q_lower for w in ["tool", "tools", "this week"]):
                    notes = list_saved_notes(days=7, category="tool") + list_saved_notes(days=7, category="ai")
                    unique = {n["id"]: n for n in notes}.values()
                    tools_list = []
                    for n in unique:
                        tools_list.extend(n.get("tools", []))

                    answer = f"You saved {len(unique)} tool & AI videos this week. Extracted tools: {', '.join(set(tools_list)) if tools_list else 'various developer utilities'}."
                    self.send_json({
                        "answer": answer,
                        "notes": list(unique)[:4]
                    })
                    return

                results = search_vault_notes(query)
                if results:
                    top = results[0]
                    answer = f"Found matching note '{top['title']}' ({top['creator']}). Summary: {top.get('summary') or top.get('body')[:160]}..."
                else:
                    answer = f"No saved notes matched '{query}' yet."

                self.send_json({
                    "answer": answer,
                    "notes": results[:3]
                })
                return

            self.send_json({"error": "Not found"}, status=404)

        except Exception as e:
            print(f"[JarvisHandler POST Error] {e}")
            self.send_json({"error": str(e)}, status=500)

def start_server():
    daemon.start_background_threads()
    socketserver.TCPServer.allow_reuse_address = True
    local_ip = daemon.get_local_ip()
    with socketserver.TCPServer(("0.0.0.0", PORT), JarvisHandler) as httpd:
        print("============================================================")
        print(" ELION (JARVIS) — Private Background Software Daemon Active ")
        print("============================================================")
        print(f" * Laptop Control Center : http://localhost:{PORT}")
        print(f" * Mobile Share Webhook  : http://{local_ip}:{PORT}/api/webhook/save")
        print(f" * Background Worker     : ACTIVE (Whisper Local + Auto-Queue)")
        print(f" * Clipboard Auto-Save   : {'ACTIVE' if daemon.clipboard_enabled else 'OFF'}")
        print("============================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            daemon.stop()
            print("\nELION Background Daemon stopped.")

if __name__ == "__main__":
    start_server()
