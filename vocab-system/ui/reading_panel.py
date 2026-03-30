from __future__ import annotations

import json
import re
import threading
import tkinter as tk
from threading import Event
from typing import Any, Dict, List

import customtkinter as ctk
from tkinter import messagebox

from core.config_manager import ConfigManager
from core.passage_generator import PassageGenerator
from data.db_manager import DBManager
from ui.components.tooltip import WordTooltip
from ui.font_manager import FontManager
from ui.textbox_manager import TextboxManager


class ReadingPanel(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        generator: PassageGenerator,
        db_manager: DBManager,
        config_path: str,
        on_generated,
        font_manager: FontManager,
        textbox_manager: TextboxManager,
    ) -> None:
        super().__init__(master)
        self.generator = generator
        self.db = db_manager
        self.config = ConfigManager(config_path)
        self.on_generated = on_generated
        self.font_manager = font_manager
        self.textbox_manager = textbox_manager
        self.tooltip = WordTooltip()

        self._blink_job = None
        self._blink = False
        self._celebration_job = None
        self._bank_refresh_job = None
        self._generate_thread: threading.Thread | None = None
        self._cancel_event = Event()
        self._trace_buffer: List[str] = []
        self._trace_window = None
        self._trace_textbox = None
        self._pair_colors = [
            ("#1E3A5F", "#4A9EFF"),
            ("#2D4D2B", "#8FCE7A"),
            ("#5A3D1E", "#FFB347"),
            ("#4A274A", "#D79BE8"),
            ("#4B2F2F", "#E99A9A"),
            ("#1F4B4B", "#7FD4D4"),
        ]
        self.direction_var = ctk.StringVar(value="freeform")
        self.direction_options: Dict[str, Dict[str, Any]] = {}
        self.current_direction_prompt = ""
        self.current_direction_id = "freeform"
        self.current_storyline_id: int | None = None

        self._build_ui()
        self._build_direction_dropdown(self.direction_frame)
        self._on_direction_changed()
        self._refresh_lexicon_status()
        self._schedule_bank_refresh()
        self.load_latest()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        top.grid_columnconfigure(1, weight=1)

        self.generate_btn = ctk.CTkButton(top, text="生成新短文", command=self.generate_new)
        self.generate_btn.grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.font_manager.register(self.generate_btn)

        self.stop_btn = ctk.CTkButton(top, text="停止", width=70, fg_color="#3A3A3A", command=self._cancel_generate)
        self.stop_btn.grid(row=0, column=1, padx=8, pady=8, sticky="w")
        self.stop_btn.configure(state="disabled")
        self.font_manager.register(self.stop_btn)

        self.history_btn = ctk.CTkButton(top, text="历史短文", fg_color="#3A3A3A", command=self._open_history_window)
        self.history_btn.grid(row=0, column=2, padx=8, pady=8, sticky="w")
        self.font_manager.register(self.history_btn)

        self.abandon_btn = ctk.CTkButton(top, text="不满意，放弃本章", fg_color="#3A3A3A", command=self._abandon_last_chapter)
        self.abandon_btn.grid(row=0, column=3, padx=8, pady=8, sticky="w")
        self.font_manager.register(self.abandon_btn)

        self.mode_tag = ctk.CTkLabel(top, text="", text_color="#FFB347")
        self.mode_tag.grid(row=0, column=3, padx=(180, 8), sticky="w")
        self.font_manager.register(self.mode_tag)

        self.status_label = ctk.CTkLabel(top, text="", text_color="#9A9A9A")
        self.status_label.grid(row=0, column=4, sticky="e", padx=8)
        self.font_manager.register(self.status_label)

        self.info_label = ctk.CTkLabel(top, text="", text_color="#9A9A9A")
        self.info_label.grid(row=1, column=0, columnspan=5, sticky="w", padx=8)
        self.info_label.grid_remove()

        self.direction_frame = ctk.CTkFrame(self)
        self.direction_frame.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 8))

        self.direction_info_float_btn = ctk.CTkButton(
            self,
            text="？",
            width=30,
            height=30,
            corner_radius=15,
            command=self._show_current_direction_info,
        )
        self.direction_info_float_btn.place(relx=1.0, y=86, anchor="ne", x=-28)
        self.font_manager.register(self.direction_info_float_btn)

        self.trace_float_btn = ctk.CTkButton(
            self,
            text="思",
            width=30,
            height=30,
            corner_radius=15,
            command=self._open_trace_window,
        )
        self.trace_float_btn.place(relx=1.0, y=122, anchor="ne", x=-28)
        self.font_manager.register(self.trace_float_btn)

        self.title_label = ctk.CTkLabel(self, text="暂无短文", font=ctk.CTkFont(size=24, weight="bold"), text_color="#4A9EFF")
        self.title_label.grid(row=2, column=0, sticky="w", padx=24)
        self.font_manager.register(self.title_label)

        pane_holder = ctk.CTkFrame(self, fg_color="transparent")
        pane_holder.grid(row=3, column=0, sticky="nsew", padx=24, pady=8)
        pane_holder.grid_columnconfigure(0, weight=1)
        pane_holder.grid_rowconfigure(0, weight=1)

        vertical_pane = tk.PanedWindow(
            pane_holder,
            orient=tk.VERTICAL,
            sashwidth=10,
            bd=0,
            relief="flat",
            bg="#2B2B2B",
            showhandle=False,
        )
        vertical_pane.grid(row=0, column=0, sticky="nsew")

        body = ctk.CTkFrame(pane_holder, fg_color="transparent")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        horizontal_pane = tk.PanedWindow(
            body,
            orient=tk.HORIZONTAL,
            sashwidth=10,
            bd=0,
            relief="flat",
            bg="#2B2B2B",
            showhandle=False,
        )
        horizontal_pane.grid(row=0, column=0, sticky="nsew")

        en_frame = ctk.CTkFrame(body, fg_color="transparent")
        en_frame.grid_columnconfigure(0, weight=1)
        en_frame.grid_rowconfigure(0, weight=1)
        self.en_box = ctk.CTkTextbox(en_frame, wrap="word", font=("Consolas", self.font_manager.size))
        self.en_box.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        self.font_manager.register(self.en_box, family="Consolas")

        zh_frame = ctk.CTkFrame(body, fg_color="transparent")
        zh_frame.grid_columnconfigure(0, weight=1)
        zh_frame.grid_rowconfigure(0, weight=1)
        self.zh_box = ctk.CTkTextbox(zh_frame, wrap="word", font=("微软雅黑", self.font_manager.size))
        self.zh_box.grid(row=0, column=0, sticky="nsew", padx=(4, 0), pady=0)
        self.font_manager.register(self.zh_box)

        horizontal_pane.add(en_frame, minsize=260)
        horizontal_pane.add(zh_frame, minsize=260)

        notes_area = ctk.CTkFrame(pane_holder, fg_color="transparent")
        notes_area.grid_columnconfigure(0, weight=1)
        notes_area.grid_rowconfigure(1, weight=1)

        notes_label = ctk.CTkLabel(notes_area, text="词汇注释", text_color="#9A9A9A")
        notes_label.grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.font_manager.register(notes_label)

        self.notes_scroll = ctk.CTkScrollableFrame(notes_area, height=210)
        self.notes_scroll.grid(row=1, column=0, sticky="nsew", pady=(0, 4))
        self.notes_scroll.grid_columnconfigure(0, weight=1)

        vertical_pane.add(body, minsize=180)
        vertical_pane.add(notes_area, minsize=120)

        self.warning_label = ctk.CTkLabel(self, text="", text_color="#FFB347")
        self.warning_label.grid(row=4, column=0, sticky="w", padx=24, pady=(0, 8))
        self.font_manager.register(self.warning_label)

    def _build_direction_dropdown(self, parent: ctk.CTkFrame) -> None:
        for child in parent.winfo_children():
            child.destroy()
        self.direction_options.clear()

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=8)

        title = ctk.CTkLabel(row, text="剧情走向：", text_color="#9A9A9A")
        title.pack(side="left", padx=(0, 12))
        self.font_manager.register(title)

        directions = self._load_directions()
        values = []
        for item in directions:
            direction_id = str(item.get("id", "freeform"))
            self.direction_options[direction_id] = item
            values.append(f"{item.get('name', direction_id)} ({direction_id})")

        value_map = {
            f"{item.get('name', str(item.get('id', 'freeform')))} ({str(item.get('id', 'freeform'))})": str(item.get("id", "freeform"))
            for item in directions
        }
        self._direction_display_to_id = value_map
        self._direction_id_to_display = {v: k for k, v in value_map.items()}

        default_display = self._direction_id_to_display.get(self.direction_var.get(), values[0] if values else "freeform")
        self.direction_display_var = ctk.StringVar(value=default_display)
        self.direction_menu = ctk.CTkOptionMenu(
            row,
            variable=self.direction_display_var,
            values=values if values else ["freeform"],
            command=self._on_direction_menu_change,
            width=280,
        )
        self.direction_menu.pack(side="left")
        self.font_manager.register(self.direction_menu)

        del_btn = ctk.CTkButton(row, text="删除当前走向", width=90, fg_color="#3A3A3A", command=self._delete_selected_direction)
        del_btn.pack(side="right", padx=(6, 0))
        self.font_manager.register(del_btn)

        add_btn = ctk.CTkButton(row, text="＋ 添加走向", width=90, command=self._on_add_direction)
        add_btn.pack(side="right")
        self.font_manager.register(add_btn)

        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(0, 8))

        cfg = self.config.load()
        p_cfg = cfg.get("learning", {}).get("passage", {})
        ref_count = int(p_cfg.get("familiar_reference_words", 80) or 80)
        ref_value = "全部" if ref_count <= 0 else str(ref_count)

        ref_label = ctk.CTkLabel(row2, text="熟词喂给量：", text_color="#9A9A9A")
        ref_label.pack(side="left")
        self.font_manager.register(ref_label)

        self.familiar_ref_menu = ctk.CTkOptionMenu(
            row2,
            values=["20", "50", "80", "120", "全部"],
            command=self._on_familiar_ref_change,
            width=120,
        )
        self.familiar_ref_menu.set(ref_value)
        self.familiar_ref_menu.pack(side="left", padx=6)
        self.font_manager.register(self.familiar_ref_menu)

        new_ref_count = int(p_cfg.get("new_word_feed_count", p_cfg.get("max_words", 10)) or 10)
        new_ref_value = "全部" if new_ref_count <= 0 else str(new_ref_count)

        new_ref_label = ctk.CTkLabel(row2, text="生词喂给量：", text_color="#9A9A9A")
        new_ref_label.pack(side="left", padx=(10, 0))
        self.font_manager.register(new_ref_label)

        self.new_ref_menu = ctk.CTkOptionMenu(
            row2,
            values=["5", "10", "20", "30", "全部"],
            command=self._on_new_ref_change,
            width=120,
        )
        self.new_ref_menu.set(new_ref_value)
        self.new_ref_menu.pack(side="left", padx=6)
        self.font_manager.register(self.new_ref_menu)

        desc = ctk.CTkLabel(
            row2,
            text="说明：短文以熟词库构建语境，再自然引入生词库目标词。",
            text_color="#9A9A9A",
        )
        desc.pack(side="left", padx=10)
        self.font_manager.register(desc)

        self.lexicon_status_label = ctk.CTkLabel(row2, text="生词库: 0 | 熟词库: 0", text_color="#9A9A9A")
        self.lexicon_status_label.pack(side="right")
        self.font_manager.register(self.lexicon_status_label)

    def _on_familiar_ref_change(self, value: str) -> None:
        ref_count = 0 if value == "全部" else int(value)
        self.config.update_config("learning.passage.familiar_reference_words", ref_count)
        self._refresh_lexicon_status()

    def _on_new_ref_change(self, value: str) -> None:
        ref_count = 0 if value == "全部" else int(value)
        self.config.update_config("learning.passage.new_word_feed_count", ref_count)
        self._refresh_lexicon_status()

    def _refresh_lexicon_status(self) -> None:
        new_count = len(self.db.list_words(word_bank="new"))
        familiar_count = len(self.db.list_words(word_bank="familiar"))
        if hasattr(self, "lexicon_status_label"):
            self.lexicon_status_label.configure(text=f"生词库: {new_count} | 熟词库: {familiar_count}")

    def _schedule_bank_refresh(self) -> None:
        self._refresh_lexicon_status()
        self._bank_refresh_job = self.after(3000, self._schedule_bank_refresh)

    def _on_direction_menu_change(self, value: str) -> None:
        selected = self._direction_display_to_id.get(value, "freeform")
        self.direction_var.set(selected)
        self._on_direction_changed()

    def _on_direction_changed(self) -> None:
        selected_id = self.direction_var.get().strip() or "freeform"
        directions = self._load_directions()
        for d in directions:
            if str(d.get("id", "")) == selected_id:
                self.current_direction_prompt = str(d.get("prompt_inject", d.get("description", "")))
                self.current_direction_id = selected_id
                break

    def _load_directions(self) -> List[Dict[str, Any]]:
        cfg = self.config.load()
        sd = cfg.get("story_directions", {})
        result: List[Dict[str, Any]] = []

        presets = sd.get("presets", [])
        if not presets:
            presets = [
                {
                    "id": "daily_life",
                    "name": "日常生活",
                    "description": "发生在普通人身上的真实日常场景",
                    "prompt_inject": "体裁：写实叙事短文；场景：现代都市日常；语气：自然温暖。",
                },
                {
                    "id": "mystery",
                    "name": "悬疑推理",
                    "description": "包含谜题、线索或反转的故事",
                    "prompt_inject": "体裁：悬疑短篇；语气：紧张克制；要求：结尾保留悬念。",
                },
                {
                    "id": "nature_science",
                    "name": "自然与科学",
                    "description": "以自然现象或科学发现为背景的叙事",
                    "prompt_inject": "体裁：科普叙事或自然描写；要求：融入至少一个科学事实。",
                },
            ]
        result.extend(presets)

        for c in sd.get("custom", []):
            item = dict(c)
            item["is_custom"] = True
            result.append(item)

        freeform = sd.get("freeform", {})
        result.append(
            {
                "id": "freeform",
                "name": str(freeform.get("name", "白板（自由发挥）")),
                "description": "不限制体裁，由模型根据词汇特点自由发挥",
                "prompt_inject": str(
                    freeform.get(
                        "prompt_inject",
                        "不限制体裁和场景，根据词汇特点自由选择最合适的体裁和情节。",
                    )
                ),
                "is_custom": False,
            }
        )
        return result

    def _show_direction_info(self, direction: Dict[str, Any]) -> None:
        win = ctk.CTkToplevel(self)
        win.title("走向说明")
        win.geometry("560x280")
        win.attributes("-topmost", True)
        win.lift()
        win.grab_set()

        name = str(direction.get("name", "未命名走向"))
        direction_id = str(direction.get("id", ""))
        desc = str(direction.get("description", ""))
        prompt = str(direction.get("prompt_inject", ""))

        title = ctk.CTkLabel(win, text=f"{name} ({direction_id})", text_color="#4A9EFF", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(anchor="w", padx=14, pady=(12, 8))
        self.font_manager.register(title)

        box = ctk.CTkTextbox(win, wrap="word", height=180, font=("微软雅黑", self.font_manager.size))
        box.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        box.insert("end", f"说明:\n{desc}\n\nPrompt 注入:\n{prompt}")
        box.configure(state="disabled")
        self.font_manager.register(box)

        close_btn = ctk.CTkButton(win, text="关闭", width=80, command=win.destroy)
        close_btn.pack(pady=(0, 12))
        self.font_manager.register(close_btn)

    def _show_current_direction_info(self) -> None:
        direction = self.direction_options.get(self.direction_var.get(), {})
        self._show_direction_info(direction)

    def _delete_selected_direction(self) -> None:
        direction = self.direction_options.get(self.direction_var.get(), {})
        if not bool(direction.get("is_custom", False)):
            messagebox.showwarning("提示", "只能删除自定义走向")
            return
        self._remove_custom_direction(str(direction.get("id", "")))

    def _on_add_direction(self) -> None:
        self._add_custom_direction()

    def _add_custom_direction(self) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("新增剧情走向")
        dlg.geometry("520x340")
        dlg.grab_set()

        name_label = ctk.CTkLabel(dlg, text="走向名称（必填）")
        name_label.pack(anchor="w", padx=12, pady=(12, 4))
        self.font_manager.register(name_label)
        name_entry = ctk.CTkEntry(dlg, width=480)
        name_entry.pack(padx=12)
        self.font_manager.register(name_entry)

        desc_label = ctk.CTkLabel(dlg, text="走向描述")
        desc_label.pack(anchor="w", padx=12, pady=(10, 4))
        self.font_manager.register(desc_label)
        desc_entry = ctk.CTkEntry(dlg, width=480)
        desc_entry.pack(padx=12)
        self.font_manager.register(desc_entry)

        prompt_label = ctk.CTkLabel(dlg, text="Prompt 指令（选填）")
        prompt_label.pack(anchor="w", padx=12, pady=(10, 4))
        self.font_manager.register(prompt_label)
        prompt_box = ctk.CTkTextbox(dlg, height=120, font=("微软雅黑", self.font_manager.size))
        prompt_box.pack(padx=12, fill="x")
        self.font_manager.register(prompt_box)
        self.textbox_manager.register(prompt_box, base_height=120)

        def submit() -> None:
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("提示", "走向名称必填")
                return
            item = self.config.add_story_direction(
                name,
                desc_entry.get().strip(),
                prompt_box.get("1.0", "end").strip(),
            )
            self.direction_var.set(item["id"])
            self._build_direction_dropdown(self.direction_frame)
            if item["id"] in self._direction_id_to_display:
                self.direction_display_var.set(self._direction_id_to_display[item["id"]])
            self._on_direction_changed()
            dlg.destroy()

        save_btn = ctk.CTkButton(dlg, text="保存", command=submit)
        save_btn.pack(pady=14)
        self.font_manager.register(save_btn)

    def _remove_custom_direction(self, direction_id: str) -> None:
        self.config.remove_story_direction(direction_id)
        if self.direction_var.get() == direction_id:
            self.direction_var.set("freeform")
        self._build_direction_dropdown(self.direction_frame)
        self.direction_display_var.set(self._direction_id_to_display.get("freeform", self.direction_display_var.get()))
        self._on_direction_changed()

    def _open_history_window(self) -> None:
        rows = self.db.list_passages()
        if not rows:
            messagebox.showinfo("提示", "还没有历史短文。")
            return

        win = ctk.CTkToplevel(self)
        win.title("历史短文")
        win.geometry("760x620")
        win.attributes("-topmost", True)
        win.lift()
        win.grab_set()
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(win)
        left.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        left.grid_columnconfigure(0, weight=1)

        def render_list() -> None:
            for child in left.winfo_children():
                child.destroy()
            current_rows = self.db.list_passages()
            if not current_rows:
                empty = ctk.CTkLabel(left, text="历史短文已清空", text_color="#9A9A9A")
                empty.grid(row=0, column=0, sticky="w", padx=8, pady=8)
                self.font_manager.register(empty)
                return

            for i, item in enumerate(current_rows):
                row_wrap = ctk.CTkFrame(left, fg_color="#2A2A2A")
                row_wrap.grid(row=i, column=0, sticky="ew", padx=6, pady=4)
                row_wrap.grid_columnconfigure(0, weight=1)

                created = str(item.get("created_at", ""))
                direction = str(item.get("story_direction", "freeform"))
                title = str(item.get("title", "")).strip() or str(item.get("content", "")).replace("\n", " ")[:15]
                preview = str(item.get("content", "")).replace("\n", " ")[:64]

                open_btn = ctk.CTkButton(
                    row_wrap,
                    text=f"{title}\n{created} | {direction}\n{preview}",
                    anchor="w",
                    height=72,
                    fg_color="#2F2F2F",
                    command=lambda row=item: open_to_main(row),
                )
                open_btn.grid(row=0, column=0, sticky="ew", padx=(8, 4), pady=8)
                self.font_manager.register(open_btn)

                del_btn = ctk.CTkButton(
                    row_wrap,
                    text="删除",
                    width=64,
                    fg_color="#E06C75",
                    command=lambda row=item: delete_item(row),
                )
                del_btn.grid(row=0, column=1, padx=(4, 8), pady=8)
                self.font_manager.register(del_btn)

        def open_to_main(item: Dict[str, Any]) -> None:
            data = self._build_render_payload_from_passage(item)
            self._set_loading(False)
            self._render(data)
            self.warning_label.configure(text="")
            self.status_label.configure(text="已加载历史短文")
            self.current_storyline_id = None
            win.destroy()

        def delete_item(item: Dict[str, Any]) -> None:
            pid = int(item.get("id", 0) or 0)
            if pid <= 0:
                return
            self.db.delete_passage_with_relations(pid)
            if self.db.get_latest_passage() is None:
                self.title_label.configure(text="暂无短文")
                self.en_box.delete("1.0", "end")
                self.zh_box.delete("1.0", "end")
                for child in self.notes_scroll.winfo_children():
                    child.destroy()
            render_list()

        render_list()

    def generate_new(self) -> None:
        if self._generate_thread is not None and self._generate_thread.is_alive():
            messagebox.showinfo("提示", "正在生成中，可点击“停止”打断")
            return

        direction_id = self.direction_var.get().strip() or "freeform"
        story_direction = self.current_direction_prompt or "自由发挥"
        self._refresh_lexicon_status()
        self._cancel_event.clear()
        self._trace_buffer = []
        self._set_loading(True)
        self.warning_label.configure(text="")

        cfg = self.config.load().get("agent_roles", {})
        self.mode_tag.configure(text=("🤖 联调模式" if bool(cfg.get("enabled", False)) else ""))

        def worker() -> None:
            try:
                data = self.generator.generate(
                    story_direction=story_direction,
                    direction_id=direction_id,
                    on_status=lambda txt: self.after(0, lambda t=txt: self.status_label.configure(text=t)),
                    on_stream_chunk=lambda d: self.after(0, lambda x=d: self._append_stream_chunk(x)),
                    cancel_event=self._cancel_event,
                )
                self.after(0, lambda: self._on_generated(data))
            except Exception as exc:
                self.after(0, lambda: self._on_error(exc))

        self._generate_thread = threading.Thread(target=worker, daemon=True)
        self._generate_thread.start()

    def _cancel_generate(self) -> None:
        if self._generate_thread is None or not self._generate_thread.is_alive():
            return
        self._cancel_event.set()
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="正在停止…")
        self.en_box.insert("end", "\n\n[控制] 已发送停止请求，等待连接释放...\n")
        self.en_box.see("end")

    def _abandon_last_chapter(self) -> None:
        if self.current_storyline_id is None:
            messagebox.showwarning("提示", "当前没有可放弃的章节")
            return
        if not messagebox.askyesno("二次确认", "确定删除本章？此操作不可撤销"):
            return
        ok = self.generator.abandon_last_chapter(int(self.current_storyline_id))
        if ok:
            self.load_latest()
            messagebox.showinfo("完成", "已放弃本章，故事线已回退")
        else:
            messagebox.showwarning("提示", "未找到可删除章节")

    def load_latest(self) -> None:
        latest = self.db.get_latest_passage()
        if not latest:
            return
        data = self._build_render_payload_from_passage(latest)
        self._render(data)

    def _build_render_payload_from_passage(self, row: Dict[str, Any]) -> Dict[str, Any]:
        notes_raw = str(row.get("vocabulary_notes", "[]") or "[]")
        try:
            notes = json.loads(notes_raw)
        except Exception:
            notes = []
        if not isinstance(notes, list):
            notes = []
        return {
            "title": str(row.get("title", "")).strip() or "最近短文",
            "content": row.get("content", ""),
            "translation": row.get("translation", ""),
            "vocabulary_notes": notes,
            "level_mix": row.get("level_mix", ""),
            "story_direction": row.get("story_direction", "freeform"),
            "removed_words": [],
        }

    def _on_generated(self, data: Dict[str, Any]) -> None:
        self._generate_thread = None
        if self._cancel_event.is_set():
            self._set_loading(False)
            self.status_label.configure(text="已停止")
            self.en_box.insert("end", "\n\n[已停止] 本次生成结果已丢弃。\n")
            self.en_box.see("end")
            return
        self._set_loading(False)
        self._render(data)
        self.current_storyline_id = int(data.get("storyline_id", 0) or 0) or None
        removed = data.get("removed_words", [])
        if removed:
            self.warning_label.configure(text=f"以下词汇不在你的词库中，已自动移除：{', '.join(removed)}")
        if bool(data.get("storyline_completed", False)):
            self._celebrate_storyline_completed()
        self.on_generated()

    def _on_error(self, exc: Exception) -> None:
        self._generate_thread = None
        self._set_loading(False)
        msg = str(exc)
        if self._cancel_event.is_set() and ("已取消" in msg or "已停止" in msg):
            self.status_label.configure(text="已停止")
            self.en_box.insert("end", "\n\n[已停止] 你已手动打断生成。\n")
            self.en_box.see("end")
            return
        messagebox.showerror("生成失败", msg)

    def _append_stream_chunk(self, delta: str) -> None:
        if not delta:
            return
        self._trace_buffer.append(delta)
        if self._trace_window is not None and self._trace_textbox is not None:
            self._trace_textbox.configure(state="normal")
            self._trace_textbox.insert("end", delta)
            self._trace_textbox.see("end")
            self._trace_textbox.configure(state="disabled")

    def _open_trace_window(self) -> None:
        if self._trace_window is not None and self._trace_window.winfo_exists():
            self._trace_window.lift()
            return

        win = ctk.CTkToplevel(self)
        self._trace_window = win
        win.title("模型思考过程")
        win.geometry("760x520")
        win.attributes("-topmost", True)
        win.lift()

        text = ctk.CTkTextbox(win, wrap="word", font=("Consolas", self.font_manager.size))
        text.pack(fill="both", expand=True, padx=12, pady=12)
        self.font_manager.register(text, family="Consolas")
        self._trace_textbox = text

        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("end", "".join(self._trace_buffer) if self._trace_buffer else "当前暂无过程输出。")
        text.configure(state="disabled")

        def on_close() -> None:
            self._trace_window = None
            self._trace_textbox = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)

    def _render(self, data: Dict[str, Any]) -> None:
        title = str(data.get("title", "未命名短文"))
        content = str(data.get("content", ""))
        translation = str(data.get("translation", ""))
        notes = data.get("vocabulary_notes", [])
        if not isinstance(notes, list):
            notes = []

        self.title_label.configure(text=title)
        self.en_box.delete("1.0", "end")
        self.en_box.insert("end", content)

        pairs: List[Dict[str, str]] = []
        missing_anchors: List[Dict[str, str]] = []
        for note in notes:
            if not isinstance(note, dict):
                continue
            word = str(note.get("word", "")).strip()
            if not word:
                continue
            zh_term = self._pick_zh_match_term(note)
            pairs.append({"word": word, "zh_term": zh_term})
            if not zh_term or zh_term not in translation:
                if zh_term:
                    missing_anchors.append({"word": word, "zh_term": zh_term})

        zh_text = translation
        if missing_anchors:
            mapping_lines = ["", "【词汇对应补齐】"]
            for item in missing_anchors:
                mapping_lines.append(f"{item['word']} -> {item['zh_term']}")
            zh_text = translation + "\n" + "\n".join(mapping_lines)

        self.zh_box.delete("1.0", "end")
        self.zh_box.insert("end", zh_text)

        for child in self.notes_scroll.winfo_children():
            child.destroy()

        for i, note in enumerate(notes):
            if not isinstance(note, dict):
                continue
            word = str(note.get("word", "")).strip()
            zh_term = self._pick_zh_match_term(note)
            card = ctk.CTkFrame(self.notes_scroll, fg_color="#2A2A2A")
            card.grid(row=i, column=0, sticky="ew", pady=8, padx=6)
            card.grid_columnconfigure(0, weight=1)
            zh_hint = f" ⇄ {zh_term}" if zh_term else ""
            word_label = ctk.CTkLabel(card, text=f"{word}{zh_hint}", text_color="#4A9EFF", font=ctk.CTkFont(size=18, weight="bold"))
            word_label.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
            self.font_manager.register(word_label)
            sent_label = ctk.CTkLabel(card, text=str(note.get("sentence_in_passage", "")), text_color="#9A9A9A", wraplength=980, justify="left")
            sent_label.grid(row=1, column=0, sticky="w", padx=16, pady=4)
            self.font_manager.register(sent_label)
            usage_label = ctk.CTkLabel(card, text=str(note.get("usage_note", "")), text_color="#E8E8E8", wraplength=980, justify="left")
            usage_label.grid(row=2, column=0, sticky="w", padx=16, pady=(4, 12))
            self.font_manager.register(usage_label)

        self._highlight_bilingual_pairs(pairs)

    def _pick_zh_match_term(self, note: Dict[str, Any]) -> str:
        anchor = str(note.get("translation_anchor", "")).strip()
        if anchor:
            cjk = "".join(ch for ch in anchor if "\u4e00" <= ch <= "\u9fff")
            if len(cjk) >= 2:
                return cjk[:8]

        sentence_zh = str(note.get("sentence_in_translation", "")).strip()
        if sentence_zh:
            m = re.search(r"[\u4e00-\u9fff]{2,8}", sentence_zh)
            if m:
                return m.group(0)

        word = str(note.get("word", "")).strip()
        info = self.db.get_word_info(word) or {}
        definition = str(info.get("definition", "")).strip()
        normalized = re.sub(r"[，；、/|]", " ", definition)
        for token in normalized.split():
            cjk = "".join(ch for ch in token if "\u4e00" <= ch <= "\u9fff")
            if len(cjk) >= 2:
                return cjk[:8]
        return ""

    def _highlight_bilingual_pairs(self, pairs: List[Dict[str, str]]) -> None:
        en_widget = self.en_box._textbox
        zh_widget = self.zh_box._textbox

        for tag in en_widget.tag_names():
            if tag.startswith("word_"):
                en_widget.tag_delete(tag)
        for tag in zh_widget.tag_names():
            if tag.startswith("zh_word_"):
                zh_widget.tag_delete(tag)

        en_content = self.en_box.get("1.0", "end-1c")
        zh_content = self.zh_box.get("1.0", "end-1c")

        unique: List[Dict[str, str]] = []
        seen = set()
        for pair in pairs:
            word = str(pair.get("word", "")).strip().lower()
            zh_term = str(pair.get("zh_term", "")).strip()
            if not word or word in seen:
                continue
            seen.add(word)
            unique.append({"word": word, "zh_term": zh_term})

        for idx, pair in enumerate(unique):
            bg, fg = self._pair_colors[idx % len(self._pair_colors)]
            word = pair["word"]
            zh_term = pair["zh_term"]

            en_tag = f"word_{word}"
            en_widget.tag_config(en_tag, background=bg, foreground=fg)
            en_pattern = re.compile(rf"\b{re.escape(word)}\b", flags=re.IGNORECASE)
            for m in en_pattern.finditer(en_content):
                en_widget.tag_add(en_tag, f"1.0+{m.start()}c", f"1.0+{m.end()}c")
            en_widget.tag_bind(en_tag, "<Enter>", lambda e, w=word: self._on_word_hover_enter(e, w))
            en_widget.tag_bind(en_tag, "<Leave>", lambda _e: self._on_word_hover_leave())

            if zh_term:
                zh_tag = f"zh_word_{idx}"
                zh_widget.tag_config(zh_tag, background=bg, foreground=fg)
                start_at = 0
                while True:
                    pos = zh_content.find(zh_term, start_at)
                    if pos < 0:
                        break
                    zh_widget.tag_add(zh_tag, f"1.0+{pos}c", f"1.0+{pos + len(zh_term)}c")
                    start_at = pos + len(zh_term)

    def _on_word_hover_enter(self, event, word: str) -> None:
        info = self.db.get_word_info(word) or {"word": word, "definition": "", "tone": "", "memory_hook": ""}
        self.tooltip.schedule_show(event.widget, event.x_root, event.y_root, info)

    def _on_word_hover_leave(self) -> None:
        self.tooltip.cancel_schedule(self.en_box._textbox)
        self.tooltip.hide()

    def _set_loading(self, loading: bool) -> None:
        self.generate_btn.configure(state="disabled" if loading else "normal", text=("生成中…" if loading else "生成新短文"))
        self.stop_btn.configure(state="normal" if loading else "disabled")
        self.abandon_btn.configure(state="disabled" if loading else "normal")
        self.direction_menu.configure(state="disabled" if loading else "normal")
        if hasattr(self, "familiar_ref_menu"):
            self.familiar_ref_menu.configure(state="disabled" if loading else "normal")
        if hasattr(self, "new_ref_menu"):
            self.new_ref_menu.configure(state="disabled" if loading else "normal")
        if loading:
            self.en_box.delete("1.0", "end")
            self.zh_box.delete("1.0", "end")
            self.en_box.insert("end", "正在生成英文正文，请稍候…")
            self.zh_box.insert("end", "正在生成中文翻译，请稍候…")
            self._start_blink("正在生成短文，请稍候")
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

    def _celebrate_storyline_completed(self) -> None:
        msg = "故事线完成！🎉"

        def flash(count: int) -> None:
            if count <= 0:
                self.warning_label.configure(text=msg, text_color="#5DBF7F")
                return
            color = "#5DBF7F" if count % 2 else "#FFB347"
            self.warning_label.configure(text=msg, text_color=color)
            self._celebration_job = self.after(240, lambda: flash(count - 1))

        if self._celebration_job is not None:
            self.after_cancel(self._celebration_job)
        flash(8)
