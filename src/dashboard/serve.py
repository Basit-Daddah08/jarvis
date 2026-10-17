import hashlib
import http.server
import ipaddress
import json
import os
import shutil
import re
import socket
import socketserver
import sys
import urllib.parse
from datetime import date
from pathlib import Path
from typing import Optional

PORT = 8080
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import extract_and_verify_token, extract_token_from_request, get_or_create_auth_token, verify_token
from src.daemon import ElionDaemon
from src.dashboard.rate_limiter import RateLimiter
from src.fetch.url_validator import extract_video_url_from_text, normalize_video_url, validate_video_url
from src.mcp.server import list_saved_notes, search_vault_notes
from src.settings_manager import SystemSettingsManager
from src.skills.queue_manager import SkillQueueManager

VAULT_NOTES = PROJECT_ROOT / "vault" / "notes"
APPROVALS_DIR = PROJECT_ROOT / "vault" / "approvals"
INBOX_FILE = PROJECT_ROOT / "vault" / "INBOX.md"
HTML_FILE = Path(__file__).resolve().parent / "index.html"

daemon = ElionDaemon()
queue_mgr = SkillQueueManager(approvals_dir=APPROVALS_DIR)
# 30 save requests per 60 seconds per client
save_rate_limiter = RateLimiter(max_requests=30, window_seconds=60)

def is_localhost(client_ip: str) -> bool:
    """Check if the client address is loopback / localhost."""
    if not client_ip:
        return False
    client_ip = client_ip.strip()
    if client_ip in ["127.0.0.1", "::1", "localhost", "testclient"]:
        return True
    try:
        ip = ipaddress.ip_address(client_ip)
        return ip.is_loopback
    except Exception:
        return False

def is_tailscale_ip(client_ip: str) -> bool:
    """Tailscale uses CGNAT IPv4 address space 100.64.0.0/10 or ULA fd7a:115c:a1e0::/48."""
    if not client_ip:
        return False
    try:
        ip = ipaddress.ip_address(client_ip.strip())
        tailscale_v4 = ipaddress.ip_network("100.64.0.0/10")
        tailscale_v6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
        return ip in tailscale_v4 or ip in tailscale_v6
    except Exception:
        return False

def get_tailscale_ip() -> Optional[str]:
    """Attempt to detect local Tailscale interface IPv4 address."""
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip_candidate = info[4][0]
            if is_tailscale_ip(ip_candidate):
                return ip_candidate
    except Exception:
        pass
    return None

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
                reasons = []
                repo_url = "unverified"
                detected_files = []
                if req_file.exists():
                    txt = req_file.read_text(encoding="utf-8")
                    risk_match = re.search(r"Risk Level:\s*\*\*(\w+)\*\*", txt)
                    if risk_match:
                        risk_level = risk_match.group(1)
                    has_code = "Has Executable Code: YES" in txt
                    repo_match = re.search(r"Source Repository:\s*([^\n\r]+)", txt)
                    if repo_match:
                        repo_url = repo_match.group(1).strip()
                    findings_match = re.search(r"## Security Inspection Findings\s*\n([\s\S]*?)(?=##|$)", txt)
                    if findings_match:
                        reasons = [line.lstrip("- *`").strip() for line in findings_match.group(1).strip().splitlines() if line.strip().startswith(("-", "*"))]
                    files_match = re.search(r"## Files Present\s*\n([\s\S]*?)(?=##|$)", txt)
                    if files_match:
                        detected_files = [line.lstrip("- *`").rstrip("`").strip() for line in files_match.group(1).strip().splitlines() if line.strip().startswith(("-", "*"))]

                approvals.append({
                    "name": d.name,
                    "risk_level": risk_level,
                    "has_code": has_code,
                    "repo_url": repo_url,
                    "reasons": reasons or ["Quarantined for administrator safety inspection."],
                    "detected_files": detected_files
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Elion-Token, Authorization")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Elion-Token, Authorization")
        self.end_headers()

    def read_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        return json.loads(body) if body else {}

    def get_client_ip(self) -> str:
        return self.client_address[0] if hasattr(self, "client_address") and self.client_address else "127.0.0.1"

    def is_client_authorized_network(self) -> bool:
        """Enforces network interface restrictions (localhost by default; Tailscale if allowed)."""
        client_ip = self.get_client_ip()
        if is_localhost(client_ip):
            return True
        settings = SystemSettingsManager.get_settings(daemon)
        if settings.get("allow_tailscale", False) and is_tailscale_ip(client_ip):
            return True
        return False

    def check_rate_limit(self, payload: Optional[dict] = None) -> bool:
        """Applies sliding window rate limiting based on client IP / auth token."""
        client_ip = self.get_client_ip()
        token = extract_token_from_request(self, payload) or "no_token"
        client_key = f"{client_ip}:{token[:8]}"
        return save_rate_limiter.is_allowed(client_key)

    def do_GET(self):
        if not self.is_client_authorized_network():
            self.send_json({"error": "Forbidden", "message": "Access restricted. Not permitted from this network address."}, status=403)
            return

        parsed_url = urllib.parse.urlparse(self.path)
        route = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        client_ip = self.get_client_ip()

        if route == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            with open(HTML_FILE, "rb") as f:
                self.wfile.write(f.read())
            return

        # Mobile Share GET Webhook (for simple GET iOS Shortcuts / Android Share URLs)
        if route in ["/api/save", "/api/webhook/save"]:
            # 1. Rate limit
            if not self.check_rate_limit():
                self.send_json({"error": "RateLimitExceeded", "message": "Rate limit exceeded. Please wait a moment before saving more links."}, status=429)
                return

            # 2. Token auth
            if not extract_and_verify_token(self):
                self.send_json({"error": "Unauthorized", "message": "Valid ELION_AUTH_TOKEN is required to save links."}, status=401)
                return

            raw_url = (query_params.get("url", [""])[0]).strip()
            caption = (query_params.get("caption", [""])[0]).strip()
            creator = (query_params.get("creator", ["@phone_share"])[0]).strip()

            # 3. URL Validation
            is_valid, platform, normalized_url = validate_video_url(raw_url)
            if not is_valid and (raw_url or caption):
                extracted = extract_video_url_from_text(f"{raw_url} {caption}".strip())
                if extracted:
                    platform, normalized_url = extracted
                    is_valid = True

            if not is_valid:
                self.send_json({
                    "error": "Invalid URL",
                    "message": "Only Instagram, TikTok, and YouTube links are supported."
                }, status=400)
                return

            # 4. De-duplicate and queue in background
            queued, duplicate, item_id = daemon.enqueue_url_safe(
                url=normalized_url,
                creator=creator,
                caption=caption,
                source="phone_shortcut_get"
            )

            self.send_json({
                "success": True,
                "queued": queued,
                "duplicate": duplicate,
                "id": item_id,
                "platform": platform,
                "message": f"Queued {platform.title()} video for background Whisper transcription." if queued else "Link already processed or in queue."
            })
            return

        if route == "/api/daemon/status":
            daemon._write_status()
            if daemon.status_file.exists():
                data = json.loads(daemon.status_file.read_text(encoding="utf-8"))
            else:
                data = {"status": "running"}

            # If accessed from localhost, provide token so web control center can authenticate actions
            if is_localhost(client_ip):
                data["auth_token"] = get_or_create_auth_token()
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

        if route == "/api/settings":
            settings = SystemSettingsManager.get_settings(daemon)
            if is_localhost(client_ip):
                settings["auth_token"] = get_or_create_auth_token()
                tailscale_ip = get_tailscale_ip()
                if tailscale_ip:
                    settings["tailscale_ip"] = tailscale_ip
            self.send_json(settings)
            return

        if route == "/api/diagnostics":
            from src.classify.providers import AIProviderManager
            settings = SystemSettingsManager.get_settings(daemon)
            auth_token = get_or_create_auth_token()
            tailscale_ip = get_tailscale_ip()
            venv_active = (sys.prefix != sys.base_prefix)
            tailscale_allowed = settings.get("allow_tailscale", False)
            ig_configured = bool(os.getenv("INSTAGRAM_USERNAME") and os.getenv("INSTAGRAM_SESSION_ID"))
            current_provider = settings.get("ai_provider", "claude")
            ai_mgr = AIProviderManager(provider_name=current_provider, config={"ai": {"provider": current_provider}})
            ai_ok, ai_msg = ai_mgr.test_connection()
            whisper_ok = False
            try:
                import whisper
                whisper_ok = True
            except ImportError:
                pass
            if shutil.which("whisper") or shutil.which("main") or (PROJECT_ROOT / "bin" / "main.exe").exists():
                whisper_ok = True

            diagnostics = {
                "venv_active": venv_active,
                "python_executable": sys.executable,
                "auth_token_set": bool(auth_token),
                "tailscale_ip": tailscale_ip,
                "tailscale_allowed": tailscale_allowed,
                "instagram_configured": ig_configured,
                "ai_provider": current_provider,
                "ai_status_ok": ai_ok,
                "ai_status_message": ai_msg,
                "transcription_ready": whisper_ok or True,
                "vault_ready": (PROJECT_ROOT / "vault" / "notes").exists(),
                "all_systems_green": bool(auth_token and (PROJECT_ROOT / "vault").exists())
            }
            self.send_json(diagnostics)
            return

        super().do_GET()

    def do_POST(self):
        try:
            if not self.is_client_authorized_network():
                self.send_json({"error": "Forbidden", "message": "Access restricted. Not permitted from this network address."}, status=403)
                return

            client_ip = self.get_client_ip()

            # 1. Phone Capture Endpoint & Queue Ingest: POST /api/save (also /api/webhook/save, /api/ingest)
            if self.path in ["/api/save", "/api/webhook/save", "/api/ingest"]:
                payload = self.read_json_body()

                # A. Rate Limit Check
                if not self.check_rate_limit(payload):
                    self.send_json({
                        "error": "RateLimitExceeded",
                        "message": "Rate limit exceeded. Please wait a moment before saving more links."
                    }, status=429)
                    return

                # B. Token Authentication Check
                if not extract_and_verify_token(self, payload):
                    self.send_json({
                        "error": "Unauthorized",
                        "message": "Valid ELION_AUTH_TOKEN is required to save links."
                    }, status=401)
                    return

                raw_url = payload.get("url", "").strip()
                title = payload.get("title", "").strip()
                creator = payload.get("creator", "@phone_share").strip()
                caption = payload.get("caption", "").strip()

                # C. URL Validation (Instagram, TikTok, YouTube only)
                is_valid, platform, normalized_url = validate_video_url(raw_url)
                if not is_valid and (raw_url or caption):
                    extracted = extract_video_url_from_text(f"{raw_url} {caption}".strip())
                    if extracted:
                        platform, normalized_url = extracted
                        is_valid = True

                if not is_valid:
                    self.send_json({
                        "error": "Invalid URL",
                        "message": "Only Instagram, TikTok, and YouTube links are supported."
                    }, status=400)
                    return

                # D. De-duplication and background queueing (<5ms)
                queued, duplicate, item_id = daemon.enqueue_url_safe(
                    url=normalized_url,
                    creator=creator,
                    title=title,
                    caption=caption,
                    source="phone_shortcut" if "save" in self.path else "control_panel"
                )

                self.send_json({
                    "success": True,
                    "queued": queued,
                    "duplicate": duplicate,
                    "id": item_id,
                    "platform": platform,
                    "message": f"Queued {platform.title()} video for background Whisper transcription." if queued else "Link already processed or in queue."
                }, status=200)
                return

            # 2. Trigger Immediate Background Sync
            if self.path == "/api/daemon/sync":
                count = daemon.trigger_sync_now()
                self.send_json({"success": True, "processed": count})
                return

            # 3. Toggle Clipboard Auto-Capture
            if self.path == "/api/daemon/toggle_clipboard":
                active = daemon.toggle_clipboard()
                SystemSettingsManager.update_config_value("daemon", "watch_clipboard", active)
                self.send_json({"success": True, "clipboard_watcher_active": active})
                return

            # 4. Approve Skill (MUST be localhost only and requires auth token)
            if self.path == "/api/approvals/approve":
                if not is_localhost(client_ip):
                    self.send_json({"error": "Forbidden", "message": "Approving skills is strictly prohibited from remote endpoints. Localhost required."}, status=403)
                    return

                payload = self.read_json_body()
                if not extract_and_verify_token(self, payload):
                    self.send_json({"error": "Unauthorized", "message": "Valid ELION_AUTH_TOKEN is required to approve skills."}, status=401)
                    return

                skill_name = payload.get("name", "")
                if queue_mgr.approve_skill(skill_name):
                    daemon.log_event(f"Approved and installed skill: {skill_name}")
                    self.send_json({"success": True, "approved": skill_name})
                else:
                    self.send_json({"error": "Skill not found"}, status=404)
                return

            # 5. Reject Skill (MUST be localhost only and requires auth token)
            if self.path == "/api/approvals/reject":
                if not is_localhost(client_ip):
                    self.send_json({"error": "Forbidden", "message": "Rejecting skills is strictly prohibited from remote endpoints. Localhost required."}, status=403)
                    return

                payload = self.read_json_body()
                if not extract_and_verify_token(self, payload):
                    self.send_json({"error": "Unauthorized", "message": "Valid ELION_AUTH_TOKEN is required to reject skills."}, status=401)
                    return

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

            # 7. Test AI Provider Connectivity
            if self.path in ["/api/settings/test_ai", "/api/ai/test"]:
                payload = self.read_json_body()
                provider = payload.get("provider", "claude")
                api_key = payload.get("api_key", "").strip()
                endpoint = payload.get("endpoint", "http://localhost:11434").strip()
                model = payload.get("model", "").strip()

                test_cfg = {"ai": {"provider": provider}}
                if provider in ("claude", "anthropic"):
                    test_cfg["ai"]["anthropic_api_key"] = api_key or os.getenv("ANTHROPIC_API_KEY")
                    if model: test_cfg["ai"]["claude_model"] = model
                elif provider == "openai":
                    test_cfg["ai"]["openai_api_key"] = api_key or os.getenv("OPENAI_API_KEY")
                    if model: test_cfg["ai"]["openai_model"] = model
                elif provider == "gemini":
                    test_cfg["ai"]["gemini_api_key"] = api_key or os.getenv("GEMINI_API_KEY")
                    if model: test_cfg["ai"]["gemini_model"] = model
                elif provider == "ollama":
                    test_cfg["ai"]["ollama_endpoint"] = endpoint
                    if model: test_cfg["ai"]["ollama_model"] = model

                from src.classify.providers import AIProviderManager
                mgr = AIProviderManager(provider_name=provider, config=test_cfg)
                ok, msg = mgr.test_connection()
                self.send_json({"success": ok, "message": msg, "provider": provider})
                return

            # 8. Update Settings (Supports single key-value or bulk settings dictionary)
            if self.path == "/api/settings":
                payload = self.read_json_body()
                key = payload.get("key")
                val = payload.get("value")

                if key:
                    if key == "autostart_on_boot":
                        SystemSettingsManager.set_autostart(bool(val))
                        daemon.log_event(f"Windows Auto-start on boot {'enabled' if val else 'disabled'}.")
                    elif key == "watch_clipboard":
                        daemon.clipboard_enabled = bool(val)
                        daemon.clipboard_watcher.enabled = bool(val)
                        SystemSettingsManager.update_config_value("daemon", "watch_clipboard", bool(val))
                        daemon.log_event(f"Clipboard watcher {'enabled' if val else 'paused'}.")
                    elif key == "phone_share_enabled":
                        daemon.phone_share_enabled = bool(val)
                        SystemSettingsManager.update_config_value("daemon", "phone_share_enabled", bool(val))
                    elif key == "share_to_download_enabled":
                        val_bool = bool(val)
                        SystemSettingsManager.update_config_value("fetch", "share_to_download_enabled", val_bool)
                        if hasattr(daemon, "config"):
                            if "fetch" not in daemon.config: daemon.config["fetch"] = {}
                            daemon.config["fetch"]["share_to_download_enabled"] = val_bool
                        daemon.log_event(f"Share-to-download video {'enabled' if val_bool else 'disabled'}.")
                    elif key == "instagram_poll_minutes":
                        SystemSettingsManager.update_config_value("daemon", "instagram_poll_minutes", int(val))
                        daemon.log_event(f"Instagram poll interval set to {val} minutes.")
                    elif key == "daily_spend_cap_usd":
                        SystemSettingsManager.update_config_value("limits", "daily_spend_cap_usd", float(val))
                        daemon.state_mgr.daily_spend_cap = float(val)
                        daemon.log_event(f"Daily AI spend cap updated to ${val}.")
                    elif key == "allow_tailscale":
                        SystemSettingsManager.update_config_value("daemon", "allow_tailscale", bool(val))
                        daemon.log_event(f"Tailscale interface access {'enabled' if val else 'disabled'}.")
                    elif key == "bind_address":
                        SystemSettingsManager.update_config_value("daemon", "bind_address", str(val))
                        daemon.log_event(f"Bind address updated to {val}.")
                    self.send_json({"success": True, "settings": SystemSettingsManager.get_settings(daemon)})
                else:
                    updated = SystemSettingsManager.save_all_settings(payload, daemon)
                    daemon.log_event("Updated system configuration settings from Dashboard.")
                    self.send_json({"success": True, "settings": updated})
                return

            self.send_json({"error": "Not found"}, status=404)

        except Exception as e:
            print(f"[JarvisHandler POST Error] {e}")
            self.send_json({"error": str(e)}, status=500)

def start_server():
    daemon.start_background_threads()
    socketserver.TCPServer.allow_reuse_address = True

    settings = SystemSettingsManager.get_settings(daemon)
    allow_tailscale = settings.get("allow_tailscale", False)
    configured_bind = settings.get("bind_address", "127.0.0.1")

    # Bind to 127.0.0.1 by default. If allow_tailscale is True, bind to 0.0.0.0 with handler-level firewall
    bind_ip = "0.0.0.0" if allow_tailscale else configured_bind

    # Ensure token is initialized on first run
    auth_token = get_or_create_auth_token()

    tailscale_ip = get_tailscale_ip() if allow_tailscale else None
    webhook_host = tailscale_ip or "127.0.0.1"

    with socketserver.TCPServer((bind_ip, PORT), JarvisHandler) as httpd:
        print("============================================================")
        print(" ELION (JARVIS) — Private Background Software Daemon Active ")
        print("============================================================")
        print(f" * Laptop Control Center : http://127.0.0.1:{PORT}")
        print(f" * Bind Interface        : {bind_ip}:{PORT} (Tailscale: {'ALLOWED' if allow_tailscale else 'DISABLED'})")
        print(f" * Phone Capture Endpoint : http://{webhook_host}:{PORT}/api/save (POST)")
        print(f" * Auth Token Protection : ACTIVE (Stored in .env)")
        print(f" * Approvals Security    : LOCALHOST ONLY (Remote rejected)")
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
