"""Tests for memory streams and periodic reflections."""
import pytest
from unittest.mock import MagicMock
from chronicler.memory import (
    MemoryStream,
    MemoryEntry,
    should_reflect,
    build_reflection_prompt,
    generate_reflection,
)
from chronicler.models import Event


class TestMemoryEntry:
    def test_create_entry(self):
        entry = MemoryEntry(
            turn=5,
            text="The Kethani Empire expanded into the Thornwood.",
            importance=6,
            entry_type="event",
        )
        assert entry.turn == 5
        assert entry.importance == 6


class TestMemoryStream:
    def test_add_entry(self):
        stream = MemoryStream(civilization_name="Kethani Empire")
        stream.add("The empire traded with the republic.", turn=1, importance=3)
        assert len(stream.entries) == 1

    def test_get_recent(self):
        stream = MemoryStream(civilization_name="Kethani Empire")
        for i in range(20):
            stream.add(f"Event {i}", turn=i, importance=5)
        recent = stream.get_recent(count=5)
        assert len(recent) == 5
        assert recent[-1].text == "Event 19"

    def test_get_important(self):
        stream = MemoryStream(civilization_name="Test")
        stream.add("Minor event", turn=1, importance=2)
        stream.add("Major event", turn=2, importance=9)
        stream.add("Medium event", turn=3, importance=5)
        important = stream.get_important(min_importance=5)
        assert len(important) == 2
        assert important[0].importance >= 5

    def test_add_reflection(self):
        stream = MemoryStream(civilization_name="Test")
        stream.add_reflection("The empire entered a golden age.", turn=10)
        assert len(stream.reflections) == 1
        assert stream.reflections[0].entry_type == "reflection"

    def test_get_context_window(self):
        """Context window returns recent entries + all reflections."""
        stream = MemoryStream(civilization_name="Test")
        for i in range(30):
            stream.add(f"Event {i}", turn=i, importance=5)
        stream.add_reflection("Era of Growth", turn=10)
        context = stream.get_context_window(recent_count=5)
        # Should have 5 recent entries + 1 reflection
        assert len(context) == 6


class TestShouldReflect:
    def test_reflects_every_10_turns(self):
        assert should_reflect(turn=10, interval=10) is True
        assert should_reflect(turn=20, interval=10) is True
        assert should_reflect(turn=0, interval=10) is False

    def test_does_not_reflect_between_intervals(self):
        assert should_reflect(turn=7, interval=10) is False
        assert should_reflect(turn=15, interval=10) is False


class TestReflectionGeneration:
    def test_build_reflection_prompt_includes_memories(self):
        stream = MemoryStream(civilization_name="Kethani Empire")
        stream.add("Expanded into Thornwood", turn=1, importance=6)
        stream.add("Traded with Selurians", turn=2, importance=3)
        stream.add("Lost a border skirmish", turn=5, importance=7)
        prompt = build_reflection_prompt(stream, era_start=1, era_end=10)
        assert "Kethani Empire" in prompt
        assert "Thornwood" in prompt

    def test_generate_reflection_returns_text(self):
        mock_client = MagicMock()
        mock_client.complete.return_value = "The Age of Expansion saw the Kethani Empire grow..."
        mock_client.model = "test-model"
        stream = MemoryStream(civilization_name="Kethani Empire")
        stream.add("Expanded", turn=1, importance=6)
        text = generate_reflection(
            stream, era_start=1, era_end=10, client=mock_client
        )
        assert "Kethani" in text or "Expansion" in text or len(text) > 0


import json
from chronicler.memory import sanitize_civ_name


class TestMemoryPersistence:
    def test_round_trip_entries_and_reflections(self, tmp_path):
        """Save a MemoryStream, load it back, verify all fields match."""
        stream = MemoryStream(civilization_name="Kethani Empire")
        for i in range(10):
            stream.add(text=f"Event {i} occurred", turn=i, importance=i % 10 + 1)
        stream.add_reflection("The Age of Iron", turn=10)
        stream.add_reflection("The Age of Sorrow", turn=20)

        path = tmp_path / "memories_kethani_empire.json"
        stream.save(path)
        assert path.exists()

        loaded = MemoryStream.load(path)
        assert loaded.civilization_name == "Kethani Empire"
        assert len(loaded.entries) == 10
        assert len(loaded.reflections) == 2

        for orig, loaded_e in zip(stream.entries, loaded.entries):
            assert orig.turn == loaded_e.turn
            assert orig.text == loaded_e.text
            assert orig.importance == loaded_e.importance
            assert orig.entry_type == loaded_e.entry_type

        for orig, loaded_r in zip(stream.reflections, loaded.reflections):
            assert orig.turn == loaded_r.turn
            assert orig.text == loaded_r.text
            assert orig.importance == loaded_r.importance

    def test_round_trip_empty_stream(self, tmp_path):
        stream = MemoryStream(civilization_name="Empty Civ")
        path = tmp_path / "memories_empty_civ.json"
        stream.save(path)
        loaded = MemoryStream.load(path)
        assert loaded.civilization_name == "Empty Civ"
        assert loaded.entries == []
        assert loaded.reflections == []

    def test_save_creates_valid_json(self, tmp_path):
        stream = MemoryStream(civilization_name="Test")
        stream.add("An event", turn=1, importance=5)
        path = tmp_path / "memories_test.json"
        stream.save(path)
        data = json.loads(path.read_text())
        assert data["civilization_name"] == "Test"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["turn"] == 1


class TestSanitizeCivName:
    def test_spaces_to_underscores(self):
        assert sanitize_civ_name("Kethani Empire") == "kethani_empire"

    def test_special_characters_stripped(self):
        assert sanitize_civ_name("Dorrathi's Clans!") == "dorrathis_clans"

    def test_already_clean(self):
        assert sanitize_civ_name("rustborn") == "rustborn"


class TestMulePromotion:
    def test_get_mule_factor_active_window(self):
        """Mule boost applies during active window."""
        from chronicler.action_engine import get_mule_factor, MULE_ACTIVE_WINDOW, MULE_FADE_TURNS
        from unittest.mock import MagicMock
        gp = MagicMock()
        gp.mule = True
        gp.active = True
        gp.born_turn = 100
        gp.utility_overrides = {"WAR": 3.0}
        # Active window
        assert get_mule_factor(gp, "WAR", 110) == 3.0
        # Fade period
        factor = get_mule_factor(gp, "WAR", 100 + MULE_ACTIVE_WINDOW + 5)
        assert 1.0 < factor < 3.0
        # After fade
        assert get_mule_factor(gp, "WAR", 100 + MULE_ACTIVE_WINDOW + MULE_FADE_TURNS + 1) == 1.0

    def test_get_mule_factor_non_mule(self):
        """Non-Mule returns 1.0."""
        from chronicler.action_engine import get_mule_factor
        from unittest.mock import MagicMock
        gp = MagicMock()
        gp.mule = False
        assert get_mule_factor(gp, "WAR", 100) == 1.0

    def test_get_mule_factor_suppression_floor(self):
        """Suppression value below 0.1 returned raw; floor applied in weight loop."""
        from chronicler.action_engine import get_mule_factor
        from unittest.mock import MagicMock
        gp = MagicMock()
        gp.mule = True
        gp.active = True
        gp.born_turn = 100
        gp.utility_overrides = {"WAR": 0.05}
        # get_mule_factor returns the raw value; 0.1 floor is in the weight loop
        assert get_mule_factor(gp, "WAR", 110) == 0.05

    def test_get_mule_factor_unspecified_action(self):
        """Actions not in utility_overrides return 1.0."""
        from chronicler.action_engine import get_mule_factor
        from unittest.mock import MagicMock
        gp = MagicMock()
        gp.mule = True
        gp.active = True
        gp.born_turn = 100
        gp.utility_overrides = {"WAR": 3.0}
        assert get_mule_factor(gp, "DEVELOP", 110) == 1.0

    def test_get_mule_factor_inactive_gp(self):
        """Inactive GreatPerson returns 1.0."""
        from chronicler.action_engine import get_mule_factor
        from unittest.mock import MagicMock
        gp = MagicMock()
        gp.mule = True
        gp.active = False
        gp.born_turn = 100
        gp.utility_overrides = {"WAR": 3.0}
        assert get_mule_factor(gp, "WAR", 110) == 1.0

    def test_get_mule_factor_fade_midpoint(self):
        """At midpoint of fade, factor is halfway between base and 1.0."""
        from chronicler.action_engine import get_mule_factor, MULE_ACTIVE_WINDOW, MULE_FADE_TURNS
        from unittest.mock import MagicMock
        gp = MagicMock()
        gp.mule = True
        gp.active = True
        gp.born_turn = 0
        gp.utility_overrides = {"WAR": 3.0}
        midpoint = MULE_ACTIVE_WINDOW + MULE_FADE_TURNS // 2
        factor = get_mule_factor(gp, "WAR", midpoint)
        expected = 3.0 + (1.0 - 3.0) * ((midpoint - MULE_ACTIVE_WINDOW) / MULE_FADE_TURNS)
        assert abs(factor - expected) < 1e-9


class TestRenderMemory:
    def test_render_vivid(self):
        from chronicler.narrative import render_memory
        mem = {"event_type": 0, "source_civ": 0, "turn": 50, "intensity": -80, "decay_factor": 10}
        result = render_memory(mem, ["Kethani", "Tessaran"])
        assert result is not None
        assert "famine" in result
        assert "vivid" in result
        assert "Kethani" in result

    def test_render_fading(self):
        from chronicler.narrative import render_memory
        mem = {"event_type": 6, "source_civ": 1, "turn": 100, "intensity": 40, "decay_factor": 10}
        result = render_memory(mem, ["Kethani", "Tessaran"])
        assert result is not None
        assert "fading" in result
        assert "Tessaran" in result

    def test_render_too_weak(self):
        from chronicler.narrative import render_memory
        mem = {"event_type": 0, "source_civ": 0, "turn": 50, "intensity": -10, "decay_factor": 10}
        result = render_memory(mem, ["Kethani"])
        assert result is None

    def test_render_unknown_civ(self):
        from chronicler.narrative import render_memory
        mem = {"event_type": 1, "source_civ": 99, "turn": 30, "intensity": -70, "decay_factor": 10}
        result = render_memory(mem, ["Kethani"])
        assert result is not None
        assert "unknown" in result

    def test_render_prosperity_no_civ_substitution(self):
        """Prosperity template has no {civ} placeholder."""
        from chronicler.narrative import render_memory
        mem = {"event_type": 5, "source_civ": 0, "turn": 20, "intensity": 65, "decay_factor": 10}
        result = render_memory(mem, ["Kethani"])
        assert result is not None
        assert "prosperity" in result
        assert "vivid" in result
