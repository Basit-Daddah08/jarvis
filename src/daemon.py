import hashlib
import json
import os
import queue
import socket
import sys
import threading
import time
import tomllib
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.classify.classifier import VideoClassifier
from src.fetch.base import VideoItem
from src.fetch.clipboard_watcher import ClipboardWatcher
from src.fetch.instagram_adapter import InstagramSavedAdapter
from src.fetch.manual_adapter import ManualDropAdapter
from src.fetch.media_extractor import MediaExtractor
from src.notes.writer import NoteWriter
from src.skills.skill_checker import SkillChecker
from src.state_manager import StateManager
from src.transcribe.transcriber import AudioTranscriber

class ElionDaemon:
    """
    ELION (JARVIS) Private Background Software Daemon.
    Runs silently in the background on the laptop:
    1. Receives zero-interruption saves from mobile apps (Instagram Saved Sync, iOS/Android Share Webhook, Cross-Device Clipboard).
    2. Downloads audio-only streams in the background.
    3. Runs local Whisper transcription and deletes temporary audio.
    4. Classifies, extracts tools/steps, checks GitHub skills, and writes Markdown notes to vault/.
    """

    def __init__(self):
        self.config = self._load_config()
        self.state_dir = PROJECT_ROOT / "state"
        self.vault_dir = PROJECT_ROOT / "vault"
        self.tmp_dir = PROJECT_ROOT / "tmp"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

        self.status_file = self.state_dir / "daemon_status.json"
        self.pid_file = self.state_dir / "daemon.pid"

        self.state_mgr = StateManager(self.state_dir)
        self.note_writer = NoteWriter(
            notes_dir=self.vault_dir / "notes",
            inbox_file=self.vault_dir / "INBOX.md"
        )
        self.transcriber = AudioTranscriber(
            model_name=self.config.get("transcribe", {}).get("model", "base.en")
        )
        self.classifier = VideoClassifier(state_manager=self.state_mgr)
        self.skill_checker = SkillChecker(
            approvals_dir=self.vault_dir / "approvals",
            queue_all_by_default=self.config.get("safety", {}).get("queue_markdown_skills", True)
        )
        self.extractor = MediaExtractor(
            tmp_dir=self.tmp_dir,
            browser_for_cookies=self.config.get("fetch", {}).get("browser_cookies", None)
        )
        self.drop_adapter = ManualDropAdapter(
            drop_dir=self.vault_dir / "drop",
            state_checker=self.state_mgr,
            tmp_dir=self.tmp_dir
        )
        self.ig_adapter = InstagramSavedAdapter(
            state_checker=self.state_mgr,
            tmp_dir=self.tmp_dir
        )

        self.work_queue: "queue.Queue[Dict]" = queue.Queue()
        self.running = False
        self.started_at = datetime.now().isoformat()
        self.last_sync_at: Optional[str] = None
        self.current_task = "Idle — Watching background sources"
        self.status = "running"
        self.processed_this_session = 0
        self.events: List[Dict[str, str]] = []

        self.clipboard_enabled = self.config.get("daemon", {}).get("watch_clipboard", True)
        self.clipboard_watcher = ClipboardWatcher(on_url_detected=self._on_clipboard_url)

    def _load_config(self) -> dict:
        cfg_path = PROJECT_ROOT / "config.toml"
        if cfg_path.exists():
            with open(cfg_path, "rb") as f:
                return tomllib.load(f)
        return {}

    def log_event(self, message: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = {"time": ts, "level": level, "message": message}
        self.events.insert(0, entry)
        self.events = self.events[:40]
        print(f"[{ts}] [{level}] {message}")
        self._write_status()

    def _write_status(self):
        data = {
            "status": self.status,
            "pid": os.getpid(),
            "started_at": self.started_at,
            "last_sync_at": self.last_sync_at,
            "current_task": self.current_task,
            "queue_size": self.work_queue.qsize(),
            "processed_this_session": self.processed_this_session,
            "total_processed_all_time": len(self.state_mgr.processed_ids),
            "clipboard_watcher_active": self.clipboard_enabled,
            "instagram_sync_configured": bool(self.ig_adapter.session_id and self.ig_adapter.username),
            "local_ip": self.get_local_ip(),
            "events": self.events[:15]
        }
        try:
            with open(self.status_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def enqueue_url(self, url: str, creator: str = "", title: str = "", caption: str = "", source: str = "mobile_share") -> str:
        """
        Immediately enqueue a video URL for background downloading & Whisper transcription.
        Returns in <5ms so mobile share sheets never block or switch apps.
        """
        url = url.strip()
        item_id = "save_" + hashlib.md5((url or caption).encode("utf-8")).hexdigest()[:10]
        self.work_queue.put({
            "id": item_id,
            "url": url,
            "creator": creator,
            "title": title,
            "caption": caption,
            "source": source
        })
        self.log_event(f"Queued new video from {source}: {url or title}")
        return item_id

    def _on_clipboard_url(self, url: str):
        if not self.state_mgr.is_processed("save_" + hashlib.md5(url.encode("utf-8")).hexdigest()[:10]):
            self.enqueue_url(url=url, source="clipboard_auto_capture")

    def process_video_item(self, item: VideoItem, source_label: str = "background"):
        """Full background pipeline for a single VideoItem: Transcribe -> Classify -> Skill Check -> Write Note."""
        if self.state_mgr.is_processed(item.id):
            return None

        self.status = "transcribing"
        self.current_task = f"Transcribing {item.id} ({item.creator})..."
        self.log_event(f"Starting background transcription for [{item.id}] from {item.creator}")

        # 1. Local Whisper transcription + caption fusion
        transcript = self.transcriber.transcribe(
            audio_path=item.audio_path,
            fallback_caption=item.raw_caption or f"Saved video from {item.creator}: {item.url}"
        )

        # 2. Classify (Keywords first, then spend-capped LLM fallback)
        title = item.title or f"Saved Video from {item.creator}"
        self.current_task = f"Classifying '{title[:40]}'..."
        self._write_status()

        classification = self.classifier.classify_video(
            transcript=transcript,
            title=title,
            caption=item.raw_caption
        )

        # 3. Skill Check & Quarantine
        if classification.tools:
            for tool_name in classification.tools:
                self.skill_checker.check_tool_skill(
                    tool_name=tool_name,
                    source_note_id=item.id
                )

        # 4. Write Vault Note & Update Daily INBOX.md
        links = list(dict.fromkeys(([item.url] if item.url and item.url.startswith("http") else []) + classification.links))
        note_path = self.note_writer.write_note(
            item_id=item.id,
            creator=item.creator or "@saved_creator",
            saved_at=item.saved_at or date.today().isoformat(),
            title=title,
            transcript=transcript,
            note_type=classification.category,
            tools=classification.tools,
            links=links,
            summary=classification.summary,
            steps=classification.steps
        )

        # 5. Mark processed & delete temporary audio file (Rule 8: Audio only, never keep media)
        self.state_mgr.mark_processed(item.id)
        self.processed_this_session += 1
        self.last_sync_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if item.audio_path and Path(item.audio_path).exists():
            if "drop" not in str(item.audio_path):
                try:
                    Path(item.audio_path).unlink()
                except Exception:
                    pass

        self.status = "running"
        self.current_task = "Idle — Watching background sources"
        self.log_event(f"Completed note: vault/notes/{note_path.name} [type={classification.category}]")
        return note_path

    def _worker_loop(self):
        """Continuously processes items from the instant queue, drop folder, and clipboard."""
        while self.running:
            try:
                # 1. Process instant queue items (from mobile webhook / clipboard)
                while not self.work_queue.empty():
                    job = self.work_queue.get_nowait()
                    url = job.get("url", "")
                    caption = job.get("caption", "")
                    title = job.get("title", "")
                    creator = job.get("creator", "")

                    if url and url.startswith("http") and not caption:
                        self.status = "downloading_audio"
                        self.current_task = f"Extracting audio from {url[:45]}..."
                        self._write_status()
                        extracted = self.extractor.extract_audio_and_metadata(url)
                        extracted.id = job["id"]
                        if title:
                            extracted.title = title
                        if creator:
                            extracted.creator = creator
                        item = extracted
                    else:
                        item = VideoItem(
                            id=job["id"],
                            url=url,
                            creator=creator or "@mobile_save",
                            title=title or (caption.split("\n")[0][:65] if caption else f"Saved Reel ({job['id']})"),
                            raw_caption=caption
                        )

                    self.process_video_item(item, source_label=job.get("source", "queue"))
                    self.work_queue.task_done()

                # 2. Check drop folder for new files/manifests
                drop_items = self.drop_adapter.fetch_new_items(max_items=5)
                for d_item in drop_items:
                    self.process_video_item(d_item, source_label="drop_folder")

                # 3. Check clipboard if enabled
                if self.clipboard_enabled:
                    self.clipboard_watcher.check_once()

            except Exception as e:
                self.log_event(f"Worker notice: {e}", level="WARN")

            time.sleep(2.5)

    def _instagram_sync_loop(self):
        """Periodically checks Instagram Saved collection in the background if configured."""
        sync_interval_minutes = self.config.get("daemon", {}).get("instagram_poll_minutes", 30)
        while self.running:
            try:
                if self.ig_adapter.session_id and self.ig_adapter.username:
                    self.status = "syncing_instagram"
                    self.current_task = "Checking Instagram Saved collection..."
                    self._write_status()
                    max_batch = self.config.get("limits", {}).get("max_items_per_batch", 10)
                    new_saves = self.ig_adapter.fetch_new_items(max_items=max_batch)
                    for item in new_saves:
                        self.process_video_item(item, source_label="instagram_saved")
                    self.status = "running"
                    self.current_task = "Idle — Watching background sources"
                    self._write_status()
            except Exception as e:
                self.log_event(f"Instagram background sync notice: {e}", level="WARN")

            # Sleep until next sync cycle
            for _ in range(int(sync_interval_minutes * 60)):
                if not self.running:
                    break
                time.sleep(1)

    def trigger_sync_now(self) -> int:
        """Manually trigger an immediate background check of drop folder & Instagram saves."""
        self.log_event("Manual background sync triggered.")
        drop_items = self.drop_adapter.fetch_new_items(max_items=10)
        count = 0
        for item in drop_items:
            if self.process_video_item(item, source_label="manual_sync"):
                count += 1
        return count

    def start_background_threads(self):
        self.running = True
        self.pid_file.write_text(str(os.getpid()), encoding="utf-8")
        self.log_event("ELION Background Daemon started on laptop.")

        t_worker = threading.Thread(target=self._worker_loop, name="ElionQueueWorker", daemon=True)
        t_worker.start()

        t_ig = threading.Thread(target=self._instagram_sync_loop, name="ElionInstagramSync", daemon=True)
        t_ig.start()

    def stop(self):
        self.running = False
        self.status = "stopped"
        self.current_task = "Stopped"
        self._write_status()
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except Exception:
                pass
