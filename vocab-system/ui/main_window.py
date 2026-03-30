from __future__ import annotations

from datetime import date
from pathlib import Path
import customtkinter as ctk
from tkinter import messagebox

from core.config_manager import ConfigManager
from core.passage_generator import PassageGenerator
from core.review_engine import ReviewEngine
from core.sentence_checker import SentenceChecker
from core.word_processor import WordProcessor
from data.db_manager import DBManager
from ui.font_manager import FontManager
from ui.input_panel import InputPanel
from ui.reading_panel import ReadingPanel
from ui.review_panel import ReviewPanel
from ui.sentence_panel import SentencePanel
from ui.textbox_manager import TextboxManager
from ui.vocab_book_panel import VocabBookPanel


font_manager = FontManager()
textbox_manager = TextboxManager()
SUPPORTED_PROVIDERS = ["minimax", "kimi", "deepseek", "gpt", "gemini"]
LEGACY_PROVIDER_ALIAS = {"openai": "gpt", "anthropic": "deepseek", "local": "deepseek"}


class MainWindow:
    def __init__(
        self,
        db_manager: DBManager,
        word_processor: WordProcessor,
        review_engine: ReviewEngine,
        sentence_checker: SentenceChecker,
        passage_generator: PassageGenerator,
        config_path: str,
    ) -> None:
        self.db = db_manager
        self.config = ConfigManager(config_path)
        cfg = self.config.load()
        ui_cfg = cfg.get("ui", {})

        ctk.set_appearance_mode(str(ui_cfg.get("theme", "dark")))
        font_size = int(ui_cfg.get("font_size", 14))
        font_manager.set_size(font_size)
        ctk.set_widget_scaling(1.0)

        self.root = ctk.CTk()
        self.root.title("词汇学习系统 v3")
        self.root.geometry(f"{int(ui_cfg.get('window_width', 1400))}x{int(ui_cfg.get('window_height', 850))}")
        self.root.resizable(True, True)
        self.root.minsize(900, 600)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(3, weight=1)

        self._build_dashboard()
        self._build_settings_bar()
        self._build_agent_panel()
        self._build_tabs(word_processor, review_engine, sentence_checker, passage_generator)
        self._add_readme_button()
        self._refresh_dashboard()
        self.review_panel.reload_due_words()
        self.tabs.set("今日复习")

    def _build_dashboard(self) -> None:
        bar = ctk.CTkFrame(self.root)
        bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        bar.grid_columnconfigure(1, weight=1)

        self.today_label = ctk.CTkLabel(bar, text="今日复习：0", font=ctk.CTkFont(size=28, weight="bold"))
        self.today_label.grid(row=0, column=0, sticky="w", padx=12, pady=8)
        font_manager.register(self.today_label)

        self.level_label = ctk.CTkLabel(bar, text="新词 0 | 学习中 0 | 已熟悉 0 | 已掌握 0")
        self.level_label.grid(row=0, column=1, sticky="w", padx=8)
        font_manager.register(self.level_label)

        self.latest_passage_btn = ctk.CTkButton(bar, text="最近短文：暂无", command=lambda: self.tabs.set("阅读短文"))
        self.latest_passage_btn.grid(row=0, column=2, sticky="e", padx=12)
        font_manager.register(self.latest_passage_btn)

    def _build_settings_bar(self) -> None:
        bar = ctk.CTkFrame(self.root)
        bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        bar.grid_columnconfigure(8, weight=1)

        cfg = self.config.load()
        raw_provider = str(cfg.get("api", {}).get("provider", "minimax")).strip().lower()
        provider = LEGACY_PROVIDER_ALIAS.get(raw_provider, raw_provider)
        if provider not in SUPPORTED_PROVIDERS:
            provider = "minimax"
        model = str(cfg.get("api", {}).get(provider, {}).get("model", ""))

        provider_label = ctk.CTkLabel(bar, text="Provider")
        provider_label.grid(row=0, column=0, padx=(12, 4), pady=8)
        font_manager.register(provider_label)

        self.provider_var = ctk.StringVar(value=provider)
        self.provider_menu = ctk.CTkOptionMenu(
            bar,
            variable=self.provider_var,
            values=SUPPORTED_PROVIDERS,
            command=self._on_provider_change,
            width=130,
        )
        self.provider_menu.grid(row=0, column=1, padx=4)
        font_manager.register(self.provider_menu)

        model_label = ctk.CTkLabel(bar, text="Model")
        model_label.grid(row=0, column=2, padx=(10, 4))
        font_manager.register(model_label)

        self.model_entry = ctk.CTkEntry(bar, width=180)
        self.model_entry.insert(0, model)
        self.model_entry.grid(row=0, column=3, padx=4)
        self.model_entry.bind("<Return>", self._on_model_commit)
        self.model_entry.bind("<FocusOut>", self._on_model_commit)
        font_manager.register(self.model_entry)

        key_btn = ctk.CTkButton(bar, text="🔑 API Key", width=100, command=self._open_key_dialog)
        key_btn.grid(row=0, column=4, padx=(10, 4))
        font_manager.register(key_btn)

        font_label = ctk.CTkLabel(bar, text="字体")
        font_label.grid(row=0, column=5, padx=(10, 4))
        font_manager.register(font_label)

        self.font_slider = ctk.CTkSlider(bar, from_=10, to=30, command=self._on_font_change)
        self.font_slider.set(int(cfg.get("ui", {}).get("font_size", 14)))
        self.font_slider.grid(row=0, column=6, padx=4)

        self.font_value_var = ctk.StringVar(value=str(int(self.font_slider.get())))
        self.font_entry = ctk.CTkEntry(bar, textvariable=self.font_value_var, width=52)
        self.font_entry.grid(row=0, column=7, padx=4)
        self.font_entry.bind("<Return>", self._on_font_entry_commit)
        self.font_entry.bind("<FocusOut>", self._on_font_entry_commit)
        font_manager.register(self.font_entry)

        self.current_label = ctk.CTkLabel(bar, text=f"当前：{provider} / {model}")
        self.current_label.grid(row=0, column=8, sticky="w", padx=8)
        font_manager.register(self.current_label)

        agent_enabled = bool(cfg.get("agent_roles", {}).get("enabled", False))
        self.agent_switch = ctk.CTkSwitch(bar, text="联调模式", command=self._toggle_agent_mode)
        self.agent_switch.grid(row=0, column=9, padx=(10, 6))
        self.agent_switch.select() if agent_enabled else self.agent_switch.deselect()
        font_manager.register(self.agent_switch)

    def _build_agent_panel(self) -> None:
        self.agent_panel = ctk.CTkFrame(self.root)
        self.agent_panel.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 6))
        self.agent_panel.grid_columnconfigure(7, weight=1)

        roles_cfg = self.config.load().get("agent_roles", {}).get("roles", {})
        providers = SUPPORTED_PROVIDERS
        role_names = ["author", "analyst", "reviewer", "news_fetcher"]

        self.role_vars = {}
        for i, role in enumerate(role_names):
            lbl = ctk.CTkLabel(self.agent_panel, text=role)
            lbl.grid(row=0, column=i * 2, padx=(8, 4), pady=6)
            font_manager.register(lbl)
            role_provider = str(roles_cfg.get(role, providers[0])).strip().lower()
            role_provider = LEGACY_PROVIDER_ALIAS.get(role_provider, role_provider)
            if role_provider not in providers:
                role_provider = providers[0]
            var = ctk.StringVar(value=role_provider)
            menu = ctk.CTkOptionMenu(
                self.agent_panel,
                variable=var,
                values=providers,
                command=lambda value, r=role: self._on_role_provider_change(r, value),
                width=110,
            )
            menu.grid(row=0, column=i * 2 + 1, padx=(0, 8), pady=6)
            font_manager.register(menu)
            self.role_vars[role] = var

        reviewer_enabled = bool(roles_cfg.get("reviewer_enabled", False))
        self.reviewer_switch = ctk.CTkSwitch(self.agent_panel, text="启用 Reviewer", command=self._toggle_reviewer)
        self.reviewer_switch.grid(row=0, column=8, padx=8)
        self.reviewer_switch.select() if reviewer_enabled else self.reviewer_switch.deselect()
        font_manager.register(self.reviewer_switch)

        if not bool(self.config.load().get("agent_roles", {}).get("enabled", False)):
            self.agent_panel.grid_remove()

    def _build_tabs(
        self,
        word_processor: WordProcessor,
        review_engine: ReviewEngine,
        sentence_checker: SentenceChecker,
        passage_generator: PassageGenerator,
    ) -> None:
        self.tabs = ctk.CTkTabview(self.root)
        self.tabs.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 12))
        for name in ["今日复习", "阅读短文", "造句练习", "添加新词", "词汇本"]:
            self.tabs.add(name)

        self.review_panel = ReviewPanel(self.tabs.tab("今日复习"), review_engine, self._refresh_dashboard, font_manager)
        self.review_panel.pack(fill="both", expand=True)

        self.input_panel = InputPanel(
            self.tabs.tab("添加新词"),
            word_processor,
            self._after_word_saved,
            font_manager,
            textbox_manager,
            str(self.config.config_path),
        )
        self.input_panel.pack(fill="both", expand=True)

        self.sentence_panel = SentencePanel(self.tabs.tab("造句练习"), sentence_checker, self.db, font_manager, textbox_manager)
        self.sentence_panel.pack(fill="both", expand=True)

        self.reading_panel = ReadingPanel(
            self.tabs.tab("阅读短文"),
            passage_generator,
            self.db,
            str(self.config.config_path),
            self._refresh_dashboard,
            font_manager,
            textbox_manager,
        )
        self.reading_panel.pack(fill="both", expand=True)

        self.vocab_book_panel = VocabBookPanel(
            self.tabs.tab("词汇本"),
            self.db,
            review_engine,
            font_manager,
            textbox_manager,
            self._refresh_dashboard,
        )
        self.vocab_book_panel.pack(fill="both", expand=True)

    def _toggle_agent_mode(self) -> None:
        enabled = bool(self.agent_switch.get())
        self.config.update_config("agent_roles.enabled", enabled)
        if enabled:
            self.agent_panel.grid()
        else:
            self.agent_panel.grid_remove()

    def _on_role_provider_change(self, role: str, value: str) -> None:
        self.config.update_config(f"agent_roles.roles.{role}", value)

    def _toggle_reviewer(self) -> None:
        self.config.update_config("agent_roles.roles.reviewer_enabled", bool(self.reviewer_switch.get()))

    def _add_readme_button(self) -> None:
        btn = ctk.CTkButton(
            self.root,
            text="？",
            width=36,
            height=36,
            corner_radius=18,
            fg_color="#2A2A2A",
            hover_color="#3A3A3A",
            text_color="#9A9A9A",
            font=("微软雅黑", 14, "bold"),
            command=self._show_readme,
        )
        btn.place(relx=1.0, rely=1.0, anchor="se", x=-16, y=-16)

    def _show_readme(self) -> None:
        win = ctk.CTkToplevel(self.root)
        win.title("关于本程序")
        win.geometry("680x520")
        win.resizable(True, True)
        win.attributes("-topmost", True)
        win.lift()

        readme_path = Path(__file__).resolve().parent.parent / "README.md"
        if readme_path.exists():
            content = readme_path.read_text(encoding="utf-8")
        else:
            content = "README.md 文件未找到。"

        textbox = ctk.CTkTextbox(win, wrap="word", font=("微软雅黑", 13))
        textbox.pack(fill="both", expand=True, padx=16, pady=16)
        textbox.insert("end", content)
        textbox.configure(state="disabled")
        font_manager.register(textbox)
        textbox_manager.register(textbox, base_height=420)

        close_btn = ctk.CTkButton(win, text="关闭", width=80, command=win.destroy)
        close_btn.pack(pady=(0, 12))
        font_manager.register(close_btn)

    def _on_provider_change(self, value: str) -> None:
        self.config.update_config("api.provider", value)
        cfg = self.config.load()
        model = str(cfg.get("api", {}).get(value, {}).get("model", ""))
        self.model_entry.delete(0, "end")
        self.model_entry.insert(0, model)
        self.current_label.configure(text=f"当前：{value} / {model}")

    def _on_model_commit(self, _evt) -> None:
        provider = self.provider_var.get().strip()
        model = self.model_entry.get().strip()
        if provider and model:
            self.config.update_config(f"api.{provider}.model", model)
            self.current_label.configure(text=f"当前：{provider} / {model}")

    def _open_key_dialog(self) -> None:
        provider = self.provider_var.get().strip()
        cfg = self.config.load()
        key = str(cfg.get("api", {}).get(provider, {}).get("api_key", ""))

        dlg = ctk.CTkToplevel(self.root)
        dlg.title("修改 API Key")
        dlg.geometry("460x160")
        dlg.grab_set()

        provider_label = ctk.CTkLabel(dlg, text=f"Provider: {provider}")
        provider_label.pack(anchor="w", padx=12, pady=(12, 6))
        font_manager.register(provider_label)

        entry = ctk.CTkEntry(dlg, show="*", width=420)
        entry.insert(0, key)
        entry.pack(padx=12, pady=6)
        font_manager.register(entry)

        def save() -> None:
            self.config.update_config(f"api.{provider}.api_key", entry.get().strip())
            messagebox.showinfo("保存成功", "API Key 已更新")
            dlg.destroy()

        save_btn = ctk.CTkButton(dlg, text="保存", command=save)
        save_btn.pack(pady=10)
        font_manager.register(save_btn)

    def _on_font_change(self, value: float) -> None:
        size = int(round(value))
        self.font_value_var.set(str(size))
        font_manager.set_size(size)
        self.config.update_config("ui.font_size", size)

    def _on_font_entry_commit(self, _evt) -> None:
        raw = self.font_value_var.get().strip()
        try:
            size = int(raw)
        except ValueError:
            size = font_manager.size
        size = max(10, min(30, size))
        self.font_value_var.set(str(size))
        self.font_slider.set(size)
        font_manager.set_size(size)
        self.config.update_config("ui.font_size", size)

    def _refresh_dashboard(self) -> None:
        due_count = len(self.db.get_due_words(date.today().isoformat()))
        self.today_label.configure(text="今日已完成，保持！" if due_count == 0 else f"今日需要复习：{due_count}")

        counts = self.db.get_level_counts(word_bank="new")
        self.level_label.configure(
            text=(
                f"新词 {counts.get('new', 0)} | 学习中 {counts.get('learning', 0)} | "
                f"已熟悉 {counts.get('familiar', 0)} | 已掌握 {counts.get('mastered', 0)}"
            )
        )

        latest = self.db.get_latest_passage()
        if latest:
            title = str(latest.get("title", "")).strip() or str(latest.get("content", "")[:40]).replace("\n", " ")
            self.latest_passage_btn.configure(text=f"最近短文：{title}")
        else:
            self.latest_passage_btn.configure(text="最近短文：暂无")

    def _after_word_saved(self) -> None:
        self.review_panel.reload_due_words()
        self.sentence_panel.reload_words()
        self.vocab_book_panel.reload_cards()
        self._refresh_dashboard()

    def run(self) -> None:
        self.root.mainloop()
