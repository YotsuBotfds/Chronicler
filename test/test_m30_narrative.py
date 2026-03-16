"""M30 agent narrative — narrator tests."""
import sys
from unittest.mock import MagicMock

# Stub out the Rust extension so tests run without a compiled wheel
if "chronicler_agents" not in sys.modules:
    sys.modules["chronicler_agents"] = MagicMock()

from chronicler.models import AgentContext, Event


def test_agent_context_in_prompt():
    """AgentContext present → prompt includes named characters with history."""
    from chronicler.narrative import build_agent_context_block

    ctx = AgentContext(
        named_characters=[
            {
                "name": "Kiran", "role": "General", "civ": "Aram",
                "origin_civ": "Bora", "status": "active",
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
    assert "desperate" in block
    assert "15%" in block
    assert "rebellion" in block.lower() or "Bora" in block


def test_no_agent_context():
    """None → empty string."""
    from chronicler.narrative import build_agent_context_block

    assert build_agent_context_block(None) == ""


def test_mood_precedence():
    """Rebellion + boom in same moment → 'desperate' wins."""
    from chronicler.narrative import compute_population_mood

    events = [
        Event(turn=10, event_type="local_rebellion", actors=["A"],
              description="test", importance=7, source="agent"),
        Event(turn=10, event_type="economic_boom", actors=["A"],
              description="test", importance=5, source="agent"),
    ]

    mood = compute_population_mood(events)
    assert mood == "desperate"
