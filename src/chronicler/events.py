"""Event types and Epitaph-style cascading probability system.

Each event modifies the probability of future events, creating chains
of causally linked occurrences. Probabilities are clamped to [0, 1].
"""
from __future__ import annotations

import random

from chronicler.models import Event

# Events that can occur during the Environment phase (natural causes)
ENVIRONMENT_EVENTS: list[str] = ["drought", "plague", "earthquake"]

# When event X occurs, modify probabilities of other events by these deltas
EVENT_CASCADE_RULES: dict[str, dict[str, float]] = {
    "drought": {
        "plague": +0.02,        # Weakened populations get sick
        "migration": +0.04,     # People flee famine
        "rebellion": +0.03,     # Hungry people revolt
        "discovery": -0.02,     # Less resources for research
    },
    "plague": {
        "rebellion": +0.03,
        "migration": +0.03,
        "leader_death": +0.02,  # Leaders die too
        "cultural_renaissance": -0.02,
    },
    "earthquake": {
        "migration": +0.02,
        "discovery": +0.01,     # Ruins exposed, new resources found
        "border_incident": +0.02,
    },
    "religious_movement": {
        "rebellion": +0.02,
        "cultural_renaissance": +0.03,
        "border_incident": +0.01,
    },
    "discovery": {
        "cultural_renaissance": +0.03,
        "border_incident": +0.02,  # Others covet the discovery
        "rebellion": -0.01,
    },
    "leader_death": {
        "rebellion": +0.05,
        "border_incident": +0.03,  # Neighbors sense weakness
        "migration": +0.01,
    },
    "rebellion": {
        "leader_death": +0.03,
        "migration": +0.02,
        "plague": +0.01,          # War brings disease
        "border_incident": +0.02,
    },
    "migration": {
        "border_incident": +0.03,
        "cultural_renaissance": +0.01,  # New ideas arrive
        "rebellion": +0.01,
    },
    "cultural_renaissance": {
        "discovery": +0.04,
        "rebellion": -0.02,       # People are content
        "religious_movement": +0.02,
    },
    "border_incident": {
        "rebellion": +0.01,
        "migration": +0.01,
    },
}


def roll_for_event(
    probabilities: dict[str, float],
    turn: int,
    seed: int | None = None,
    allowed_types: list[str] | None = None,
) -> Event | None:
    """Roll against each event probability; return at most one event.

    Events are checked in shuffled order. The first one that triggers wins.
    This means at most one event fires per call.
    """
    rng = random.Random(seed)
    candidates = list(probabilities.keys())
    if allowed_types is not None:
        candidates = [c for c in candidates if c in allowed_types]
    rng.shuffle(candidates)

    for event_type in candidates:
        prob = probabilities.get(event_type, 0.0)
        if rng.random() < prob:
            return Event(
                turn=turn,
                event_type=event_type,
                actors=[],
                description="",  # Filled in by narrative engine
                importance=5,
            )
    return None


def apply_probability_cascade(
    event_type: str,
    probabilities: dict[str, float],
) -> dict[str, float]:
    """Apply cascading probability modifications after an event occurs."""
    rules = EVENT_CASCADE_RULES.get(event_type)
    if rules is None:
        return dict(probabilities)

    updated = dict(probabilities)
    for target, delta in rules.items():
        if target in updated:
            updated[target] = max(0.0, min(1.0, updated[target] + delta))
    return updated
