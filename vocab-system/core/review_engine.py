from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

import yaml

from data.db_manager import DBManager
from core.level_manager import LevelManager


class ReviewEngine:
    def __init__(
        self,
        db_manager: DBManager,
        level_manager: LevelManager,
        config_path: str = "config.yaml",
    ) -> None:
        self.db = db_manager
        self.level_manager = level_manager
        self.intervals = self._load_intervals(config_path)

    def _load_intervals(self, config_path: str) -> List[int]:
        config_file = Path(config_path)
        with config_file.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        intervals = config.get("learning", {}).get("review_intervals", [1, 3, 7, 15, 30, 90])
        if not intervals:
            return [1, 3, 7]
        return [int(x) for x in intervals]

    def get_due_words_today(self, today: date | None = None) -> List[Dict[str, Any]]:
        d = today or date.today()
        return self.db.get_due_words(d.isoformat())

    def record_review(self, word_id: int, result: str, today: date | None = None) -> str:
        if word_id is None:
            raise ValueError("word_id 不能为空")
        if not self.db.get_word_by_id(int(word_id)):
            raise ValueError(f"无效的 word_id: {word_id}")
        d = today or date.today()
        latest = self.db.get_latest_review_record(word_id)
        remembered = result == "remembered"

        if latest:
            idx = int(latest["interval_index"])
            next_idx = min(idx + 1, len(self.intervals) - 1) if remembered else 0
        else:
            next_idx = 0 if remembered else 0

        next_days = self.intervals[next_idx]
        next_date = d + timedelta(days=next_days)

        self.db.add_review_record(
            word_id=word_id,
            review_date=d.isoformat(),
            result="remembered" if remembered else "forgotten",
            next_review_date=next_date.isoformat(),
            interval_index=next_idx,
        )
        self.level_manager.update_level(word_id)
        return next_date.isoformat()

    def get_weak_words(self) -> List[Dict[str, Any]]:
        return self.db.get_weak_words_recent()
