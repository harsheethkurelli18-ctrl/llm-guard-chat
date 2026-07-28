"""
Provider abstraction so the app can call Anthropic, OpenAI, or Groq
interchangeably, and fall back to a local Ollama model if every cloud
provider fails (auth error, outage, no API key configured, etc).

Each provider exposes a single async `stream(messages, system) -> AsyncIterator[str]`
so the FastAPI route doesn't need to know which backend served the request.
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Protocol

import httpx

from app.config import settings


class LLMProvider(Protocol):
    name: str

    async def stream(self, messages: list[dict], system: str) -> AsyncIterator[str]:
        ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def stream(self, messages: list[dict], system: str) -> AsyncIterator[str]:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self.api_key)
        async with client.messages.stream(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def stream(self, messages: list[dict], system: str) -> AsyncIterator[str]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        full_messages = [{"role": "system", "content": system}, *messages]
        stream = await client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class GroqProvider:
    """Groq's API is OpenAI-compatible, so we just point the OpenAI SDK
    at Groq's base URL."""
    name = "groq"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def stream(self, messages: list[dict], system: str) -> AsyncIterator[str]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key, base_url="https://api.groq.com/openai/v1")
        full_messages = [{"role": "system", "content": system}, *messages]
        stream = await client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class OllamaProvider:
    """Local fallback — no API key, no network egress required. Used when
    cloud providers are unavailable, unconfigured, or fail at runtime."""
    name = "ollama-local"

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def stream(self, messages: list[dict], system: str) -> AsyncIterator[str]:
        full_messages = [{"role": "system", "content": system}, *messages]
        payload = {"model": self.model, "messages": full_messages, "stream": True}

        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    content = data.get("message", {}).get("content")
                    if content:
                        yield content


def build_primary_provider() -> LLMProvider | None:
    provider = settings.llm_provider
    if provider == "anthropic" and settings.anthropic_api_key:
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    if provider == "openai" and settings.openai_api_key:
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    if provider == "groq" and settings.groq_api_key:
        return GroqProvider(settings.groq_api_key, settings.groq_model)
    return None


def build_fallback_provider() -> LLMProvider | None:
    if not settings.enable_local_fallback:
        return None
    return OllamaProvider(settings.ollama_base_url, settings.ollama_model)
