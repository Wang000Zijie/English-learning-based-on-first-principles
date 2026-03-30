from __future__ import annotations

import json
from pathlib import Path

from core.level_manager import LevelManager
from core.word_processor import WordProcessor
from data.db_manager import DBManager


class MockAPI:
    def ask(self, prompt: str) -> str:
        words = ["abandon", "resilient", "ambiguous"]
        payload = []
        for w in words:
            payload.append(
                {
                    "word": w,
                    "definition": f"{w} 的核心释义",
                    "tone": "通用中性",
                    "nuance": "有语感差异",
                    "scenario": "真实场景",
                    "collocations": [f"{w} sth", f"{w} quickly", f"{w} with care"],
                    "memory_hook": "记忆钩子",
                    "example_sentence": f"I use {w} in context. | 我在语境中使用它。",
                    "common_mistake": "错法 -> 正法",
                }
            )
        return json.dumps(payload, ensure_ascii=False)


def main() -> None:
    base = Path(__file__).resolve().parent
    db_path = base / "data" / "step2_test.db"
    if db_path.exists():
        db_path.unlink()

    db = DBManager(str(db_path))
    level_manager = LevelManager(db, str(base / "config.yaml"))
    wp = WordProcessor(
        api_client=MockAPI(),
        db_manager=db,
        level_manager=level_manager,
        config_path=str(base / "config.yaml"),
        prompt_path=str(base / "prompts" / "word_analysis.txt"),
    )

    result = wp.analyze_words(["abandon", "resilient", "ambiguous"], "测试场景")
    words = {x["word"] for x in result}
    assert words == {"abandon", "resilient", "ambiguous"}

    rows = db.list_words()
    assert len(rows) == 3
    assert all(r["level"] == "new" for r in rows)
    print("[step2] 通过")


if __name__ == "__main__":
    main()
