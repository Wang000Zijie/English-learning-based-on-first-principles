from __future__ import annotations

import json
from pathlib import Path

from core.level_manager import LevelManager
from core.passage_generator import PassageGenerator
from data.db_manager import DBManager


class MockAPI:
    def ask(self, prompt: str) -> str:
        return json.dumps(
            {
                "title": "A Small Choice",
                "genre": "叙事短故事",
                "content": "I felt happy to abandon my old fear and start again.",
                "translation": "我很开心地放下旧恐惧，重新开始。",
                "vocabulary_notes": [
                    {
                        "word": "abandon",
                        "sentence_in_passage": "I felt happy to abandon my old fear and start again.",
                        "usage_note": "这里表示主动放弃旧心态。",
                    }
                ],
                "reading_tip": "注意词在语境中的情绪色彩。",
            },
            ensure_ascii=False,
        )


def main() -> None:
    base = Path(__file__).resolve().parent
    db_path = base / "data" / "step5_test.db"
    if db_path.exists():
        db_path.unlink()

    db = DBManager(str(db_path))
    db.upsert_word({"word": "abandon", "definition": "放弃", "level": "learning"})
    db.upsert_word({"word": "happy", "definition": "开心", "level": "familiar"})

    level_manager = LevelManager(db, str(base / "config.yaml"))
    gen = PassageGenerator(
        api_client=MockAPI(),
        db_manager=db,
        level_manager=level_manager,
        config_path=str(base / "config.yaml"),
        prompt_path=str(base / "prompts" / "passage_generation.txt"),
    )
    data = gen.generate()
    assert data.get("content")
    latest = db.get_latest_passage()
    assert latest is not None
    print("[step5] 通过")


if __name__ == "__main__":
    main()
