from __future__ import annotations

import customtkinter as ctk
from typing import Callable, Dict

from ui.font_manager import FontManager


LEVEL_COLORS = {
    "new": "#7A7A7A",
    "learning": "#4A9EFF",
    "familiar": "#FFB347",
    "mastered": "#5DBF7F",
}

LEVEL_TEXT = {
    "new": "新词",
    "learning": "学习中",
    "familiar": "已熟悉",
    "mastered": "已掌握",
}


class WordCard(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        item: Dict,
        font_manager: FontManager,
        on_edit: Callable[[Dict], None],
        on_delete: Callable[[Dict], None],
        on_review: Callable[[Dict], None],
        selectable: bool,
        on_select: Callable[[int, bool], None],
    ) -> None:
        super().__init__(master, fg_color="#232323")
        self.item = item
        self.font_manager = font_manager
        self.on_select = on_select

        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        top.grid_columnconfigure(0, weight=1)

        word_label = ctk.CTkLabel(top, text=str(item.get("word", "")), text_color="#E8E8E8", font=ctk.CTkFont(size=18, weight="bold"))
        word_label.grid(row=0, column=0, sticky="w")
        self.font_manager.register(word_label)

        level = str(item.get("level", "new"))
        tag = ctk.CTkLabel(
            top,
            text=LEVEL_TEXT.get(level, level),
            fg_color=LEVEL_COLORS.get(level, "#7A7A7A"),
            corner_radius=8,
            text_color="#FFFFFF",
            width=72,
        )
        tag.grid(row=0, column=1, sticky="e")
        self.font_manager.register(tag)

        def_label = ctk.CTkLabel(self, text=str(item.get("definition", "")), text_color="#CFCFCF", justify="left", wraplength=360)
        def_label.grid(row=1, column=0, sticky="w", padx=10)
        self.font_manager.register(def_label)

        stats = ctk.CTkLabel(
            self,
            text=(
                f"抽中 {int(item.get('passage_count', 0) or 0)} 次  "
                f"复习 {int(item.get('total_reviews', 0) or 0)} 次  "
                f"正确率 {float(item.get('pass_rate', 0) or 0):.0f}%"
            ),
            text_color="#9A9A9A",
        )
        stats.grid(row=2, column=0, sticky="w", padx=10, pady=(8, 2))
        self.font_manager.register(stats)

        next_review = ctk.CTkLabel(self, text=f"下次复习：{item.get('next_review_date', '待安排')}", text_color="#9A9A9A")
        next_review.grid(row=3, column=0, sticky="w", padx=10)
        self.font_manager.register(next_review)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=10, pady=(8, 10))

        edit_btn = ctk.CTkButton(actions, text="编辑", width=64, command=lambda: on_edit(item))
        edit_btn.pack(side="left")
        self.font_manager.register(edit_btn)
        del_btn = ctk.CTkButton(actions, text="删除", width=64, fg_color="#3A3A3A", command=lambda: on_delete(item))
        del_btn.pack(side="left", padx=6)
        self.font_manager.register(del_btn)
        review_btn = ctk.CTkButton(actions, text="立即复习", width=86, fg_color="#4A9EFF", command=lambda: on_review(item))
        review_btn.pack(side="left")
        self.font_manager.register(review_btn)

        if selectable:
            selected_var = ctk.BooleanVar(value=False)
            check = ctk.CTkCheckBox(
                actions,
                text="",
                width=20,
                variable=selected_var,
                command=lambda: self.on_select(int(item.get("id", 0)), bool(selected_var.get())),
            )
            check.pack(side="right")
            self.font_manager.register(check)
