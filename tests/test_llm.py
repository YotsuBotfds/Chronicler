"""Tests for LLM client protocol and implementations."""
import pytest
from unittest.mock import MagicMock
from chronicler.llm import (
    LLMClient,
    LocalClient,
    LocalNarrativeClient,
    AnthropicClient,
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
            content=[MagicMock(text="The empire rose from the ashes...")]
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
