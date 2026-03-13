"""Tests for chronicle compilation."""
import pytest
from chronicler.chronicle import compile_chronicle, ChronicleEntry


class TestChronicleEntry:
    def test_create_entry(self):
        entry = ChronicleEntry(turn=1, text="The war began.", era=None)
        assert entry.turn == 1


class TestCompileChronicle:
    def test_produces_markdown(self):
        entries = [
            ChronicleEntry(turn=1, text="The empires met at the border."),
            ChronicleEntry(turn=2, text="Trade agreements were forged."),
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
            ChronicleEntry(turn=i, text=f"Events of turn {i}.")
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
        entries = [ChronicleEntry(turn=1, text="Something happened.")]
        result = compile_chronicle(
            world_name="Aetheris",
            entries=entries,
            era_reflections={},
            epilogue="And so the world turned on.",
        )
        assert "And so the world turned on." in result
