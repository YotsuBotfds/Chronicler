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


class TestValidConstants:
    def test_injectable_events_match_default_probabilities(self):
        from chronicler.world_gen import DEFAULT_EVENT_PROBABILITIES
        assert VALID_INJECTABLE_EVENTS == set(DEFAULT_EVENT_PROBABILITIES.keys())

    def test_valid_stats(self):
        expected = {"population", "military", "economy", "culture", "stability", "treasury"}
        assert VALID_STATS == expected
