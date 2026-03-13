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
