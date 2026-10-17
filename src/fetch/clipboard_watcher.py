import os
import subprocess
import sys
import time
from typing import Callable, Optional, Set
from .url_validator import ANY_VIDEO_URL_PATTERN as VIDEO_URL_PATTERN
from .url_validator import extract_video_url_from_text, validate_video_url

class ClipboardWatcher:
    """
    Watches the system clipboard (including Windows Phone Link cross-device clipboard
    synced from Android/iOS) for video/reel links (Instagram, TikTok, YouTube)
    and queues them automatically in the background.
    """

    def __init__(self, on_url_detected: Callable[[str], None]):
        self.on_url_detected = on_url_detected
        self.seen_urls: Set[str] = set()
        self.last_text: str = ""
        self.enabled: bool = True

    def _read_clipboard_text(self) -> Optional[str]:
        """Reads unicode text from the OS clipboard safely and fast."""
        # 1. On Windows, use Win32 user32/kernel32 API for microsecond access
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32

                user32.OpenClipboard.argtypes = [wintypes.HWND]
                user32.OpenClipboard.restype = wintypes.BOOL
                user32.CloseClipboard.argtypes = []
                user32.CloseClipboard.restype = wintypes.BOOL
                user32.GetClipboardData.argtypes = [wintypes.UINT]
                user32.GetClipboardData.restype = wintypes.HANDLE
                kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
                kernel32.GlobalLock.restype = wintypes.LPVOID
                kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
                kernel32.GlobalUnlock.restype = wintypes.BOOL

                CF_UNICODETEXT = 13
                if user32.OpenClipboard(None):
                    try:
                        h_mem = user32.GetClipboardData(CF_UNICODETEXT)
                        if h_mem:
                            p_data = kernel32.GlobalLock(h_mem)
                            if p_data:
                                try:
                                    return ctypes.c_wchar_p(p_data).value
                                finally:
                                    kernel32.GlobalUnlock(h_mem)
                    finally:
                        user32.CloseClipboard()
            except Exception:
                pass

        # 2. Fallback using PowerShell on Windows or pbpaste / xclip on Unix
        try:
            if sys.platform == "win32":
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", "Get-Clipboard"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                )
                return res.stdout
            elif sys.platform == "darwin":
                res = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=2)
                return res.stdout
            else:
                res = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=2)
                return res.stdout
        except Exception:
            return None

    def check_once(self) -> Optional[str]:
        """Check clipboard for supported video URLs (Instagram, TikTok, YouTube)."""
        if not self.enabled:
            return None

        raw_text = self._read_clipboard_text()
        text = (raw_text or "").strip()
        if not text or text == self.last_text:
            return None

        self.last_text = text

        # Check direct URL or extracted URL from share text
        extracted = extract_video_url_from_text(text)
        if extracted:
            platform, canonical_url = extracted
            if canonical_url not in self.seen_urls:
                self.seen_urls.add(canonical_url)
                self.on_url_detected(canonical_url)
                return canonical_url

        return None
