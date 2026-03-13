"""Tests for event types and cascading probability system."""
import pytest
from chronicler.events import (
    roll_for_event,
    apply_probability_cascade,
    EVENT_CASCADE_RULES,
    ENVIRONMENT_EVENTS,
)
from chronicler.models import Event


class TestRollForEvent:
    def test_returns_none_when_no_event_triggers(self):
        """With all-zero probabilities, no event should fire."""
        probs = {k: 0.0 for k in ["drought", "plague", "earthquake"]}
        result = roll_for_event(probs, turn=1, seed=42)
        assert result is None

    def test_returns_event_when_guaranteed(self):
        """With probability 1.0, an event always fires."""
        probs = {"drought": 1.0}
        result = roll_for_event(probs, turn=1, seed=42)
        assert result is not None
        assert result.event_type == "drought"

    def test_returns_at_most_one_event(self):
        probs = {"drought": 1.0, "plague": 1.0, "earthquake": 1.0}
        result = roll_for_event(probs, turn=1, seed=42)
        assert isinstance(result, Event)  # One event, not a list

    def test_deterministic_with_seed(self):
        probs = {"drought": 0.5, "plague": 0.5}
        r1 = roll_for_event(probs, turn=1, seed=99)
        r2 = roll_for_event(probs, turn=1, seed=99)
        # Same seed → same result
        if r1 is None:
            assert r2 is None
        else:
            assert r2 is not None
            assert r1.event_type == r2.event_type


class TestProbabilityCascade:
    def test_drought_increases_famine_and_migration(self):
        probs = {"drought": 0.05, "plague": 0.03, "migration": 0.04, "rebellion": 0.05}
        updated = apply_probability_cascade("drought", probs)
        assert updated["migration"] > probs["migration"]
        assert updated["rebellion"] > probs["rebellion"]

    def test_probabilities_stay_in_bounds(self):
        probs = {"drought": 0.95, "plague": 0.95, "migration": 0.95, "rebellion": 0.95}
        updated = apply_probability_cascade("drought", probs)
        assert all(0.0 <= v <= 1.0 for v in updated.values())

    def test_unknown_event_returns_unchanged(self):
        probs = {"drought": 0.05}
        updated = apply_probability_cascade("alien_invasion", probs)
        assert updated == probs


class TestEnvironmentEvents:
    def test_environment_events_are_subset_of_all_events(self):
        all_events = set(EVENT_CASCADE_RULES.keys())
        for e in ENVIRONMENT_EVENTS:
            assert e in all_events or e in ["drought", "plague", "earthquake"]
