"""Tests for LLM client protocol and implementations."""
import pytest
from unittest.mock import MagicMock, patch
from chronicler.llm import LLMClient, LocalClient, AnthropicClient, create_clients


class TestLLMClientProtocol:
    def test_local_client_conforms_to_protocol(self):
        client = LocalClient(base_url="http://localhost:1234/v1", model="test-model")
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
    def test_creates_both_clients(self):
        mock_anthropic_sdk = MagicMock()
        sim_client, narrative_client = create_clients(
            local_url="http://localhost:1234/v1",
            local_model="gemma-3",
            narrative_model="claude-sonnet-4-6",
            anthropic_client=mock_anthropic_sdk,
        )
        assert isinstance(sim_client, LocalClient)
        assert isinstance(narrative_client, AnthropicClient)

    def test_api_only_mode(self):
        """When no local URL provided, both clients use Anthropic."""
        mock_anthropic_sdk = MagicMock()
        sim_client, narrative_client = create_clients(
            local_url=None,
            local_model=None,
            narrative_model="claude-sonnet-4-6",
            anthropic_client=mock_anthropic_sdk,
        )
        assert isinstance(sim_client, AnthropicClient)
        assert isinstance(narrative_client, AnthropicClient)
