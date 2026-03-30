from __future__ import annotations

from typing import List, Tuple


class FontManager:
    def __init__(self, initial_size: int = 14) -> None:
        self.size = int(initial_size)
        self._listeners: List[Tuple[object, str]] = []

    def register(self, widget: object, family: str = "微软雅黑") -> None:
        self._listeners.append((widget, family))
        try:
            widget.configure(font=(family, self.size))
        except Exception:
            pass

    def set_size(self, new_size: float | int) -> None:
        self.size = int(float(new_size))
        alive: List[Tuple[object, str]] = []
        for widget, family in self._listeners:
            try:
                widget.configure(font=(family, self.size))
                alive.append((widget, family))
            except Exception:
                continue
        self._listeners = alive
