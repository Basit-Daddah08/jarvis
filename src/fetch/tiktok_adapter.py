from pathlib import Path
from typing import List, Optional
from .base import BaseFetchAdapter, VideoItem

class TikTokSavedAdapter(BaseFetchAdapter):
    """Adapter for ingesting saved TikTok videos."""

    def __init__(self, username: Optional[str] = None, state_checker=None):
        self.username = username
        self.state_checker = state_checker

    def fetch_new_items(self, max_items: int = 10) -> List[VideoItem]:
        items: List[VideoItem] = []
        if not self.username:
            return items

        try:
            import yt_dlp
            source_url = f"https://www.tiktok.com/@{self.username}"
            ydl_opts = {
                "quiet": True,
                "extract_flat": True,
                "playlistend": max_items
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source_url, download=False)
                entries = info.get("entries", [])
                for entry in entries:
                    video_id = entry.get("id")
                    if self.state_checker and self.state_checker.is_processed(f"tiktok_{video_id}"):
                        continue
                    item = VideoItem(
                        id=f"tiktok_{video_id}",
                        url=entry.get("url") or f"https://www.tiktok.com/@{self.username}/video/{video_id}",
                        creator=f"@{self.username}",
                        title=entry.get("title", ""),
                        raw_caption=entry.get("description", ""),
                        platform="tiktok"
                    )
                    items.append(item)
                    if len(items) >= max_items:
                        break
        except ImportError:
            print("[TikTokSavedAdapter] yt-dlp is not installed. To fetch from TikTok: pip install yt-dlp")
        except Exception as e:
            print(f"[TikTokSavedAdapter] Error: {e}")

        return items
