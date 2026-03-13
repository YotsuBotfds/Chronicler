"""LLM client protocol with swappable local/API implementations.

Hybrid inference strategy:
- LocalClient: OpenAI-compatible API (LM Studio) for high-volume simulation calls.
  Action selection, event resolution — hundreds of small calls, free.
- AnthropicClient: Claude API for quality-sensitive narrative generation.
  Chronicle prose, era reflections — fewer calls, higher quality.

Both implement the same LLMClient protocol so the rest of the codebase
is backend-agnostic.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable, Any


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM completion backends."""
    model: str

    def complete(self, prompt: str, max_tokens: int = 500, system: str | None = None) -> str:
        """Send a prompt and return the completion text."""
        ...


class LocalClient:
    """OpenAI-compatible client for local inference (LM Studio, ollama, etc.)."""

    def __init__(self, base_url: str, model: str):
        self.model = model
        self.base_url = base_url
        from openai import OpenAI
        self._client = OpenAI(base_url=base_url, api_key="not-needed")

    def complete(self, prompt: str, max_tokens: int = 500, system: str | None = None) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()


class AnthropicClient:
    """Anthropic SDK client for Claude API calls."""

    def __init__(self, client: Any, model: str = "claude-sonnet-4-6"):
        self.model = model
        self._client = client

    def complete(self, prompt: str, max_tokens: int = 500, system: str | None = None) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        return response.content[0].text.strip()


def create_clients(
    local_url: str | None,
    local_model: str | None,
    narrative_model: str,
    anthropic_client: Any,
) -> tuple[LLMClient, LLMClient]:
    """Create simulation and narrative clients based on configuration.

    If local_url is provided, simulation calls route to the local model
    and narrative calls route to Claude API (hybrid mode).
    If local_url is None, everything routes to Claude API (API-only mode).
    """
    narrative_client = AnthropicClient(client=anthropic_client, model=narrative_model)

    if local_url and local_model:
        sim_client: LLMClient = LocalClient(base_url=local_url, model=local_model)
    else:
        sim_client = AnthropicClient(
            client=anthropic_client,
            model="claude-haiku-4-5-20251001",
        )

    return sim_client, narrative_client
