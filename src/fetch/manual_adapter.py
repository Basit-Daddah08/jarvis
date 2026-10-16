import hashlib
import json
import re
from pathlib import Path
from typing import List, Optional
from .base import BaseFetchAdapter, VideoItem
from .media_extractor import MediaExtractor

class ManualDropAdapter(BaseFetchAdapter):
    """
    Watches vault/drop/ for:
    - Mobile Share Webhook queue (mobile_queue.json)
    - JSON manifests (*.json)
    - Plain text URL lists (*.txt)
    - Direct audio files (*.wav, *.mp3, *.m4a)
    Automatically extracts audio-only streams in the background for any URLs.
    """

    def __init__(self, drop_dir: Path, state_checker=None, tmp_dir: Optional[Path] = None):
        self.drop_dir = Path(drop_dir)
        self.drop_dir.mkdir(parents=True, exist_ok=True)
        self.state_checker = state_checker
        self.tmp_dir = tmp_dir or (self.drop_dir.parent.parent / "tmp")
        self.extractor = MediaExtractor(tmp_dir=self.tmp_dir)

    def fetch_new_items(self, max_items: int = 10) -> List[VideoItem]:
        items: List[VideoItem] = []

        # 1. JSON files in vault/drop/ (including mobile_queue.json)
        for json_file in sorted(self.drop_dir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entries = data if isinstance(data, list) else [data]
                for entry in entries:
                    url = entry.get("url", "")
                    item_id = str(entry.get("id") or hashlib.md5(url.encode()).hexdigest()[:12])
                    if self.state_checker and self.state_checker.is_processed(item_id):
                        continue

                    audio_p = entry.get("audio_path")
                    caption = entry.get("caption", "")
                    title = entry.get("title", "")
                    creator = entry.get("creator", "@unknown")

                    # If no local audio & no caption provided, try extracting from URL
                    if not audio_p and not caption and url.startswith("http"):
                        extracted = self.extractor.extract_audio_and_metadata(url)
                        audio_p = extracted.audio_path
                        caption = caption or extracted.raw_caption
                        if not title:
                            title = extracted.title
                        if creator == "@unknown":
                            creator = extracted.creator

                    item = VideoItem(
                        id=item_id,
                        url=url or f"https://instagram.com/reel/{item_id}",
                        creator=creator,
                        title=title,
                        saved_at=entry.get("saved_at", ""),
                        audio_path=Path(audio_p) if audio_p else None,
                        raw_caption=caption,
                        platform=entry.get("platform", "instagram")
                    )
                    items.append(item)
                    if len(items) >= max_items:
                        return items
            except Exception as e:
                print(f"[ManualDropAdapter] Notice reading {json_file.name}: {e}")

        # 2. Plain text URL files (*.txt) in vault/drop/
        for txt_file in sorted(self.drop_dir.glob("*.txt")):
            try:
                lines = txt_file.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    url = line.strip()
                    if not url.startswith("http"):
                        continue
                    item_id = "url_" + hashlib.md5(url.encode()).hexdigest()[:10]
                    if self.state_checker and self.state_checker.is_processed(item_id):
                        continue

                    extracted = self.extractor.extract_audio_and_metadata(url)
                    extracted.id = item_id
                    items.append(extracted)
                    if len(items) >= max_items:
                        return items
            except Exception as e:
                print(f"[ManualDropAdapter] Notice reading {txt_file.name}: {e}")

        # 3. Standalone audio files (*.wav, *.mp3, *.m4a)
        audio_extensions = {".wav", ".mp3", ".m4a"}
        for audio_file in sorted(self.drop_dir.iterdir()):
            if audio_file.suffix.lower() in audio_extensions:
                file_hash = hashlib.md5(audio_file.stem.encode()).hexdigest()[:10]
                item_id = f"local_{file_hash}"
                if self.state_checker and self.state_checker.is_processed(item_id):
                    continue

                item = VideoItem(
                    id=item_id,
                    url=f"local://drop/{audio_file.name}",
                    creator="@saved_audio",
                    title=audio_file.stem.replace("_", " ").title(),
                    audio_path=audio_file,
                    raw_caption=f"Local audio file: {audio_file.name}",
                    platform="local"
                )
                items.append(item)
                if len(items) >= max_items:
                    break

        return items
