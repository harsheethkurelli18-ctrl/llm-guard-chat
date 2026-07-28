"""
LLMClient: tries the configured cloud provider first; if it raises
(auth failure, rate limit, network error, no key configured) it
transparently falls back to a local Ollama model so the chat still
works offline / without API credits.
"""
import logging
from typing import AsyncIterator

from app.llm.providers import build_fallback_provider, build_primary_provider

logger = logging.getLogger("llm_guard_chat.client")


class LLMClient:
    def __init__(self):
        self.primary = build_primary_provider()
        self.fallback = build_fallback_provider()

    async def stream_reply(
        self, messages: list[dict], system: str
    ) -> AsyncIterator[tuple[str, str]]:
        """Yields (chunk_text, provider_name). Falls back on failure."""
        if self.primary is not None:
            try:
                async for chunk in self.primary.stream(messages, system):
                    yield chunk, self.primary.name
                return
            except Exception as exc:  # noqa: BLE001 - intentional broad catch for fallback
                logger.warning("Primary provider %s failed: %s", self.primary.name, exc)

        if self.fallback is not None:
            try:
                async for chunk in self.fallback.stream(messages, system):
                    yield chunk, self.fallback.name
                return
            except Exception as exc:  # noqa: BLE001
                logger.error("Fallback provider failed too: %s", exc)
                raise RuntimeError(
                    "Both the primary API and local fallback model are unavailable."
                ) from exc

        raise RuntimeError(
            "No LLM provider configured. Set an API key in .env or enable local fallback."
        )
