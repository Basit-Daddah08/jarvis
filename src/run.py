import argparse
import os
import sys
import tomllib
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.classify.classifier import VideoClassifier
from src.fetch.base import VideoItem
from src.fetch.instagram_adapter import InstagramSavedAdapter
from src.fetch.manual_adapter import ManualDropAdapter
from src.notes.writer import NoteWriter
from src.skills.skill_checker import SkillChecker
from src.state_manager import StateManager
from src.transcribe.transcriber import AudioTranscriber

def load_config() -> dict:
    config_path = PROJECT_ROOT / "config.toml"
    if config_path.exists():
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    return {}

def run_pipeline(adapter_override: str = None, limit_override: int = None):
    config = load_config()
    limits_cfg = config.get("limits", {})
    fetch_cfg = config.get("fetch", {})
    transcribe_cfg = config.get("transcribe", {})
    safety_cfg = config.get("safety", {})

    state_mgr = StateManager(PROJECT_ROOT / "state")
    note_writer = NoteWriter(
        notes_dir=PROJECT_ROOT / "vault" / "notes",
        inbox_file=PROJECT_ROOT / "vault" / "INBOX.md"
    )
    transcriber = AudioTranscriber(
        model_name=transcribe_cfg.get("model", "base.en")
    )
    classifier = VideoClassifier(state_manager=state_mgr)
    skill_checker = SkillChecker(
        approvals_dir=PROJECT_ROOT / "vault" / "approvals",
        queue_all_by_default=safety_cfg.get("queue_markdown_skills", True)
    )

    adapter_name = adapter_override or fetch_cfg.get("active_adapter", "manual_drop")
    max_items = limit_override or limits_cfg.get("max_items_per_batch", 10)

    print(f"==================================================")
    print(f"JARVIS Nightly Pipeline (Phases 1-4 Active)")
    print(f"Adapter: {adapter_name} | Max items: {max_items}")
    print(f"==================================================")

    # Instantiate selected adapter
    if adapter_name == "instagram":
        adapter = InstagramSavedAdapter(state_checker=state_mgr)
    elif adapter_name == "youtube":
        from src.fetch.youtube_adapter import YouTubeSavedAdapter
        adapter = YouTubeSavedAdapter(state_checker=state_mgr)
    elif adapter_name == "tiktok":
        from src.fetch.tiktok_adapter import TikTokSavedAdapter
        adapter = TikTokSavedAdapter(state_checker=state_mgr)
    else:
        adapter = ManualDropAdapter(
            drop_dir=PROJECT_ROOT / "vault" / "drop",
            state_checker=state_mgr
        )

    # 1. Fetch
    new_items = adapter.fetch_new_items(max_items=max_items)
    print(f"Found {len(new_items)} new unhandled item(s).")

    if not new_items:
        print("Nothing new to process. All caught up!")
        return

    # 2. Process each item
    processed_count = 0
    for item in new_items:
        print(f"\nProcessing [{item.id}] from {item.creator}: '{item.title or item.url}'")

        if state_mgr.is_processed(item.id):
            print(f"Skipping {item.id} (already in state/processed.json)")
            continue

        # Transcribe audio
        audio_file = item.audio_path
        if audio_file and audio_file.exists():
            print(f"Transcribing audio file: {audio_file.name}...")
            transcript = transcriber.transcribe(audio_file)
        else:
            transcript = item.raw_caption or f"Video by {item.creator} discussing tools and workflows. Link: {item.url}"

        # Classify and summarize
        title = item.title or f"Saved video from {item.creator}"
        classification = classifier.classify_video(
            transcript=transcript,
            title=title,
            caption=item.raw_caption
        )
        print(f"Classified as: '{classification.category}' (confidence: {classification.confidence:.2f}, source: {classification.source})")

        # Skill check for tools named
        if classification.tools:
            print(f"Tools detected: {classification.tools}")
            for tool_name in classification.tools:
                skill_checker.check_tool_skill(
                    tool_name=tool_name,
                    source_note_id=item.id
                )

        # Write note with category, steps, and links
        note_path = note_writer.write_note(
            item_id=item.id,
            creator=item.creator,
            saved_at=item.saved_at,
            title=title,
            transcript=transcript,
            note_type=classification.category,
            tools=classification.tools,
            links=classification.links,
            summary=classification.summary,
            steps=classification.steps
        )
        print(f"Created note: {note_path.relative_to(PROJECT_ROOT)}")

        # Mark processed
        state_mgr.mark_processed(item.id)
        processed_count += 1

        # Cleanup audio if configured
        if audio_file and audio_file.exists() and fetch_cfg.get("cleanup_audio_after_transcription", True):
            if "drop" not in str(audio_file):
                try:
                    audio_file.unlink()
                except Exception:
                    pass

    print(f"\n[DONE] Successfully processed {processed_count} video(s) into vault.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS Pipeline Runner")
    parser.add_argument("--adapter", choices=["manual_drop", "instagram", "youtube", "tiktok"], help="Override fetch adapter")
    parser.add_argument("--limit", type=int, help="Override batch limit")
    args = parser.parse_args()

    run_pipeline(adapter_override=args.adapter, limit_override=args.limit)
