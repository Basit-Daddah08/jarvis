import re
import urllib.parse
from typing import Optional, Tuple

# Supported platform patterns:
# 1. Instagram: reels, posts, tv, shares
INSTAGRAM_PATTERN = re.compile(
    r"^https?://(?:www\.|m\.)?(?:instagram\.com|instagr\.am)/(?:reel|p|tv|share)/([A-Za-z0-9_-]+)",
    re.IGNORECASE
)

# 2. TikTok: @user/video/id, vm.tiktok.com, vt.tiktok.com, tiktok.com/t/
TIKTOK_PATTERN = re.compile(
    r"^https?://(?:(?:www\.|m\.)?tiktok\.com/(?:@[^/\s]+/video/|t/)|(?:vt|vm)\.tiktok\.com/)([A-Za-z0-9_-]+)",
    re.IGNORECASE
)

# 3. YouTube: shorts, youtu.be, watch?v=
YOUTUBE_PATTERN = re.compile(
    r"^https?://(?:(?:www\.|m\.)?youtube\.com/(?:shorts/|watch\?v=)|youtu\.be/)([A-Za-z0-9_-]+)",
    re.IGNORECASE
)

# Regex to find video URLs embedded inside share captions/text
ANY_VIDEO_URL_PATTERN = re.compile(
    r"https?://(?:www\.|m\.)?(?:"
    r"(?:instagram\.com|instagr\.am)/(?:reel|p|tv|share)/[A-Za-z0-9_-]+|"
    r"tiktok\.com/(?:@[^/\s]+/video/\d+|t/[A-Za-z0-9_-]+)|"
    r"(?:vt|vm)\.tiktok\.com/[A-Za-z0-9_-]+|"
    r"youtube\.com/shorts/[A-Za-z0-9_-]+|"
    r"youtube\.com/watch\?v=[A-Za-z0-9_-]+|"
    r"youtu\.be/[A-Za-z0-9_-]+"
    r")[^\s\"'<>]*",
    re.IGNORECASE
)

def normalize_video_url(url: str) -> str:
    """Strip tracking queries (e.g. ?igsh=, ?si=, ?feature=) to ensure consistent de-duplication."""
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url.strip())
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        # For youtube.com/watch keep the 'v' query param
        if "youtube.com" in parsed.netloc and parsed.path == "/watch":
            qs = urllib.parse.parse_qs(parsed.query)
            if "v" in qs:
                clean_url = f"{clean_url}?v={qs['v'][0]}"
        return clean_url.rstrip("/")
    except Exception:
        return url.strip()

def validate_video_url(url: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates whether a URL belongs to Instagram, TikTok, or YouTube.
    Returns: (is_valid: bool, platform: Optional[str], canonical_url: Optional[str])
    """
    if not url or not isinstance(url, str):
        return False, None, None

    clean_url = url.strip()

    # Check Instagram
    if INSTAGRAM_PATTERN.search(clean_url):
        return True, "instagram", normalize_video_url(clean_url)

    # Check TikTok
    if TIKTOK_PATTERN.search(clean_url):
        return True, "tiktok", normalize_video_url(clean_url)

    # Check YouTube
    if YOUTUBE_PATTERN.search(clean_url):
        return True, "youtube", normalize_video_url(clean_url)

    return False, None, None

def extract_video_url_from_text(text: str) -> Optional[Tuple[str, str]]:
    """
    Extracts the first valid video URL from raw text (e.g. mobile share sheet input).
    Returns (platform, normalized_url) or None.
    """
    if not text:
        return None
    match = ANY_VIDEO_URL_PATTERN.search(text)
    if match:
        raw_url = match.group(0).rstrip(".,);!?")
        is_valid, platform, normalized = validate_video_url(raw_url)
        if is_valid and platform and normalized:
            return platform, normalized
    return None
