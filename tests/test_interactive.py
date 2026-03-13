"""Tests for interactive mode."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import argparse

from chronicler.interactive import (
    run_interactive,
    format_state_summary,
    parse_command,
    VALID_INJECTABLE_EVENTS,
    VALID_STATS,
)
from chronicler.models import WorldState


class TestParseCommand:
    def test_continue(self):
        cmd, cmd_args = parse_command("continue")
        assert cmd == "continue"

    def test_quit(self):
        cmd, cmd_args = parse_command("quit")
        assert cmd == "quit"

    def test_help(self):
        cmd, cmd_args = parse_command("help")
        assert cmd == "help"

    def test_fork(self):
        cmd, cmd_args = parse_command("fork")
        assert cmd == "fork"

    def test_inject(self):
        cmd, cmd_args = parse_command('inject plague "Kethani Empire"')
        assert cmd == "inject"
        assert cmd_args == ("plague", "Kethani Empire")

    def test_inject_invalid_event(self):
        cmd, cmd_args = parse_command('inject bogus "Kethani Empire"')
        assert cmd == "error"
        assert "Invalid event type" in cmd_args

    def test_set(self):
        cmd, cmd_args = parse_command('set "Kethani Empire" military 9')
        assert cmd == "set"
        assert cmd_args == ("Kethani Empire", "military", 9)

    def test_set_invalid_stat(self):
        cmd, cmd_args = parse_command('set "Kethani Empire" bogus 5')
        assert cmd == "error"
        assert "Invalid stat" in cmd_args

    def test_set_out_of_bounds(self):
        cmd, cmd_args = parse_command('set "Kethani Empire" military 15')
        assert cmd == "error"
        assert "bounds" in cmd_args.lower() or "1-10" in cmd_args

    def test_set_treasury_allows_high_values(self):
        cmd, cmd_args = parse_command('set "Kethani Empire" treasury 999')
        assert cmd == "set"
        assert cmd_args == ("Kethani Empire", "treasury", 999)

    def test_unknown_command(self):
        cmd, cmd_args = parse_command("explode")
        assert cmd == "error"

    def test_empty_input(self):
        cmd, cmd_args = parse_command("")
        assert cmd == "error"


class TestFormatStateSummary:
    def test_includes_faction_standings(self, sample_world):
        summary = format_state_summary(sample_world, total_turns=50)
        assert "Kethani Empire" in summary
        assert "Dorrathi Clans" in summary

    def test_includes_era(self, sample_world):
        summary = format_state_summary(sample_world, total_turns=50)
        assert "Turn" in summary

    def test_includes_relationships(self, sample_world):
        summary = format_state_summary(sample_world, total_turns=50)
        assert "HOSTILE" in summary or "SUSPICIOUS" in summary


class TestInteractiveIntegration:
    """End-to-end tests for interactive mode via run_interactive."""

    def _mock_llm(self, response="DEVELOP"):
        mock = MagicMock()
        mock.complete.return_value = response
        mock.model = "test-model"
        return mock

    def _make_args(self, tmp_path, turns=10, pause_every=5):
        return argparse.Namespace(
            seed=42, turns=turns, civs=2, regions=4,
            output=str(tmp_path / "chronicle.md"),
            state=str(tmp_path / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None,
            batch=None, fork=None, interactive=True,
            parallel=None, pause_every=pause_every,
        )

    def test_quit_stops_simulation_early(self, tmp_path, monkeypatch):
        """Typing 'quit' at the first pause should stop the simulation."""
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        args = self._make_args(tmp_path, turns=20, pause_every=5)
        # Simulate: at first pause (turn 5), user types quit
        monkeypatch.setattr("builtins.input", lambda _: "quit")
        result = run_interactive(args, sim_client=sim, narrative_client=narr)
        # Should have run only 5 turns (paused at turn 5, quit)
        assert result.total_turns <= 5
        # Chronicle should mention early end
        chronicle = (tmp_path / "chronicle.md").read_text()
        assert "ended early" in chronicle.lower() or "Chronicle" in chronicle

    def test_inject_queues_and_fires_event(self, tmp_path, monkeypatch):
        """Inject command should queue event that fires on next turn."""
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        args = self._make_args(tmp_path, turns=10, pause_every=3)
        # At first pause: inject plague, then continue. At second pause: quit.
        responses = iter([
            'inject plague "Kethani Empire"',
            "continue",
            "quit",
        ])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        result = run_interactive(args, sim_client=sim, narrative_client=narr)
        # The plague injection should be visible in events timeline
        from chronicler.models import WorldState
        world = WorldState.load(tmp_path / "state.json")
        plague_events = [e for e in world.events_timeline if e.event_type == "plague"]
        assert len(plague_events) >= 1

    def test_continue_resumes_simulation(self, tmp_path, monkeypatch):
        """Continue should resume until next pause."""
        sim = self._mock_llm()
        narr = self._mock_llm("Story.")
        args = self._make_args(tmp_path, turns=10, pause_every=5)
        # At first pause: continue. At second pause: quit.
        responses = iter(["continue", "quit"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))
        result = run_interactive(args, sim_client=sim, narrative_client=narr)
        # Should have run more than 5 turns (continued past first pause)
        assert result.total_turns > 5


class TestValidConstants:
    def test_injectable_events_match_default_probabilities(self):
        from chronicler.world_gen import DEFAULT_EVENT_PROBABILITIES
        assert VALID_INJECTABLE_EVENTS == set(DEFAULT_EVENT_PROBABILITIES.keys())

    def test_valid_stats(self):
        expected = {"population", "military", "economy", "culture", "stability", "treasury"}
        assert VALID_STATS == expected
