import shutil
import tempfile
import unittest
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.fetch.base import VideoItem
from src.fetch.manual_adapter import ManualDropAdapter
from src.notes.writer import NoteWriter
from src.state_manager import StateManager
from src.transcribe.transcriber import AudioTranscriber

class TestPhase1Pipeline(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.state_dir = self.test_dir / "state"
        self.notes_dir = self.test_dir / "vault" / "notes"
        self.inbox_file = self.test_dir / "vault" / "INBOX.md"
        self.drop_dir = self.test_dir / "vault" / "drop"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_state_manager_idempotency(self):
        mgr = StateManager(self.state_dir)
        self.assertFalse(mgr.is_processed("reel_123"))
        mgr.mark_processed("reel_123")
        self.assertTrue(mgr.is_processed("reel_123"))

        # Re-instantiate to check persistence from disk
        mgr2 = StateManager(self.state_dir)
        self.assertTrue(mgr2.is_processed("reel_123"))
        self.assertFalse(mgr2.is_processed("reel_456"))

    def test_state_manager_spend_cap(self):
        mgr = StateManager(self.state_dir)
        self.assertTrue(mgr.can_spend(0.10))
        mgr.record_spend(0.95)
        self.assertFalse(mgr.can_spend(0.10)) # Exceeds $1.00 cap
        self.assertTrue(mgr.can_spend(0.04))

    def test_note_writer_and_inbox(self):
        writer = NoteWriter(self.notes_dir, self.inbox_file)
        note_p = writer.write_note(
            item_id="vid_test_01",
            creator="@elion_founder",
            saved_at="2026-10-10",
            title="Building with MCP Tools",
            transcript="This is a test transcript of the video content.",
            note_type="other"
        )

        self.assertTrue(note_p.exists())
        with open(note_p, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('id: vid_test_01', content)
        self.assertIn('creator: "@elion_founder"', content)
        self.assertIn('type: other', content)
        self.assertIn('# Building with MCP Tools', content)
        self.assertIn('This is a test transcript of the video content.', content)

        # Check INBOX.md
        self.assertTrue(self.inbox_file.exists())
        with open(self.inbox_file, "r", encoding="utf-8") as f:
            inbox_text = f.read()
        self.assertIn('### [Building with MCP Tools](notes/vid_test_01.md)', inbox_text)
        self.assertIn('@elion_founder', inbox_text)

    def test_manual_adapter(self):
        drop = self.drop_dir
        drop.mkdir(parents=True, exist_ok=True)

        # Write sample manifest
        manifest_file = drop / "test_saves.json"
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write('[{"id": "reel_abc", "url": "https://instagram.com/reel/reel_abc", "creator": "@techlead", "title": "Top 3 CLI Tools"}]')

        mgr = StateManager(self.state_dir)
        adapter = ManualDropAdapter(drop, state_checker=mgr)
        items = adapter.fetch_new_items()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "reel_abc")
        self.assertEqual(items[0].creator, "@techlead")

if __name__ == "__main__":
    unittest.main()
