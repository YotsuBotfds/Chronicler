"""Migrated legacy narrative regressions from the retired test/ tree."""

from chronicler.models import AgentContext, Event
from chronicler.narrative import build_agent_context_block, compute_population_mood


def test_build_agent_context_block_renders_named_history_and_mood():
    ctx = AgentContext(
        named_characters=[
            {
                "name": "Kiran",
                "role": "General",
                "civ": "Aram",
                "origin_civ": "Bora",
                "status": "active",
                "recent_history": [
                    {"turn": 195, "event": "migration", "region": "Aram"},
                    {"turn": 180, "event": "rebellion", "region": "Bora"},
                ],
            },
        ],
        population_mood="desperate",
        displacement_fraction=0.15,
    )

    block = build_agent_context_block(ctx)

    assert "Kiran" in block
    assert "Population mood: desperate" in block
    assert "Displacement: 15% of population displaced" in block
    assert "rebellion in Bora (turn 180)" in block


def test_build_agent_context_block_none_is_empty():
    assert build_agent_context_block(None) == ""


def test_compute_population_mood_prefers_desperate_over_boom():
    mood = compute_population_mood(
        [
            Event(
                turn=10,
                event_type="local_rebellion",
                actors=["A"],
                description="test",
                importance=7,
                source="agent",
            ),
            Event(
                turn=10,
                event_type="economic_boom",
                actors=["A"],
                description="test",
                importance=5,
                source="agent",
            ),
        ]
    )

    assert mood == "desperate"
