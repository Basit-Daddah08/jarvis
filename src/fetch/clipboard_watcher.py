import re
import subprocess
import time
from typing import Callable, Optional, Set

VIDEO_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:"
    r"instagram\.com/(?:reel|p|tv)/[A-Za-z0-9_-]+|"
    r"tiktok\.com/@[^/\s]+/video/\d+|"
    r"vm\.tiktok\.com/[A-Za-z0-9_-]+|"
    r"youtube\.com/shorts/[A-Za-z0-9_-]+|"
    r"youtu\.be/[A-Za-z0-9_-]+"
    r")[^\s\"'<>]*",
    re.IGNORECASE
)

class ClipboardWatcher:
    """
    Watches the system clipboard (including Windows Phone Link cross-device clipboard
    synced from Android/iOS) for video/reel links and queues them automatically in the background.
    """

    def __init__(self, on_url_detected: Callable[[str], None]):
        self.on_url_detected = on_url_detected
        self.seen_urls: Set[str] = set()
        self.last_text: str = ""

    def check_once(self) -> Optional[str]:
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )
            text = (res.stdout or "").strip()
            if not text or text == self.last_text:
                return None
            self.last_text = text

            match = VIDEO_URL_PATTERN.search(text)
            if match:
                url = match.group(0).rstrip(".,);!")
                if url not in self.seen_urls:
                    self.seen_urls.add(url)
                    self.on_url_detected(url)
                    return url
        except Exception:
            pass
        return None
