"""Routes LLM requests to the correct provider client."""

from __future__ import annotations

from memory_layer.llm.anthropic_client import AnthropicClient
from memory_layer.llm.base import BaseLLMClient
from memory_layer.llm.google_client import GoogleClient
from memory_layer.llm.openai_client import OpenAIClient
from memory_layer.models.keys import LLMProvider

_PROVIDER_MAP: dict[str, type[BaseLLMClient]] = {
    LLMProvider.OPENAI: OpenAIClient,
    LLMProvider.ANTHROPIC: AnthropicClient,
    LLMProvider.GOOGLE: GoogleClient,
}


class LLMRouter:
    """Creates and caches LLM clients per user+provider."""

    def __init__(self) -> None:
        self._cache: dict[str, BaseLLMClient] = {}

    def get_client(
        self,
        provider: str,
        api_key: str,
        model: str | None = None,
    ) -> BaseLLMClient:
        cache_key = f"{provider}:{api_key[:8]}"
        if cache_key not in self._cache:
            cls = _PROVIDER_MAP.get(provider)
            if cls is None:
                raise ValueError(f"Unsupported provider: {provider}")
            self._cache[cache_key] = cls(api_key=api_key, model=model)
        return self._cache[cache_key]

    def clear_cache(self) -> None:
        self._cache.clear()
