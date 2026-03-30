from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Dict, List

import yaml

from data.db_manager import DBManager


class LevelManager:
    def __init__(self, db_manager: DBManager, config_path: str = "config.yaml") -> None:
        self.db = db_manager
        self.config_path = Path(config_path)
        self.thresholds = self._load_thresholds()

    def _load_thresholds(self) -> Dict[str, int]:
        with self.config_path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return config.get("learning", {}).get(
            "level_thresholds",
            {"new": 0, "learning": 1, "familiar": 3, "mastered": 6},
        )

    def initialize_level(self, word_id: int) -> None:
        self.db.update_word_level(word_id, "new")

    def update_level(self, word_id: int) -> str:
        stats_rows = self.db.get_word_stats(word_id)
        if not stats_rows:
            return "new"
        total_reviews = int(stats_rows[0].get("total_reviews", 0) or 0)

        if total_reviews >= int(self.thresholds.get("mastered", 6)):
            level = "mastered"
        elif total_reviews >= int(self.thresholds.get("familiar", 3)):
            level = "familiar"
        elif total_reviews >= int(self.thresholds.get("learning", 1)):
            level = "learning"
        else:
            level = "new"

        self.db.update_word_level(word_id, level)
        return level

    def update_levels_for_all(self) -> None:
        for row in self.db.get_word_stats():
            self.update_level(int(row["id"]))

    def select_words_for_passage(
        self,
        levels: List[str],
        min_words: int,
        max_words: int,
        word_bank: str | None = None,
    ) -> List[Dict[str, Any]]:
        candidates = self.db.get_words_by_levels(levels, word_bank=word_bank)
        if not candidates:
            candidates = self.db.list_words(word_bank=word_bank)
        if not candidates:
            return []

        target_count = min(max(min_words, 1), max_words)
        target_count = min(target_count, len(candidates))

        weight_by_level = {
            "learning": 3.0,
            "familiar": 2.0,
            "new": 1.5,
            "mastered": 1.0,
        }
        pool = candidates[:]
        selected: List[Dict[str, Any]] = []

        while pool and len(selected) < target_count:
            weights = [weight_by_level.get(item.get("level", "new"), 1.0) for item in pool]
            idx = self._weighted_pick_index(weights)
            selected.append(pool.pop(idx))

        return selected

    def _weighted_pick_index(self, weights: List[float]) -> int:
        total = sum(weights)
        if total <= 0:
            return random.randint(0, len(weights) - 1)
        r = random.random() * total
        acc = 0.0
        for i, w in enumerate(weights):
            acc += w
            if acc >= r:
                return i
        return len(weights) - 1
