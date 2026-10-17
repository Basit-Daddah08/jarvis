import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Set

class StateManager:
    """Manages processed video IDs and daily spend tracking."""

    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.processed_file = self.state_dir / "processed.json"
        self.spend_file = self.state_dir / "spend.json"
        self._load_state()

    def _load_state(self):
        # Load or initialize processed IDs
        if self.processed_file.exists():
            try:
                with open(self.processed_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.processed_ids: Set[str] = set(data.get("processed_ids", []))
            except Exception:
                self.processed_ids = set()
        else:
            self.processed_ids = set()
            self._save_processed()

        # Load or initialize spend tracker
        today_str = date.today().isoformat()
        if self.spend_file.exists():
            try:
                with open(self.spend_file, "r", encoding="utf-8") as f:
                    self.spend_data = json.load(f)
                    # Reset if date changed
                    if self.spend_data.get("date") != today_str:
                        self.spend_data = {
                            "date": today_str,
                            "spent_usd": 0.0,
                            "daily_cap_usd": self.spend_data.get("daily_cap_usd", 1.00),
                            "calls_count": 0,
                        }
                        self._save_spend()
            except Exception:
                self.spend_data = {"date": today_str, "spent_usd": 0.0, "daily_cap_usd": 1.00, "calls_count": 0}
                self._save_spend()
        else:
            self.spend_data = {"date": today_str, "spent_usd": 0.0, "daily_cap_usd": 1.00, "calls_count": 0}
            self._save_spend()

    def is_processed(self, item_id: str) -> bool:
        """Check if an item ID has already been handled."""
        return item_id in self.processed_ids

    def mark_processed(self, item_id: str):
        """Record an item ID as handled to ensure idempotency."""
        self.processed_ids.add(item_id)
        self._save_processed()

    def _save_processed(self):
        with open(self.processed_file, "w", encoding="utf-8") as f:
            json.dump({
                "processed_ids": sorted(list(self.processed_ids)),
                "last_updated": datetime.now().isoformat()
            }, f, indent=2)

    def can_spend(self, estimated_cost_usd: float = 0.01) -> bool:
        """Check if daily paid-AI spend cap allows more calls."""
        spent = self.spend_data.get("spent_usd", 0.0)
        cap = self.spend_data.get("daily_cap_usd", 1.00)
        return (spent + estimated_cost_usd) <= cap

    def record_spend(self, cost_usd: float):
        """Update daily spend counter."""
        self.spend_data["spent_usd"] = round(self.spend_data.get("spent_usd", 0.0) + cost_usd, 4)
        self.spend_data["calls_count"] = self.spend_data.get("calls_count", 0) + 1
        self._save_spend()

    def get_today_spend(self) -> dict:
        today_str = date.today().isoformat()
        if self.spend_data.get("date") != today_str:
            self.spend_data = {
                "date": today_str,
                "spent_usd": 0.0,
                "daily_cap_usd": self.spend_data.get("daily_cap_usd", 1.00),
                "calls_count": 0,
            }
            self._save_spend()
        return self.spend_data

    @property
    def daily_spend_cap(self) -> float:
        return float(self.spend_data.get("daily_cap_usd", 1.00))

    @daily_spend_cap.setter
    def daily_spend_cap(self, value: float):
        self.spend_data["daily_cap_usd"] = float(value)
        self._save_spend()

    def _save_spend(self):
        with open(self.spend_file, "w", encoding="utf-8") as f:
            json.dump(self.spend_data, f, indent=2)
