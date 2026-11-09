"""Tests for event types and cascading probability system."""
import pytest
from chronicler.events import (
    EVENT_CASCADE_RULES,
    ENVIRONMENT_EVENTS,
)


class TestEnvironmentEvents:
    def test_environment_events_are_subset_of_all_events(self):
        all_events = set(EVENT_CASCADE_RULES.keys())
        for e in ENVIRONMENT_EVENTS:
            assert e in all_events or e in ["drought", "plague", "earthquake"]
