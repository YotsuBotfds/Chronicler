"""Migrated legacy curator regressions from the retired test/ tree."""

from chronicler.curator import compute_base_scores
from chronicler.models import Event, NamedEvent


def _event(turn: int, event_type: str, actors: list[str], importance: int) -> Event:
    return Event(
        turn=turn,
        event_type=event_type,
        actors=actors,
        description="test",
        importance=importance,
        source="agent",
    )


def test_compute_base_scores_adds_named_character_bonus_once():
    events = [
        _event(10, "local_rebellion", ["Kiran", "Vesh", "Talo"], 7),
    ]

    scores = compute_base_scores(
        events,
        [],
        dominant_power="",
        seed=42,
        named_characters={"Kiran", "Vesh", "Talo"},
    )

    assert scores[0] == 11.0


def test_compute_base_scores_rewards_named_character_reference():
    events = [
        _event(10, "local_rebellion", ["Kiran", "Aram"], 7),
        _event(10, "mass_migration", ["Aram"], 5),
    ]

    scores = compute_base_scores(
        events,
        [],
        dominant_power="Aram",
        seed=42,
        named_characters={"Kiran"},
    )

    assert scores[0] == 13.0
    assert scores[1] == 9.0


def test_compute_base_scores_named_event_bonus_is_source_agnostic():
    events = [
        _event(10, "local_rebellion", ["Kiran"], 7),
    ]
    named_events = [
        NamedEvent(
            name="The Uprising",
            event_type="local_rebellion",
            turn=10,
            actors=["Kiran"],
            description="test",
            importance=7,
        )
    ]

    scores = compute_base_scores(events, named_events, dominant_power="", seed=42)

    assert scores[0] == 12.0
