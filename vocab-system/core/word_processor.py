from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Any, Callable, Dict, List

import yaml

from core.api_client import APIClient
from core.level_manager import LevelManager
from data.db_manager import DBManager


class WordProcessor:
    def __init__(
        self,
        api_client: APIClient,
        db_manager: DBManager,
        level_manager: LevelManager,
        config_path: str = "config.yaml",
        prompt_path: str = "prompts/word_analysis.txt",
    ) -> None:
        self.api_client = api_client
        self.db = db_manager
        self.level_manager = level_manager
        self.config_path = Path(config_path)
        self.prompt_template = Path(prompt_path).read_text(encoding="utf-8")
        self.max_words = self._load_max_words(config_path)
        self.log_file = self.config_path.parent / "logs" / "parse_errors.log"

    def _load_max_words(self, config_path: str) -> int:
        with Path(config_path).open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return int(config.get("learning", {}).get("max_words_per_batch", 20))

    def analyze_words(self, words: List[str], source_context: str) -> List[Dict[str, Any]]:
        return self.analyze_words_with_progress(words, source_context)

    def analyze_words_with_progress(
        self,
        words: List[str],
        source_context: str,
        on_progress: Callable[[str], None] | None = None,
        on_stream_chunk: Callable[[str], None] | None = None,
        cancel_event: Event | None = None,
    ) -> List[Dict[str, Any]]:
        clean_words = self._normalize_input_words(words)
        if not clean_words:
            raise ValueError("未检测到有效英文单词。请检查输入是否包含英文字母词汇。")

        def emit(msg: str) -> None:
            if on_progress is not None:
                on_progress(msg)

        def is_cancelled() -> bool:
            return bool(cancel_event is not None and cancel_event.is_set())

        if is_cancelled():
            raise ValueError("已取消本次分析")

        saved: List[Dict[str, Any]] = []
        batch_size = max(1, int(self.max_words))
        batches = [clean_words[i : i + batch_size] for i in range(0, len(clean_words), batch_size)]

        for idx, batch_words in enumerate(batches, start=1):
            if is_cancelled():
                raise ValueError("已取消本次分析")

            emit(f"第 {idx}/{len(batches)} 批：正在连接 AI…")
            prompt = self.prompt_template.replace("{source_context}", source_context.strip()).replace(
                "{words}", "\n".join(f"- {w}" for w in batch_words)
            )

            chunks: List[str] = []

            def on_chunk(delta: str) -> None:
                chunks.append(delta)
                if on_stream_chunk is not None:
                    on_stream_chunk(delta)
                if len(chunks) % 8 == 0:
                    emit(f"第 {idx}/{len(batches)} 批：AI 输出中… {sum(len(x) for x in chunks)} 字")

            ask_stream = getattr(self.api_client, "ask_stream", None)
            if callable(ask_stream):
                ask_stream(prompt, on_chunk, should_stop=is_cancelled)
                raw = "".join(chunks)
            else:
                emit(f"第 {idx}/{len(batches)} 批：AI 输出中…")
                raw = self.api_client.ask(prompt)
                if on_stream_chunk is not None and raw:
                    on_stream_chunk(raw)

            if is_cancelled():
                raise ValueError("已取消本次分析")

            emit(f"第 {idx}/{len(batches)} 批：AI 输出完成，正在解析…")
            parsed = self._parse_with_retry(raw, module_name="word_processor", base_prompt=prompt)

            batch_saved = 0
            for item in parsed:
                if is_cancelled():
                    raise ValueError("已取消本次分析")
                item["source_context"] = source_context
                item["word_bank"] = "new"
                word_id = self.db.upsert_word(item)
                self.level_manager.initialize_level(word_id)
                item["id"] = word_id
                saved.append(item)
                batch_saved += 1

            emit(f"第 {idx}/{len(batches)} 批：保存完成 {batch_saved} 个")

        emit(f"全部完成，共保存 {len(saved)} 个")
        return saved

    def _normalize_input_words(self, words: List[str]) -> List[str]:
        text = "\n".join(str(w) for w in words if w is not None)
        # Accept mixed Chinese/English input and keep only English-like tokens.
        candidates = re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)?", text)
        ordered: List[str] = []
        seen = set()
        for token in candidates:
            w = token.strip().lower()
            if not w or w in seen:
                continue
            seen.add(w)
            ordered.append(w)
        return ordered

    def _parse_with_retry(self, raw: str, module_name: str, base_prompt: str) -> List[Dict[str, Any]]:
        try:
            return self._parse_analysis_response(raw)
        except Exception as first_exc:
            self._log_parse_error(module_name, raw, first_exc)
            retry_prompt = (
                "上次你的返回格式不合法，这次请严格只输出 JSON，没有任何其他内容。\n\n"
                + base_prompt
            )
            retry_raw = self.api_client.ask(retry_prompt)
            try:
                return self._parse_analysis_response(retry_raw)
            except Exception as second_exc:
                self._log_parse_error(module_name, retry_raw, second_exc)
                raise ValueError("词汇分析返回格式异常，请稍后重试。") from second_exc

    def _parse_analysis_response(self, text: str) -> List[Dict[str, Any]]:
        data = self._parse_json_with_cleanup(text)

        if isinstance(data, dict) and "words" in data:
            data = data["words"]
        elif isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError("Word analysis response must be a JSON list.")

        normalized: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "word": str(self._pick(item, ["word", "单词"]) or "").strip(),
                    "definition": str(
                        self._pick(item, ["definition", "meaning", "释义", "中文释义"]) or ""
                    ).strip(),
                    "tone": str(self._pick(item, ["tone", "style", "情感色彩", "语气"]) or "").strip(),
                    "scenario": str(self._pick(item, ["scenario", "usage", "使用场景"]) or "").strip(),
                    "memory_hook": str(
                        self._pick(item, ["memory_hook", "mnemonic", "记忆钩子"]) or ""
                    ).strip(),
                }
            )
        return [x for x in normalized if x["word"] and x["definition"]]

    def _parse_json_with_cleanup(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            cleaned = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
            json_str = self._extract_json(cleaned)
            return json.loads(json_str)

    def _pick(self, item: Dict[str, Any], keys: List[str]) -> Any:
        for key in keys:
            if key in item and item[key] is not None:
                return item[key]
        return None

    def _log_parse_error(self, module_name: str, content: str, exc: Exception) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().isoformat(timespec="seconds")
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{module_name}] 原始返回内容：{content}\n")
            f.write(f"[{ts}] [{module_name}] 解析错误：{exc}\n\n")

    def _extract_json(self, text: str) -> str:
        fence_match = re.search(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fence_match:
            return fence_match.group(1)

        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch not in "[{":
                continue
            try:
                _, end = decoder.raw_decode(text[idx:])
                return text[idx : idx + end]
            except json.JSONDecodeError:
                continue

        raise ValueError("No JSON payload found in model response.")
