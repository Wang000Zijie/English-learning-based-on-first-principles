from __future__ import annotations

import threading
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from typing import List

from core.sentence_checker import SentenceChecker
from data.db_manager import DBManager
from ui.font_manager import FontManager
from ui.textbox_manager import TextboxManager


class SentencePanel(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        sentence_checker: SentenceChecker,
        db_manager: DBManager,
        font_manager: FontManager,
        textbox_manager: TextboxManager,
    ) -> None:
        super().__init__(master)
        self.sentence_checker = sentence_checker
        self.db = db_manager
        self.font_manager = font_manager
        self.textbox_manager = textbox_manager
        self.words: List[dict] = []
        self._blink_job = None
        self._blink = False
        self._build_ui()
        self.reload_words()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)
        title = ctk.CTkLabel(self, text="造句练习", font=ctk.CTkFont(size=24, weight="bold"), text_color="#4A9EFF")
        title.grid(row=0, column=0, sticky="w", padx=24, pady=(20, 12))
        self.font_manager.register(title)

        top = ctk.CTkFrame(self)
        top.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 8))
        top_label = ctk.CTkLabel(top, text="选择目标词:", text_color="#9A9A9A")
        top_label.pack(side="left")
        self.font_manager.register(top_label)

        self.word_var = ctk.StringVar()
        self.word_box = ctk.CTkComboBox(top, variable=self.word_var, values=[])
        self.word_box.pack(side="left", fill="x", expand=True, padx=6)
        self.font_manager.register(self.word_box)

        reload_btn = ctk.CTkButton(top, text="刷新词库", width=90, command=self.reload_words)
        reload_btn.pack(side="left")
        self.font_manager.register(reload_btn)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 8))
        self.submit_btn = ctk.CTkButton(actions, text="提交批改", command=self._check)
        self.submit_btn.pack(side="left")
        self.font_manager.register(self.submit_btn)
        self.status_label = ctk.CTkLabel(actions, text="", text_color="#9A9A9A")
        self.status_label.pack(side="left", padx=12)
        self.font_manager.register(self.status_label)

        pane_holder = ctk.CTkFrame(self, fg_color="transparent")
        pane_holder.grid(row=5, column=0, sticky="nsew", padx=24, pady=(0, 20))
        pane_holder.grid_columnconfigure(0, weight=1)
        pane_holder.grid_rowconfigure(0, weight=1)

        pane = tk.PanedWindow(
            pane_holder,
            orient=tk.VERTICAL,
            sashwidth=10,
            bd=0,
            relief="flat",
            bg="#2B2B2B",
            showhandle=False,
        )
        pane.grid(row=0, column=0, sticky="nsew")

        sentence_section = ctk.CTkFrame(pane_holder, fg_color="transparent")
        sentence_section.grid_columnconfigure(0, weight=1)
        sentence_section.grid_rowconfigure(1, weight=1)
        sentence_label = ctk.CTkLabel(sentence_section, text="输入你的句子:", text_color="#9A9A9A")
        sentence_label.grid(row=0, column=0, sticky="w")
        self.font_manager.register(sentence_label)
        self.sentence_text = ctk.CTkTextbox(sentence_section, height=120, font=("微软雅黑", self.font_manager.size))
        self.sentence_text.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.font_manager.register(self.sentence_text)

        stream_section = ctk.CTkFrame(pane_holder, fg_color="transparent")
        stream_section.grid_columnconfigure(0, weight=1)
        stream_section.grid_rowconfigure(1, weight=1)
        stream_label = ctk.CTkLabel(stream_section, text="流式输出", text_color="#9A9A9A")
        stream_label.grid(row=0, column=0, sticky="w")
        self.font_manager.register(stream_label)
        self.stream_text = ctk.CTkTextbox(stream_section, height=90, font=("Consolas", self.font_manager.size))
        self.stream_text.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.font_manager.register(self.stream_text, family="Consolas")

        result_section = ctk.CTkFrame(pane_holder, fg_color="transparent")
        result_section.grid_columnconfigure(0, weight=1)
        result_section.grid_rowconfigure(1, weight=1)
        result_label = ctk.CTkLabel(result_section, text="批改结果", text_color="#9A9A9A")
        result_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.font_manager.register(result_label)

        self.result_container = ctk.CTkScrollableFrame(result_section, height=240)
        self.result_container.grid(row=1, column=0, sticky="nsew")
        self.result_container.grid_columnconfigure(0, weight=1)

        self.badge = ctk.CTkLabel(self.result_container, text="等待提交", text_color="#9A9A9A")
        self.badge.grid(row=0, column=0, sticky="w", pady=(4, 8))
        self.font_manager.register(self.badge)
        self.usage_card = ctk.CTkTextbox(self.result_container, height=110, font=("微软雅黑", self.font_manager.size))
        self.usage_card.grid(row=1, column=0, sticky="ew", pady=6)
        self.font_manager.register(self.usage_card)
        self.grammar_card = ctk.CTkTextbox(self.result_container, height=120, font=("微软雅黑", self.font_manager.size))
        self.grammar_card.grid(row=2, column=0, sticky="ew", pady=6)
        self.font_manager.register(self.grammar_card)
        self.natural_card = ctk.CTkTextbox(self.result_container, height=90, font=("微软雅黑", self.font_manager.size))
        self.natural_card.grid(row=3, column=0, sticky="ew", pady=6)
        self.font_manager.register(self.natural_card)
        self.encourage_label = ctk.CTkLabel(self.result_container, text="", text_color="#FFB347")
        self.encourage_label.grid(row=4, column=0, sticky="ew", pady=(6, 2))
        self.font_manager.register(self.encourage_label)

        pane.add(sentence_section, minsize=120)
        pane.add(stream_section, minsize=100)
        pane.add(result_section, minsize=180)

    def reload_words(self) -> None:
        self.words = self.db.list_words()
        names = [w["word"] for w in self.words]
        self.word_box.configure(values=names)
        if names:
            self.word_var.set(names[0])

    def _check(self) -> None:
        selected = self.word_var.get().strip()
        sentence = self.sentence_text.get("1.0", "end").strip()

        if not selected:
            messagebox.showwarning("提示", "请先选择目标词。")
            return
        if not sentence:
            messagebox.showwarning("提示", "请先输入句子。")
            return

        word_obj = next((w for w in self.words if w["word"] == selected), None)
        if not word_obj:
            messagebox.showerror("错误", "未找到所选单词，请刷新词库。")
            return

        self._set_loading(True)
        self.stream_text.delete("1.0", "end")

        def worker() -> None:
            try:
                result = self.sentence_checker.check_sentence_stream(
                    word_obj["id"],
                    selected,
                    sentence,
                    callback=lambda part: self.stream_text.after(0, lambda p=part: self.stream_text.insert("end", p)),
                )
                self.after(0, lambda: self._render_result(result))
            except Exception as exc:
                self.after(0, lambda: self._on_error(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _render_result(self, result: dict) -> None:
        self._set_loading(False)
        ok = bool(result.get("is_correct", False))
        self.badge.configure(
            text=("✓ 基本正确" if ok else "✗ 有误"),
            text_color=("#5DBF7F" if ok else "#E06C75"),
            font=ctk.CTkFont(size=18, weight="bold"),
        )

        self.usage_card.delete("1.0", "end")
        self.usage_card.insert("end", "词汇使用分析\n" + str(result.get("word_usage_analysis", "")))

        self.grammar_card.delete("1.0", "end")
        issues = result.get("grammar_issues", [])
        if issues:
            lines = ["语法问题列表"]
            for idx, issue in enumerate(issues, start=1):
                if isinstance(issue, dict):
                    lines.append(
                        f"{idx}. 错误: {issue.get('error', '')}\n   解释: {issue.get('explanation', '')}\n   修正: {issue.get('fix', '')}"
                    )
                else:
                    lines.append(f"{idx}. {issue}")
            self.grammar_card.insert("end", "\n".join(lines))
        else:
            self.grammar_card.insert("end", "语法问题列表\n无明显语法问题")

        self.natural_card.delete("1.0", "end")
        self.natural_card.insert(
            "end",
            "更自然版本\n" + str(result.get("more_natural_version", "")) + "\n\n修正句子\n" + str(result.get("corrected_sentence", "")),
        )

        self.encourage_label.configure(text=str(result.get("encouragement", "")))

    def _on_error(self, exc: Exception) -> None:
        self._set_loading(False)
        messagebox.showerror("批改失败", str(exc))

    def _set_loading(self, loading: bool) -> None:
        self.submit_btn.configure(state="disabled" if loading else "normal", text=("批改中…" if loading else "提交批改"))
        if loading:
            self._start_blink("批改中")
        else:
            self._stop_blink()
            self.status_label.configure(text="")

    def _start_blink(self, text: str) -> None:
        self._blink = not self._blink
        self.status_label.configure(text=f"{text} {'▌' if self._blink else ' '}")
        self._blink_job = self.after(500, lambda: self._start_blink(text))

    def _stop_blink(self) -> None:
        if self._blink_job is not None:
            self.after_cancel(self._blink_job)
            self._blink_job = None
