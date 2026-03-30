from __future__ import annotations

from typing import Any, Dict, List

import requests

from core.config_manager import ConfigManager


class NewsFetcher:
    def __init__(self, config_path: str) -> None:
        self.config = ConfigManager(config_path)

    def search(self, query: str, freshness: str = "oneWeek") -> List[Dict[str, Any]]:
        cfg = self.config.load().get("news", {})
        provider = str(cfg.get("provider", "none"))
        if provider == "bocha":
            return self._search_bocha(query, freshness)
        if provider == "tavily":
            return self._search_tavily(query)
        return []

    def _search_bocha(self, query: str, freshness: str) -> List[Dict[str, Any]]:
        cfg = self.config.load().get("news", {}).get("bocha", {})
        headers = {
            "Authorization": f"Bearer {cfg.get('api_key', '')}",
            "Content-Type": "application/json",
        }
        body = {
            "query": query,
            "freshness": freshness or cfg.get("freshness", "oneWeek"),
            "summary": True,
            "count": int(cfg.get("count", 5)),
        }
        response = requests.post(
            str(cfg.get("base_url", "https://api.bochaai.com/v1/web-search")),
            headers=headers,
            json=body,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json() or {}
        rows = payload.get("data", {}).get("webPages", {}).get("value", [])
        result: List[Dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "title": row.get("name", ""),
                    "url": row.get("url", ""),
                    "snippet": row.get("snippet", ""),
                    "content": row.get("summary", "") or row.get("snippet", ""),
                    "provider": "bocha",
                    "published_date": row.get("datePublished", ""),
                }
            )
        return result

    def _search_tavily(self, query: str) -> List[Dict[str, Any]]:
        cfg = self.config.load().get("news", {}).get("tavily", {})
        headers = {"Content-Type": "application/json"}
        body = {
            "api_key": cfg.get("api_key", ""),
            "query": query,
            "search_depth": cfg.get("search_depth", "advanced"),
            "max_results": int(cfg.get("max_results", 5)),
            "include_raw_content": bool(cfg.get("include_raw_content", True)),
            "include_answer": False,
        }
        response = requests.post(
            str(cfg.get("base_url", "https://api.tavily.com/search")),
            headers=headers,
            json=body,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json() or {}
        rows = payload.get("results", [])
        result: List[Dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "title": row.get("title", ""),
                    "url": row.get("url", ""),
                    "snippet": row.get("content", ""),
                    "content": row.get("raw_content", "") or row.get("content", ""),
                    "provider": "tavily",
                    "published_date": row.get("published_date", ""),
                }
            )
        return result
