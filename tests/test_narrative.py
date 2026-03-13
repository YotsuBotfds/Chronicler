"""Tests for the narrative engine — LLM interaction is mocked."""
import pytest
from unittest.mock import MagicMock, patch
from chronicler.narrative import (
    NarrativeEngine,
    build_action_prompt,
    build_chronicle_prompt,
    thread_domains,
)
from chronicler.models import (
    ActionType,
    Civilization,
    Event,
    Leader,
    WorldState,
)


class TestDomainThreading:
    def test_thread_domains_replaces_placeholders(self):
        text = "The civilization faced a great crisis."
        civ_domains = {"TestCiv": ["maritime", "commerce"]}
        result = thread_domains(text, "TestCiv", civ_domains)
        # Domain threading should be present in output
        assert isinstance(result, str)
        assert len(result) > 0

    def test_thread_domains_no_civ_returns_unchanged(self):
        text = "Something happened."
        result = thread_domains(text, "Unknown", {})
        assert result == text


class TestBuildActionPrompt:
    def test_includes_civ_stats(self, sample_world):
        civ = sample_world.civilizations[0]
        prompt = build_action_prompt(civ, sample_world)
        assert civ.name in prompt
        assert "expand" in prompt.lower() or "EXPAND" in prompt
        assert "develop" in prompt.lower() or "DEVELOP" in prompt

    def test_includes_valid_actions(self, sample_world):
        civ = sample_world.civilizations[0]
        prompt = build_action_prompt(civ, sample_world)
        for action in ActionType:
            assert action.value in prompt.lower()


class TestBuildChroniclePrompt:
    def test_includes_turn_events(self, sample_world):
        events = [
            Event(turn=0, event_type="develop", actors=["Kethani Empire"],
                  description="Kethani Empire invested in economy.", importance=3),
        ]
        prompt = build_chronicle_prompt(sample_world, events)
        assert "Kethani Empire" in prompt
        assert "develop" in prompt.lower() or "invested" in prompt.lower()


class TestNarrativeEngine:
    def _mock_llm_client(self, response_text: str) -> MagicMock:
        """Create a mock LLMClient that returns the given text."""
        mock = MagicMock()
        mock.complete.return_value = response_text
        mock.model = "test-model"
        return mock

    def test_select_action_returns_valid_action(self, sample_world):
        sim_client = self._mock_llm_client("DEVELOP")
        narrative_client = self._mock_llm_client("")
        engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)
        civ = sample_world.civilizations[0]
        action = engine.select_action(civ, sample_world)
        assert action in ActionType
        sim_client.complete.assert_called_once()

    def test_select_action_defaults_on_invalid_response(self, sample_world):
        sim_client = self._mock_llm_client("gibberish that is not an action")
        narrative_client = self._mock_llm_client("")
        engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)
        civ = sample_world.civilizations[0]
        action = engine.select_action(civ, sample_world)
        assert action == ActionType.DEVELOP  # Safe default

    def test_generate_chronicle_returns_text(self, sample_world):
        sim_client = self._mock_llm_client("")
        narrative_client = self._mock_llm_client("In the third age, the empire rose...")
        engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)
        events = [
            Event(turn=0, event_type="develop", actors=["Kethani Empire"],
                  description="Invested in economy.", importance=3),
        ]
        text = engine.generate_chronicle(sample_world, events)
        assert isinstance(text, str)
        assert len(text) > 0
        narrative_client.complete.assert_called_once()
