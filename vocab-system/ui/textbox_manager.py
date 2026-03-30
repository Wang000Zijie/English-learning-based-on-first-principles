from __future__ import annotations

from typing import List, Tuple


class TextboxManager:
    def __init__(self, initial_scale: float = 1.0) -> None:
        self.scale = float(initial_scale)
        self._listeners: List[Tuple[object, int]] = []

    def register(self, widget: object, base_height: int) -> None:
        base = max(40, int(base_height))
        self._listeners.append((widget, base))
        try:
            widget.configure(height=int(base * self.scale))
        except Exception:
            pass

    def set_scale(self, scale: float) -> None:
        self.scale = max(0.6, min(2.2, float(scale)))
        alive: List[Tuple[object, int]] = []
        for widget, base in self._listeners:
            try:
                widget.configure(height=int(base * self.scale))
                alive.append((widget, base))
            except Exception:
                continue
        self._listeners = alive
