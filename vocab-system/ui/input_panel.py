from __future__ import annotations

import json
import re
import threading
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from typing import Callable, List

from core.api_client import APIClientError
from core.news_fetcher import NewsFetcher
from core.word_processor import WordProcessor
from ui.font_manager import FontManager
from ui.textbox_manager import TextboxManager


class InputPanel(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        word_processor: WordProcessor,
        on_saved: Callable[[], None],
        font_manager: FontManager,
        textbox_manager: TextboxManager,
        config_path: str,
    ) -> None:
        super().__init__(master)
        self.word_processor = word_processor
        self.on_saved = on_saved
        self.font_manager = font_manager
        self.textbox_manager = textbox_manager
        self.news_fetcher = NewsFetcher(config_path)

        self._blink_job = None
        self._blink = False
        self._analysis_thread: threading.Thread | None = None
        self._cancel_event = threading.Event()
        self._stream_preview_chunks: List[str] = []
        self.news_results: List[dict] = []

        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(self, text="添加新词", font=ctk.CTkFont(size=24, weight="bold"), text_color="#4A9EFF")
        title.grid(row=0, column=0, sticky="w", padx=24, pady=(20, 12))
        self.font_manager.register(title)

        self.mode_tabs = ctk.CTkTabview(self)
        self.mode_tabs.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 20))
        self.mode_tabs.add("手动输入")
        self.mode_tabs.add("从新闻导入")

        self._build_manual_tab(self.mode_tabs.tab("手动输入"))
        self._build_news_tab(self.mode_tabs.tab("从新闻导入"))

        self.grid_rowconfigure(1, weight=1)

    def _build_manual_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        pane = tk.PanedWindow(
            tab,
            orient=tk.VERTICAL,
            sashwidth=10,
            bd=0,
            relief="flat",
            bg="#2B2B2B",
            showhandle=False,
        )
        pane.grid(row=0, column=0, sticky="nsew", pady=(10, 20))

        top_section = ctk.CTkFrame(tab, fg_color="transparent")
        top_section.grid_columnconfigure(0, weight=1)

        label_words = ctk.CTkLabel(top_section, text="输入单词（逗号、空格或换行分隔）", text_color="#9A9A9A")
        label_words.grid(row=0, column=0, sticky="w", pady=(4, 2))
        self.font_manager.register(label_words)

        self.words_text = ctk.CTkTextbox(top_section, height=120, font=("微软雅黑", self.font_manager.size))
        self.words_text.grid(row=1, column=0, sticky="nsew", pady=(4, 12))
        self.font_manager.register(self.words_text)
        top_section.grid_rowconfigure(1, weight=1)

        context_label = ctk.CTkLabel(top_section, text="来源场景", text_color="#9A9A9A")
        context_label.grid(row=2, column=0, sticky="w")
        self.font_manager.register(context_label)

        self.context_entry = ctk.CTkEntry(top_section)
        self.context_entry.grid(row=3, column=0, sticky="ew", pady=(4, 12))
        self.font_manager.register(self.context_entry)

        actions = ctk.CTkFrame(top_section, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew")
        self.analyze_btn = ctk.CTkButton(actions, text="分析并保存", command=self._analyze)
        self.analyze_btn.pack(side="left")
        self.font_manager.register(self.analyze_btn)

        self.stop_btn = ctk.CTkButton(actions, text="停止", width=70, fg_color="#3A3A3A", command=self._cancel_analyze)
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.stop_btn.configure(state="disabled")
        self.font_manager.register(self.stop_btn)

        self.status_label = ctk.CTkLabel(actions, text="", text_color="#9A9A9A")
        self.status_label.pack(side="left", padx=12)
        self.font_manager.register(self.status_label)

        bottom_section = ctk.CTkFrame(tab, fg_color="transparent")
        bottom_section.grid_columnconfigure(0, weight=1)
        bottom_section.grid_rowconfigure(1, weight=1)

        result_label = ctk.CTkLabel(bottom_section, text="分析结果", text_color="#9A9A9A")
        result_label.grid(row=0, column=0, sticky="w", pady=(4, 4))
        self.font_manager.register(result_label)

        self.result_text = ctk.CTkTextbox(bottom_section, height=280, font=("微软雅黑", self.font_manager.size))
        self.result_text.grid(row=1, column=0, sticky="nsew", pady=(0, 4))
        self.font_manager.register(self.result_text)

        pane.add(top_section, minsize=220)
        pane.add(bottom_section, minsize=180)

    def _build_news_tab(self, tab: ctk.CTkFrame) -> None:
        tab.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(tab)
        top.grid(row=0, column=0, sticky="ew", pady=(12, 8))
        top.grid_columnconfigure(1, weight=1)

        q_label = ctk.CTkLabel(top, text="关键词")
        q_label.grid(row=0, column=0, padx=(8, 4), pady=8)
        self.font_manager.register(q_label)

        self.news_query = ctk.CTkEntry(top)
        self.news_query.grid(row=0, column=1, sticky="ew", padx=4)
        self.font_manager.register(self.news_query)

        self.freshness_var = ctk.StringVar(value="oneWeek")
        freshness = ctk.CTkOptionMenu(top, variable=self.freshness_var, values=["oneDay", "oneWeek", "oneMonth", "noLimit"])
        freshness.grid(row=0, column=2, padx=4)
        self.font_manager.register(freshness)

        search_btn = ctk.CTkButton(top, text="搜索", command=self._search_news)
        search_btn.grid(row=0, column=3, padx=(4, 8))
        self.font_manager.register(search_btn)

        self.news_list = ctk.CTkScrollableFrame(tab, height=220)
        self.news_list.grid(row=1, column=0, sticky="nsew")
        self.news_list.grid_columnconfigure(0, weight=1)

        extract_btn = ctk.CTkButton(tab, text="提取生词到手动输入", command=self._extract_from_selected_news)
        extract_btn.grid(row=2, column=0, sticky="w", pady=10)
        self.font_manager.register(extract_btn)

        tab.grid_rowconfigure(1, weight=1)

    def _parse_words(self, raw: str) -> List[str]:
        tokens = re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)?", raw)
        ordered: List[str] = []
        seen = set()
        for t in tokens:
            w = t.strip().lower()
            if not w or w in seen:
                continue
            seen.add(w)
            ordered.append(w)
        return ordered

    def _analyze(self) -> None:
        if self._analysis_thread is not None and self._analysis_thread.is_alive():
            messagebox.showinfo("提示", "分析正在进行中，可点击“停止”打断")
            return

        words_raw = self.words_text.get("1.0", "end").strip()
        source_context = self.context_entry.get().strip()
        words = self._parse_words(words_raw)
        if not words:
            messagebox.showwarning("提示", "请先输入至少一个单词。")
            return

        self._cancel_event.clear()
        self._stream_preview_chunks = []
        self._set_loading(True, "分析中")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("end", "正在连接 AI 并接收输出…\n\n")

        def worker() -> None:
            try:
                results = self.word_processor.analyze_words_with_progress(
                    words,
                    source_context,
                    on_progress=lambda msg: self.after(0, lambda m=msg: self._update_progress(m)),
                    on_stream_chunk=lambda d: self.after(0, lambda x=d: self._append_stream_chunk(x)),
                    cancel_event=self._cancel_event,
                )
                self.after(0, lambda: self._on_success(results))
            except Exception as exc:
                self.after(0, lambda: self._on_error(exc))

        self._analysis_thread = threading.Thread(target=worker, daemon=True)
        self._analysis_thread.start()

    def _cancel_analyze(self) -> None:
        if self._analysis_thread is None or not self._analysis_thread.is_alive():
            return
        self._cancel_event.set()
        self._update_progress("正在停止…")
        self.stop_btn.configure(state="disabled")
        self.analyze_btn.configure(text="停止中…")
        self.result_text.insert("end", "\n[控制] 已发送停止请求，等待连接释放...\n")
        self.result_text.see("end")

    def _update_progress(self, message: str) -> None:
        self.status_label.configure(text=message)
        self.result_text.insert("end", f"[进度] {message}\n")
        self.result_text.see("end")

    def _append_stream_chunk(self, delta: str) -> None:
        if not delta:
            return
        self.result_text.insert("end", delta)
        self.result_text.see("end")

    def _on_success(self, results: List[dict]) -> None:
        if self._cancel_event.is_set():
            self._analysis_thread = None
            self._set_loading(False, "")
            self.status_label.configure(text="已停止")
            self.result_text.insert("end", "\n[已停止] 本次结果已丢弃，不会写入数据库。\n")
            self.result_text.see("end")
            return
        self._analysis_thread = None
        self._set_loading(False, "")
        self.status_label.configure(text="完成")
        if not results:
            self.result_text.insert("end", "\n\n[结果] 未得到有效分析结果。\n")
        else:
            self.result_text.insert("end", "\n\n========== 入库结果 ==========" + "\n")
            for item in results:
                self.result_text.insert(
                    "end",
                    (
                        f"单词: {item.get('word', '')}\n"
                        f"释义: {item.get('definition', '')}\n"
                        f"色彩: {item.get('tone', '')}\n"
                        f"场景: {item.get('scenario', '')}\n"
                        f"记忆: {item.get('memory_hook', '')}\n"
                        f"来源: {item.get('source_context', '')}\n"
                        + "-" * 42
                        + "\n"
                    ),
                )
        self.result_text.see("end")
        self.on_saved()
        messagebox.showinfo("完成", f"已保存 {len(results)} 个单词。")

    def _on_error(self, exc: Exception) -> None:
        self._analysis_thread = None
        self._set_loading(False, "")
        msg = str(exc)
        if self._cancel_event.is_set() and ("已停止" in msg or "已取消" in msg):
            self.status_label.configure(text="已停止")
            self.result_text.insert("end", "\n[已停止] 你已手动打断本次分析。\n")
            self.result_text.see("end")
            return
        if isinstance(exc, APIClientError) and "网络连接失败" in msg:
            msg = "连接失败：无法连到 AI 服务，请检查网络、代理或 base_url 后重试。"
        messagebox.showerror("分析失败", msg)

    def _set_loading(self, loading: bool, text: str) -> None:
        self.analyze_btn.configure(state="disabled" if loading else "normal", text=("分析中…" if loading else "分析并保存"))
        self.stop_btn.configure(state="normal" if loading else "disabled")
        if loading:
            self.status_label.configure(text=text)
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

    def _search_news(self) -> None:
        query = self.news_query.get().strip()
        if not query:
            messagebox.showwarning("提示", "请输入搜索关键词")
            return
        try:
            self.news_results = self.news_fetcher.search(query=query, freshness=self.freshness_var.get().strip())
        except Exception as exc:
            messagebox.showerror("搜索失败", str(exc))
            return

        for c in self.news_list.winfo_children():
            c.destroy()

        self._selected_news: List[ctk.BooleanVar] = []
        for i, row in enumerate(self.news_results):
            card = ctk.CTkFrame(self.news_list)
            card.grid(row=i, column=0, sticky="ew", padx=6, pady=6)
            card.grid_columnconfigure(1, weight=1)

            var = ctk.BooleanVar(value=False)
            self._selected_news.append(var)
            cb = ctk.CTkCheckBox(card, text="", variable=var)
            cb.grid(row=0, column=0, padx=6, pady=6, sticky="n")
            self.font_manager.register(cb)

            title = ctk.CTkLabel(card, text=str(row.get("title", "")), text_color="#4A9EFF", justify="left", wraplength=920)
            title.grid(row=0, column=1, sticky="w", padx=4, pady=(6, 2))
            self.font_manager.register(title)

            snippet = ctk.CTkLabel(card, text=str(row.get("snippet", "")), text_color="#CFCFCF", justify="left", wraplength=920)
            snippet.grid(row=1, column=1, sticky="w", padx=4, pady=(0, 6))
            self.font_manager.register(snippet)

    def _extract_from_selected_news(self) -> None:
        selected = [self.news_results[i] for i, var in enumerate(getattr(self, "_selected_news", [])) if bool(var.get())]
        if not selected:
            messagebox.showwarning("提示", "请先选择新闻")
            return
        article_content = "\n\n".join(str(x.get("content", "")) for x in selected)
        prompt = self.word_processor.config_path.parent.joinpath("prompts", "news_word_extraction.txt").read_text(encoding="utf-8")
        prompt = prompt.replace("{article_content}", article_content[:12000])
        try:
            raw = self.word_processor.api_client.ask_with_role(prompt, "analyst")
            data = json.loads(raw)
            words = data.get("words", []) if isinstance(data, dict) else []
            source_context = str(data.get("source_context", "新闻导入")) if isinstance(data, dict) else "新闻导入"
            if not words:
                raise ValueError("未提取到有效词汇")
            self.words_text.delete("1.0", "end")
            self.words_text.insert("end", "\n".join(words))
            self.context_entry.delete(0, "end")
            self.context_entry.insert(0, source_context)
            self.mode_tabs.set("手动输入")
            messagebox.showinfo("完成", f"已提取 {len(words)} 个词，已填入手动输入区")
        except Exception as exc:
            messagebox.showerror("提取失败", str(exc))
