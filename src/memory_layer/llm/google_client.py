"""Google Generative AI LLM client."""

from __future__ import annotations

import json

from google import genai
from google.genai import types

from memory_layer.llm.base import BaseLLMClient, LLMResponse


class GoogleClient(BaseLLMClient):
    provider = "google"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        super().__init__(api_key, model)
        self._client = genai.Client(api_key=api_key)

    @property
    def default_model(self) -> str:
        return "gemini-2.0-flash"

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if system:
            config.system_instruction = system

        resp = await self._client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        text = resp.text or ""
        usage = {}
        if resp.usage_metadata:
            usage = {
                "prompt_tokens": resp.usage_metadata.prompt_token_count or 0,
                "completion_tokens": resp.usage_metadata.candidates_token_count or 0,
            }
        return LLMResponse(content=text, model=self.model, usage=usage)

    async def complete_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict:
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        )
        if system:
            config.system_instruction = system

        resp = await self._client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return json.loads(resp.text or "{}")
