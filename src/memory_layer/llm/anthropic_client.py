"""Anthropic LLM client."""

from __future__ import annotations

import json

import anthropic

from memory_layer.llm.base import BaseLLMClient, LLMResponse


class AnthropicClient(BaseLLMClient):
    provider = "anthropic"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        super().__init__(api_key, model)
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def default_model(self) -> str:
        return "claude-sonnet-4-20250514"

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        resp = await self._client.messages.create(**kwargs)
        content = resp.content[0].text if resp.content else ""
        return LLMResponse(
            content=content,
            model=resp.model,
            usage={
                "prompt_tokens": resp.usage.input_tokens,
                "completion_tokens": resp.usage.output_tokens,
            },
        )

    async def complete_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict:
        json_prompt = f"{prompt}\n\nRespond with valid JSON only, no other text."
        resp = await self.complete(json_prompt, system=system, temperature=temperature, max_tokens=max_tokens)
        text = resp.content.strip()
        # Strip markdown fences if the model wrapped its response
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        if not text:
            return {}
        return json.loads(text)
