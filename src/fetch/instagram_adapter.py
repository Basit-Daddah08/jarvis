import os
import random
import time
from pathlib import Path
from typing import List, Optional
from .base import BaseFetchAdapter, VideoItem
from .media_extractor import MediaExtractor

class InstagramSavedAdapter(BaseFetchAdapter):
    """
    Background sync adapter for Instagram Saved Reels.
    Users simply tap 'Save' (Bookmark) inside Instagram on their phone without ever leaving the app.
    This laptop background adapter periodically syncs new saves, extracts audio-only streams,
    and feeds them to the local Whisper transcription daemon.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        username: Optional[str] = None,
        state_checker=None,
        tmp_dir: Optional[Path] = None
    ):
        self.session_id = session_id or os.getenv("INSTAGRAM_SESSION_ID")
        self.username = username or os.getenv("INSTAGRAM_USERNAME")
        self.state_checker = state_checker
        self.tmp_dir = tmp_dir or Path("tmp")
        self.extractor = MediaExtractor(tmp_dir=self.tmp_dir)

    def fetch_new_items(self, max_items: int = 10) -> List[VideoItem]:
        items: List[VideoItem] = []
        if not self.session_id or not self.username:
            return items

        try:
            import instaloader
            L = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                save_metadata=False,
                compress_json=False,
                quiet=True
            )

            L.context._session.cookies.set("sessionid", self.session_id, domain=".instagram.com")
            profile = instaloader.Profile.from_username(L.context, self.username)
            saved_posts = profile.get_saved_posts()

            for post in saved_posts:
                if len(items) >= max_items:
                    break

                shortcode = post.shortcode
                item_id = f"ig_{shortcode}"
                if self.state_checker and (self.state_checker.is_processed(item_id) or self.state_checker.is_processed(shortcode)):
                    continue

                # Respect safety pacing rules (random jitter between fetches)
                delay = random.uniform(8.0, 20.0)
                time.sleep(delay)

                post_url = f"https://www.instagram.com/reel/{shortcode}/"
                audio_path = None

                # Extract audio-only stream in background if it's a video/reel
                if getattr(post, "is_video", True):
                    extracted = self.extractor.extract_audio_and_metadata(post_url)
                    audio_path = extracted.audio_path

                caption = post.caption or ""
                first_line = caption.split("\n")[0][:70] if caption else f"Instagram Reel {shortcode}"

                item = VideoItem(
                    id=item_id,
                    url=post_url,
                    creator=f"@{post.owner_username}",
                    title=getattr(post, "title", None) or first_line,
                    saved_at=post.date_utc.strftime("%Y-%m-%d"),
                    audio_path=audio_path,
                    raw_caption=caption,
                    platform="instagram"
                )
                items.append(item)

        except Exception as e:
            print(f"[InstagramSavedAdapter] Paused background sync safely: {e}")

        return items
