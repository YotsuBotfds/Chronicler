"""Food-crisis labels: famine (sustained severe shortage) and dearth (a lean season).

The agent-mode famine check reports any shortfall after the cooldown
(``chronicler.ecology._check_famine_yield``); the label reads the region's run
of severely short turns. See docs/integration/navigation-famine-labels.md.
Since the hunger work a dearth's effects are milder than a famine's
(tests/test_hunger_mortality.py, docs/integration/hunger-mortality.md).
"""
from __future__ import annotations

import json

import pytest

from chronicler import provenance as prov
from chronicler.ecology import FAMINE_SEVERE_SUFFICIENCY, FAMINE_SEVERE_TURNS, _check_famine_yield
from chronicler.economy import EconomyResult
from chronicler.models import (
    EMPTY_SLOT,
    FOOD_CRISIS_EVENT_TYPES,
    Civilization,
    ClimatePhase,
    Event,
    Leader,
    Region,
    RegionEcology,
    ResourceType,
    WorldState,
)


def _world(*, mode: str = "hybrid") -> WorldState:
    region = Region(
        name="Fields", terrain="plains", carrying_capacity=100,
        resources="fertile", population=20, controller="Farmers",
        ecology=RegionEcology(soil=0.9, water=0.6, forest_cover=0.2),
        resource_types=[ResourceType.GRAIN, EMPTY_SLOT, EMPTY_SLOT],
        resource_base_yields=[1.0, 0.0, 0.0],
        resource_effective_yields=[1.0, 0.0, 0.0],
    )
    civ = Civilization(
        name="Farmers", population=20, military=20, economy=40,
        culture=30, stability=80, regions=[region.name],
        leader=Leader(name="Farmer", trait="cautious", reign_start=0),
    )
    return WorldState(name="Lean", seed=42, turn=0, agent_mode=mode, regions=[region], civilizations=[civ])


def _turn(world: WorldState, sufficiency: float | None) -> list[Event]:
    """One famine check with this turn's sufficiency, then the cooldown tick."""
    result = None if sufficiency is None else EconomyResult(food_sufficiency={"Fields": sufficiency})
    events = _check_famine_yield(
        world, {"Fields": [0.01, 0.0, 0.0]}, ClimatePhase.DROUGHT, threshold=0.12,
        subsistence_base=0.15, economy_result=result,
    )
    world.turn += 1
    for region in world.regions:
        if region.famine_cooldown > 0:
            region.famine_cooldown -= 1
    return events


def test_first_shortfall_is_a_dearth_with_milder_effects():
    world = _world()
    events = _turn(world, 0.1)
    assert [e.event_type for e in events] == ["dearth"]
    ev = events[0]
    assert ev.importance == 4 and ev.region == "Fields" and ev.actors == ["Farmers"]
    assert "Dearth" in ev.description and "Famine" not in ev.description
    # Every report sets the five-turn cooldown; a dearth drains a third of a
    # famine's stability (1 of 3) and marks its cooldown as a dearth's.
    assert world.civilizations[0].stability == 79
    assert world.regions[0].famine_cooldown == 4  # set to 5, one turn ticked
    assert world.regions[0].dearth_cooldown is True
    assert world.regions[0].population == 20  # agents own population in hybrid


def test_famine_after_a_season_of_severe_shortage():
    world = _world()
    labels = [[e.event_type for e in _turn(world, 0.3)] for _ in range(11)]
    # Reports every five turns; the severe run is 1 at the first, then 6, 11.
    assert labels[0] == ["dearth"]
    assert labels[5] == ["famine"] and labels[10] == ["famine"]
    assert all(not row for i, row in enumerate(labels) if i not in (0, 5, 10))
    assert world.regions[0].food_severe_turns == 11


@pytest.mark.parametrize("run", [FAMINE_SEVERE_TURNS - 1, FAMINE_SEVERE_TURNS])
def test_severe_run_length_sets_the_label(run):
    world = _world()
    for _ in range(4):
        _turn(world, 1.5)
    world.regions[0].famine_cooldown = run - 1  # the report falls on the last severe turn
    events = []
    for _ in range(run):
        events = _turn(world, 0.2)
    assert world.regions[0].food_severe_turns == run
    assert [e.event_type for e in events] == (["famine"] if run >= FAMINE_SEVERE_TURNS else ["dearth"])


def test_mild_shortfall_never_becomes_famine():
    world = _world()
    labels = {e.event_type for _ in range(30) for e in _turn(world, FAMINE_SEVERE_SUFFICIENCY + 0.05)}
    assert labels == {"dearth"}
    assert world.regions[0].food_severe_turns is None


def test_severe_run_resets_and_is_omitted_while_none():
    world = _world()
    _turn(world, 0.2)
    _turn(world, 0.2)
    assert world.regions[0].food_severe_turns == 2
    assert json.loads(world.model_dump_json())["regions"][0]["food_severe_turns"] == 2
    _turn(world, 0.8)  # short, not severe
    assert world.regions[0].food_severe_turns is None
    assert "food_severe_turns" not in json.loads(world.model_dump_json())["regions"][0]
    _turn(world, 0.2)
    _turn(world, None)  # not measured: no evidence of a severe shortage
    assert world.regions[0].food_severe_turns is None
    world.regions[0].population = 0
    _turn(world, 0.2)
    assert world.regions[0].food_severe_turns is None


def test_saved_run_resumes_the_count():
    world = _world()
    _turn(world, 0.2)
    _turn(world, 0.2)
    loaded = WorldState.model_validate_json(world.model_dump_json())
    assert loaded.regions[0].food_severe_turns == 2
    _turn(loaded, 0.2)
    assert loaded.regions[0].food_severe_turns == 3


def test_aggregate_famine_keeps_its_label():
    world = _world(mode="off")
    events = _turn(world, None)
    assert [e.event_type for e in events] == ["famine"]
    assert world.regions[0].food_severe_turns is None


def test_shadow_mode_labels_and_scales_its_population_loss():
    world = _world(mode="shadow")
    events = _turn(world, 0.9)
    assert [e.event_type for e in events] == ["dearth"]
    assert world.regions[0].population == 20  # a mild dearth takes no toll
    world = _world(mode="shadow")
    world.regions[0].food_severe_turns = FAMINE_SEVERE_TURNS
    assert [e.event_type for e in _turn(world, 0.0)] == ["famine"]
    assert world.regions[0].population == 15  # a total famine takes the full toll


# --- provenance: one episode per region whatever the label ---------------------------------

def _run(world: WorldState, sufficiencies: list[float]) -> list[Event]:
    """Turns of famine checks through provenance; returns the kept timeline."""
    timeline: list[Event] = []
    for s in sufficiencies:
        prov.begin_turn(world)
        events = _check_famine_yield(
            world, {"Fields": [0.01, 0.0, 0.0]}, ClimatePhase.DROUGHT, threshold=0.12,
            subsistence_base=0.15, economy_result=EconomyResult(food_sufficiency={"Fields": s}),
        )
        timeline += prov.observe(world, events)
        timeline += prov.end_turn(world)
        world.turn += 1
        for region in world.regions:
            if region.famine_cooldown > 0:
                region.famine_cooldown -= 1
    return timeline


def test_dearth_deepening_into_famine_is_one_episode():
    world = _world()
    timeline = _run(world, [0.3] * 11 + [1.5] * 8)
    reports = [(e.turn, e.event_type, e.episode) for e in timeline if e.event_type in FOOD_CRISIS_EVENT_TYPES]
    assert reports == [(0, "dearth", "onset"), (5, "famine", "tick"), (10, "famine", "tick")]
    ends = [e for e in timeline if e.episode == "end"]
    assert [e.event_type for e in ends] == ["famine_ended"]
    assert ends[0].causes == [timeline[0].event_id] and ends[0].duration == 15
    assert "famine" in ends[0].description


def test_dearth_only_episode_ends_as_dearth():
    world = _world()
    timeline = _run(world, [0.9] * 6 + [1.5] * 8)
    assert [e.episode for e in timeline if e.event_type == "dearth"] == ["onset", "tick"]
    ends = [e for e in timeline if e.episode == "end"]
    assert [e.event_type for e in ends] == ["dearth_ended"]
    assert "dearth" in ends[0].description


def test_open_episode_lookups_find_a_dearth():
    world = _world()
    timeline = _run(world, [0.9])
    assert prov.open_episode(world, "famine", "Fields") == timeline[0].event_id
    assert prov._famines_of(world, "Farmers") == [timeline[0].event_id]


# --- simulation consumers read both labels -----------------------------------------------------

def test_traditions_and_factions_count_a_dearth_like_a_famine():
    from chronicler.factions import tick_factions
    from chronicler.traditions import update_event_counts

    world = _world()
    world.events_timeline.append(Event(turn=0, event_type="dearth", actors=["Farmers"],
                                       description="Dearth in Fields.", importance=4, region="Fields"))
    update_event_counts(world)
    assert world.civilizations[0].event_counts["famines_survived"] == 1

    def influence(event_type: str) -> dict:
        w = _world()
        w.events_timeline.append(Event(turn=0, event_type=event_type, actors=["Farmers"],
                                       description="x", importance=4, region="Fields"))
        tick_factions(w)
        return dict(w.civilizations[0].factions.influence)

    assert influence("dearth") == influence("famine")


def test_aid_convoys_answer_a_dearth_onset():
    from chronicler.diplomacy import _aid_convoys

    seen = []
    world = _world()
    world.diplomacy = type("D", (), {"active": lambda self, kind: seen.append(kind) or []})()
    ev = Event(turn=0, event_type="dearth", actors=["Farmers"], description="x", importance=4,
               region="Fields", episode="onset")
    assert _aid_convoys(world, [ev]) == []
    assert seen == ["alliance"]  # it looked for allies to send relief
    seen.clear()
    tick = ev.model_copy(update={"episode": "tick"})
    assert _aid_convoys(world, [tick]) == [] and seen == []
