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
