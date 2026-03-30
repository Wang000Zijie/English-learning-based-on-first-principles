from __future__ import annotations

import tkinter as tk
from typing import Optional


class WordTooltip:
    def __init__(self) -> None:
        self.tip: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None

    def schedule_show(self, widget: tk.Widget, x_root: int, y_root: int, payload: dict) -> None:
        self.cancel_schedule(widget)

        def _show() -> None:
            self.show(widget, x_root, y_root, payload)

        self._after_id = widget.after(150, _show)

    def cancel_schedule(self, widget: tk.Widget) -> None:
        if self._after_id is not None:
            try:
                widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def hide(self) -> None:
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None

    def show(self, widget: tk.Widget, x_root: int, y_root: int, payload: dict) -> None:
        self.hide()
        self.tip = tk.Toplevel(widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x_root + 15}+{y_root - 10}")

        frame = tk.Frame(self.tip, bg="#2A2A2A", bd=1, relief="solid")
        frame.pack()

        tk.Label(
            frame,
            text=str(payload.get("word", "")),
            bg="#2A2A2A",
            fg="#4A9EFF",
            font=("微软雅黑", 14, "bold"),
            wraplength=340,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(10, 4))

        tk.Label(
            frame,
            text=f"释义  {payload.get('definition', '')}",
            bg="#2A2A2A",
            fg="#E8E8E8",
            font=("微软雅黑", 11),
            wraplength=340,
            justify="left",
        ).pack(anchor="w", padx=12, pady=2)

        tk.Label(
            frame,
            text=f"色彩  {payload.get('tone', '')}",
            bg="#2A2A2A",
            fg="#9A9A9A",
            font=("微软雅黑", 10),
            wraplength=340,
            justify="left",
        ).pack(anchor="w", padx=12, pady=2)

        tk.Label(
            frame,
            text=f"记忆  {payload.get('memory_hook', '')}",
            bg="#2A2A2A",
            fg="#FFB347",
            font=("微软雅黑", 10),
            wraplength=340,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(2, 10))
