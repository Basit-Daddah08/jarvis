from pathlib import Path
from typing import List, Optional
from .base import BaseFetchAdapter, VideoItem

class YouTubeSavedAdapter(BaseFetchAdapter):
    """Adapter for ingesting saved YouTube Shorts and videos."""

    def __init__(self, playlist_url_or_channel: Optional[str] = None, state_checker=None):
        self.source = playlist_url_or_channel
        self.state_checker = state_checker

    def fetch_new_items(self, max_items: int = 10) -> List[VideoItem]:
        items: List[VideoItem] = []
        if not self.source:
            return items

        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "extract_flat": True,
                "playlistend": max_items
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.source, download=False)
                entries = info.get("entries", [])
                for entry in entries:
                    video_id = entry.get("id")
                    if self.state_checker and self.state_checker.is_processed(f"yt_{video_id}"):
                        continue
                    item = VideoItem(
                        id=f"yt_{video_id}",
                        url=entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                        creator=f"@{entry.get('uploader') or 'youtube'}",
                        title=entry.get("title", ""),
                        raw_caption=entry.get("description", ""),
                        platform="youtube"
                    )
                    items.append(item)
                    if len(items) >= max_items:
                        break
        except ImportError:
            print("[YouTubeSavedAdapter] yt-dlp is not installed. To fetch from YouTube: pip install yt-dlp")
        except Exception as e:
            print(f"[YouTubeSavedAdapter] Error: {e}")

        return items
