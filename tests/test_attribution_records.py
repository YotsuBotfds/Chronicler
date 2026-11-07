"""D2 attribution records (``--attribution-records``): offline cases.

Constructed war scenarios on ``tests/war_fixtures.py`` (A holds Avalon and
Brook, B holds Crag, Dun and Edge; a stand-in bridge with real roster ids),
the cities and retail harnesses of their own suites, and a restoration through
``politics.check_restoration``. Each records actor, victim and cause at the
event, closes at the livelihoods Phase 10 hook and changes nothing it
observes. Native hybrid runs: ``tests/test_attribution_records_native.py``.
"""
from __future__ import annotations

import ast
import json
import pickle
from pathlib import Path

import pytest

from chronicler import attribution_records as AR
from chronicler import livelihoods as LV
from chronicler.attribution_records_state import (
    BURDEN_KINDS, BURDEN_NATURES, BURDEN_UNITS, CASUALTY_CAUSES, COUNTERS, LIFETIME, MAX_ENTRIES,
    AttributionRecordsState,
)
from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
from chronicler.feature_catalog import REQUIREMENTS
from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES, LivelihoodsState
from chronicler.main import _build_parser
from chronicler.models import Civilization, ExileModifier, Leader, TechEra, TreatyRecord
from chronicler.war.armies import apply_casualties, reconcile_rosters
from chronicler.war.battles import fight, side_for, siege_turn
from chronicler.war.common import build_context
from chronicler.war.occupation import _revolt, start_occupation, tick_occupations
from tests.war_fixtures import FakeBridge, FakeSnapshot, place_army, start_war, war_world

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "chronicler"
AVALON, BROOK, CRAG, DUN, EDGE = range(5)
A, B = 0, 1


def parse(*argv):
    return _build_parser().parse_args(list(argv))


def _world(*, turn=5, extra=()):
    world = war_world()
    world.agent_mode = "hybrid"
    world.turn = turn
    LV.configure_livelihoods(world, parse("--attribution-records", *extra), agent_mode="hybrid")
    return world


def _state(world) -> AttributionRecordsState:
    return world.livelihoods.attribution_records


def _commit(world):
    LV.phase10(world)
    return _state(world).frame


def _armies(world, war, *, a=40, b=30, region="Crag"):
    """A's and B's armies in ``region`` with real roster ids (A: 101.., B: 1..)."""
    rows = [(i, CRAG, 1, B) for i in range(1, b + 1)] + [(i, AVALON, 1, A) for i in range(101, 101 + a)]
    bridge = FakeBridge(rows)
    ctx = build_context(world, bridge=bridge)
    army_a = place_army(world, "A", region, a, war.war_key, roster=[(i, AVALON) for i in range(101, 101 + a)])
    army_b = place_army(world, "B", region, b, war.war_key, roster=[(i, CRAG) for i in range(1, b + 1)])
    for army in (army_a, army_b):
        army.raised_turn = world.turn
    return ctx, bridge, army_a, army_b


def _rows(frame, **match):
    return [r for r in frame["casualties"]["rows"] if all(r[k] == v for k, v in match.items())]


def _entries(frame, kind):
    return [e for e in frame["burdens"]["entries"] if e["kind"] == kind]


# --- registry and switch ---------------------------------------------------------------

def test_the_switch_is_inserted_before_the_ledger_with_cli_catalog_and_manifest_keys():
    assert LIVELIHOODS_SWITCHES[-2:] == ("attribution_records", "wealth_accounting")
    # After every acting package: A3, A4's titled trade, C2's epidemic care, then X1's
    # residence ledger (record-only, immediately before D2).
    assert LIVELIHOODS_SWITCHES.index("attribution_records") == LIVELIHOODS_SWITCHES.index("residence_ledger") + 1
    assert LIVELIHOODS_SWITCHES.index("residence_ledger") == LIVELIHOODS_SWITCHES.index("epidemic_care") + 1
    assert LIVELIHOODS_SWITCHES.index("epidemic_care") == LIVELIHOODS_SWITCHES.index("infrastructure_condition") + 1
    assert LIVELIHOODS_SWITCHES.index("infrastructure_condition") == LIVELIHOODS_SWITCHES.index("titled_trade") + 1
    assert LIVELIHOODS_SWITCHES.index("titled_trade") == LIVELIHOODS_SWITCHES.index("workshop_economics") + 1
    assert LV.LIVELIHOODS_ARG_KEYS[-2:] == ("attribution_records", "wealth_accounting")
    assert "attribution_records" not in LV.LIVELIHOODS_CHOICES
    assert REQUIREMENTS["attribution_records"] == ({"agents": ["hybrid"]},)
    assert "attribution_records" in SIMULATION_ARG_KEYS
    default = parse()
    assert default.attribution_records is None
    assert "attribution_records" not in simulation_config(default)       # feature-off manifests keep their bytes
    assert simulation_config(parse("--attribution-records"))["attribution_records"] is True
    assert simulation_config(parse("--no-attribution-records"))["attribution_records"] is False
    assert LV.livelihoods_arguments(parse("--attribution-records")) == ["--attribution-records"]
    assert LV.livelihoods_arguments(parse("--no-attribution-records")) == ["--no-attribution-records"]
    assert "attribution_records" in LivelihoodsState.model_fields


@pytest.mark.parametrize("mode", ["off", "demographics-only", "shadow"])
def test_the_switch_requires_hybrid_also_when_saved(mode):
    world = war_world()
    world.agent_mode = mode
    with pytest.raises(ValueError, match="requires --agents hybrid"):
        LV.configure_livelihoods(world, parse("--attribution-records"), agent_mode=mode)
    saved = _world()
    saved.agent_mode = mode
    with pytest.raises(ValueError, match="pass --no-attribution-records to end it"):
        LV.configure_livelihoods(saved, parse(), agent_mode=mode)
    LV.configure_livelihoods(saved, parse("--no-attribution-records"), agent_mode="hybrid")
    assert not AR.attribution_records_active(saved) and _state(saved).counters["switched_off"] == 1


def test_off_worlds_have_no_state_and_the_notes_are_no_ops():
    world = war_world()
    world.agent_mode = "hybrid"
    world.turn = 5
    LV.configure_livelihoods(world, parse("--food-allocation"), agent_mode="hybrid")
    assert world.livelihoods.attribution_records is None
    ctx, war = start_war(world)
    ctx, _bridge, army_a, _army_b = _armies(world, war)
    apply_casualties(ctx, army_a, 3, cause="attrition")
    AR.note_conquest(world, world.regions[CRAG], world.civilizations[A], world.civilizations[B])
    assert "attribution_records" not in world.livelihoods.model_dump(mode="json")
    assert "attribution_records" not in LV.livelihoods_feature_flags(world)


def test_the_state_round_trips_json_and_pickle_and_drops_the_pending_turn():
    world = _world()
    ctx, war = start_war(world)
    ctx, _bridge, army_a, _b = _armies(world, war)
    apply_casualties(ctx, army_a, 2, cause="attrition")
    _commit(world)
    world.turn += 1
    apply_casualties(ctx, army_a, 1, cause="attrition")            # pending, not committed
    state = _state(world)
    assert state._turn is not None
    restored = pickle.loads(pickle.dumps(state))
    assert restored._turn is None and restored.model_dump() == state.model_dump()
    again = AttributionRecordsState.model_validate_json(state.model_dump_json())
    assert again.model_dump() == state.model_dump()
    assert set(state.counters) <= set(COUNTERS) and set(state.lifetime) <= set(LIFETIME)


# --- 2. casualties by cause --------------------------------------------------------------

def test_a_field_battle_records_each_sides_deaths_with_the_other_side_as_actor():
    world = _world()
    ctx, war = start_war(world)
    ctx, bridge, army_a, army_b = _armies(world, war)
    fight(ctx, war, world.regions[CRAG], side_for(world, world.civ_map["A"], [army_a]),
          side_for(world, world.civ_map["B"], [army_b]), kind="field")
    battle = world.war_state.battles[-1]
    frame = _commit(world)
    a_rows = _rows(frame, victim=A, cause="battle")
    b_rows = _rows(frame, victim=B, cause="battle")
    assert [(r["actor"], r["actor_name"], r["kind"], r["deaths"]) for r in a_rows] == [
        (B, "B", "field", battle.attacker_losses)]
    assert [(r["actor"], r["actor_name"], r["kind"], r["deaths"]) for r in b_rows] == [
        (A, "A", "field", battle.defender_losses)]
    assert all(r["war"] == war.war_key and r["war_start"] == war.start_turn and r["class"] == "combat"
               for r in a_rows + b_rows)
    # Every queued death is a recorded death, once.
    assert len(bridge._sim.queued) == battle.attacker_losses + battle.defender_losses
    closures = {r["army"]: r for r in frame["casualties"]["armies"]}
    assert closures[army_a.army_id]["closes"] and closures[army_b.army_id]["closes"]
    assert closures[army_a.army_id]["counter_change"] == army_a.casualties


@pytest.mark.parametrize("cause", ["attrition", "trapped", "revolt", "natural"])
def test_each_cause_is_recorded_in_its_own_class_with_its_actor(cause):
    world = _world()
    ctx, war = start_war(world)
    ctx, bridge, army_a, army_b = _armies(world, war)
    if cause == "attrition":
        apply_casualties(ctx, army_a, 4, cause="attrition")
        expected = (None, None, 4)
    elif cause == "trapped":
        # A beaten army with nowhere to go bleeds a fifth, after the battle it lost.
        fight(ctx, war, world.regions[CRAG], side_for(world, world.civ_map["A"], [army_a]),
              side_for(world, world.civ_map["B"], [army_b]), kind="field")
        before = army_a.casualties
        from chronicler.war.battles import _retreat
        world.regions[CRAG].adjacencies = []
        world.regions[BROOK].adjacencies = [n for n in world.regions[BROOK].adjacencies if n != "Crag"]
        world.regions[DUN].adjacencies = [n for n in world.regions[DUN].adjacencies if n != "Crag"]
        ctx = build_context(world, bridge=bridge)
        army_a.region = "Crag"                                 # isolated: nowhere to fall back to
        _retreat(ctx, army_a)
        expected = (B, "B", army_a.casualties - before)
    elif cause == "revolt":
        # A occupies Crag; the people of B rise against A's garrison.
        occ = start_occupation(ctx, world.regions[CRAG], world.civ_map["A"], war, army_a)
        occ.unrest = 900
        import random
        world.regions[CRAG].population = 400                   # partisans outnumber the garrison
        before = army_a.casualties
        _revolt(ctx, occ, world.regions[CRAG], world.civ_map["B"], world.civ_map["A"], [army_a],
                random.Random(1))
        expected = (B, "B", army_a.casualties - before)
    else:
        alive = [(i, AVALON, 1, A) for i in range(101, 141) if i not in (103, 117)]
        alive += [(i, CRAG, 1, B) for i in range(1, 31)]
        reconcile_rosters(world, FakeSnapshot(alive))
        expected = (None, None, 2)
    frame = _commit(world)
    rows = _rows(frame, victim=A, cause=cause)
    assert [(r["actor"], r["actor_name"], r["deaths"]) for r in rows] == [expected]
    assert rows[0]["class"] == {"attrition": "attrition", "trapped": "combat", "revolt": "combat",
                                "natural": "natural"}[cause]
    assert rows[0]["opponent"] == B and rows[0]["opponent_name"] == "B"
    assert frame["casualties"]["by_cause"][cause] == expected[2] and frame["casualties"]["unresolved"] == 0
    assert all(c["closes"] for c in frame["casualties"]["armies"] if c["army"] == army_a.army_id)
    assert _state(world).lifetime[f"deaths_{cause}"] == expected[2]


def test_natural_deaths_are_separated_from_the_campaigns_on_the_same_army():
    world = _world()
    ctx, war = start_war(world)
    ctx, bridge, army_a, army_b = _armies(world, war)
    apply_casualties(ctx, army_a, 3, cause="attrition")
    fight(ctx, war, world.regions[CRAG], side_for(world, world.civ_map["A"], [army_a]),
          side_for(world, world.civ_map["B"], [army_b]), kind="field")
    queued = set(bridge._sim.queued)
    survivors = [aid for aid, _r in army_a.roster]
    natural = survivors[:2]                                    # die in the tick of other causes
    rows = [(aid, AVALON, 1, A) for aid in survivors if aid not in natural]
    rows += [(aid, CRAG, 1, B) for aid, _r in army_b.roster]
    reconcile_rosters(world, FakeSnapshot(rows))
    assert not queued & set(natural)
    frame = _commit(world)
    by_cause = {r["cause"]: r["deaths"] for r in _rows(frame, victim=A)}
    assert by_cause["attrition"] == 3 and by_cause["natural"] == 2
    assert by_cause["battle"] == world.war_state.battles[-1].attacker_losses
    # army.casualties merges them; the record keeps them apart and closes on it.
    closure = next(c for c in frame["casualties"]["armies"] if c["army"] == army_a.army_id)
    assert closure["counter_change"] == army_a.casualties == sum(by_cause.values()) and closure["closes"]


def test_two_battles_in_one_turn_resolve_their_actors_by_battle_record():
    """A third civ C fights A in another region the same turn: each death is
    attributed to the side of its own battle record, not the army's war."""
    world = _world()
    c = Civilization(name="C", population=30, military=50, economy=40, culture=40, stability=60,
                     tech_era=TechEra.IRON, treasury=100, leader=Leader(name="Ruler of C", trait="bold", reign_start=0),
                     regions=[], asabiya=0.6, capital_region=None)
    world.civilizations.append(c)
    world.invalidate_civ_map()
    ctx, war_ab = start_war(world, "A", "B")
    _ctx, war_ac = start_war(world, "C", "A")
    ctx, bridge, army_a, army_b = _armies(world, war_ab)
    army_a2 = place_army(world, "A", "Brook", 30, war_ab.war_key, roster=[(i, AVALON) for i in range(201, 231)])
    army_c = place_army(world, "C", "Brook", 30, war_ac.war_key, roster=[(i, BROOK) for i in range(301, 331)])
    for army in (army_a2, army_c):
        army.raised_turn = world.turn
    fight(ctx, war_ab, world.regions[CRAG], side_for(world, world.civ_map["A"], [army_a]),
          side_for(world, world.civ_map["B"], [army_b]), kind="field")
    fight(ctx, war_ac, world.regions[BROOK], side_for(world, world.civ_map["C"], [army_c]),
          side_for(world, world.civ_map["A"], [army_a2]), kind="field")
    first, second = world.war_state.battles[-2:]
    frame = _commit(world)
    rows = _rows(frame, victim=A, cause="battle")
    assert {(r["actor_name"], r["war"], r["deaths"]) for r in rows} == {
        ("B", war_ab.war_key, first.attacker_losses), ("C", war_ac.war_key, second.defender_losses)}
    # army_a2 was raised for the war with B but died fighting C: the war is the battle's.
    assert _rows(frame, victim=2)[0]["actor"] == A


# --- 1. granary seizures ------------------------------------------------------------------

def _granaries(world, grain=100.0):
    from chronicler.grain_reserves import _ensure, set_grain_reserves_enabled
    set_grain_reserves_enabled(world, True)
    state = _ensure(world)
    for rid, region in enumerate(world.regions):
        state.granaries[rid].grain = grain
        state.granaries[rid].owner = next(i for i, c in enumerate(world.civilizations) if c.name == region.controller)
    return state


def test_siege_occupation_and_conquest_seizures_name_actor_victim_and_flow():
    from chronicler.action_engine import apply_region_conquest
    world = _world()
    reserves = _granaries(world)
    ctx, war = start_war(world)
    ctx, _bridge, army_a, _b = _armies(world, war)
    crag, dun = world.regions[CRAG], world.regions[DUN]
    siege_turn(ctx, war, crag, [army_a], world.civ_map["A"], world.civ_map["B"])
    start_occupation(ctx, crag, world.civ_map["A"], war, army_a)
    apply_region_conquest(world.civ_map["A"], world.civ_map["B"], dun, world, seed=1)
    frame = _commit(world)
    seizures = frame["granary"]["seizures"]
    assert [(s["region"], s["cause"], s["actor"], s["victim"], s["books_owner"], s["owner_stale"]) for s in seizures] == [
        (CRAG, "siege", A, B, B, False), (CRAG, "occupation", A, B, B, False), (DUN, "conquest", A, B, B, False)]
    assert [s["grain"] for s in seizures] == pytest.approx([15.0, 100 * 0.85 * 0.2, 50.0])
    assert [s["flow"] for s in seizures] == [i for i, f in enumerate(reserves.flows) if f.kind == 3]
    assert seizures[2]["via"] == "war" and frame["granary"]["unattributed"] == 0
    assert [e["amount"] for e in _entries(frame, "granary_seizure")] == [s["grain"] for s in seizures]
    assert all(e["nature"] == "destroyed" and e["unit"] == "grain" for e in _entries(frame, "granary_seizure"))


def test_two_conquests_in_one_turn_are_two_seizures_and_the_second_owner_on_the_books_is_stale():
    """RL1's same-turn conquest (``--no-campaigns``): Crag is taken by A from B,
    then by C from A in the same turn. The granary books still name B (set at
    the Phase 2 opening); the second seizure's victim is A."""
    from chronicler.action_engine import apply_region_conquest
    world = _world()
    c = Civilization(name="C", population=30, military=50, economy=40, culture=40, stability=60,
                     tech_era=TechEra.IRON, treasury=100, leader=Leader(name="Ruler of C", trait="bold", reign_start=0),
                     regions=["Edge"], asabiya=0.6, capital_region="Edge")
    world.civilizations.append(c)
    world.civ_map["B"].regions.remove("Edge")
    world.regions[EDGE].controller = "C"
    world.invalidate_civ_map()
    _granaries(world)
    crag = world.regions[CRAG]
    crag.stockpile.goods = {"grain": 8.0, "timber": 4.0}
    apply_region_conquest(world.civ_map["A"], world.civ_map["B"], crag, world, seed=1)
    apply_region_conquest(world.civ_map["C"], world.civ_map["A"], crag, world, seed=2)
    frame = _commit(world)
    seizures = frame["granary"]["seizures"]
    assert [(s["actor_name"], s["victim_name"], s["books_owner_name"], s["owner_stale"]) for s in seizures] == [
        ("A", "B", "B", False), ("C", "A", "B", True)]
    assert [s["grain"] for s in seizures] == pytest.approx([50.0, 25.0])
    losses = _entries(frame, "conquest_stock_loss")
    assert [(e["actor_name"], e["victim_name"], e["cause"]) for e in losses] == [("A", "B", "conquest"),
                                                                                ("C", "A", "conquest")]
    assert [e["amount"] for e in losses] == pytest.approx([6.0, 3.0])
    assert [e["detail"]["food"] for e in losses] == pytest.approx([4.0, 2.0])
    pairs = {(p["kind"], p["actor_name"], p["victim_name"]): p for p in frame["burdens"]["pairs"]}
    assert pairs[("granary_seizure", "C", "A")]["amount"] == pytest.approx(25.0)


def test_a_seizure_no_note_saw_is_counted_unattributed():
    from chronicler.grain_reserves import seize_granary
    world = _world()
    _granaries(world)
    seize_granary(world, world.regions[CRAG], 0.5)               # a path without the note
    frame = _commit(world)
    assert frame["granary"] == {"active": True, "seizures": [], "unattributed": 1}
    assert _state(world).counters["granary_unattributed"] == 1


def test_granaries_off_is_not_observed_not_zero():
    world = _world()
    assert _commit(world)["granary"] == {"active": False, "seizures": [], "unattributed": None}


# --- 3. restored-civ identity --------------------------------------------------------------

def test_a_restoration_reuses_the_index_and_name_and_is_dated_with_the_old_polity():
    from chronicler.politics import check_restoration
    from chronicler.tuning import K_RESTORATION_BASE_PROB
    world = _world(turn=5)
    b = world.civ_map["B"]
    b.founded_turn = 0
    _commit(world)                                               # turn 5: B alive
    world.turn = 6
    for name in list(b.regions):                                 # B falls to A
        world.regions[[r.name for r in world.regions].index(name)].controller = "A"
        world.civ_map["A"].regions.append(name)
    b.regions = []
    world.exile_modifiers.append(ExileModifier(original_civ_name="B", absorber_civ="A",
                                               conquered_regions=["Crag", "Dun", "Edge"]))
    assert _commit(world)["identity"] == []
    world.turn = 7
    world.civ_map["A"].stability = 10
    world.tuning_overrides = {K_RESTORATION_BASE_PROB: 1.0}
    events = check_restoration(world)
    assert [e.event_type for e in events] == ["restoration"]
    assert world.civilizations.index(b) == B and b.regions and b.founded_turn == 7
    frame = _commit(world)
    assert frame["identity"] == [{"turn": 7, "kind": "restored", "civ": B, "name": "B", "detail": {
        "observed_previous_turn": True, "old_founded_turn": 0, "new_founded_turn": 7,
        "old_last_alive_turn": 5, "old_alive_at_last_observation": False}}]
    assert _state(world).identity_log[-1].kind == "restored" and _state(world).counters["identity_events"] == 1


def test_a_new_index_with_an_old_name_and_a_revival_are_identity_events():
    world = _world()
    _commit(world)
    world.turn += 1
    b = world.civ_map["B"]
    held = list(b.regions)
    b.regions = []
    _commit(world)
    world.turn += 1
    b.regions = held                                             # alive again, no new founding
    twin = Civilization(name="A", population=10, military=5, economy=5, culture=5, stability=50,
                        tech_era=TechEra.IRON, treasury=0, leader=Leader(name="X", trait="bold", reign_start=0),
                        regions=[], asabiya=0.5, capital_region=None, founded_turn=world.turn)
    world.civilizations.append(twin)
    world.invalidate_civ_map()
    frame = _commit(world)
    kinds = {(e["kind"], e["civ"]) for e in frame["identity"]}
    assert kinds == {("revived", B), ("name_reused", 2)}
    reused = next(e for e in frame["identity"] if e["kind"] == "name_reused")
    assert reused["detail"]["older_indices"] == [A]


# --- 5. burdens ---------------------------------------------------------------------------

def test_occupation_plunder_is_minted_and_its_turns_are_destroyed_and_minted():
    world = _world()
    ctx, war = start_war(world)
    ctx, _bridge, army_a, _b = _armies(world, war)
    crag = world.regions[CRAG]
    crag.population = 57
    crag.stockpile.goods = {"grain": 20.0, "fish": 4.0, "timber": 9.0}
    occ = start_occupation(ctx, crag, world.civ_map["A"], war, army_a)
    tick_occupations(ctx)
    frame = _commit(world)
    plunder = _entries(frame, "occupation_plunder")
    assert [(e["actor"], e["victim"], e["amount"], e["nature"], e["unit"]) for e in plunder] == [
        (A, B, 5, "minted", "treasury")]
    food = _entries(frame, "food_requisition")
    assert [(e["actor"], e["victim"], e["cause"], e["nature"]) for e in food] == [(A, B, "occupation", "destroyed")]
    assert food[0]["amount"] == pytest.approx(24.0 * 0.2)
    tax = _entries(frame, "occupation_tax_loss")
    req = _entries(frame, "occupation_requisition")
    assert [(e["actor"], e["victim"], e["amount"], e["nature"]) for e in tax] == [(A, B, 2, "destroyed")]
    assert [(e["actor"], e["victim"], e["amount"], e["nature"]) for e in req] == [(A, B, 1, "minted")]
    assert tax[0]["receipt"] == {"war": occ.war_key, "since_turn": world.turn}


def test_a_treaty_payment_is_a_transfer_from_the_loser_to_the_winner():
    world = _world()
    world.war_state.treaties.append(TreatyRecord(turn=world.turn, name="Peace of Brook", war_key="A:B",
                                                 parties=["A", "B"], winner="A", kind="negotiated",
                                                 treasury_paid=17))
    world.war_state.treaties.append(TreatyRecord(turn=world.turn - 1, name="Old", war_key="A:B",
                                                 parties=["A", "B"], winner="B", kind="negotiated",
                                                 treasury_paid=9))
    frame = _commit(world)
    assert [(e["actor"], e["victim"], e["amount"], e["nature"], e["receipt"]["treaty"])
            for e in _entries(frame, "treaty_payment")] == [(A, B, 17, "transfer", 0)]


def test_a_quarantine_closure_is_a_restriction_on_the_target(monkeypatch):
    from chronicler import quarantine_rules as Q
    rules = Q.QuarantineRulesState(mode="closure", closures=[
        Q.QuarantineClosure(id=4, civ=A, target=B, opened_turn=5, last_renewed_turn=5)])
    rules.receipt = Q.QuarantineReceipt(turn=5, decided=[(A, B)], routes_removed=[(A, B)])
    monkeypatch.setattr(Q, "rules_of", lambda world: rules)
    world = _world()
    frame = _commit(world)
    assert [(e["actor"], e["victim"], e["amount"], e["nature"], e["unit"], e["receipt"])
            for e in _entries(frame, "quarantine_closure")] == [(A, B, 1, "restriction", "routes", {"closure": 4})]


def test_city_dues_are_internal_transfers_and_a_sack_pays_the_sacker():
    from tests.test_cities import KETHANI, THORNWALL, THORNWOOD, _city, _economy, _settle, _tick
    from tests.test_cities import _world as cities_world
    world = cities_world()
    world.agent_mode = "hybrid"
    LV.configure_livelihoods(world, parse("--attribution-records"), agent_mode="hybrid")
    s = _settle(world, THORNWOOD, 30)
    _tick(world, economy=_economy(routes={"Thornwood": 2}))
    frame = _commit(world)
    dues = _entries(frame, "city_dues")
    assert [(e["actor"], e["victim"], e["city"], e["nature"]) for e in dues] == [
        (THORNWALL, THORNWALL, s.settlement_id, "transfer")]
    assert dues[0]["amount"] == pytest.approx(world.cities.owed[THORNWALL], abs=1e-5)
    assert next(p for p in frame["burdens"]["pairs"] if p["kind"] == "city_dues")["internal"] is True
    city = _city(world, s.settlement_id)
    city.wealth = 80.0
    world.regions[THORNWOOD].occupied_by = world.civilizations[KETHANI].name
    world.turn = 1
    _tick(world)
    frame = _commit(world)
    sack = _entries(frame, "city_sack")
    loss = _entries(frame, "city_sack_loss")
    assert [(e["actor"], e["victim"], e["amount"], e["nature"]) for e in sack] == [(KETHANI, THORNWALL, 40, "transfer")]
    # loot 40.0, all paid: the destroyed fraction is zero, counted but not paired.
    assert loss == [] and frame["burdens"]["zero_events"] == {"city_sack_loss": 1}


def test_a_guild_levy_is_split_from_the_ordinary_dues(monkeypatch):
    import chronicler.guilds as G
    from chronicler.cities_state import City
    world = _world()
    city = City(settlement_id=9, name="Crag Town", region=CRAG, founded_turn=0, founder=B, lord=B)
    monkeypatch.setattr(G, "_levied", lambda world, guild: True)
    AR.note_city_dues(world, city, 10.0, 0.25, 2.5, object())
    frame = _commit(world)
    assert [(e["kind"], e["actor"], e["victim"], e["city"]) for e in frame["burdens"]["entries"]] == [
        ("city_dues", B, B, 9), ("guild_levy", B, B, 9)]
    assert [e["amount"] for e in frame["burdens"]["entries"]] == pytest.approx([2.5 - 10 * G.LEVY_SHARE,
                                                                                10 * G.LEVY_SHARE])


def test_retail_war_losses_are_matched_to_their_records_twice_in_one_turn():
    from tests.test_household_retail import VERDANT, Harness, _conquer
    from tests.test_household_retail_war import KETHANI, SELURIAN, THORNWALL, _pilot
    h = Harness("--attribution-records")
    _pilot(h)

    def two():
        _conquer(h, VERDANT, KETHANI)
        _conquer(h, VERDANT, SELURIAN)
    h.turn(between=two)
    frame = _state(h.world).frame
    retail = _entries(frame, "retail_war_loss")
    records = [r for r in h.state.log if r.kind == "war_loss"]
    assert [(e["actor_name"], e["victim_name"], e["amount"]) for e in retail] == [
        (KETHANI, THORNWALL, records[0].milli), (SELURIAN, KETHANI, records[1].milli)]
    assert [e["receipt"]["retail_record"] for e in retail] == [
        h.state.log_dropped + i for i, r in enumerate(h.state.log) if r.kind == "war_loss"]
    assert frame["burdens"]["retail_unattributed"] == 0


def test_the_burden_registry_is_closed():
    assert {n for _a, n, _u in BURDEN_KINDS.values()} <= set(BURDEN_NATURES)
    assert {u for _a, _n, u in BURDEN_KINDS.values()} <= set(BURDEN_UNITS)
    for kind in BURDEN_KINDS:
        assert f"burden_{kind}" in LIFETIME and f"burden_{kind}_events" in LIFETIME
    for cause in CASUALTY_CAUSES:
        assert f"deaths_{cause}" in LIFETIME


def test_entries_are_capped_but_pairs_stay_exact():
    world = _world()
    _s = _state(world)
    from chronicler.cities_state import City
    city = City(settlement_id=1, name="Crag Town", region=CRAG, founded_turn=0, founder=B, lord=B)
    for _ in range(MAX_ENTRIES + 5):
        AR.note_city_dues(world, city, 4.0, 0.25, 1.0, None)
    frame = _commit(world)
    assert len(frame["burdens"]["entries"]) == MAX_ENTRIES and frame["burdens"]["entries_dropped"] == 5
    pair = frame["burdens"]["pairs"][0]
    assert pair["events"] == MAX_ENTRIES + 5 and pair["amount"] == pytest.approx(MAX_ENTRIES + 5)


# --- seams --------------------------------------------------------------------------------

#: Every call of a note function from the simulation: (module, function, note) -> calls.
NOTE_SITES = {
    ("war.armies", "apply_casualties", "note_casualties"): 1,
    ("war.armies", "drain_population", "note_war_drain"): 1,
    ("war.armies", "reconcile_rosters", "note_natural_deaths"): 1,
    ("war.occupation", "_requisition", "note_requisition"): 1,
    ("war.occupation", "start_occupation", "note_plunder"): 1,
    ("war.occupation", "tick_occupations", "note_occupation_turn"): 1,
    ("action_engine", "apply_region_conquest", "note_conquest"): 1,
    ("cities", "_commerce", "note_city_dues"): 1,
    ("cities", "_sack", "note_city_sack"): 1,
}


def _calls(names):
    found = {}
    for path in sorted(SRC.rglob("*.py")):
        module = path.relative_to(SRC).with_suffix("").as_posix().replace("/", ".")
        if module == "attribution_records":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names:
                    key = (module, fn.name, node.func.id)
                    found[key] = found.get(key, 0) + 1
    return found


def test_every_note_site_is_registered_and_guarded():
    notes = {n for _m, _f, n in NOTE_SITES}
    # Every note the package defines is registered (fail closed on a new seam).
    assert notes == {name for name in dir(AR) if name.startswith("note_") and callable(getattr(AR, name))}
    assert _calls(notes) == NOTE_SITES
    for module, function, note in NOTE_SITES:
        source = (SRC / (module.replace(".", "/") + ".py")).read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function)
        guarded = [n for n in ast.walk(fn) if isinstance(n, ast.If) and "livelihoods" in ast.unparse(n.test)
                   and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == note
                           for c in ast.walk(n))]
        assert guarded, f"{module}.{function} calls {note} outside the livelihoods guard"


def test_every_casualty_cause_at_a_call_site_is_declared():
    causes = set()
    for path in sorted((SRC / "war").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "apply_casualties":
                for kw in node.keywords:
                    if kw.arg == "cause":
                        if isinstance(kw.value, ast.Constant):
                            causes.add(kw.value.value)
                        else:
                            causes.add("<computed>")
    # _apply_side_losses forwards its own literal ("battle" from fight).
    assert causes - {"<computed>"} <= set(CASUALTY_CAUSES)
    assert {"attrition", "trapped", "revolt"} <= causes


def test_a_note_after_the_commit_is_counted_and_dropped():
    world = _world()
    ctx, war = start_war(world)
    ctx, _bridge, army_a, _b = _armies(world, war)
    _commit(world)
    apply_casualties(ctx, army_a, 1, cause="attrition")
    state = _state(world)
    assert state.counters["notes_after_close"] == 1 and state.log[-1].kind == "note_after_close"
    assert state._turn is None


def test_notes_of_a_turn_without_its_commit_mark_it_unobserved():
    world = _world()
    ctx, war = start_war(world)
    ctx, _bridge, army_a, _b = _armies(world, war)
    apply_casualties(ctx, army_a, 1, cause="attrition")
    world.turn += 1
    frame = _commit(world)
    state = _state(world)
    assert state.counters["turns_unobserved"] == 1 and frame["casualties"]["rows"] == []
    # The army's counter moved in the unobserved turn: no baseline, unchecked.
    assert frame["casualties"]["armies"] == []


# --- observer identity and reading ---------------------------------------------------------

def _scenario(flags):
    """Battle, attrition, siege, occupation, natural deaths and a conquest,
    with granaries, over two committed turns."""
    from chronicler.action_engine import apply_region_conquest
    world = war_world()
    world.agent_mode = "hybrid"
    world.turn = 5
    if flags:
        LV.configure_livelihoods(world, parse(*flags), agent_mode="hybrid")
    _granaries(world)
    ctx, war = start_war(world)
    ctx, bridge, army_a, army_b = _armies(world, war)
    apply_casualties(ctx, army_a, 2, cause="attrition")
    fight(ctx, war, world.regions[CRAG], side_for(world, world.civ_map["A"], [army_a]),
          side_for(world, world.civ_map["B"], [army_b]), kind="field")
    siege_turn(ctx, war, world.regions[EDGE], [army_a], world.civ_map["A"], world.civ_map["B"])
    start_occupation(ctx, world.regions[EDGE], world.civ_map["A"], war, army_a)
    rows = [(aid, AVALON, 1, A) for aid, _r in army_a.roster[1:]] + [(aid, CRAG, 1, B) for aid, _r in army_b.roster]
    reconcile_rosters(world, FakeSnapshot(rows))
    LV.phase10(world)
    world.turn += 1
    tick_occupations(ctx)
    apply_region_conquest(world.civ_map["A"], world.civ_map["B"], world.regions[DUN], world, seed=3)
    LV.phase10(world)
    return world, bridge


def test_with_the_switch_on_everything_but_its_record_equals_the_switch_off():
    on, bridge_on = _scenario(("--attribution-records",))
    off, bridge_off = _scenario(())
    dump_on = on.model_dump(mode="json")
    dump_off = off.model_dump(mode="json")
    record = dump_on["livelihoods"].pop("attribution_records")
    assert dump_on.pop("livelihoods") == {"schema_version": 1} and "livelihoods" not in dump_off
    assert record["frame"]["turn"] == 6 and dump_on == dump_off
    assert bridge_on._sim.queued == bridge_off._sim.queued and LV.livelihoods_snapshot_fields(off) == {}
    frame = record["frame"]
    assert {e["kind"] for e in frame["burdens"]["entries"]} >= {"occupation_tax_loss", "granary_seizure"}
    assert frame["burdens"]["zero_events"] == {"conquest_stock_loss": 1}        # Dun's market was empty


@pytest.mark.parametrize("case", ["absent", "malformed", "unobserved", "recorded_zero", "recorded"])
def test_reader_states_are_distinct(case):
    world = _world()
    if case == "recorded":
        ctx, war = start_war(world)
        ctx, _bridge, army_a, _b = _armies(world, war)
        apply_casualties(ctx, army_a, 1, cause="attrition")
    _commit(world)
    world.turn += 1
    snapshot = LV.livelihoods_snapshot_fields(world)
    record = snapshot["livelihoods"]["attribution_records"]
    assert record["stage"] == "D2" and record["source_turn"] == world.turn - 1
    assert json.loads(json.dumps(snapshot)) == snapshot
    if case == "absent":
        snapshot = {"livelihoods": {"schema_version": 1}}
    elif case == "malformed":
        record["frame"] = {"turn": record["source_turn"]}
    elif case == "unobserved":
        world.turn += 1                                          # the next turn was not committed
        snapshot = LV.livelihoods_snapshot_fields(world)
    status, frame = AR.record_status(snapshot)
    assert status == case
    assert (frame is None) == (case in ("absent", "malformed", "unobserved"))


def test_the_snapshot_never_aliases_the_state():
    world = _world()
    _commit(world)
    world.turn += 1
    record = LV.livelihoods_snapshot_fields(world)["livelihoods"]["attribution_records"]
    record["frame"]["identity"].append("x")
    assert _state(world).frame["identity"] == []


# --- review m1, m2, n1, n2 ------------------------------------------------------------------

def test_deaths_where_a_war_drain_staged_deaths_are_not_filed_as_natural():
    """A siege drains Crag (actor A) and an occupation's crushed revolt drains
    Edge twice by different hands: B's soldiers found dead after the tick in
    Crag are war_drain with actor A; in Edge possibly_enemy; elsewhere natural."""
    from chronicler.war.armies import drain_population
    world = _world()
    ctx, war = start_war(world)
    world.regions[EDGE].population = 400
    ctx, bridge, army_a, army_b = _armies(world, war)
    army_b.roster = [(1, CRAG), (2, CRAG), (3, EDGE), (4, DUN)] + [(i, CRAG) for i in range(5, 31)]
    drain_population(ctx, ["Crag"], 3, actor=world.civ_map["A"])
    drain_population(ctx, ["Edge"], 2, actor=world.civ_map["A"])
    drain_population(ctx, ["Edge"], 2)                                 # no actor named
    alive = [(i, CRAG, 1, B) for i in range(5, 31)] + [(i, AVALON, 1, A) for i in range(101, 141)]
    reconcile_rosters(world, FakeSnapshot(alive))
    frame = _commit(world)
    rows = {(r["cause"], r["actor"]): r["deaths"] for r in _rows(frame, victim=B)}
    assert rows == {("war_drain", A): 2, ("possibly_enemy", None): 1, ("natural", None): 1}
    assert frame["casualties"]["by_class"] == {"combat": 0, "attrition": 0, "natural": 1, "war_drain": 3}
    assert [(d["region"], d["staged"], d["actors"], d["unnamed"]) for d in frame["casualties"]["war_drains"]] == [
        (CRAG, 3, ["A"], 0), (EDGE, 4, ["A"], 1)]
    assert _state(world).counters["war_drain_deaths"] == 3 and _state(world).lifetime["deaths_war_drain"] == 2


@pytest.mark.parametrize("site", ["siege", "garrison", "depopulation", "crushed_revolt"])
def test_each_war_drain_names_its_actor(site):
    import random
    world = _world()
    ctx, war = start_war(world)
    ctx, bridge, army_a, army_b = _armies(world, war)
    crag = world.regions[CRAG]
    crag.population = 400
    if site == "siege":
        siege_turn(ctx, war, crag, [army_a], world.civ_map["A"], world.civ_map["B"])
    elif site == "garrison":
        from chronicler.war.battles import skirmish
        skirmish(ctx, war, crag, [army_a], world.civ_map["A"], world.civ_map["B"], 20)
    else:
        occ = start_occupation(ctx, crag, world.civ_map["A"], war, army_a)
        occ.unrest = 900
        if site == "depopulation":
            from chronicler.war import params as P
            # After this turn's change, unrest sits between depopulation and revolt.
            delta = P.UNREST_BASE + P.UNREST_CULTURE - min(P.UNREST_GARRISON_CAP, army_a.soldiers * P.UNREST_PER_SOLDIER)
            occ.unrest = P.UNREST_DEPOPULATION + 10 - delta
            tick_occupations(ctx)
        else:
            crag.population = 100                                      # few partisans: the garrison crushes them
            _revolt(ctx, occ, crag, world.civ_map["B"], world.civ_map["A"], [army_a], random.Random(1))
    frame = _commit(world)
    drains = {d["region"]: d for d in frame["casualties"]["war_drains"]}
    assert drains[CRAG]["actors"] == ["A"] and drains[CRAG]["unnamed"] == 0 and drains[CRAG]["staged"] > 0


def test_battle_checks_bound_each_sides_recorded_deaths_by_its_battle_record():
    world = _world()
    ctx, war = start_war(world)
    ctx, bridge, army_a, army_b = _armies(world, war)
    fight(ctx, war, world.regions[CRAG], side_for(world, world.civ_map["A"], [army_a]),
          side_for(world, world.civ_map["B"], [army_b]), kind="field")
    battle = world.war_state.battles[-1]
    frame = _commit(world)
    assert frame["casualties"]["battle_checks"] == [
        {"battle": len(world.war_state.battles) - 1, "side": "A", "recorded": battle.attacker_losses,
         "battle_losses": battle.attacker_losses, "holds": True},
        {"battle": len(world.war_state.battles) - 1, "side": "B", "recorded": battle.defender_losses,
         "battle_losses": battle.defender_losses, "holds": True}]
    # A note resolved to the wrong side would exceed the record and fail.
    world.turn += 1
    note = {"army": army_a.army_id, "victim": A, "victim_name": "A", "war": war.war_key, "cause": "battle",
            "count": battle.attacker_losses + 1, "battle": len(world.war_state.battles) - 1}
    t = AR._Turn(world.turn)
    t.casualties.append(note)
    _state(world)._turn = t
    frame = _commit(world)
    assert frame["casualties"]["battle_checks"][0]["holds"] is False
    assert _state(world).counters["battle_checks_failed"] == 1


def test_zero_amount_events_are_counted_not_paired_and_a_sack_without_a_sacker_is_lost():
    from chronicler.cities_state import City
    world = _world()
    ctx, war = start_war(world)
    ctx, _bridge, army_a, _b = _armies(world, war)
    crag = world.regions[CRAG]
    crag.population = 5                                                # plunder 5 // 10 == 0
    start_occupation(ctx, crag, world.civ_map["A"], war, army_a)
    city = City(settlement_id=3, name="Crag Town", region=CRAG, founded_turn=0, founder=B, lord=B)
    AR.note_city_sack(world, city, -1, B, 7.5, 7)
    frame = _commit(world)
    zero = frame["burdens"]["zero_events"]
    assert zero["occupation_plunder"] == 1 and zero["city_sack"] == 1
    assert not _entries(frame, "occupation_plunder")
    assert [(e["actor"], e["victim"], e["amount"]) for e in _entries(frame, "city_sack_loss")] == [(None, B, 7.5)]


def test_no_more_deaths_are_labelled_war_drain_than_the_drains_staged():
    """Crag staged one death; three of B's soldiers there (two armies) died:
    one is war_drain, the other two natural and counted beyond the staged."""
    from chronicler.war.armies import drain_population
    world = _world()
    ctx, war = start_war(world)
    ctx, bridge, army_a, army_b = _armies(world, war)
    second = place_army(world, "B", "Crag", 10, war.war_key, roster=[(i, CRAG) for i in range(51, 61)])
    second.raised_turn = world.turn
    drain_population(ctx, ["Crag"], 1, actor=world.civ_map["A"])
    dead = {1, 2, 51}
    alive = [(i, CRAG, 1, B) for i in list(range(1, 31)) + list(range(51, 61)) if i not in dead]
    alive += [(i, AVALON, 1, A) for i in range(101, 141)]
    reconcile_rosters(world, FakeSnapshot(alive))
    frame = _commit(world)
    rows = {(r["cause"], r["actor"]): r["deaths"] for r in _rows(frame, victim=B)}
    assert rows == {("war_drain", A): 1, ("natural", None): 2}
    assert [(d["staged"], d["labelled"], d["beyond_staged"]) for d in frame["casualties"]["war_drains"]] == [(1, 1, 2)]
