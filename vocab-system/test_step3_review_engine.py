from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from core.level_manager import LevelManager
from core.review_engine import ReviewEngine
from data.db_manager import DBManager


def main() -> None:
    base = Path(__file__).resolve().parent
    db_path = base / "data" / "step3_test.db"
    if db_path.exists():
        db_path.unlink()

    db = DBManager(str(db_path))
    word_id = db.upsert_word({"word": "abandon", "definition": "放弃", "level": "new"})

    today = date.today()
    db.add_review_record(word_id, (today - timedelta(days=3)).isoformat(), "forgotten", (today - timedelta(days=2)).isoformat(), 0)
    db.add_review_record(word_id, (today - timedelta(days=2)).isoformat(), "forgotten", (today - timedelta(days=1)).isoformat(), 0)
    db.add_review_record(word_id, (today - timedelta(days=1)).isoformat(), "remembered", today.isoformat(), 1)

    level_manager = LevelManager(db, str(base / "config.yaml"))
    engine = ReviewEngine(db, level_manager, str(base / "config.yaml"))

    due = engine.get_due_words_today(today)
    assert any(x["id"] == word_id for x in due)

    weak = engine.get_weak_words()
    assert any(x["id"] == word_id for x in weak)

    next_date = engine.record_review(word_id, "remembered", today)
    assert next_date
    print("[step3] 通过")


if __name__ == "__main__":
    main()
