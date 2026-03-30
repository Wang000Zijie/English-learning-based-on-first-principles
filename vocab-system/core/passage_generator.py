from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Any, Callable, Dict, List, Optional

import yaml

from core.api_client import APIClient
from core.config_manager import ConfigManager
from core.level_manager import LevelManager
from core.storyline_manager import StorylineManager
from data.db_manager import DBManager


class PassageGenerator:
    def __init__(
        self,
        api_client: APIClient,
        db_manager: DBManager,
        level_manager: LevelManager,
        config_path: str = "config.yaml",
        prompt_path: str = "prompts/passage_generation.txt",
        review_prompt_path: str = "prompts/passage_review.txt",
    ) -> None:
        self.api_client = api_client
        self.db = db_manager
        self.level_manager = level_manager
        self.config_path = Path(config_path)
        self.config_manager = ConfigManager(config_path)
        self.prompt_template = Path(prompt_path).read_text(encoding="utf-8")
        self.review_prompt_template = Path(review_prompt_path).read_text(encoding="utf-8") if Path(review_prompt_path).exists() else ""
        self.storyline_manager = StorylineManager(db_manager)
        self.log_file = self.config_path.parent / "logs" / "parse_errors.log"

    def generate(
        self,
        story_direction: str = "freeform",
        direction_id: str = "freeform",
        on_status: Optional[Callable[[str], None]] = None,
        on_stream_chunk: Optional[Callable[[str], None]] = None,
        cancel_event: Optional[Event] = None,
    ) -> Dict[str, Any]:
        def is_cancelled() -> bool:
            return bool(cancel_event is not None and cancel_event.is_set())

        if is_cancelled():
            raise ValueError("已取消生成")

        cfg = self._load_passage_cfg()
        new_feed_count = int(cfg["new_word_feed_count"])
        if new_feed_count <= 0:
            target_words = self.db.get_words_by_levels(cfg["preferred_levels"], word_bank="new")
            if not target_words:
                target_words = self.db.list_words(word_bank="new")
        else:
            target_words = self.level_manager.select_words_for_passage(
                levels=cfg["preferred_levels"],
                min_words=new_feed_count,
                max_words=new_feed_count,
                word_bank="new",
            )
        if not target_words:
            raise ValueError("生词库为空，无法生成短文。请先添加生词。")

        familiar_ref_count = int(cfg["familiar_reference_words"])
        if familiar_ref_count <= 0:
            familiar_words = self.db.list_words(word_bank="familiar")
        else:
            familiar_words = self.level_manager.select_words_for_passage(
                levels=["mastered", "familiar", "learning", "new"],
                min_words=familiar_ref_count,
                max_words=familiar_ref_count,
                word_bank="familiar",
            )

        allowed_word_to_id = {str(w["word"]).lower(): int(w["id"]) for w in target_words}
        word_lines = [f"{w['word']}（{w.get('definition', '')}）" for w in target_words]
        familiar_lines = [f"{w['word']}（{w.get('definition', '')}）" for w in familiar_words]

        storyline = self.storyline_manager.get_or_create_active_storyline(
            word_ids=[int(w["id"]) for w in target_words],
            direction_id=direction_id,
            name_hint=f"{target_words[0]['word']} 等词汇",
        )
        storyline_id = int(storyline["id"])
        continuation = ""
        use_continuation = bool(cfg.get("continue_previous_chapter", False))
        last_ending = self.storyline_manager.get_last_chapter_ending(storyline_id) if use_continuation else ""
        if use_continuation and last_ending:
            continuation = (
                "\n\n【上一章结尾（请在此基础上续写，保持人物、场景的连贯性）】\n"
                f"{last_ending}\n\n"
                "【本章要求】\n"
                "- 时间线在上一章之后\n"
                "- 可以出现上一章的人物或地点，但剧情必须有新的发展\n"
                "- 不要重复上一章已经出现过的情节\n"
            )

        prompt = (
            self.prompt_template.replace("{story_direction}", story_direction)
            .replace("{familiar_word_count}", str(len(familiar_words)))
            .replace("{familiar_word_list_with_definitions}", "\n".join(familiar_lines) if familiar_lines else "（熟词库暂为空）")
            .replace("{word_list_with_definitions}", "\n".join(word_lines))
        ) + continuation

        if on_status:
            on_status("Author 写作中…")
        raw = self._ask_author(prompt, on_stream_chunk=on_stream_chunk, cancel_event=cancel_event)
        if is_cancelled():
            raise ValueError("已取消生成")
        raw = self._run_multi_model_review_if_needed(raw, allowed_word_to_id, on_status, cancel_event=cancel_event)
        if is_cancelled():
            raise ValueError("已取消生成")
        data = self._parse_with_retry(raw, module_name="passage_generator", base_prompt=prompt)
        if not isinstance(data, dict):
            raise ValueError("短文生成返回格式错误，应为 JSON 对象。")

        notes = data.get("vocabulary_notes", [])
        if not isinstance(notes, list):
            notes = []
        cleaned_notes: List[Dict[str, Any]] = []
        removed_words: List[str] = []
        used_word_ids: List[int] = []
        word_to_definition = {str(w.get("word", "")).lower(): str(w.get("definition", "") or "") for w in target_words}
        for n in notes:
            if not isinstance(n, dict):
                continue
            note_word = str(n.get("word", "")).strip().lower()
            if note_word in allowed_word_to_id:
                cleaned_notes.append(n)
                wid = allowed_word_to_id[note_word]
                if wid not in used_word_ids:
                    used_word_ids.append(wid)
            elif note_word:
                removed_words.append(note_word)

        if removed_words:
            self._log_parse_error(
                "passage_generator_warning",
                f"以下词汇不在你的词库中，已自动移除：{', '.join(removed_words)}",
                ValueError("illegal_vocabulary_notes"),
            )

        translation_text = str(data.get("translation", ""))
        self._normalize_translation_anchors(cleaned_notes, translation_text, word_to_definition)
        data["vocabulary_notes"] = cleaned_notes
        data["title"] = self._make_short_title(
            str(data.get("title", "")),
            str(data.get("translation", "")),
            str(data.get("content", "")),
        )
        level_mix = self._build_level_mix(target_words)
        pid = self.db.add_passage_record(
            title=str(data.get("title", "")),
            content=str(data.get("content", "")),
            translation=str(data.get("translation", "")),
            vocabulary_notes=cleaned_notes,
            word_ids=used_word_ids,
            level_mix=level_mix,
            story_direction=direction_id,
        )
        self.storyline_manager.add_chapter(
            storyline_id=storyline_id,
            passage_id=pid,
            mastery_snapshot={str(w["word"]): str(w.get("level", "new")) for w in target_words},
        )
        self.db.increment_passage_count(used_word_ids)
        data["id"] = pid
        data["word_ids"] = used_word_ids
        data["level_mix"] = level_mix
        data["removed_words"] = removed_words
        data["storyline_id"] = storyline_id

        if self.storyline_manager.is_storyline_mastered(storyline):
            self.db.complete_storyline(storyline_id)
            data["storyline_completed"] = True
        else:
            data["storyline_completed"] = False

        if on_status:
            on_status("完成")
        return data

    def abandon_last_chapter(self, storyline_id: int) -> bool:
        deleted = self.storyline_manager.abandon_last_chapter(storyline_id)
        return deleted is not None

    def _ask_author(
        self,
        prompt: str,
        on_stream_chunk: Optional[Callable[[str], None]] = None,
        cancel_event: Optional[Event] = None,
    ) -> str:
        def is_cancelled() -> bool:
            return bool(cancel_event is not None and cancel_event.is_set())

        cfg = self.config_manager.load().get("agent_roles", {})
        role = "author" if bool(cfg.get("enabled", False)) else None
        ask_stream = getattr(self.api_client, "ask_stream_with_role" if role else "ask_stream", None)
        if callable(ask_stream):
            chunks: List[str] = []

            def on_chunk(delta: str) -> None:
                chunks.append(delta)
                if on_stream_chunk is not None:
                    on_stream_chunk(delta)

            if role:
                self.api_client.ask_stream_with_role(prompt, on_chunk, role, should_stop=is_cancelled)
            else:
                self.api_client.ask_stream(prompt, on_chunk, should_stop=is_cancelled)
            return "".join(chunks)

        if bool(cfg.get("enabled", False)):
            return self.api_client.ask_with_role(prompt, "author")
        return self.api_client.ask(prompt)

    def _run_multi_model_review_if_needed(
        self,
        draft: str,
        allowed_word_to_id: Dict[str, int],
        on_status: Optional[Callable[[str], None]] = None,
        cancel_event: Optional[Event] = None,
    ) -> str:
        if cancel_event is not None and cancel_event.is_set():
            raise ValueError("已取消生成")
        cfg = self.config_manager.load().get("agent_roles", {})
        if not bool(cfg.get("enabled", False)):
            return draft

        if on_status:
            on_status("Analyst 审核中…")
        review = self._analyst_review(draft, list(allowed_word_to_id.keys()))
        quality = str(review.get("overall_quality", "acceptable")).lower()
        issues = review.get("issues", [])
        if quality == "poor" or (isinstance(issues, list) and len(issues) > 3):
            fix_prompt = (
                "请根据以下问题修订你的短文，确保输出仍为 JSON，且 vocabulary_notes 只包含给定目标词。\n"
                f"问题：{json.dumps(review, ensure_ascii=False)}\n\n"
                f"原稿：{draft}"
            )
            draft = self._ask_author(fix_prompt, cancel_event=cancel_event)

        roles = cfg.get("roles", {})
        if bool(roles.get("reviewer_enabled", False)):
            if on_status:
                on_status("Reviewer 润色中…")
            reviewer_prompt = (
                "你是英文文本润色编辑。保持 JSON 结构不变，仅改进语言自然度与一致性。\n\n"
                f"{draft}"
            )
            draft = self.api_client.ask_with_role(reviewer_prompt, "reviewer")
        return draft

    def _analyst_review(self, passage_payload: str, word_list: List[str]) -> Dict[str, Any]:
        if self.review_prompt_template:
            prompt = (
                self.review_prompt_template.replace("{word_list}", ", ".join(word_list)).replace(
                    "{passage_content}", passage_payload
                )
            )
        else:
            prompt = (
                "你是一位英语语言分析师。请审查以下短文 JSON，返回 JSON："
                '{"issues": [], "overall_quality": "good", "suggested_fixes": []}\n\n'
                f"目标词：{', '.join(word_list)}\n{passage_payload}"
            )
        raw = self.api_client.ask_with_role(prompt, "analyst")
        try:
            data = self._parse_json(raw)
            return data if isinstance(data, dict) else {"issues": [], "overall_quality": "acceptable"}
        except Exception:
            return {"issues": [], "overall_quality": "acceptable"}

    def _load_passage_cfg(self) -> Dict[str, Any]:
        with self.config_path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        p = config.get("learning", {}).get("passage", {})
        legacy_max = int(p.get("max_words", 10))
        return {
            "preferred_levels": list(p.get("preferred_levels", ["learning", "familiar"])),
            "familiar_reference_words": int(p.get("familiar_reference_words", 80)),
            "new_word_feed_count": int(p.get("new_word_feed_count", legacy_max)),
            "continue_previous_chapter": bool(p.get("continue_previous_chapter", False)),
        }

    def _parse_with_retry(self, raw: str, module_name: str, base_prompt: str) -> Any:
        try:
            return self._parse_json(raw)
        except Exception as first_exc:
            self._log_parse_error(module_name, raw, first_exc)
            retry_prompt = (
                "上次你的返回格式不合法，这次请严格只输出 JSON，没有任何其他内容。\n\n"
                + base_prompt
            )
            retry_raw = self.api_client.ask(retry_prompt)
            try:
                return self._parse_json(retry_raw)
            except Exception as second_exc:
                self._log_parse_error(module_name, retry_raw, second_exc)
                raise ValueError("短文生成解析失败，请稍后重试。") from second_exc

    def _parse_json(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            cleaned = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
            decoder = json.JSONDecoder()
            for idx, ch in enumerate(cleaned):
                if ch not in "[{":
                    continue
                try:
                    obj, _end = decoder.raw_decode(cleaned[idx:])
                    return obj
                except json.JSONDecodeError:
                    continue
            return json.loads(cleaned)

    def _log_parse_error(self, module_name: str, content: str, exc: Exception) -> None:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().isoformat(timespec="seconds")
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{module_name}] 原始返回内容：{content}\n")
            f.write(f"[{ts}] [{module_name}] 解析错误：{exc}\n\n")

    def _build_level_mix(self, words: List[Dict[str, Any]]) -> str:
        bucket: Dict[str, int] = {}
        for w in words:
            lv = str(w.get("level", "new"))
            bucket[lv] = bucket.get(lv, 0) + 1
        return "，".join(f"{k}:{v}" for k, v in sorted(bucket.items()))

    def _make_short_title(self, raw_title: str, translation: str, content: str) -> str:
        def clean(text: str) -> str:
            text = re.sub(r"\s+", " ", (text or "").strip())
            text = text.strip("\"'，。！？：:；;,.!?")
            return text

        def trim_to_15(text: str) -> str:
            t = clean(text)
            return t[:15] if len(t) > 15 else t

        title = trim_to_15(raw_title)
        if title:
            return title

        zh = clean(translation)
        if zh:
            cut = re.split(r"[。！？!?\n]", zh)[0].strip()
            cut = trim_to_15(cut)
            if cut:
                return cut

        en = clean(content)
        if en:
            first = re.split(r"[.!?\n]", en)[0].strip()
            words = first.split()
            if words:
                return " ".join(words[:4])[:15]
        return "短文速览"

    def _normalize_translation_anchors(
        self,
        notes: List[Dict[str, Any]],
        translation: str,
        word_to_definition: Dict[str, str],
    ) -> None:
        def first_cjk_term(text: str) -> str:
            cleaned = re.sub(r"[，；、/|]", " ", text or "")
            for token in cleaned.split():
                cjk = "".join(ch for ch in token if "\u4e00" <= ch <= "\u9fff")
                if 2 <= len(cjk) <= 8:
                    return cjk
            return ""

        def pick_anchor(note: Dict[str, Any], fallback_def: str) -> str:
            candidates = [
                str(note.get("translation_anchor", "")).strip(),
                str(note.get("zh_anchor", "")).strip(),
                first_cjk_term(str(note.get("sentence_in_translation", "")).strip()),
                first_cjk_term(fallback_def),
            ]
            for c in candidates:
                if c:
                    return c
            return ""

        for note in notes:
            if not isinstance(note, dict):
                continue
            word = str(note.get("word", "")).strip().lower()
            anchor = pick_anchor(note, word_to_definition.get(word, ""))
            note["translation_anchor"] = anchor
            sentence_zh = str(note.get("sentence_in_translation", "")).strip()
            if sentence_zh and sentence_zh not in translation:
                note["sentence_in_translation"] = ""
