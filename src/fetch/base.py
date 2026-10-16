from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional

@dataclass
class VideoItem:
    id: str
    url: str
    creator: str
    title: str = ""
    saved_at: str = field(default_factory=lambda: date.today().isoformat())
    audio_path: Optional[Path] = None
    raw_caption: str = ""
    platform: str = "instagram"

class BaseFetchAdapter(ABC):
    """Abstract base class for swappable video ingestion sources."""

    @abstractmethod
    def fetch_new_items(self, max_items: int = 10) -> List[VideoItem]:
        """Fetch unhandled items from source. Returns list of VideoItem with audio available."""
        pass
