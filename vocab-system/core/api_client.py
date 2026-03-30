from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml


class APIClientError(Exception):
    """Raised when upstream AI API call fails."""


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: Optional[int]


class APIClient:
    """The only gateway for external model access in the application."""

    ALLOWED_PROVIDERS = {"kimi", "minimax", "deepseek", "gpt", "gemini"}
    LEGACY_PROVIDER_ALIAS = {
        "openai": "gpt",
        "anthropic": "deepseek",
        "local": "deepseek",
    }
    LEGACY_MODEL_ALIAS = {
        ("minimax", "MiniMax-Text-01"): "MiniMax-M2.7",
    }

    def __init__(self, config_path: str = "config.yaml") -> None:
        self.config_path = Path(config_path)

    def ask(self, prompt: str) -> str:
        provider = self._resolve_provider()
        return self._ask_with_provider(provider, prompt)

    def ask_with_role(self, prompt: str, role: str) -> str:
        provider_name = self._provider_from_role(role)
        provider = self._resolve_provider(provider_name)
        return self._ask_with_provider(provider, prompt)

    def ask_stream(
        self,
        prompt: str,
        callback: Callable[[str], None],
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        provider = self._resolve_provider()
        self._ask_stream_with_provider(provider, prompt, callback, should_stop)

    def ask_stream_with_role(
        self,
        prompt: str,
        callback: Callable[[str], None],
        role: str,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        provider_name = self._provider_from_role(role)
        provider = self._resolve_provider(provider_name)
        self._ask_stream_with_provider(provider, prompt, callback, should_stop)

    def _ask_with_provider(self, provider: ProviderConfig, prompt: str) -> str:
        if not prompt or not prompt.strip():
            raise APIClientError("Prompt cannot be empty.")
        return self._ask_openai_compatible(provider, prompt)

    def _ask_stream_with_provider(
        self,
        provider: ProviderConfig,
        prompt: str,
        callback: Callable[[str], None],
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        if not prompt or not prompt.strip():
            raise APIClientError("Prompt cannot be empty.")
        self._ask_openai_compatible_stream(provider, prompt, callback, should_stop)

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise APIClientError(f"Config file not found: {self.config_path}")

        with self.config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _provider_from_role(self, role: str) -> str | None:
        raw_config = self._load_config()
        agent_roles = raw_config.get("agent_roles", {})
        if not bool(agent_roles.get("enabled", False)):
            return None
        roles = agent_roles.get("roles", {})
        value = str(roles.get(role, "")).strip()
        if not value:
            return None
        normalized = self._normalize_provider_name(value)
        return normalized

    def _normalize_provider_name(self, provider_name: str) -> str:
        raw = str(provider_name or "").strip().lower()
        if not raw:
            return ""
        return self.LEGACY_PROVIDER_ALIAS.get(raw, raw)

    def _resolve_provider(self, provider_override: str | None = None) -> ProviderConfig:
        raw_config = self._load_config()
        api_cfg = raw_config.get("api", {})
        provider_name = self._normalize_provider_name(str(provider_override or api_cfg.get("provider", "")))
        if not provider_name:
            raise APIClientError("Missing api.provider in config.yaml")
        if provider_name not in self.ALLOWED_PROVIDERS:
            raise APIClientError(
                f"不支持的 provider: {provider_name}。仅支持: {', '.join(sorted(self.ALLOWED_PROVIDERS))}"
            )

        detail = api_cfg.get(provider_name)
        if not detail:
            raise APIClientError(f"Missing provider block for '{provider_name}'")

        cfg_key = str(detail.get("api_key", "")).strip()
        provider_env_map = {
            "deepseek": os.getenv("DEEPSEEK_API_KEY", ""),
            "gpt": os.getenv("OPENAI_API_KEY", ""),
            "kimi": os.getenv("KIMI_API_KEY", ""),
            "minimax": os.getenv("MINIMAX_API_KEY", ""),
            "gemini": os.getenv("GEMINI_API_KEY", ""),
        }
        env_key = str(
            os.getenv("VOCAB_API_KEY", "")
            or provider_env_map.get(provider_name, "")
        ).strip()
        api_key = env_key or cfg_key

        if not str(api_key).strip():
            raise APIClientError(
                f"API 密钥为空（provider={provider_name}）。"
                "请检查 config.yaml 中的 api_key 配置。"
            )

        model_name = str(detail.get("model", ""))
        model_name = self.LEGACY_MODEL_ALIAS.get((provider_name, model_name), model_name)

        return ProviderConfig(
            name=provider_name,
            base_url=str(detail.get("base_url", "")).rstrip("/"),
            api_key=api_key,
            model=model_name,
            temperature=float(detail.get("temperature", 0.3)),
            max_tokens=(None if detail.get("max_tokens", None) in (None, "", 0, "0") else int(detail.get("max_tokens"))),
        )

    def _ask_openai_compatible(self, provider: ProviderConfig, prompt: str) -> str:
        from openai import APIConnectionError as OpenAIConnectionError
        from openai import AuthenticationError as OpenAIAuthenticationError
        from openai import OpenAI
        from openai import OpenAIError
        from openai import APITimeoutError

        client = OpenAI(base_url=provider.base_url, api_key=provider.api_key)
        for attempt in range(2):
            try:
                payload: Dict[str, Any] = {
                    "model": provider.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": provider.temperature,
                }
                if provider.max_tokens is not None:
                    payload["max_tokens"] = provider.max_tokens
                resp = client.chat.completions.create(**payload)
                text = (resp.choices[0].message.content or "").strip()
                usage = getattr(resp, "usage", None)
                if usage is not None:
                    prompt_tokens = getattr(usage, "prompt_tokens", 0)
                    completion_tokens = getattr(usage, "completion_tokens", 0)
                    print(f"[API] 本次消耗 {prompt_tokens} + {completion_tokens} tokens")
                return text
            except APITimeoutError as exc:
                if attempt == 0:
                    continue
                raise APIClientError("网络连接失败，请检查网络后重试") from exc
            except OpenAIAuthenticationError as exc:
                raise APIClientError("API 密钥无效，请检查 config.yaml 中的 api_key 配置") from exc
            except OpenAIConnectionError as exc:
                raise APIClientError("网络连接失败，请检查网络后重试") from exc
            except OpenAIError as exc:
                raise APIClientError(f"API 调用失败: {exc}") from exc
            except Exception as exc:
                raise APIClientError(f"未知错误: {exc}") from exc
        raise APIClientError("API 调用失败")

    def _ask_openai_compatible_stream(
        self,
        provider: ProviderConfig,
        prompt: str,
        callback: Callable[[str], None],
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        from openai import OpenAI
        from openai import AuthenticationError as OpenAIAuthenticationError
        from openai import APIConnectionError as OpenAIConnectionError
        from openai import OpenAIError

        client = OpenAI(base_url=provider.base_url, api_key=provider.api_key)
        try:
            payload: Dict[str, Any] = {
                "model": provider.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": provider.temperature,
                "stream": True,
            }
            if provider.max_tokens is not None:
                payload["max_tokens"] = provider.max_tokens
            stream = client.chat.completions.create(**payload)
            for chunk in stream:
                if should_stop is not None and should_stop():
                    close_fn = getattr(stream, "close", None)
                    if callable(close_fn):
                        close_fn()
                    raise APIClientError("已停止本次生成")
                delta = ""
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta.content or ""
                if delta:
                    callback(delta)
        except OpenAIAuthenticationError as exc:
            raise APIClientError("API 密钥无效，请检查 config.yaml 中的 api_key 配置") from exc
        except OpenAIConnectionError as exc:
            raise APIClientError("网络连接失败，请检查网络后重试") from exc
        except OpenAIError as exc:
            raise APIClientError(f"API 调用失败: {exc}") from exc
