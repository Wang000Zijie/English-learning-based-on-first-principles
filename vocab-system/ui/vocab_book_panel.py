from __future__ import annotations

import csv
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Dict, List, Set

import customtkinter as ctk

from core.review_engine import ReviewEngine
from data.db_manager import DBManager
from ui.components.flashcard import FlashcardWindow
from ui.components.word_card import WordCard
from ui.font_manager import FontManager
from ui.textbox_manager import TextboxManager


class VocabBookPanel(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        db_manager: DBManager,
        review_engine: ReviewEngine,
        font_manager: FontManager,
        textbox_manager: TextboxManager,
        on_changed,
    ) -> None:
        super().__init__(master)
        self.db = db_manager
        self.review_engine = review_engine
        self.font_manager = font_manager
        self.textbox_manager = textbox_manager
        self.on_changed = on_changed

        self.selected_ids: Set[int] = set()
        self.level_filter: Set[str] = set()
        self.bank_var = ctk.StringVar(value="new")
        self.time_sort_var = ctk.StringVar(value="created_at_desc")
        self.extra_sort_vars: Dict[str, ctk.BooleanVar] = {
            "usage_count_desc": ctk.BooleanVar(value=False),
            "reviews_desc": ctk.BooleanVar(value=False),
            "accuracy_desc": ctk.BooleanVar(value=False),
        }
        self.sort_desc_label_var = ctk.StringVar(value="时间倒序")

        self._build_ui()
        self._refresh_sort_desc()
        self.reload_cards()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        top.grid_columnconfigure(1, weight=1)

        search_label = ctk.CTkLabel(top, text="搜索")
        search_label.grid(row=0, column=0, padx=(8, 4), pady=8)
        self.font_manager.register(search_label)
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(top, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=8)
        self.search_entry.bind("<KeyRelease>", lambda _e: self.reload_cards())
        self.font_manager.register(self.search_entry)

        sort_btn = ctk.CTkButton(top, text="排序设置", width=86, fg_color="#3A3A3A", command=self._open_sort_dialog)
        sort_btn.grid(row=0, column=2, padx=(6, 4))
        self.font_manager.register(sort_btn)

        sort_desc = ctk.CTkLabel(top, textvariable=self.sort_desc_label_var, text_color="#9A9A9A")
        sort_desc.grid(row=0, column=3, padx=(2, 8), sticky="w")
        self.font_manager.register(sort_desc)

        self.bank_menu = ctk.CTkOptionMenu(
            top,
            values=["生词库(new)", "熟词库(familiar)"],
            command=self._on_bank_change,
            width=132,
        )
        self.bank_menu.set("生词库(new)")
        self.bank_menu.grid(row=0, column=4, padx=6)
        self.font_manager.register(self.bank_menu)

        flash_btn = ctk.CTkButton(top, text="开始自测", command=self._start_flashcard)
        flash_btn.grid(row=0, column=5, padx=6)
        self.font_manager.register(flash_btn)

        export_btn = ctk.CTkButton(top, text="导出选中", fg_color="#3A3A3A", command=self._export_selected)
        export_btn.grid(row=0, column=6, padx=6)
        self.font_manager.register(export_btn)

        del_btn = ctk.CTkButton(top, text="删除选中", fg_color="#E06C75", command=self._delete_selected)
        del_btn.grid(row=0, column=7, padx=(6, 12))
        self.font_manager.register(del_btn)

        chips = ctk.CTkFrame(self, fg_color="transparent")
        chips.grid(row=1, column=0, sticky="ew", padx=16)
        level_names = {
            "new": "新词",
            "learning": "学习中",
            "familiar": "已熟悉",
            "mastered": "已掌握",
        }
        for idx, level in enumerate(["new", "learning", "familiar", "mastered"]):
            chip = ctk.CTkCheckBox(
                chips,
                text=level_names.get(level, level),
                command=lambda lv=level: self._toggle_level(lv),
            )
            chip.grid(row=0, column=idx, padx=6, pady=(0, 8))
            self.font_manager.register(chip)

        self.grid = ctk.CTkScrollableFrame(self)
        self.grid.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 14))
        self.grid.grid_columnconfigure((0, 1, 2), weight=1)

    def _toggle_level(self, level: str) -> None:
        if level in self.level_filter:
            self.level_filter.remove(level)
        else:
            self.level_filter.add(level)
        self.reload_cards()

    def _on_bank_change(self, value: str) -> None:
        self.bank_var.set("familiar" if "familiar" in value else "new")
        self.reload_cards()

    def reload_cards(self) -> None:
        self.selected_ids.clear()
        for child in self.grid.winfo_children():
            child.destroy()
        words = self.db.list_words_advanced(
            query=self.search_var.get().strip(),
            levels=sorted(self.level_filter) if self.level_filter else None,
            sort_keys=self._get_sort_keys(),
            word_bank=self.bank_var.get().strip(),
        )
        for i, item in enumerate(words):
            card = WordCard(
                self.grid,
                item=item,
                font_manager=self.font_manager,
                on_edit=self._edit_word,
                on_delete=self._delete_word,
                on_review=self._review_now,
                selectable=True,
                on_select=self._on_select,
            )
            card.grid(row=i // 3, column=i % 3, sticky="nsew", padx=8, pady=8)

    def _on_select(self, word_id: int, selected: bool) -> None:
        if selected:
            self.selected_ids.add(word_id)
        else:
            self.selected_ids.discard(word_id)

    def _edit_word(self, item: Dict) -> None:
        word_id = int(item.get("id", 0) or 0)
        if word_id <= 0:
            messagebox.showerror("错误", "词条 ID 无效，无法编辑")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title(f"编辑词条：{item.get('word', '')}")
        dlg.geometry("640x560")
        dlg.attributes("-topmost", True)
        dlg.grab_set()

        form = ctk.CTkScrollableFrame(dlg)
        form.pack(fill="both", expand=True, padx=12, pady=12)
        form.grid_columnconfigure(1, weight=1)

        entries: Dict[str, ctk.CTkEntry] = {}

        def add_entry(row: int, key: str, label: str, default: str) -> None:
            lbl = ctk.CTkLabel(form, text=label)
            lbl.grid(row=row, column=0, sticky="w", padx=(8, 6), pady=6)
            self.font_manager.register(lbl)
            ent = ctk.CTkEntry(form)
            ent.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=6)
            ent.insert(0, default)
            self.font_manager.register(ent)
            entries[key] = ent

        add_entry(0, "word", "单词", str(item.get("word", "")))
        add_entry(1, "definition", "释义", str(item.get("definition", "")))
        add_entry(2, "tone", "语气", str(item.get("tone", "")))
        add_entry(3, "scenario", "场景", str(item.get("scenario", "")))
        add_entry(4, "memory_hook", "记忆钩子", str(item.get("memory_hook", "")))
        add_entry(5, "example_sentence", "例句", str(item.get("example_sentence", "")))
        add_entry(6, "common_mistake", "常见错误", str(item.get("common_mistake", "")))
        add_entry(7, "source_context", "来源", str(item.get("source_context", "")))

        level_label = ctk.CTkLabel(form, text="等级")
        level_label.grid(row=8, column=0, sticky="w", padx=(8, 6), pady=6)
        self.font_manager.register(level_label)
        level_var = ctk.StringVar(value=str(item.get("level", "new") or "new"))
        level_menu = ctk.CTkOptionMenu(form, variable=level_var, values=["new", "learning", "familiar", "mastered"])
        level_menu.grid(row=8, column=1, sticky="w", padx=(0, 8), pady=6)
        self.font_manager.register(level_menu)

        bank_label = ctk.CTkLabel(form, text="词库")
        bank_label.grid(row=9, column=0, sticky="w", padx=(8, 6), pady=6)
        self.font_manager.register(bank_label)
        bank_var = ctk.StringVar(value=str(item.get("word_bank", "new") or "new"))
        bank_menu = ctk.CTkOptionMenu(form, variable=bank_var, values=["new", "familiar"])
        bank_menu.grid(row=9, column=1, sticky="w", padx=(0, 8), pady=6)
        self.font_manager.register(bank_menu)

        actions = ctk.CTkFrame(dlg, fg_color="transparent")
        actions.pack(fill="x", padx=12, pady=(0, 12))

        def save() -> None:
            word = entries["word"].get().strip().lower()
            if not word:
                messagebox.showwarning("提示", "单词不能为空")
                return
            payload = {
                "word": word,
                "definition": entries["definition"].get().strip(),
                "tone": entries["tone"].get().strip(),
                "scenario": entries["scenario"].get().strip(),
                "memory_hook": entries["memory_hook"].get().strip(),
                "example_sentence": entries["example_sentence"].get().strip(),
                "common_mistake": entries["common_mistake"].get().strip(),
                "source_context": entries["source_context"].get().strip(),
                "level": level_var.get().strip() or "new",
                "word_bank": bank_var.get().strip() or "new",
            }
            try:
                self.db.update_word_fields(word_id, payload)
            except Exception as exc:
                messagebox.showerror("保存失败", str(exc))
                return
            self.reload_cards()
            self.on_changed()
            dlg.destroy()

        save_btn = ctk.CTkButton(actions, text="保存", command=save)
        save_btn.pack(side="left")
        self.font_manager.register(save_btn)

        cancel_btn = ctk.CTkButton(actions, text="取消", fg_color="#3A3A3A", command=dlg.destroy)
        cancel_btn.pack(side="left", padx=8)
        self.font_manager.register(cancel_btn)

    def _delete_word(self, item: Dict) -> None:
        if not messagebox.askyesno("确认", f"删除单词 {item.get('word', '')} ?"):
            return
        word_id = int(item.get("id", 0) or 0)
        if word_id <= 0:
            messagebox.showerror("删除失败", "词条 ID 无效")
            return
        try:
            self.db.delete_words([word_id])
            self.selected_ids.discard(word_id)
            self.reload_cards()
            self.on_changed()
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc))

    def _review_now(self, item: Dict) -> None:
        self.review_engine.record_review(int(item.get("id", 0)), "forgotten")
        messagebox.showinfo("完成", "已加入复习队列")
        self.reload_cards()
        self.on_changed()

    def _delete_selected(self) -> None:
        valid_ids = sorted(i for i in self.selected_ids if int(i) > 0)
        if not valid_ids:
            messagebox.showwarning("提示", "请先选择词汇")
            return
        if not messagebox.askyesno("确认", f"确定删除 {len(valid_ids)} 个词汇？"):
            return
        try:
            self.db.delete_words(valid_ids)
            self.selected_ids.clear()
            self.reload_cards()
            self.on_changed()
        except Exception as exc:
            messagebox.showerror("删除失败", str(exc))

    def _export_selected(self) -> None:
        if not self.selected_ids:
            messagebox.showwarning("提示", "请先选择词汇")
            return
        rows = [w for w in self.db.list_words_advanced() if int(w.get("id", 0)) in self.selected_ids]
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        fields = [
            "word",
            "definition",
            "tone",
            "scenario",
            "collocations",
            "memory_hook",
            "example_sentence",
            "common_mistake",
            "level",
            "total_reviews",
            "pass_rate",
        ]
        with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fields})
        messagebox.showinfo("完成", f"已导出 {len(rows)} 条")

    def _start_flashcard(self) -> None:
        words = self.db.list_words_advanced(
            query=self.search_var.get().strip(),
            levels=sorted(self.level_filter) if self.level_filter else None,
            sort_keys=self._get_sort_keys(),
            word_bank=self.bank_var.get().strip(),
        )
        if not words:
            messagebox.showwarning("提示", "当前筛选结果为空")
            return

        def on_grade(word_id: int, result: str) -> None:
            self.review_engine.record_review(word_id, result)

        FlashcardWindow(self, words, on_grade, self.font_manager, self.textbox_manager)

    def _get_sort_keys(self) -> List[str]:
        keys: List[str] = [self.time_sort_var.get().strip() or "created_at_desc"]
        for key in ["usage_count_desc", "reviews_desc", "accuracy_desc"]:
            if bool(self.extra_sort_vars[key].get()):
                keys.append(key)
        return keys

    def _refresh_sort_desc(self) -> None:
        names: Dict[str, str] = {
            "created_at_desc": "时间倒序",
            "created_at_asc": "时间正序",
            "usage_count_desc": "使用次数",
            "reviews_desc": "复习次数",
            "accuracy_desc": "正确率",
        }
        labels = [names.get(k, k) for k in self._get_sort_keys()]
        self.sort_desc_label_var.set(" + ".join(labels))

    def _open_sort_dialog(self) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("排序设置")
        dlg.geometry("420x340")
        dlg.attributes("-topmost", True)
        dlg.grab_set()

        title = ctk.CTkLabel(dlg, text="支持单项排序，也支持多项组合排序", text_color="#9A9A9A")
        title.pack(anchor="w", padx=14, pady=(12, 8))
        self.font_manager.register(title)

        section_time = ctk.CTkLabel(dlg, text="时间排序", text_color="#E8E8E8")
        section_time.pack(anchor="w", padx=14, pady=(4, 4))
        self.font_manager.register(section_time)

        time_values = {
            "时间倒序（新到旧）": "created_at_desc",
            "时间正序（旧到新）": "created_at_asc",
        }

        time_var = ctk.StringVar(value=self.time_sort_var.get())
        for text, value in time_values.items():
            rb = ctk.CTkRadioButton(dlg, text=text, value=value, variable=time_var)
            rb.pack(anchor="w", padx=18, pady=2)
            self.font_manager.register(rb)

        section_extra = ctk.CTkLabel(dlg, text="附加排序（按下列顺序依次生效）", text_color="#E8E8E8")
        section_extra.pack(anchor="w", padx=14, pady=(10, 4))
        self.font_manager.register(section_extra)

        local_vars: Dict[str, ctk.BooleanVar] = {}
        for text, key in [
            ("使用次数（抽中次数）", "usage_count_desc"),
            ("复习次数", "reviews_desc"),
            ("正确率", "accuracy_desc"),
        ]:
            var = ctk.BooleanVar(value=bool(self.extra_sort_vars[key].get()))
            local_vars[key] = var
            cb = ctk.CTkCheckBox(dlg, text=text, variable=var)
            cb.pack(anchor="w", padx=18, pady=2)
            self.font_manager.register(cb)

        note = ctk.CTkLabel(dlg, text="优先级固定为：时间 -> 使用次数 -> 复习次数 -> 正确率", text_color="#9A9A9A")
        note.pack(anchor="w", padx=14, pady=(8, 6))
        self.font_manager.register(note)

        actions = ctk.CTkFrame(dlg, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(6, 12))

        def apply_sort() -> None:
            self.time_sort_var.set(time_var.get().strip() or "created_at_desc")
            for key, var in local_vars.items():
                self.extra_sort_vars[key].set(bool(var.get()))
            self._refresh_sort_desc()
            self.reload_cards()
            dlg.destroy()

        ok_btn = ctk.CTkButton(actions, text="应用", command=apply_sort)
        ok_btn.pack(side="left")
        self.font_manager.register(ok_btn)

        cancel_btn = ctk.CTkButton(actions, text="取消", fg_color="#3A3A3A", command=dlg.destroy)
        cancel_btn.pack(side="left", padx=8)
        self.font_manager.register(cancel_btn)
