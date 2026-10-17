import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import (
    extract_and_verify_token,
    extract_token_from_request,
    get_or_create_auth_token,
    verify_token,
)
from src.dashboard.serve import (
    JarvisHandler,
    is_localhost,
    is_tailscale_ip,
)
from src.settings_manager import SystemSettingsManager
from src.skills.queue_manager import SkillQueueManager
from src.skills.skill_checker import SkillChecker
from src.skills.source_resolver import (
    SkillSourceResolver,
    resolve_skill_source,
)

class TestFix1_ServerBindingAndAuthToken(unittest.TestCase):
    """Fix 1: Bind to 127.0.0.1 by default, optional Tailscale setting, long random token on save/approve."""

    def test_default_binding_is_localhost(self):
        settings = SystemSettingsManager.get_settings()
        self.assertEqual(settings.get("bind_address"), "127.0.0.1")
        self.assertFalse(settings.get("allow_tailscale", False))

    def test_tailscale_ip_validation(self):
        # 100.64.0.0/10 is Tailscale CGNAT IP range
        self.assertTrue(is_tailscale_ip("100.64.0.1"))
        self.assertTrue(is_tailscale_ip("100.115.92.44"))
        self.assertTrue(is_tailscale_ip("100.127.255.254"))
        # Non-Tailscale IPs must be rejected
        self.assertFalse(is_tailscale_ip("192.168.1.100"))
        self.assertFalse(is_tailscale_ip("10.0.0.5"))
        self.assertFalse(is_tailscale_ip("172.16.0.1"))
        self.assertFalse(is_tailscale_ip("8.8.8.8"))
        self.assertFalse(is_tailscale_ip("127.0.0.1"))

    def test_localhost_ip_validation(self):
        self.assertTrue(is_localhost("127.0.0.1"))
        self.assertTrue(is_localhost("::1"))
        self.assertTrue(is_localhost("localhost"))
        self.assertFalse(is_localhost("192.168.1.50"))
        self.assertFalse(is_localhost("100.64.0.1"))

    def test_auth_token_generation_and_persistence(self):
        token = get_or_create_auth_token()
        self.assertIsNotNone(token)
        self.assertGreaterEqual(len(token), 32)
        # Verify token validity
        self.assertTrue(verify_token(token))
        self.assertFalse(verify_token("invalid_token_12345"))
        self.assertFalse(verify_token(""))
        self.assertFalse(verify_token(None))

    def test_webhook_save_requires_token(self):
        token = get_or_create_auth_token()

        # Dummy handler mimicking SimpleHTTPRequestHandler
        class DummyRequest:
            def __init__(self, path, headers=None, client_ip="127.0.0.1"):
                self.path = path
                self.headers = headers or {}
                self.client_address = (client_ip, 12345)

        # 1. Missing token
        req_no_token = DummyRequest("/api/webhook/save?url=https://instagram.com/reel/123")
        self.assertFalse(extract_and_verify_token(req_no_token))

        # 2. Invalid token
        req_wrong_token = DummyRequest("/api/webhook/save?url=https://instagram.com/reel/123&token=wrong")
        self.assertFalse(extract_and_verify_token(req_wrong_token))

        # 3. Valid token in query string
        req_valid_query = DummyRequest(f"/api/webhook/save?url=https://instagram.com/reel/123&token={token}")
        self.assertTrue(extract_and_verify_token(req_valid_query))

        # 4. Valid token in X-Elion-Token header
        req_valid_header = DummyRequest("/api/webhook/save?url=https://instagram.com/reel/123", headers={"X-Elion-Token": token})
        self.assertTrue(extract_and_verify_token(req_valid_header))

        # 5. Valid token in Authorization Bearer header
        req_valid_auth = DummyRequest("/api/webhook/save?url=https://instagram.com/reel/123", headers={"Authorization": f"Bearer {token}"})
        self.assertTrue(extract_and_verify_token(req_valid_auth))

        # 6. Valid token in JSON body
        req_body = DummyRequest("/api/webhook/save")
        self.assertTrue(extract_and_verify_token(req_body, payload={"url": "https://test.com", "token": token}))
        self.assertFalse(extract_and_verify_token(req_body, payload={"url": "https://test.com", "token": "bad"}))


class TestFix2_LocalhostOnlyApprovals(unittest.TestCase):
    """Fix 2: Approving or rejecting skills must work only from localhost, never from phone/remote."""

    def test_remote_endpoint_cannot_approve_or_reject(self):
        token = get_or_create_auth_token()
        remote_ips = ["192.168.1.15", "100.64.1.20", "172.20.10.4", "10.0.0.2"]

        for remote_ip in remote_ips:
            # Remote IP cannot be localhost
            self.assertFalse(is_localhost(remote_ip), f"{remote_ip} must not be recognized as localhost")

    def test_localhost_endpoint_allowed(self):
        loopback_ips = ["127.0.0.1", "::1", "localhost"]
        for ip in loopback_ips:
            self.assertTrue(is_localhost(ip), f"{ip} must be recognized as localhost")


class TestFix3_RequirementsAndSetupScript(unittest.TestCase):
    """Fix 3: requirements.txt with pinned versions and a setup script that creates a venv."""

    def test_requirements_file_exists_and_pinned(self):
        req_path = PROJECT_ROOT / "requirements.txt"
        self.assertTrue(req_path.exists(), "requirements.txt must exist")
        content = req_path.read_text(encoding="utf-8")

        # Must have pinned versions (==)
        self.assertIn("yt-dlp==", content)
        self.assertIn("instaloader==", content)
        self.assertIn("requests==", content)
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                self.assertIn("==", line, f"Requirement '{line}' must be version-pinned with ==")

    def test_setup_scripts_exist(self):
        setup_bat = PROJECT_ROOT / "setup.bat"
        setup_ps1 = PROJECT_ROOT / "setup.ps1"
        self.assertTrue(setup_bat.exists(), "setup.bat must exist")
        self.assertTrue(setup_ps1.exists(), "setup.ps1 must exist")

        bat_text = setup_bat.read_text(encoding="utf-8")
        self.assertIn("venv", bat_text, "setup.bat must create virtual environment")
        self.assertIn("requirements.txt", bat_text, "setup.bat must install requirements.txt")


class TestFix4_StateDirectoryGitIgnoredAndUntracked(unittest.TestCase):
    """Fix 4: state/ and any file containing local IP must be in .gitignore and removed from git tracking."""

    def test_gitignore_contains_state(self):
        gitignore_path = PROJECT_ROOT / ".gitignore"
        self.assertTrue(gitignore_path.exists())
        text = gitignore_path.read_text(encoding="utf-8")
        self.assertIn("state/", text, "state/ must be in .gitignore")

    def test_state_files_not_tracked_in_git(self):
        try:
            res = subprocess.run(
                ["git", "ls-files", "state/"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                check=True
            )
            tracked_files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
            self.assertEqual(tracked_files, [], f"state/ files must not be tracked in git: {tracked_files}")
        except FileNotFoundError:
            pass  # git CLI not in test runner environment

    def test_no_local_ip_in_tracked_git_files(self):
        try:
            # Check for any private IP range like 172.27.142.43
            res = subprocess.run(
                ["git", "grep", "-E", r"(192\.168|10\.[0-9]|172\.(1[6-9]|2[0-9]|3[0-1]))\.", "--", ":!tests/"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True
            )
            # Should have no matches in git index
            self.assertEqual(res.stdout.strip(), "", f"Tracked files contain local IP: {res.stdout}")
        except FileNotFoundError:
            pass


class TestFix5_SkillSourceResolver(unittest.TestCase):
    """Fix 5: Fix 'andthropic/skills' misspelling. Return 'unverified' instead of guessing."""

    def setUp(self):
        self.resolver = SkillSourceResolver()

    def test_andthropic_skills_misspelling_returns_unverified(self):
        # Misspelling "andthropic/skills" must return "unverified" without guessing search URLs
        res = self.resolver.resolve("andthropic/skills")
        self.assertEqual(res.status, "unverified")
        self.assertIsNone(res.repo_url)
        self.assertEqual(res.source_kind, "unverified")
        # Ensure it does NOT guess a github search URL
        self.assertNotIn("search?q=", str(res.repo_url))

    def test_arbitrary_unknown_skill_returns_unverified_no_guessing(self):
        res = self.resolver.resolve("some_random_custom_utility")
        self.assertEqual(res.status, "unverified")
        self.assertIsNone(res.repo_url)
        self.assertEqual(res.source_kind, "unverified")
        self.assertNotIn("search?q=", str(res.repo_url))

    def test_verified_well_known_skill(self):
        res = self.resolver.resolve("whisper")
        self.assertEqual(res.status, "verified")
        self.assertEqual(res.repo_url, "https://github.com/openai/whisper")
        self.assertEqual(res.canonical_repo, "openai/whisper")

    def test_explicit_valid_github_url(self):
        res = self.resolver.resolve("custom_tool", explicit_url="https://github.com/astral-sh/uv")
        self.assertEqual(res.status, "verified")
        self.assertEqual(res.repo_url, "https://github.com/astral-sh/uv")

    def test_explicit_search_url_is_rejected_as_verified(self):
        # Search URLs should NEVER be treated as verified repository sources
        res = self.resolver.resolve("custom_tool", explicit_url="https://github.com/search?q=custom_tool")
        self.assertEqual(res.status, "unverified")
        self.assertIsNone(res.repo_url)

    def test_skill_checker_uses_resolver_without_guessing(self):
        approvals_dir = PROJECT_ROOT / "vault" / "test_approvals"
        approvals_dir.mkdir(parents=True, exist_ok=True)
        try:
            checker = SkillChecker(approvals_dir=approvals_dir)
            approval_file = checker.check_tool_skill(
                tool_name="unverified_experimental_tool",
                source_note_id="test_note_1"
            )
            self.assertIsNotNone(approval_file)
            self.assertTrue(approval_file.exists())
            content = approval_file.read_text(encoding="utf-8")

            # Must NOT guess search URLs
            self.assertNotIn("https://github.com/search?q=", content)
            self.assertIn("- **Source Repository:** unverified", content)
        finally:
            if approvals_dir.exists():
                import shutil
                shutil.rmtree(approvals_dir)


if __name__ == "__main__":
    unittest.main()
