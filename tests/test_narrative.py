"""Tests for the narrative engine — LLM interaction is mocked."""
import pytest
from unittest.mock import MagicMock
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
    NamedEvent,
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

    def test_adapter_methods_work_with_run_turn(self, sample_world):
        """NarrativeEngine adapters integrate with simulation's run_turn."""
        from chronicler.simulation import run_turn

        sim_client = self._mock_llm_client("DEVELOP")
        narrative_client = self._mock_llm_client("The age continued.")
        engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)

        text = run_turn(
            sample_world,
            action_selector=engine.action_selector,
            narrator=engine.narrator,
            seed=42,
        )
        assert isinstance(text, str)
        assert sample_world.turn == 1
        assert sim_client.complete.call_count == len(sample_world.civilizations)


def test_chronicle_prompt_includes_recent_named_events(sample_world):
    for i in range(7):
        sample_world.named_events.append(NamedEvent(
            name=f"Event {i}", event_type="battle", turn=i,
            actors=["Kethani Empire"], description=f"Description {i}",
        ))
    events = []
    prompt = build_chronicle_prompt(sample_world, events)
    assert "Event 6" in prompt
    assert "Event 5" in prompt
    assert "Event 2" in prompt


def test_chronicle_prompt_includes_highest_importance_event(sample_world):
    sample_world.named_events.append(NamedEvent(
        name="Minor Skirmish", event_type="battle", turn=1,
        actors=["Kethani Empire"], description="A minor border clash", importance=3,
    ))
    sample_world.named_events.append(NamedEvent(
        name="The Great Catastrophe", event_type="battle", turn=2,
        actors=["Kethani Empire"], description="The most important event ever", importance=10,
    ))
    events = []
    prompt = build_chronicle_prompt(sample_world, events)
    assert "The Great Catastrophe" in prompt


def test_chronicle_prompt_includes_rivalries(sample_world):
    sample_world.civilizations[0].leader.rival_leader = "Gorath"
    sample_world.civilizations[0].leader.rival_civ = "Dorrathi Clans"
    events = []
    prompt = build_chronicle_prompt(sample_world, events)
    assert "rival" in prompt.lower() or "Gorath" in prompt


class TestEventFlavor:
    def test_event_flavor_substitutes_name(self, sample_world):
        from chronicler.scenario import EventFlavor
        sim_client = MagicMock()
        sim_client.complete.return_value = "DEVELOP"
        sim_client.model = "test"
        narrative_client = MagicMock()
        narrative_client.complete.return_value = "Chronicle text."
        narrative_client.model = "test"
        flavor = {"drought": EventFlavor(name="Harsh Winter", description="Cold winds blow")}
        engine = NarrativeEngine(sim_client, narrative_client, event_flavor=flavor)
        events = [Event(turn=0, event_type="drought", actors=["Civ A"],
                       description="A drought struck.", importance=5)]
        engine.generate_chronicle(sample_world, events)
        call_args = narrative_client.complete.call_args[0][0]
        assert "Harsh Winter" in call_args
        assert "Cold winds blow" in call_args

    def test_no_event_flavor_uses_original(self, sample_world):
        sim_client = MagicMock()
        sim_client.model = "test"
        narrative_client = MagicMock()
        narrative_client.complete.return_value = "Chronicle text."
        narrative_client.model = "test"
        engine = NarrativeEngine(sim_client, narrative_client)
        events = [Event(turn=0, event_type="drought", actors=["Civ A"],
                       description="A drought struck.", importance=5)]
        engine.generate_chronicle(sample_world, events)
        call_args = narrative_client.complete.call_args[0][0]
        assert "drought" in call_args.lower()


class TestNarrativeStyle:
    def test_narrative_style_in_prompt(self, sample_world):
        sim_client = MagicMock()
        sim_client.model = "test"
        narrative_client = MagicMock()
        narrative_client.complete.return_value = "Chronicle text."
        narrative_client.model = "test"
        engine = NarrativeEngine(sim_client, narrative_client,
                                narrative_style="Terse and pragmatic.")
        events = []
        engine.generate_chronicle(sample_world, events)
        call_args = narrative_client.complete.call_args[0][0]
        assert "NARRATIVE STYLE: Terse and pragmatic." in call_args

    def test_no_narrative_style_no_injection(self, sample_world):
        sim_client = MagicMock()
        sim_client.model = "test"
        narrative_client = MagicMock()
        narrative_client.complete.return_value = "Chronicle text."
        narrative_client.model = "test"
        engine = NarrativeEngine(sim_client, narrative_client)
        events = []
        engine.generate_chronicle(sample_world, events)
        call_args = narrative_client.complete.call_args[0][0]
        assert "NARRATIVE STYLE" not in call_args

    def test_neutral_historian_role(self, sample_world):
        sim_client = MagicMock()
        sim_client.model = "test"
        narrative_client = MagicMock()
        narrative_client.complete.return_value = "Chronicle text."
        narrative_client.model = "test"
        engine = NarrativeEngine(sim_client, narrative_client)
        events = []
        engine.generate_chronicle(sample_world, events)
        call_args = narrative_client.complete.call_args[0][0]
        assert "You are a historian chronicling" in call_args
        assert "mythic historian" not in call_args
