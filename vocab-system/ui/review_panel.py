from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox
from typing import Callable, Dict, List

from core.review_engine import ReviewEngine
from ui.font_manager import FontManager


class ReviewPanel(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        review_engine: ReviewEngine,
        on_reviewed: Callable[[], None],
        font_manager: FontManager,
    ) -> None:
        super().__init__(master)
        self.review_engine = review_engine
        self.on_reviewed = on_reviewed
        self.font_manager = font_manager
        self.words: List[Dict] = []
        self.current_idx = 0
        self.current_word_id = None
        self._status_job = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(self, text="今日复习", font=ctk.CTkFont(size=24, weight="bold"), text_color="#4A9EFF")
        title.grid(row=0, column=0, sticky="w", padx=24, pady=(20, 12))
        self.font_manager.register(title)

        self.count_label = ctk.CTkLabel(self, text="待复习: 0")
        self.count_label.grid(row=1, column=0, sticky="w", padx=24)
        self.font_manager.register(self.count_label)
        refresh_btn = ctk.CTkButton(self, text="刷新", width=90, command=self.reload_due_words)
        refresh_btn.grid(
            row=1, column=0, sticky="e", padx=24
        )
        self.font_manager.register(refresh_btn)

        self.word_label = ctk.CTkLabel(self, text="暂无待复习单词", font=ctk.CTkFont(size=36, weight="bold"), text_color="#4A9EFF")
        self.word_label.grid(row=2, column=0, sticky="w", padx=24, pady=(18, 8))
        self.font_manager.register(self.word_label)

        self.card = ctk.CTkFrame(self, fg_color="#2A2A2A")
        self.card.grid(row=3, column=0, sticky="nsew", padx=24, pady=8)
        self.card.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.definition_value = self._make_row(0, "释义")
        self.tone_value = self._make_row(1, "色彩")
        self.scenario_value = self._make_row(2, "场景")
        self.memory_value = self._make_row(3, "记忆")
        self.source_value = self._make_row(4, "来源")

        actions = ctk.CTkFrame(self)
        actions.grid(row=4, column=0, sticky="ew", padx=24, pady=8)
        detail_btn = ctk.CTkButton(actions, text="显示解析", command=self._show_detail)
        detail_btn.pack(side="left", padx=(6, 0), pady=6)
        self.font_manager.register(detail_btn)
        self.btn_remembered = ctk.CTkButton(actions, text="记住了", fg_color="#5DBF7F", hover_color="#4EAA70", command=self.on_remembered)
        self.btn_remembered.pack(side="left", padx=8, pady=6)
        self.font_manager.register(self.btn_remembered)
        self.btn_forgotten = ctk.CTkButton(actions, text="没记住", fg_color="#E06C75", hover_color="#C55C63", command=self.on_forgotten)
        self.btn_forgotten.pack(side="left", pady=6)
        self.font_manager.register(self.btn_forgotten)

        self.status_label = ctk.CTkLabel(self, text="", text_color="#5DBF7F")
        self.status_label.grid(row=5, column=0, sticky="w", padx=24, pady=(2, 10))
        self.font_manager.register(self.status_label)

    def _make_row(self, row: int, title: str) -> ctk.CTkLabel:
        ctk.CTkLabel(self.card, text=title, text_color="#9A9A9A").grid(row=row, column=0, sticky="nw", padx=16, pady=(12 if row == 0 else 6, 6))
        self.font_manager.register(self.card.winfo_children()[-1])
        value = ctk.CTkLabel(self.card, text="-", text_color="#E8E8E8", justify="left", wraplength=900)
        value.grid(row=row, column=1, sticky="w", padx=(8, 16), pady=(12 if row == 0 else 6, 6))
        self.font_manager.register(value)
        return value

    def reload_due_words(self) -> None:
        self.words = self.review_engine.get_due_words_today()
        self.current_idx = 0
        self.count_label.configure(text=f"待复习: {len(self.words)}")
        self._render_current_word()

    def _render_current_word(self) -> None:
        self.definition_value.configure(text="-")
        self.tone_value.configure(text="-")
        self.scenario_value.configure(text="-")
        self.memory_value.configure(text="-")
        self.source_value.configure(text="-")
        if not self.words:
            self.current_word_id = None
            self.word_label.configure(text="今天没有需要复习的词，做得很好！")
            return
        if self.current_idx >= len(self.words):
            self.current_word_id = None
            self.word_label.configure(text="今天复习已完成，继续保持！")
            return

        current = self.words[self.current_idx]
        self.current_word_id = current.get("id")
        self.word_label.configure(text=current["word"])

    def _show_detail(self) -> None:
        if not self.words or self.current_idx >= len(self.words):
            return
        current = self.words[self.current_idx]
        self.definition_value.configure(text=str(current.get("definition", "")))
        self.tone_value.configure(text=str(current.get("tone", "")))
        self.scenario_value.configure(text=str(current.get("scenario", "")))
        self.memory_value.configure(text=str(current.get("memory_hook", "")))
        self.source_value.configure(text=str(current.get("source_context", "")))

    def _reload_and_next(self) -> None:
        self.words = self.review_engine.get_due_words_today()
        self.current_idx = 0
        self.count_label.configure(text=f"待复习: {len(self.words)}")
        self._render_current_word()

    def _set_buttons_state(self, state: str) -> None:
        self.btn_remembered.configure(state=state)
        self.btn_forgotten.configure(state=state)

    def _show_status(self, text: str, error: bool = False) -> None:
        self.status_label.configure(text=text, text_color=("#E06C75" if error else "#5DBF7F"))
        if self._status_job is not None:
            self.after_cancel(self._status_job)
        self._status_job = self.after(3000, lambda: self.status_label.configure(text=""))

    def on_remembered(self) -> None:
        try:
            if self.current_word_id is None:
                self._show_status("没有正在复习的词，请先点击刷新", error=True)
                return
            self._set_buttons_state("disabled")
            self.review_engine.record_review(int(self.current_word_id), "remembered")
            self._reload_and_next()
            self._show_status("已记录：记住了 ✓")
            self.on_reviewed()
        except Exception as exc:
            self._show_status(f"记录失败：{exc}", error=True)
            self._set_buttons_state("normal")
            messagebox.showerror("记录失败", str(exc))
        else:
            self._set_buttons_state("normal")

    def on_forgotten(self) -> None:
        try:
            if self.current_word_id is None:
                self._show_status("没有正在复习的词，请先点击刷新", error=True)
                return
            self._set_buttons_state("disabled")
            self.review_engine.record_review(int(self.current_word_id), "forgotten")
            self._reload_and_next()
            self._show_status("已记录：没记住，已重新安排复习")
            self.on_reviewed()
        except Exception as exc:
            self._show_status(f"记录失败：{exc}", error=True)
            self._set_buttons_state("normal")
            messagebox.showerror("记录失败", str(exc))
        else:
            self._set_buttons_state("normal")

