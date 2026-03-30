from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml


class ConfigManager:
    def __init__(self, config_path: str = "config.yaml") -> None:
        self.config_path = Path(config_path)

    def load(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {}
        with self.config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def save(self, config: Dict[str, Any]) -> None:
        with self.config_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)

    def update_config(self, key_path: str, value: Any) -> None:
        cfg = self.load()
        keys = key_path.split(".")
        cursor: Dict[str, Any] = cfg
        for k in keys[:-1]:
            if k not in cursor or not isinstance(cursor[k], dict):
                cursor[k] = {}
            cursor = cursor[k]
        cursor[keys[-1]] = value
        self.save(cfg)

    def get(self, key_path: str, default: Any = None) -> Any:
        cfg = self.load()
        keys = key_path.split(".")
        cur: Any = cfg
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    def add_story_direction(self, name: str, description: str, prompt_inject: str = "") -> Dict[str, str]:
        cfg = self.load()
        sd = cfg.setdefault("story_directions", {})
        custom = sd.setdefault("custom", [])
        base_id = name.strip().lower().replace(" ", "_") or "custom_direction"
        used = {str(item.get("id", "")) for item in custom}
        final_id = base_id
        idx = 1
        while final_id in used:
            final_id = f"{base_id}_{idx}"
            idx += 1
        item = {
            "id": final_id,
            "name": name.strip() or "自定义",
            "description": description.strip(),
            "prompt_inject": (prompt_inject.strip() or description.strip()),
        }
        custom.append(item)
        self.save(cfg)
        return item

    def remove_story_direction(self, direction_id: str) -> None:
        cfg = self.load()
        custom: List[Dict[str, Any]] = cfg.get("story_directions", {}).get("custom", [])
        cfg.setdefault("story_directions", {})["custom"] = [x for x in custom if x.get("id") != direction_id]
        self.save(cfg)
