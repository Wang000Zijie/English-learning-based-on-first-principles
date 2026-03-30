from __future__ import annotations

import random
from typing import Callable, Dict, List

import customtkinter as ctk

from ui.font_manager import FontManager
from ui.textbox_manager import TextboxManager


class FlashcardWindow(ctk.CTkToplevel):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        words: List[Dict],
        on_grade: Callable[[int, str], None],
        font_manager: FontManager,
        textbox_manager: TextboxManager,
    ) -> None:
        super().__init__(master)
        self.title("闪卡自测")
        self.geometry("920x620")
        self.grab_set()

        self.words = words[:]
        random.shuffle(self.words)
        self.on_grade = on_grade
        self.font_manager = font_manager
        self.textbox_manager = textbox_manager

        self.index = 0
        self.flipped = False
        self.remembered = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.progress = ctk.CTkLabel(self, text="0 / 0")
        self.progress.grid(row=0, column=0, sticky="e", padx=20, pady=12)
        self.font_manager.register(self.progress)

        self.card = ctk.CTkTextbox(self, font=("微软雅黑", self.font_manager.size))
        self.card.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        self.font_manager.register(self.card)
        self.textbox_manager.register(self.card, base_height=420)

        actions = ctk.CTkFrame(self)
        actions.grid(row=2, column=0, sticky="ew", padx=20, pady=12)

        self.flip_btn = ctk.CTkButton(actions, text="翻面（空格）", command=self.flip)
        self.flip_btn.pack(side="left")
        self.font_manager.register(self.flip_btn)

        self.btn1 = ctk.CTkButton(actions, text="1 完全记住", fg_color="#5DBF7F", command=lambda: self.grade("remembered"))
        self.btn1.pack(side="left", padx=8)
        self.font_manager.register(self.btn1)
        self.btn2 = ctk.CTkButton(actions, text="2 模糊", command=lambda: self.grade("forgotten"))
        self.btn2.pack(side="left", padx=4)
        self.font_manager.register(self.btn2)
        self.btn3 = ctk.CTkButton(actions, text="3 不记得", fg_color="#E06C75", command=lambda: self.grade("forgotten"))
        self.btn3.pack(side="left", padx=4)
        self.font_manager.register(self.btn3)

        self.bind("<space>", lambda _e: self.flip())
        self.bind("1", lambda _e: self.grade("remembered"))
        self.bind("2", lambda _e: self.grade("forgotten"))
        self.bind("3", lambda _e: self.grade("forgotten"))
        self.bind("<Right>", lambda _e: self.grade("remembered"))
        self.bind("<Left>", lambda _e: self.grade("forgotten"))

        self.render()

    def render(self) -> None:
        if self.index >= len(self.words):
            total = len(self.words)
            rate = (self.remembered / total * 100) if total else 0.0
            self.card.delete("1.0", "end")
            self.card.insert("end", f"自测结束\n\n测了 {total} 张\n记住 {self.remembered} 张\n准确率 {rate:.1f}%")
            self.progress.configure(text="已完成")
            return

        item = self.words[self.index]
        self.progress.configure(text=f"{self.index + 1} / {len(self.words)}")
        self.card.delete("1.0", "end")
        if not self.flipped:
            self.card.insert("end", f"\n\n\n{item.get('word', '')}")
        else:
            self.card.insert(
                "end",
                (
                    f"{item.get('word', '')}\n\n"
                    f"释义: {item.get('definition', '')}\n"
                    f"记忆钩子: {item.get('memory_hook', '')}\n"
                    f"例句: {item.get('example_sentence', '')}\n"
                    f"常见错误: {item.get('common_mistake', '')}"
                ),
            )

    def flip(self) -> None:
        if self.index >= len(self.words):
            return
        self.flipped = not self.flipped
        self.render()

    def grade(self, result: str) -> None:
        if self.index >= len(self.words):
            return
        item = self.words[self.index]
        if result == "remembered":
            self.remembered += 1
        self.on_grade(int(item.get("id", 0)), result)
        self.index += 1
        self.flipped = False
        self.render()
