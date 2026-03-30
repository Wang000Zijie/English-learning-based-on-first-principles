from __future__ import annotations

import json
from pathlib import Path

from core.sentence_checker import SentenceChecker
from data.db_manager import DBManager


class MockAPI:
    def ask(self, prompt: str) -> str:
        return json.dumps(
            {
                "is_correct": False,
                "grammar_issues": [
                    {
                        "error": "He abandon",
                        "explanation": "第三人称单数需加s",
                        "fix": "He abandons",
                    }
                ],
                "corrected_sentence": "He abandons the plan.",
                "word_usage_analysis": "词义正确，时态需调整。",
                "more_natural_version": "He decided to abandon the plan.",
                "encouragement": "你已经抓住了核心词义。",
            },
            ensure_ascii=False,
        )


def main() -> None:
    base = Path(__file__).resolve().parent
    db_path = base / "data" / "step4_test.db"
    if db_path.exists():
        db_path.unlink()

    db = DBManager(str(db_path))
    word_id = db.upsert_word({"word": "abandon", "definition": "放弃"})

    checker = SentenceChecker(
        api_client=MockAPI(),
        db_manager=db,
        prompt_path=str(base / "prompts" / "sentence_check.txt"),
    )
    result = checker.check_sentence(word_id, "abandon", "He abandon the plan.")
    assert result["corrected_sentence"]
    assert isinstance(result["grammar_issues"], list)
    print("[step4] 通过")


if __name__ == "__main__":
    main()
