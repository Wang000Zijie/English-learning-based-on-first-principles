from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from data.db_manager import DBManager


class StorylineManager:
    def __init__(self, db_manager: DBManager) -> None:
        self.db = db_manager

    def get_or_create_active_storyline(
        self,
        word_ids: List[int],
        direction_id: str,
        name_hint: str = "词汇故事线",
    ) -> Dict[str, Any]:
        active = self.db.get_active_storyline(direction_id)
        if active:
            return active
        name = f"第一章：{name_hint}"
        sid = self.db.create_storyline(name=name, word_ids=word_ids, direction_id=direction_id)
        created = self.db.get_storyline_by_id(sid)
        if not created:
            raise RuntimeError("Failed to create storyline")
        return created

    def get_last_chapter_ending(self, storyline_id: int) -> str:
        last = self.db.get_last_storyline_chapter(storyline_id)
        if not last:
            return ""
        passage = self.db.get_passage_by_id(int(last["passage_id"]))
        if not passage:
            return ""
        content = str(passage.get("content", "")).strip()
        if not content:
            return ""
        parts = [x.strip() for x in content.split("\n") if x.strip()]
        if parts:
            return parts[-1]
        return content[-200:]

    def add_chapter(self, storyline_id: int, passage_id: int, mastery_snapshot: Dict[str, Any]) -> int:
        last = self.db.get_last_storyline_chapter(storyline_id)
        next_no = (int(last["chapter_number"]) + 1) if last else 1
        return self.db.add_storyline_chapter(
            storyline_id=storyline_id,
            chapter_number=next_no,
            passage_id=passage_id,
            mastery_snapshot=mastery_snapshot,
        )

    def abandon_last_chapter(self, storyline_id: int) -> Optional[int]:
        return self.db.delete_storyline_last_chapter(storyline_id)

    def is_storyline_mastered(self, storyline: Dict[str, Any]) -> bool:
        raw = storyline.get("word_ids", "[]")
        try:
            word_ids = json.loads(raw) if isinstance(raw, str) else list(raw)
        except Exception:
            word_ids = []
        if not word_ids:
            return False
        for wid in word_ids:
            word = self.db.get_word_by_id(int(wid))
            if not word or str(word.get("level", "new")) != "mastered":
                return False
        return True
