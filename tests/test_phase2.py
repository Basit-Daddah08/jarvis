import shutil
import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.classify.keywords import classify_by_keywords, extract_links, extract_tools_from_text
from src.classify.classifier import VideoClassifier
from src.notes.writer import NoteWriter
from src.state_manager import StateManager

class TestPhase2Classification(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.state_dir = self.test_dir / "state"
        self.notes_dir = self.test_dir / "vault" / "notes"
        self.inbox_file = self.test_dir / "vault" / "INBOX.md"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_classify_tool_keywords(self):
        text = "Check out this terminal tool on https://github.com/astral-sh/uv. Run pip install uv or cargo install. Step 1 clone the repo. Step 2 run the cli."
        res = classify_by_keywords(text)
        self.assertIn(res.category, ["tool", "ai"])
        self.assertTrue(len(res.steps) >= 1)
        self.assertIn("https://github.com/astral-sh/uv", res.links)

    def test_classify_ai_keywords(self):
        text = "Here is how to set up an autonomous AI agent with Claude Code and whisper models. First install the model. Next configure your prompt."
        res = classify_by_keywords(text)
        self.assertEqual(res.category, "ai")
        self.assertTrue(len(res.steps) >= 1)

    def test_classify_other_keywords(self):
        text = "Discipline is the bridge between goals and accomplishment. Build great habits, go to the gym, and maintain stoic focus every morning."
        res = classify_by_keywords(text)
        self.assertEqual(res.category, "other")
        self.assertEqual(len(res.steps), 0)

    def test_tool_extraction(self):
        text = "We use whisper.cpp and ollama with docker to run local inferences."
        tools = extract_tools_from_text(text)
        self.assertIn("whisper.cpp", tools)
        self.assertIn("ollama", tools)
        self.assertIn("docker", tools)

    def test_note_generation_tool_vs_other(self):
        writer = NoteWriter(self.notes_dir, self.inbox_file)

        # Tool note with summary, steps, and tools
        tool_note = writer.write_note(
            item_id="tool_101",
            creator="@coder",
            saved_at="2026-10-10",
            title="Fast Python with UV",
            transcript="uv is 100x faster than pip.",
            note_type="tool",
            tools=["uv"],
            links=["https://github.com/astral-sh/uv"],
            summary="UV is a blisteringly fast Python package manager.",
            steps=["Install uv via curl or pip", "Run uv pip install"]
        )

        with open(tool_note, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('type: tool', content)
        self.assertIn('## Summary', content)
        self.assertIn('## Steps', content)
        self.assertIn('1. Install uv via curl or pip', content)
        self.assertIn('## Transcript', content)

        # Other note with full transcript
        other_note = writer.write_note(
            item_id="mindset_202",
            creator="@naval",
            saved_at="2026-10-10",
            title="On Specific Knowledge",
            transcript="Specific knowledge cannot be taught, but it can be learned.",
            note_type="other"
        )

        with open(other_note, "r", encoding="utf-8") as f:
            other_content = f.read()

        self.assertIn('type: other', other_content)
        self.assertNotIn('## Steps', other_content)
        self.assertIn('## Transcript', other_content)
        self.assertIn('Specific knowledge cannot be taught', other_content)

if __name__ == "__main__":
    unittest.main()
