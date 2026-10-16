import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from .base import VideoItem

class MediaExtractor:
    """
    Background media & audio extractor for Instagram Reels, TikTok, and YouTube Shorts.
    Downloads AUDIO ONLY into a temporary directory for local Whisper transcription,
    and extracts caption/creator metadata automatically.
    """

    def __init__(self, tmp_dir: Path, browser_for_cookies: Optional[str] = None):
        self.tmp_dir = Path(tmp_dir)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.browser_for_cookies = browser_for_cookies or os.getenv("BROWSER_COOKIES")

    def extract_audio_and_metadata(self, url: str) -> VideoItem:
        """
        Given a reel/video URL, fetches metadata and downloads audio-only stream to tmp_dir.
        Never keeps video files.
        """
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
        item_id = f"save_{url_hash}"
        platform = self._detect_platform(url)

        try:
            import yt_dlp

            out_tmpl = str(self.tmp_dir / f"{item_id}.%(ext)s")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": out_tmpl,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }

            if self.browser_for_cookies and self.browser_for_cookies.lower() != "none":
                ydl_opts["cookiesfrombrowser"] = (self.browser_for_cookies.lower(),)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                shortcode = info.get("id") or url_hash
                item_id = f"{platform}_{shortcode}"
                uploader = info.get("uploader") or info.get("channel") or info.get("uploader_id") or "creator"
                if not str(uploader).startswith("@"):
                    uploader = f"@{uploader}"

                description = info.get("description") or info.get("title") or ""
                title = info.get("title") or (description.split("\n")[0][:70] if description else f"Saved {platform.title()} Video")

                # Locate downloaded audio file
                downloaded_path = Path(ydl.prepare_filename(info))
                if not downloaded_path.exists():
                    # Search by prefix
                    matches = list(self.tmp_dir.glob(f"{url_hash}.*")) + list(self.tmp_dir.glob(f"*{shortcode}*"))
                    downloaded_path = matches[0] if matches else None

                return VideoItem(
                    id=item_id,
                    url=url,
                    creator=uploader,
                    title=title,
                    audio_path=downloaded_path,
                    raw_caption=description,
                    platform=platform
                )

        except Exception as e:
            print(f"[MediaExtractor] Notice: Direct stream download fell back to metadata for {url} ({e})")
            return VideoItem(
                id=item_id,
                url=url,
                creator="@saved_creator",
                title=f"Saved {platform.title()} Video ({item_id})",
                audio_path=None,
                raw_caption=f"Saved from {url}",
                platform=platform
            )

    @staticmethod
    def _detect_platform(url: str) -> str:
        u = url.lower()
        if "instagram.com" in u:
            return "instagram"
        if "tiktok.com" in u:
            return "tiktok"
        if "youtube.com" in u or "youtu.be" in u:
            return "youtube"
        return "web"
