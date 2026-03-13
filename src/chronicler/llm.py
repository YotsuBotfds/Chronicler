"""LLM client protocol with swappable local/API implementations.

Default mode: local-only via LM Studio's OpenAI-compatible endpoint.
Both sim and narrative clients route to local models — zero API cost.

The LLMClient protocol is preserved so API support (AnthropicClient)
can be re-added as an optional mode via `pip install chronicler[api]`.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable, Any

DEFAULT_LOCAL_URL = "http://localhost:1234/v1"


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM completion backends."""
    model: str

    def complete(self, prompt: str, max_tokens: int = 500, system: str | None = None) -> str:
        """Send a prompt and return the completion text."""
        ...


class LocalClient:
    """OpenAI-compatible client for local inference (LM Studio, ollama, etc.)."""

    def __init__(self, base_url: str, model: str, temperature: float = 0.7):
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
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
            temperature=self.temperature,
        )
        return response.choices[0].message.content.strip()


class LocalNarrativeClient(LocalClient):
    """Local client tuned for narrative generation — higher temperature and token limit."""

    def __init__(self, base_url: str, model: str, temperature: float = 0.8):
        super().__init__(base_url=base_url, model=model, temperature=temperature)

    def complete(self, prompt: str, max_tokens: int = 1500, system: str | None = None) -> str:
        return super().complete(prompt, max_tokens=max_tokens, system=system)


class AnthropicClient:
    """Anthropic SDK client for Claude API calls.

    Optional — requires `pip install chronicler[api]`.
    """

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
    local_url: str = DEFAULT_LOCAL_URL,
    sim_model: str | None = None,
    narrative_model: str | None = None,
) -> tuple[LLMClient, LLMClient]:
    """Create simulation and narrative clients. Defaults to local-only mode.

    Both clients route to LM Studio. sim_client uses low temperature (0.3)
    for deterministic action selection; narrative_client uses high temperature
    (0.8) and higher max_tokens for creative prose.

    If sim_model or narrative_model is None, LM Studio will use whatever
    model is currently loaded (pass model="" for this behavior).
    """
    sim_client: LLMClient = LocalClient(
        base_url=local_url,
        model=sim_model or "",
        temperature=0.3,
    )
    narrative_client: LLMClient = LocalNarrativeClient(
        base_url=local_url,
        model=narrative_model or "",
        temperature=0.8,
    )

    return sim_client, narrative_client
