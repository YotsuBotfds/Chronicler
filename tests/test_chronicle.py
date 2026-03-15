"""Tests for chronicle compilation."""
import pytest
from chronicler.chronicle import compile_chronicle
from chronicler.models import (
    ChronicleEntry, NarrativeRole, CausalLink, Event, NamedEvent,
)


def _entry(turn, narrative, covers_turns=None):
    """Helper to build a minimal ChronicleEntry for tests."""
    ct = covers_turns or (turn, turn)
    return ChronicleEntry(
        turn=turn, covers_turns=ct,
        events=[], named_events=[],
        narrative=narrative, importance=5.0,
        narrative_role=NarrativeRole.RESOLUTION,
        causal_links=[],
    )


class TestChronicleEntry:
    def test_create_entry(self):
        entry = _entry(1, "The war began.")
        assert entry.turn == 1


class TestCompileChronicle:
    def test_produces_markdown(self):
        entries = [
            _entry(1, "The empires met at the border."),
            _entry(2, "Trade agreements were forged."),
        ]
        result = compile_chronicle(
            world_name="Aetheris",
            entries=entries,
            era_reflections={},
        )
        assert "# Chronicle of Aetheris" in result
        assert "The empires met" in result

    def test_inserts_era_headers(self):
        entries = [
            _entry(i, f"Events of turn {i}.")
            for i in range(1, 21)
        ]
        era_reflections = {
            10: "## The Age of Iron\n\nA time of conflict and expansion.",
            20: "## The Age of Commerce\n\nPeace brought prosperity.",
        }
        result = compile_chronicle(
            world_name="Aetheris",
            entries=entries,
            era_reflections=era_reflections,
        )
        assert "Age of Iron" in result
        assert "Age of Commerce" in result

    def test_empty_chronicle(self):
        result = compile_chronicle(world_name="Aetheris", entries=[], era_reflections={})
        assert "Chronicle of Aetheris" in result

    def test_includes_world_summary_at_end(self):
        entries = [_entry(1, "Something happened.")]
        result = compile_chronicle(
            world_name="Aetheris",
            entries=entries,
            era_reflections={},
            epilogue="And so the world turned on.",
        )
        assert "And so the world turned on." in result


class TestNewChronicleEntry:
    def test_new_chronicle_entry_creation(self):
        entry = ChronicleEntry(
            turn=50, covers_turns=(45, 55),
            events=[Event(turn=50, event_type="war", actors=["A"], description="test")],
            named_events=[], narrative="The armies clashed at dawn.",
            importance=8.5, narrative_role=NarrativeRole.CLIMAX,
            causal_links=[],
        )
        assert entry.turn == 50
        assert entry.narrative == "The armies clashed at dawn."
        assert entry.narrative_role == NarrativeRole.CLIMAX

    def test_chronicle_entry_round_trip(self):
        entry = ChronicleEntry(
            turn=50, covers_turns=(45, 55),
            events=[], named_events=[],
            narrative="test", importance=5.0,
            narrative_role=NarrativeRole.RESOLUTION,
            causal_links=[CausalLink(
                cause_turn=40, cause_event_type="drought",
                effect_turn=50, effect_event_type="famine",
                pattern="drought\u2192famine",
            )],
        )
        data = entry.model_dump()
        restored = ChronicleEntry.model_validate(data)
        assert restored == entry
        assert restored.narrative_role == NarrativeRole.RESOLUTION
