"""Tests for the narrative engine — LLM interaction is mocked."""
import pytest
from unittest.mock import MagicMock
from chronicler.narrative import (
    NarrativeEngine,
    build_chronicle_prompt,
    thread_domains,
)
from chronicler.models import (
    Event,
    NamedEvent,
)


class TestDomainThreading:
    def test_thread_domains_preserves_text_with_known_domains(self):
        text = "The civilization faced a great crisis."
        civ_domains = {"TestCiv": ["maritime", "commerce"]}
        result = thread_domains(text, "TestCiv", civ_domains)
        assert result == text

    def test_thread_domains_no_civ_returns_unchanged(self):
        text = "Something happened."
        result = thread_domains(text, "Unknown", {})
        assert result == text


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
        from chronicler.action_engine import ActionEngine
        from chronicler.simulation import run_turn

        sim_client = self._mock_llm_client("")
        narrative_client = self._mock_llm_client("The age continued.")
        engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)
        action_engine = ActionEngine(sample_world)

        text = run_turn(
            sample_world,
            action_selector=lambda civ, world, _engine=action_engine: _engine.select_action(civ, seed=world.seed),
            narrator=engine.narrator,
            seed=42,
        )
        assert isinstance(text, str)
        assert sample_world.turn == 1
        assert narrative_client.complete.call_count == 1


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
        # Iron-era civs get the archaic chronicler voice
        assert "You chronicle the world of" in call_args
        assert "archaic chronicler" in call_args


import logging


def test_narrate_batch_warns_on_first_failure(caplog):
    """narrate_batch logs a warning on the first LLM failure."""
    from unittest.mock import MagicMock
    from chronicler.narrative import NarrativeEngine
    from chronicler.models import NarrativeMoment, NarrativeRole, Event, TurnSnapshot

    mock_client = MagicMock()
    mock_client.complete.side_effect = Exception("API error")
    mock_client.model = "test"

    engine = NarrativeEngine(
        sim_client=MagicMock(model="test"),
        narrative_client=mock_client,
    )

    moment = NarrativeMoment(
        events=[Event(
            event_type="war", description="A war happened",
            actors=["Civ1"], importance=7, turn=10, source="simulation",
        )],
        named_events=[],
        turn_range=(10, 10),
        anchor_turn=10,
        score=7.0,
        narrative_role=NarrativeRole.CLIMAX,
        causal_links=[],
        bonus_applied=0.0,
    )
    history = [TurnSnapshot(turn=10, civ_stats={}, region_control={}, relationships={})]

    with caplog.at_level(logging.WARNING):
        entries = engine.narrate_batch([moment], history)

    assert len(entries) == 1
    assert "API error" in caplog.text or "narration failed" in caplog.text.lower()


def test_narrate_batch_does_not_mutate_live_arc_summary(sample_world):
    """Narration must not write LLM-generated summaries back onto live GP objects."""
    from chronicler.models import GreatPerson, NarrativeMoment, NarrativeRole, TurnSnapshot

    gp = GreatPerson(
        name="Kiran",
        role="general",
        trait="bold",
        civilization="Kethani Empire",
        origin_civilization="Kethani Empire",
        born_turn=5,
        source="agent",
        agent_id=42,
        arc_summary="Earlier deeds remained in memory.",
    )

    mock_client = MagicMock()
    mock_client.complete.side_effect = [
        "Kiran led the armies through the mountain pass.",
        "Kiran: Led the armies through the mountain pass.",
    ]
    mock_client.model = "test"

    engine = NarrativeEngine(
        sim_client=MagicMock(model="test"),
        narrative_client=mock_client,
    )
    engine._is_api_client = lambda: True

    moment = NarrativeMoment(
        events=[Event(
            event_type="campaign",
            description="Kiran led the armies through the mountain pass.",
            actors=["Kiran", "Kethani Empire"],
            importance=8,
            turn=10,
            source="agent",
        )],
        named_events=[],
        turn_range=(10, 10),
        anchor_turn=10,
        score=8.0,
        narrative_role=NarrativeRole.CLIMAX,
        causal_links=[],
        bonus_applied=0.0,
    )
    history = [TurnSnapshot(turn=10, civ_stats={}, region_control={}, relationships={})]

    entries = engine.narrate_batch(
        [moment],
        history,
        great_persons=[gp],
        gp_by_name={"Kiran": gp},
        world=sample_world,
    )

    assert len(entries) == 1
    assert gp.arc_summary == "Earlier deeds remained in memory."
    assert mock_client.complete.call_count == 1


def test_agent_context_has_urban_fields():
    """AgentContext includes urbanization fields when populated."""
    from chronicler.models import AgentContext, SettlementSummary
    ctx = AgentContext(
        urban_fraction_delta_20t=0.05,
        top_settlements=[
            SettlementSummary(
                settlement_id=1,
                name="Ur",
                region_name="Lower Mesopotamia",
                population_estimate=500,
                centroid_x=0.4,
                centroid_y=0.6,
                founding_turn=12,
                status="active",
            )
        ],
    )
    assert ctx.urban_fraction_delta_20t == 0.05
    assert len(ctx.top_settlements) == 1


def test_agent_context_block_renders_urban_context():
    """Agent context block should include urban trend and top settlements."""
    from chronicler.models import AgentContext, SettlementSummary
    from chronicler.narrative import build_agent_context_block

    ctx = AgentContext(
        urban_fraction_delta_20t=0.123,
        top_settlements=[
            SettlementSummary(
                settlement_id=1,
                name="Ur",
                region_name="Lower Mesopotamia",
                population_estimate=500,
                centroid_x=0.4,
                centroid_y=0.6,
                founding_turn=12,
                status="active",
            )
        ],
    )
    block = build_agent_context_block(ctx)
    assert "Urbanization trend (20 turns): +12.3pp" in block
    assert "Largest settlements:" in block
    assert "Ur (Lower Mesopotamia, pop ~500)" in block


def test_agent_context_includes_relationships():
    from chronicler.narrative import build_agent_context_for_moment
    from chronicler.models import NarrativeMoment, Event, GreatPerson, NarrativeRole

    moment = NarrativeMoment(
        anchor_turn=100,
        turn_range=(95, 105),
        events=[Event(turn=100, event_type="rebellion", actors=["Civ1"],
                      description="Rebellion", importance=7, source="agent")],
        named_events=[],
        score=10.0,
        causal_links=[],
        narrative_role=NarrativeRole.CLIMAX,
        bonus_applied=0.0,
    )

    gp1 = GreatPerson(name="Mentor", role="general", trait="bold",
                      civilization="Civ1", origin_civilization="Civ1",
                      born_turn=0, source="agent", agent_id=100)
    gp2 = GreatPerson(name="Apprentice", role="general", trait="cautious",
                      civilization="Civ1", origin_civilization="Civ1",
                      born_turn=50, source="agent", agent_id=200)

    social_edges = [(100, 200, 0, 50)]  # REL_MENTOR
    agent_name_map = {100: "Mentor", 200: "Apprentice"}

    ctx = build_agent_context_for_moment(
        moment, [gp1, gp2], {},
        social_edges=social_edges,
        agent_name_map=agent_name_map,
    )
    assert ctx is not None
    assert len(ctx.relationships) >= 1
    assert ctx.relationships[0]["type"] == "mentor"


def test_agent_context_recent_history_omits_fake_turn_zero():
    from chronicler.narrative import build_agent_context_for_moment, build_agent_context_block
    from chronicler.models import NarrativeMoment, Event, GreatPerson, NarrativeRole

    moment = NarrativeMoment(
        anchor_turn=25,
        turn_range=(25, 25),
        events=[Event(
            turn=25,
            event_type="campaign",
            actors=["Kiran"],
            description="Kiran campaigns abroad.",
            importance=7,
            source="agent",
        )],
        named_events=[],
        score=8.0,
        causal_links=[],
        narrative_role=NarrativeRole.CLIMAX,
        bonus_applied=0.0,
    )
    gp = GreatPerson(
        name="Kiran",
        role="general",
        trait="bold",
        civilization="Civ1",
        origin_civilization="Civ1",
        born_turn=5,
        source="agent",
        agent_id=42,
        deeds=["Promoted as General in Iron Peaks"],
    )

    ctx = build_agent_context_for_moment(moment, [gp], {})

    assert ctx is not None
    block = build_agent_context_block(ctx)
    assert "turn 0" not in block
    assert "Promoted as General in Iron Peaks" in block


def test_agent_context_marks_retired_characters_as_retired():
    from chronicler.narrative import build_agent_context_for_moment
    from chronicler.models import NarrativeMoment, Event, GreatPerson, NarrativeRole

    moment = NarrativeMoment(
        anchor_turn=30,
        turn_range=(30, 30),
        events=[Event(
            turn=30,
            event_type="great_person_retired",
            actors=["Old Sage", "Civ1"],
            description="Old Sage retires after long service.",
            importance=6,
            source="agent",
        )],
        named_events=[],
        score=7.0,
        causal_links=[],
        narrative_role=NarrativeRole.RESOLUTION,
        bonus_applied=0.0,
    )
    gp = GreatPerson(
        name="Old Sage",
        role="scientist",
        trait="visionary",
        civilization="Civ1",
        origin_civilization="Civ1",
        born_turn=2,
        source="agent",
        agent_id=7,
        active=False,
        alive=False,
        fate="retired",
        death_turn=30,
    )

    ctx = build_agent_context_for_moment(moment, [gp], {})

    assert ctx is not None
    assert ctx.named_characters[0]["status"] == "retired"


def test_prepare_narration_prompts_threads_focal_civ_gini(sample_world):
    from chronicler.models import CivSnapshot, GreatPerson, NarrativeMoment, NarrativeRole, TurnSnapshot

    civ_name = sample_world.civilizations[0].name
    moment = NarrativeMoment(
        anchor_turn=10,
        turn_range=(10, 10),
        events=[Event(
            turn=10,
            event_type="campaign",
            actors=[civ_name],
            description="A campaign unfolds",
            importance=7,
            source="agent",
        )],
        named_events=[],
        score=8.0,
        causal_links=[],
        narrative_role=NarrativeRole.CLIMAX,
        bonus_applied=0.0,
    )
    history = [TurnSnapshot(
        turn=10,
        civ_stats={
            civ_name: CivSnapshot(
                population=50, military=30, economy=40, culture=35,
                stability=55, treasury=20, asabiya=0.5, tech_era="iron",
                trait="bold", regions=list(sample_world.civilizations[0].regions),
                leader_name=sample_world.civilizations[0].leader.name, alive=True,
            )
        },
        region_control={},
        relationships={},
    )]
    gp = GreatPerson(
        name="Kiran",
        role="general",
        trait="bold",
        civilization=civ_name,
        origin_civilization=civ_name,
        born_turn=5,
        source="agent",
        agent_id=42,
    )

    engine = NarrativeEngine(
        sim_client=MagicMock(model="test"),
        narrative_client=MagicMock(model="test"),
    )
    engine._world = sample_world

    prepared = engine._prepare_narration_prompts(
        [moment],
        history,
        great_persons=[gp],
        gini_by_civ={0: 0.37},
    )

    assert prepared[0]["agent_ctx"] is not None
    assert prepared[0]["agent_ctx"].gini_coefficient == pytest.approx(0.37)
