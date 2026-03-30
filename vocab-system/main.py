from __future__ import annotations

from pathlib import Path

from core.api_client import APIClient
from core.level_manager import LevelManager
from core.passage_generator import PassageGenerator
from core.review_engine import ReviewEngine
from core.sentence_checker import SentenceChecker
from core.word_processor import WordProcessor
from data.db_manager import DBManager
from ui.main_window import MainWindow


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    config_path = base_dir / "config.yaml"
    db_path = base_dir / "data" / "vocab.db"
    word_prompt = base_dir / "prompts" / "word_analysis.txt"
    sentence_prompt = base_dir / "prompts" / "sentence_check.txt"
    passage_prompt = base_dir / "prompts" / "passage_generation.txt"
    passage_review_prompt = base_dir / "prompts" / "passage_review.txt"

    db = DBManager(str(db_path))
    api = APIClient(str(config_path))
    level_manager = LevelManager(db_manager=db, config_path=str(config_path))

    word_processor = WordProcessor(
        api_client=api,
        db_manager=db,
        level_manager=level_manager,
        config_path=str(config_path),
        prompt_path=str(word_prompt),
    )
    review_engine = ReviewEngine(db_manager=db, level_manager=level_manager, config_path=str(config_path))
    sentence_checker = SentenceChecker(
        api_client=api,
        db_manager=db,
        prompt_path=str(sentence_prompt),
    )
    passage_generator = PassageGenerator(
        api_client=api,
        db_manager=db,
        level_manager=level_manager,
        config_path=str(config_path),
        prompt_path=str(passage_prompt),
        review_prompt_path=str(passage_review_prompt),
    )

    app = MainWindow(
        db_manager=db,
        word_processor=word_processor,
        review_engine=review_engine,
        sentence_checker=sentence_checker,
        passage_generator=passage_generator,
        config_path=str(config_path),
    )
    app.run()


if __name__ == "__main__":
    main()
