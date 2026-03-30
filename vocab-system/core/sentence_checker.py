from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict

from core.api_client import APIClient
from data.db_manager import DBManager


class SentenceChecker:
    def __init__(
        self,
        api_client: APIClient,
        db_manager: DBManager,
        prompt_path: str = "prompts/sentence_check.txt",
    ) -> None:
        self.api_client = api_client
        self.db = db_manager
        self.prompt_template = Path(prompt_path).read_text(encoding="utf-8")

    def check_sentence(self, word_id: int, word: str, sentence: str) -> Dict[str, Any]:
        prompt = self.prompt_template.replace("{target_word}", word.strip()).replace(
            "{user_sentence}", sentence.strip()
        )
        raw = self.api_client.ask(prompt)
        result = self._parse_result(raw)

        self._persist(word_id, sentence, result)
        return result

    def check_sentence_stream(
        self,
        word_id: int,
        word: str,
        sentence: str,
        callback: Callable[[str], None],
    ) -> Dict[str, Any]:
        prompt = self.prompt_template.replace("{target_word}", word.strip()).replace(
            "{user_sentence}", sentence.strip()
        )
        chunks: list[str] = []

        def on_chunk(text: str) -> None:
            chunks.append(text)
            callback(text)

        self.api_client.ask_stream(prompt, on_chunk)
        result = self._parse_result("".join(chunks))
        self._persist(word_id, sentence, result)
        return result

    def _persist(self, word_id: int, sentence: str, result: Dict[str, Any]) -> None:
        self.db.add_sentence_record(
            word_id=word_id,
            original_sentence=sentence,
            corrected_sentence=result.get("corrected_sentence", ""),
            word_usage_analysis=result.get("word_usage_analysis", ""),
            more_natural_version=result.get("more_natural_version", ""),
            grammar_issues=result.get("grammar_issues", []),
            encouragement=result.get("encouragement", ""),
            is_correct=bool(result.get("is_correct", False)),
        )

    def _parse_result(self, text: str) -> Dict[str, Any]:
        json_str = self._extract_json(text)
        data = json.loads(json_str)

        if not isinstance(data, dict):
            raise ValueError("Sentence check response must be a JSON object.")

        return {
            "is_correct": bool(data.get("is_correct", False)),
            "grammar_issues": data.get("grammar_issues", []),
            "corrected_sentence": str(data.get("corrected_sentence", "")).strip(),
            "word_usage_analysis": str(data.get("word_usage_analysis", "")).strip(),
            "more_natural_version": str(data.get("more_natural_version", "")).strip(),
            "encouragement": str(data.get("encouragement", "继续加油！")).strip(),
        }

    def _extract_json(self, text: str) -> str:
        fence_match = re.search(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            return fence_match.group(1)

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]

        raise ValueError("No JSON object found in sentence check response.")
