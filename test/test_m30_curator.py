"""M30 agent narrative — curator scoring tests."""
from chronicler.models import Event, NamedEvent
from chronicler.curator import compute_base_scores


def test_character_reference_bonus():
    """+2.0 when named character in actors."""
    events = [
        Event(turn=10, event_type="local_rebellion", actors=["Kiran", "Aram"],
              description="test", importance=7, source="agent"),
        Event(turn=10, event_type="mass_migration", actors=["Aram"],
              description="test", importance=5, source="agent"),
    ]
    named_characters = {"Kiran"}
    scores = compute_base_scores(events, [], "Aram", 42,
                                  named_characters=named_characters)

    # First event: 7 (importance) + 2.0 (dominant power) + 2.0 (character ref) + 2.0 (rarity) = 13.0
    # Second event: 5 + 2.0 (dominant) + 2.0 (rarity) = 9.0
    assert scores[0] == 13.0
    assert scores[1] == 9.0


def test_saturation_guard():
    """Multiple named characters in one event → still only +2.0."""
    events = [
        Event(turn=10, event_type="local_rebellion",
              actors=["Kiran", "Vesh", "Talo"],
              description="test", importance=7, source="agent"),
    ]
    named_characters = {"Kiran", "Vesh", "Talo"}
    scores = compute_base_scores(events, [], "", 42,
                                  named_characters=named_characters)

    # 7 + 2.0 (character ref, once) + 2.0 (rarity) = 11.0
    assert scores[0] == 11.0


def test_source_agnostic_named_event():
    """Agent events eligible for NamedEvent promotion via existing logic."""
    events = [
        Event(turn=10, event_type="local_rebellion", actors=["Kiran"],
              description="test", importance=7, source="agent"),
    ]
    named_events = [
        NamedEvent(name="The Uprising", event_type="local_rebellion",
                   turn=10, actors=["Kiran"], description="test", importance=7),
    ]
    scores = compute_base_scores(events, named_events, "", 42)

    # 7 + 3.0 (named event) + 2.0 (rarity) = 12.0
    assert scores[0] == 12.0
