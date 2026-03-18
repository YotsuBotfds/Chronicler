"""Tests for M45 arc classifier."""
import pytest
from chronicler.models import GreatPerson, Event
from chronicler.arcs import classify_arc


def _make_gp(**kwargs) -> GreatPerson:
    defaults = dict(
        name="Kiran", role="general", trait="bold",
        civilization="Aram", origin_civilization="Aram",
        born_turn=100, source="agent", agent_id=1,
    )
    defaults.update(kwargs)
    return GreatPerson(**defaults)


def _make_event(turn, event_type, actors, **kwargs) -> Event:
    return Event(
        turn=turn,
        event_type=event_type,
        actors=actors,
        description=kwargs.get("description", ""),
        importance=kwargs.get("importance", 5),
    )


def test_classify_no_events():
    gp = _make_gp()
    phase, arc_type = classify_arc(gp, [], None, current_turn=150)
    # Bold + active + career >= 20 → "rising" partial from Rise-and-Fall
    # But also "embattled" partial from Tragic Hero (bold + active)
    # Both have condition_count=1, Tragic Hero is later → "embattled" wins
    assert phase == "embattled"
    assert arc_type is None


def test_classify_no_events_non_bold():
    gp = _make_gp(trait="cautious")
    phase, arc_type = classify_arc(gp, [], None, current_turn=150)
    # cautious + active + career >= 20 → "rising" partial only
    assert phase == "rising"
    assert arc_type is None


def test_classify_no_events_young():
    """Character below RISING_CAREER_THRESHOLD -> no arc."""
    gp = _make_gp(trait="cautious", born_turn=145)
    phase, arc_type = classify_arc(gp, [], None, current_turn=150)
    assert phase is None
    assert arc_type is None


def test_classify_rise_and_fall():
    gp = _make_gp(trait="cautious", fate="dead", alive=False, active=False, death_turn=140)
    events = [
        _make_event(140, "character_death", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=140)
    assert arc_type == "Rise-and-Fall"
    assert phase == "fallen"


def test_classify_exile_and_return():
    gp = _make_gp(trait="cautious")
    events = [
        _make_event(120, "conquest_exile", ["Kiran", "Aram", "Bora"]),
        _make_event(160, "exile_return", ["Kiran"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=160)
    assert arc_type == "Exile-and-Return"


def test_classify_exile_partial():
    gp = _make_gp(trait="cautious")
    events = [
        _make_event(120, "conquest_exile", ["Kiran", "Aram", "Bora"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=150)
    assert phase == "exiled"
    assert arc_type is None


def test_classify_tragic_hero():
    gp = _make_gp(trait="bold", fate="dead", alive=False, active=False,
                   death_turn=120)  # career = 20 turns < threshold of 35
    phase, arc_type = classify_arc(gp, [], None, current_turn=120)
    assert arc_type == "Tragic-Hero"
    assert phase == "embattled"


def test_classify_tragic_hero_long_career():
    """Bold character who lived long is NOT a tragic hero."""
    gp = _make_gp(trait="bold", fate="dead", alive=False, active=False,
                   death_turn=200)  # career = 100 turns > threshold
    events = [_make_event(200, "character_death", ["Kiran", "Aram"])]
    phase, arc_type = classify_arc(gp, events, None, current_turn=200)
    # Rise-and-Fall should match (career >= 20, has death)
    assert arc_type == "Rise-and-Fall"


def test_classify_wanderer():
    gp = _make_gp(trait="cautious")
    events = [
        _make_event(110, "notable_migration", ["Kiran"]),
        _make_event(120, "notable_migration", ["Kiran"]),
        _make_event(130, "notable_migration", ["Kiran"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=130)
    assert arc_type == "Wanderer"
    assert phase == "wandering"


def test_classify_wanderer_partial():
    gp = _make_gp(trait="cautious")
    events = [
        _make_event(110, "notable_migration", ["Kiran"]),
        _make_event(120, "notable_migration", ["Kiran"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=120)
    assert phase == "wandering"
    assert arc_type is None


def test_classify_defector():
    gp = _make_gp(trait="cautious", civilization="Bora")
    events = [
        _make_event(130, "secession_defection", ["Kiran"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=130)
    assert arc_type == "Defector"
    assert phase == "defecting"


def test_classify_defector_partial():
    gp = _make_gp(trait="cautious", civilization="Bora")
    phase, arc_type = classify_arc(gp, [], None, current_turn=130)
    assert phase == "defecting"
    assert arc_type is None


def test_classify_prophet():
    gp = _make_gp(role="prophet", trait="cautious")
    events = [
        _make_event(140, "pilgrimage_return", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=140)
    assert arc_type == "Prophet"


def test_classify_prophet_mid_pilgrimage():
    gp = _make_gp(role="prophet", trait="cautious", pilgrimage_return_turn=160)
    phase, arc_type = classify_arc(gp, [], None, current_turn=140)
    assert phase == "converting"
    assert arc_type is None


def test_classify_martyr():
    gp = _make_gp(role="prophet", trait="cautious", fate="dead", alive=False,
                   active=False, death_turn=120)
    events = [
        _make_event(120, "character_death", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=120)
    assert arc_type == "Martyr"


def test_classify_martyr_long_career():
    """Prophet who lived long is NOT a martyr."""
    gp = _make_gp(role="prophet", trait="cautious", fate="dead", alive=False,
                   active=False, death_turn=200)
    events = [
        _make_event(200, "character_death", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=200)
    assert arc_type == "Rise-and-Fall"  # career >= 20, has death event


def test_classify_reclassification():
    """Wanderer reclassifies to Exile-and-Return when return event added."""
    gp = _make_gp(trait="cautious")
    events_before = [
        _make_event(110, "notable_migration", ["Kiran"]),
        _make_event(120, "notable_migration", ["Kiran"]),
        _make_event(130, "notable_migration", ["Kiran"]),
        _make_event(140, "conquest_exile", ["Kiran", "Aram", "Bora"]),
    ]
    _, type_before = classify_arc(gp, events_before, None, current_turn=150)
    assert type_before == "Wanderer"

    events_after = events_before + [
        _make_event(180, "exile_return", ["Kiran"]),
    ]
    _, type_after = classify_arc(gp, events_after, None, current_turn=180)
    assert type_after == "Exile-and-Return"


def test_classify_priority():
    """Bold prophet who died young: Martyr wins (later in check order)."""
    gp = _make_gp(role="prophet", trait="bold", fate="dead",
                   alive=False, active=False, death_turn=120)
    events = [
        _make_event(120, "character_death", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=120)
    assert arc_type == "Martyr"


def test_classify_dead_character():
    """Death on current turn still classifies."""
    gp = _make_gp(trait="cautious", fate="dead", alive=False, active=False, death_turn=140)
    events = [
        _make_event(140, "character_death", ["Kiran", "Aram"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=140)
    assert arc_type == "Rise-and-Fall"
    assert phase == "fallen"


def test_arc_type_turn_set():
    """arc_type_turn updates on classification — simulates call site."""
    gp = _make_gp(trait="cautious")
    events = [
        _make_event(130, "notable_migration", ["Kiran"]),
        _make_event(140, "notable_migration", ["Kiran"]),
        _make_event(150, "notable_migration", ["Kiran"]),
    ]
    _, arc_type = classify_arc(gp, events, None, current_turn=150)
    assert arc_type == "Wanderer"

    prev_type = gp.arc_type
    if arc_type is not None and arc_type != prev_type:
        gp.arc_type = arc_type
        gp.arc_type_turn = 150
    assert gp.arc_type_turn == 150
    assert gp.arc_type == "Wanderer"


def test_events_filtered_by_character_name():
    """Events not involving this character are ignored."""
    gp = _make_gp(name="Kiran", trait="cautious")
    events = [
        _make_event(120, "character_death", ["OtherPerson", "Aram"]),
        _make_event(130, "notable_migration", ["OtherPerson"]),
    ]
    phase, arc_type = classify_arc(gp, events, None, current_turn=150)
    # Only Rise-and-Fall partial (career >= 20, active)
    assert phase == "rising"
    assert arc_type is None
