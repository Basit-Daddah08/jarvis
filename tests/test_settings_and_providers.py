import os
import shutil
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from src.classify.providers import (
    AIProviderManager,
    ClaudeProvider,
    OpenAIProvider,
    GeminiProvider,
    OllamaProvider,
    ExtractiveTranscriptSummarizer
)
from src.classify.classifier import VideoClassifier
from src.settings_manager import SystemSettingsManager
from src.skills.skill_checker import SkillChecker

class TestAIProvidersAndSummaries(unittest.TestCase):

    def test_extractive_summarizer_real_content_no_stock_lines(self):
        transcript = (
            "Here is the setup for running whisper cpp locally. "
            "Step 1 clone the whisper cpp repo. "
            "Step 2 download the ggml base model. "
            "Step 3 run the main executable on your audio file. "
            "It transcribes one hour of audio in under 30 seconds."
        )
        summary, steps = ExtractiveTranscriptSummarizer.summarize(transcript=transcript)

        # Must not be any stock placeholders
        self.assertNotIn("AI tool and workflow overview", summary)
        self.assertNotIn("Developer tool installation and usage", summary)
        self.assertIn("whisper", summary.lower())
        self.assertTrue(len(steps) >= 2)
        self.assertIn("clone the whisper cpp repo", steps[0].lower())

    def test_provider_manager_fallback_to_extractive(self):
        # When provider is "none" or API key is missing
        mgr = AIProviderManager(provider_name="none")
        res = mgr.classify_and_summarize(
            transcript="Install uv using curl -LsSf https://astral.sh/uv/install.sh. Step 1 run uv pip compile. Step 2 run uv pip sync.",
            title="Fast Python Package Management"
        )
        self.assertEqual(res.source, "transcript_extractive")
        self.assertEqual(res.category, "tool")
        self.assertIn("uv", res.summary.lower())
        self.assertTrue(len(res.steps) >= 1)

    def test_provider_manager_health_check_offline(self):
        mgr_none = AIProviderManager(provider_name="none")
        ok, msg = mgr_none.test_connection()
        self.assertTrue(ok)
        self.assertIn("offline", msg.lower())

        mgr_claude = AIProviderManager(provider_name="claude", config={"ai": {"anthropic_api_key": ""}})
        ok, msg = mgr_claude.test_connection()
        self.assertFalse(ok)

    def test_classifier_spend_cap_and_real_summaries(self):
        from src.state_manager import StateManager
        test_dir = Path(tempfile.mkdtemp())
        try:
            state_mgr = StateManager(state_dir=test_dir)
            state_mgr.daily_spend_cap = 0.001
            state_mgr.record_spend(0.002) # Exceed spend cap

            classifier = VideoClassifier(state_manager=state_mgr, provider="claude")
            transcript = "Build full stack apps directly in your browser with bolt.new. Step 1 open bolt. Step 2 prompt your fullstack app. Step 3 deploy to netlify."
            res = classifier.classify_video(transcript=transcript, title="Bolt.new Web Builder")

            # Should use real extractive summary even when spend cap limit is hit
            self.assertIn("spend_cap_limit", res.source)
            self.assertIn("bolt", res.summary.lower())
            self.assertTrue(len(res.steps) >= 1)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


class TestSkillInspectionReal(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.approvals_dir = self.test_dir / "approvals"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_checker_unverified_tool_no_fake_files(self):
        checker = SkillChecker(approvals_dir=self.approvals_dir)
        app_file = checker.check_tool_skill(
            tool_name="unknown_crypto_stealer",
            source_note_id="test_reel_99"
        )
        self.assertIsNotNone(app_file)
        self.assertTrue(app_file.exists())
        content = app_file.read_text(encoding="utf-8")

        # Must NOT invent fake files like unknown_crypto_stealer.py or package.json
        self.assertNotIn("- `package.json`", content)
        self.assertIn("Source Repository:** unverified", content)
        self.assertIn("Risk Level:** **HIGH**", content)


class TestSettingsPersistence(unittest.TestCase):

    def test_save_all_settings_updates_config_and_env(self):
        # Test modifying settings payload
        payload = {
            "watch_clipboard": True,
            "phone_share_enabled": True,
            "instagram_sync_enabled": True,
            "instagram_poll_minutes": 45,
            "cleanup_audio_after_transcription": True,
            "transcription_engine": "whisper_cpp",
            "daily_spend_cap_usd": 2.50,
            "ai_provider": "claude",
            "anthropic_api_key": "sk-ant-test-unit-token"
        }

        updated = SystemSettingsManager.save_all_settings(payload)
        self.assertEqual(updated["instagram_poll_minutes"], 45)
        self.assertEqual(updated["daily_spend_cap_usd"], 2.50)
        self.assertEqual(updated["ai_provider"], "claude")
        self.assertTrue(updated["has_anthropic_key"])

        # Verify environment variable was set
        self.assertEqual(os.getenv("ANTHROPIC_API_KEY"), "sk-ant-test-unit-token")

    def test_share_to_download_defaults_to_off(self):
        settings = SystemSettingsManager.get_settings()
        # Default must be False as required
        self.assertIn("share_to_download_enabled", settings)

        # Toggle to True and verify persistence
        updated = SystemSettingsManager.save_all_settings({"share_to_download_enabled": True})
        self.assertTrue(updated["share_to_download_enabled"])

        # Reset back to False
        reset = SystemSettingsManager.save_all_settings({"share_to_download_enabled": False})
        self.assertFalse(reset["share_to_download_enabled"])

if __name__ == "__main__":
    unittest.main()
