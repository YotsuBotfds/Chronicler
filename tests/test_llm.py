"""Tests for LLM client protocol and implementations."""
import pytest
from unittest.mock import MagicMock
from chronicler.llm import (
    LLMClient,
    LocalClient,
    LocalNarrativeClient,
    AnthropicClient,
    GeminiClient,
    create_clients,
)


class TestLLMClientProtocol:
    def test_local_client_conforms_to_protocol(self):
        client = LocalClient(base_url="http://localhost:1234/v1", model="test-model")
        assert hasattr(client, "complete")
        assert hasattr(client, "model")

    def test_local_narrative_client_conforms_to_protocol(self):
        client = LocalNarrativeClient(base_url="http://localhost:1234/v1", model="test-model")
        assert hasattr(client, "complete")
        assert hasattr(client, "model")

    def test_anthropic_client_conforms_to_protocol(self):
        mock_sdk = MagicMock()
        client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")
        assert hasattr(client, "complete")
        assert hasattr(client, "model")

    def test_gemini_client_conforms_to_protocol(self):
        mock_sdk = MagicMock()
        client = GeminiClient(client=mock_sdk, model="gemini-2.5-pro")
        assert hasattr(client, "complete")
        assert hasattr(client, "model")


class TestLocalClient:
    def test_complete_calls_openai_api(self):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="DEVELOP"))]
        )
        client = LocalClient(base_url="http://localhost:1234/v1", model="test-model")
        client._client = mock_openai  # Inject mock

        result = client.complete("Pick an action", max_tokens=10)
        assert result == "DEVELOP"
        mock_openai.chat.completions.create.assert_called_once()

    def test_complete_with_system_prompt(self):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="WAR"))]
        )
        client = LocalClient(base_url="http://localhost:1234/v1", model="test-model")
        client._client = mock_openai

        result = client.complete("Pick an action", max_tokens=10, system="You are a warlord.")
        assert result == "WAR"
        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"

    def test_respects_temperature(self):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="DEVELOP"))]
        )
        client = LocalClient(base_url="http://localhost:1234/v1", model="test", temperature=0.3)
        client._client = mock_openai

        client.complete("test")
        call_args = mock_openai.chat.completions.create.call_args
        assert call_args.kwargs["temperature"] == 0.3


class TestLocalNarrativeClient:
    def test_default_max_tokens_is_1500(self):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="The empire rose..."))]
        )
        client = LocalNarrativeClient(base_url="http://localhost:1234/v1", model="test")
        client._client = mock_openai

        client.complete("Write prose")
        call_args = mock_openai.chat.completions.create.call_args
        assert call_args.kwargs["max_tokens"] == 1500

    def test_default_temperature_is_0_8(self):
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="The empire rose..."))]
        )
        client = LocalNarrativeClient(base_url="http://localhost:1234/v1", model="test")
        client._client = mock_openai

        client.complete("Write prose")
        call_args = mock_openai.chat.completions.create.call_args
        assert call_args.kwargs["temperature"] == 0.8


class TestAnthropicClient:
    def test_complete_calls_anthropic_api(self):
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = MagicMock(
            content=[MagicMock(text="The empire rose from the ashes...")],
            usage=MagicMock(input_tokens=0, output_tokens=0),
        )
        client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")

        result = client.complete("Write a chronicle entry", max_tokens=500)
        assert "empire" in result
        mock_sdk.messages.create.assert_called_once()

    def test_token_tracking_accumulators(self):
        """AnthropicClient tracks input/output tokens and call count."""
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = MagicMock(
            content=[MagicMock(text="The empire rose...")],
            usage=MagicMock(input_tokens=150, output_tokens=80),
        )
        client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")

        assert client.total_input_tokens == 0
        assert client.total_output_tokens == 0
        assert client.call_count == 0

        client.complete("Write a chronicle entry", max_tokens=500)

        assert client.total_input_tokens == 150
        assert client.total_output_tokens == 80
        assert client.call_count == 1

    def test_token_tracking_accumulates_across_calls(self):
        """Token counts accumulate across multiple API calls."""
        mock_sdk = MagicMock()
        mock_sdk.messages.create.side_effect = [
            MagicMock(
                content=[MagicMock(text="First entry...")],
                usage=MagicMock(input_tokens=100, output_tokens=50),
            ),
            MagicMock(
                content=[MagicMock(text="Second entry...")],
                usage=MagicMock(input_tokens=200, output_tokens=100),
            ),
        ]
        client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")

        client.complete("First")
        client.complete("Second")

        assert client.total_input_tokens == 300
        assert client.total_output_tokens == 150
        assert client.call_count == 2

    def test_complete_retries_transient_failures(self):
        class RateLimitError(Exception):
            status_code = 429

        mock_sdk = MagicMock()
        mock_sdk.messages.create.side_effect = [
            RateLimitError("rate limit"),
            MagicMock(
                content=[MagicMock(text="Recovered response")],
                usage=MagicMock(input_tokens=10, output_tokens=5),
            ),
        ]
        client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")

        import unittest.mock as mock
        with mock.patch("time.sleep") as mock_sleep:
            result = client.complete("Retry me", max_tokens=100)

        assert result == "Recovered response"
        assert mock_sdk.messages.create.call_count == 2
        mock_sleep.assert_called_once()

    def test_complete_rejects_empty_content(self):
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = MagicMock(
            content=[],
            usage=MagicMock(input_tokens=0, output_tokens=0),
        )
        client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")

        with pytest.raises(ValueError, match="no content"):
            client.complete("Write a chronicle entry", max_tokens=500)

    def test_batch_complete_treats_empty_content_as_missing_result(self):
        mock_sdk = MagicMock()
        mock_sdk.messages.batches.create.return_value = MagicMock(
            id="batch-1",
            processing_status="ended",
        )
        mock_sdk.messages.batches.results.return_value = [
            MagicMock(
                custom_id="moment-0",
                result=MagicMock(
                    type="succeeded",
                    message=MagicMock(
                        content=[],
                        usage=MagicMock(input_tokens=3, output_tokens=2),
                    ),
                ),
            )
        ]
        client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")

        result = client.batch_complete([{"prompt": "One", "max_tokens": 50}], poll_interval=0)

        assert result == [None]


class TestGeminiClient:
    def _make_mock_response(self, text="The empire rose...", prompt_tokens=150, candidates_tokens=80):
        return MagicMock(
            text=f"  {text}  ",  # whitespace to verify strip()
            usage_metadata=MagicMock(
                prompt_token_count=prompt_tokens,
                candidates_token_count=candidates_tokens,
            ),
        )

    def test_complete_calls_gemini_api(self):
        mock_sdk = MagicMock()
        mock_sdk.models.generate_content.return_value = self._make_mock_response()
        client = GeminiClient(client=mock_sdk, model="gemini-2.5-pro")

        result = client.complete("Write a chronicle entry", max_tokens=500)
        assert "empire" in result
        mock_sdk.models.generate_content.assert_called_once()

    def test_complete_with_system_prompt(self):
        mock_sdk = MagicMock()
        mock_sdk.models.generate_content.return_value = self._make_mock_response()
        client = GeminiClient(client=mock_sdk, model="gemini-2.5-pro")

        client.complete("Write prose", system="You are a historian.")
        call_args = mock_sdk.models.generate_content.call_args
        assert call_args.kwargs["config"]["system_instruction"] == "You are a historian."

    def test_token_tracking_accumulators(self):
        mock_sdk = MagicMock()
        mock_sdk.models.generate_content.return_value = self._make_mock_response(
            prompt_tokens=150, candidates_tokens=80
        )
        client = GeminiClient(client=mock_sdk, model="gemini-2.5-pro")

        assert client.total_input_tokens == 0
        assert client.total_output_tokens == 0
        assert client.call_count == 0

        client.complete("Write a chronicle entry", max_tokens=500)

        assert client.total_input_tokens == 150
        assert client.total_output_tokens == 80
        assert client.call_count == 1

    def test_token_tracking_accumulates_across_calls(self):
        mock_sdk = MagicMock()
        mock_sdk.models.generate_content.side_effect = [
            self._make_mock_response(text="First", prompt_tokens=100, candidates_tokens=50),
            self._make_mock_response(text="Second", prompt_tokens=200, candidates_tokens=100),
        ]
        client = GeminiClient(client=mock_sdk, model="gemini-2.5-pro")
        client._rate_limit_delay = 0  # skip sleep in tests

        client.complete("First")
        client.complete("Second")

        assert client.total_input_tokens == 300
        assert client.total_output_tokens == 150
        assert client.call_count == 2

    def test_rate_limit_skips_first_call(self):
        """First call should not sleep, subsequent calls should."""
        import unittest.mock as mock
        mock_sdk = MagicMock()
        mock_sdk.models.generate_content.return_value = self._make_mock_response()
        client = GeminiClient(client=mock_sdk, model="gemini-2.5-pro")
        client._rate_limit_delay = 0.01

        with mock.patch("time.sleep") as mock_sleep:
            client.complete("First call")
            mock_sleep.assert_not_called()

            client.complete("Second call")
            mock_sleep.assert_called_once_with(0.01)

    def test_strips_response_whitespace(self):
        mock_sdk = MagicMock()
        mock_sdk.models.generate_content.return_value = self._make_mock_response(
            text="  The empire rose  "
        )
        client = GeminiClient(client=mock_sdk, model="gemini-2.5-pro")

        result = client.complete("Write prose")
        assert result == "The empire rose"

    def test_complete_retries_transient_failures(self):
        class ServiceUnavailable(Exception):
            status_code = 503

        mock_sdk = MagicMock()
        mock_sdk.models.generate_content.side_effect = [
            ServiceUnavailable("temporarily unavailable"),
            self._make_mock_response(text="Recovered"),
        ]
        client = GeminiClient(client=mock_sdk, model="gemini-2.5-pro")
        client._rate_limit_delay = 0

        import unittest.mock as mock
        with mock.patch("time.sleep") as mock_sleep:
            result = client.complete("Retry me")

        assert result == "Recovered"
        assert mock_sdk.models.generate_content.call_count == 2
        mock_sleep.assert_called_once()


class TestCreateClients:
    def test_local_only_default(self):
        """Default mode: both clients are local."""
        sim_client, narrative_client = create_clients()
        assert isinstance(sim_client, LocalClient)
        assert isinstance(narrative_client, LocalNarrativeClient)

    def test_sim_client_low_temperature(self):
        """Sim client should use low temperature for deterministic action selection."""
        sim_client, _ = create_clients()
        assert sim_client.temperature == 0.3

    def test_narrative_client_high_temperature(self):
        """Narrative client should use high temperature for creative prose."""
        _, narrative_client = create_clients()
        assert narrative_client.temperature == 0.8

    def test_custom_model_names(self):
        sim_client, narrative_client = create_clients(
            sim_model="qwen2.5-7b",
            narrative_model="qwen3-30b",
        )
        assert sim_client.model == "qwen2.5-7b"
        assert narrative_client.model == "qwen3-30b"

    def test_default_model_is_empty_string(self):
        """When no model specified, use empty string (LM Studio uses loaded model)."""
        sim_client, narrative_client = create_clients()
        assert sim_client.model == ""
        assert narrative_client.model == ""

    def test_narrator_api_returns_anthropic_client(self):
        """When narrator='api', narrative client is AnthropicClient."""
        import unittest.mock as mock
        mock_anthropic_module = MagicMock()
        mock_anthropic_instance = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_anthropic_instance
        mock_openai_module = MagicMock()
        mock_openai_module.OpenAI.return_value = MagicMock()

        with mock.patch.dict("sys.modules", {
            "anthropic": mock_anthropic_module,
            "openai": mock_openai_module,
        }):
            _, narrative_client = create_clients(narrator="api")
            assert isinstance(narrative_client, AnthropicClient)
            assert narrative_client.model == "claude-sonnet-4-6"

    def test_narrator_api_with_custom_model(self):
        """--narrative-model flows through to AnthropicClient."""
        import unittest.mock as mock
        mock_anthropic_module = MagicMock()
        mock_anthropic_instance = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_anthropic_instance
        mock_openai_module = MagicMock()
        mock_openai_module.OpenAI.return_value = MagicMock()

        with mock.patch.dict("sys.modules", {
            "anthropic": mock_anthropic_module,
            "openai": mock_openai_module,
        }):
            _, narrative_client = create_clients(
                narrator="api", narrative_model="claude-opus-4-6"
            )
            assert narrative_client.model == "claude-opus-4-6"

    def test_narrator_local_unchanged(self):
        """narrator='local' produces same result as default."""
        import unittest.mock as mock
        mock_openai_module = MagicMock()
        mock_openai_module.OpenAI.return_value = MagicMock()

        with mock.patch.dict("sys.modules", {"openai": mock_openai_module}):
            sim, narr = create_clients(narrator="local")
            assert isinstance(narr, LocalNarrativeClient)

    def test_narrator_gemini_returns_gemini_client(self):
        """When narrator='gemini', narrative client is GeminiClient."""
        import unittest.mock as mock
        mock_genai_module = MagicMock()
        mock_google_module = MagicMock()
        mock_google_module.genai = mock_genai_module
        mock_openai_module = MagicMock()
        mock_openai_module.OpenAI.return_value = MagicMock()

        with mock.patch.dict("sys.modules", {
            "google": mock_google_module,
            "google.genai": mock_genai_module,
            "openai": mock_openai_module,
        }):
            _, narrative_client = create_clients(narrator="gemini")
            assert isinstance(narrative_client, GeminiClient)
            assert narrative_client.model == "gemini-2.5-pro"

    def test_narrator_gemini_with_custom_model(self):
        """--narrative-model flows through to GeminiClient."""
        import unittest.mock as mock
        mock_genai_module = MagicMock()
        mock_google_module = MagicMock()
        mock_google_module.genai = mock_genai_module
        mock_openai_module = MagicMock()
        mock_openai_module.OpenAI.return_value = MagicMock()

        with mock.patch.dict("sys.modules", {
            "google": mock_google_module,
            "google.genai": mock_genai_module,
            "openai": mock_openai_module,
        }):
            _, narrative_client = create_clients(
                narrator="gemini", narrative_model="gemini-2.5-flash"
            )
            assert narrative_client.model == "gemini-2.5-flash"
