"""LLM client protocol with swappable local/API implementations.

Default mode: local-only via LM Studio's OpenAI-compatible endpoint.
Both sim and narrative clients route to local models — zero API cost.

The LLMClient protocol is preserved so API support (AnthropicClient)
can be re-added as an optional mode via `pip install chronicler[api]`.
"""
from __future__ import annotations

import numbers
import time
from typing import Protocol, runtime_checkable, Any

DEFAULT_LOCAL_URL = "http://localhost:1234/v1"
_TRANSIENT_RETRY_ATTEMPTS = 2
_TRANSIENT_RETRY_BASE_DELAY_S = 0.5
_TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
_TRANSIENT_ERROR_MARKERS = (
    "connection",
    "overloaded",
    "rate limit",
    "reset by peer",
    "service unavailable",
    "temporar",
    "timeout",
    "timed out",
    "try again",
    "unavailable",
)


def _coerce_token_count(value: Any) -> int:
    """Return an integer token count, treating absent/mock values as zero."""
    if isinstance(value, numbers.Real):
        return int(value)
    return 0


def _extract_status_code(exc: Exception) -> int | None:
    """Read a best-effort HTTP-ish status code from SDK exceptions."""
    for candidate in (
        getattr(exc, "status_code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
    ):
        if isinstance(candidate, numbers.Real):
            return int(candidate)
    return None


def _is_transient_llm_error(exc: Exception) -> bool:
    """Heuristic retry gate for network/rate-limit/server-side failures."""
    status_code = _extract_status_code(exc)
    if status_code in _TRANSIENT_STATUS_CODES:
        return True
    exc_text = f"{exc.__class__.__name__} {exc}".lower()
    return any(marker in exc_text for marker in _TRANSIENT_ERROR_MARKERS)


def _call_with_transient_retry(fn, *, sleep=None):
    """Retry transient LLM/API failures with short exponential backoff."""
    sleep_fn = time.sleep if sleep is None else sleep
    for attempt in range(_TRANSIENT_RETRY_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            if not _is_transient_llm_error(exc) or attempt >= _TRANSIENT_RETRY_ATTEMPTS:
                raise
            sleep_fn(_TRANSIENT_RETRY_BASE_DELAY_S * (2 ** attempt))


def _extract_anthropic_text(content: Any) -> str:
    """Return the first non-empty text block from an Anthropic response."""
    if not content:
        raise ValueError("Anthropic response contained no content blocks")
    for block in content:
        text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
    raise ValueError("Anthropic response contained no text content")


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
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.call_count: int = 0

    def complete(self, prompt: str, max_tokens: int = 500, system: str | None = None) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = _call_with_transient_retry(
            lambda: self._client.messages.create(**kwargs)
        )
        usage = getattr(response, "usage", None)
        self.total_input_tokens += _coerce_token_count(getattr(usage, "input_tokens", 0))
        self.total_output_tokens += _coerce_token_count(getattr(usage, "output_tokens", 0))
        self.call_count += 1
        return _extract_anthropic_text(getattr(response, "content", None))

    def batch_complete(
        self,
        requests: list[dict[str, Any]],
        poll_interval: float = 10.0,
    ) -> list[str | None]:
        """Submit requests via Anthropic Message Batches API (50% cheaper).

        Each request dict has keys: prompt, max_tokens, system (optional).
        Returns list of response texts in the same order, None for failures.
        """
        batch_requests = []
        for i, req in enumerate(requests):
            params: dict[str, Any] = {
                "model": self.model,
                "max_tokens": req.get("max_tokens", 500),
                "messages": [{"role": "user", "content": req["prompt"]}],
            }
            if req.get("system"):
                params["system"] = req["system"]
            batch_requests.append({
                "custom_id": f"moment-{i}",
                "params": params,
            })

        batch = _call_with_transient_retry(
            lambda: self._client.messages.batches.create(requests=batch_requests)
        )
        print(f"  Batch submitted: {batch.id} ({len(batch_requests)} requests)")

        # Poll until complete (terminal statuses: ended, expired, canceled)
        while batch.processing_status not in ("ended", "expired", "canceled"):
            time.sleep(poll_interval)
            batch = _call_with_transient_retry(
                lambda: self._client.messages.batches.retrieve(batch.id)
            )
            succeeded = batch.request_counts.succeeded
            total = len(batch_requests)
            print(f"  Batch progress: {succeeded}/{total} complete")

        # Handle expired/canceled batches — return None for all requests
        if batch.processing_status in ("expired", "canceled"):
            print(f"  Batch {batch.processing_status}: {batch.id}")
            return [None] * len(requests)

        # Collect results in order
        results: dict[str, str | None] = {}
        batch_results = _call_with_transient_retry(
            lambda: list(self._client.messages.batches.results(batch.id))
        )
        for result in batch_results:
            custom_id = result.custom_id
            if result.result.type == "succeeded":
                msg = result.result.message
                usage = getattr(msg, "usage", None)
                self.total_input_tokens += _coerce_token_count(getattr(usage, "input_tokens", 0))
                self.total_output_tokens += _coerce_token_count(getattr(usage, "output_tokens", 0))
                self.call_count += 1
                try:
                    results[custom_id] = _extract_anthropic_text(getattr(msg, "content", None))
                except ValueError:
                    results[custom_id] = None
            else:
                results[custom_id] = None

        return [results.get(f"moment-{i}") for i in range(len(requests))]


class GeminiClient:
    """Google Gemini SDK client for Gemini API calls.

    Optional — requires `pip install -e ".[gemini]"` or `pip install google-genai`.
    """

    def __init__(self, client: Any, model: str = "gemini-2.5-pro"):
        self.model = model
        self._client = client
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.call_count: int = 0
        self._rate_limit_delay: float = 12.0  # 5 RPM free tier

    def complete(self, prompt: str, max_tokens: int = 500, system: str | None = None) -> str:
        import time

        # Blocking sleep is safe here: narration is sequential, post-simulation.
        if self.call_count > 0:
            time.sleep(self._rate_limit_delay)

        # Thinking models (2.5-flash/pro) use output budget for both thinking
        # and visible text. Scale up so the visible response isn't truncated.
        config: dict[str, Any] = {"max_output_tokens": max_tokens * 4}
        if system:
            config["system_instruction"] = system

        response = _call_with_transient_retry(
            lambda: self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        )
        usage = response.usage_metadata
        prompt_tokens = _coerce_token_count(getattr(usage, "prompt_token_count", 0))
        candidate_tokens = _coerce_token_count(getattr(usage, "candidates_token_count", 0))
        thought_tokens = _coerce_token_count(getattr(usage, "thoughts_token_count", 0))
        self.total_input_tokens += prompt_tokens
        # Thinking models (2.5-flash/pro) split output into candidates + thoughts
        self.total_output_tokens += candidate_tokens + thought_tokens
        self.call_count += 1
        return response.text.strip()


def create_clients(
    local_url: str = DEFAULT_LOCAL_URL,
    sim_model: str | None = None,
    narrative_model: str | None = None,
    narrator: str = "local",
) -> tuple[LLMClient, LLMClient]:
    """Create simulation and narrative clients.

    sim_client always routes to local LM Studio (free, high volume).
    narrative_client routes to local or Anthropic API based on narrator mode.
    """
    sim_client: LLMClient = LocalClient(
        base_url=local_url,
        model=sim_model or "",
        temperature=0.3,
    )

    if narrator == "api":
        import anthropic
        narrative_client: LLMClient = AnthropicClient(
            client=anthropic.Anthropic(),
            model=narrative_model or "claude-sonnet-4-6",
        )
    elif narrator == "gemini":
        from google import genai
        narrative_client = GeminiClient(
            client=genai.Client(),
            model=narrative_model or "gemini-2.5-pro",
        )
    else:
        narrative_client = LocalNarrativeClient(
            base_url=local_url,
            model=narrative_model or "",
            temperature=0.8,
        )

    return sim_client, narrative_client
