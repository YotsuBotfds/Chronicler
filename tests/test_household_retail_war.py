"""A5-1: war reaches owned stock once per event (household retail rules v2).

Offline, on the stand-in native of ``test_household_retail.py`` (template
seed 42 with constructed people). Version 2 (``--household-retail-rules 2``,
the default of a new retail state) applies each conquest
(``action_engine.apply_region_conquest``), siege turn and occupation start
(``war.occupation._requisition``) to the owned stock of a pilot region at the
event, once, with its cause, actor and victim. Version 1 reproduces
checkpoints 2-3 (its own tests stay in ``test_household_retail.py``, pinned to
``--household-retail-rules 1``). Recorded limits RL1 (same-turn conquest
versus duplicate processing), RL2 (occupation and siege of owned stock) and
RL3 (legacy state-file resume) are covered here; the native and CLI halves
are in ``test_household_retail_war_native.py``.
"""
from __future__ import annotations

import json
import pickle
import random
import sys
from fractions import Fraction

import numpy as np
import pytest

from chronicler import household_retail as HR
from chronicler import livelihoods as LV
from chronicler.economy import FOOD_GOODS
from chronicler.household_retail_state import (
    COUNTERS, RULES_VERSION, WAR_CAUSES, HouseholdRetailState, RetailRecord, RetailRegion,
)
from chronicler.livelihoods import LivelihoodsRefusal, configure_livelihoods
from chronicler.main import _build_parser
from chronicler.war.occupation import _requisition
from chronicler.world_gen import generate_world
from tests.test_household_retail import ASHARA, THORNWOOD, VERDANT, Harness, _calls, _conquer, _owners, _people
from tests.war_fixtures import place_army, start_war

# Template seed 42: civilization indices and names.
ASHKARI, KETHANI, THORNWALL, SELURIAN = "Ashkari Nomads", "Kethani Empire", "Thornwall Confederacy", "Selurian Republic"
INDEX = {ASHKARI: 0, KETHANI: 1, THORNWALL: 2, SELURIAN: 3}
V1 = ("--household-retail-rules", "1")
parse = _build_parser().parse_args


def _share(goods, survival):
    """``v - floor(v x f)`` per good, ``f`` as its decimal value."""
    keep = Fraction(str(survival))
    return [v - (v * keep.numerator) // keep.denominator for v in goods]


def _war_records(h):
    return [r for r in h.state.log if r.kind == "war_loss"]


def _who(record):
    return (record.cause, record.actor, record.actor_name, record.victim, record.victim_name)


def _civ(h, name):
    return h.world.civ_map[name]


def _pilot(h, *, grain=9.0, fish=1.3, people=(1, 2, 3)):
    """Verdant Plains (Thornwall's capital, a market pilot) with owned grain and fish."""
    _people(h, VERDANT, people, wealth=0.0)
    h.turn({VERDANT: {"grain": grain, "fish": fish}})
    reg = h.state.region(VERDANT)
    assert reg.goods[0] > 0 and reg.goods[1] > 0 and len(reg.claims) == len(people)
    return reg


# --- rules version and registration ---------------------------------------------------

def test_a_new_state_runs_version_2_and_the_option_selects_version_1():
    assert RULES_VERSION == 2 and WAR_CAUSES == ("conquest", "siege", "occupation")
    h2, h1 = Harness(), Harness(*V1)
    assert (h2.state.rules_version, h2.state.rules) == (2, "2")
    assert (h1.state.rules_version, h1.state.rules) == (1, "1")
    assert HouseholdRetailState().rules_version == 1                 # absent: a state saved before A5
    # A saved state keeps its version when the option is omitted.
    configure_livelihoods(h1.world, parse(["--household-retail"]), agent_mode="hybrid")
    assert h1.state.rules_version == 1
    # Counters are appended, never reordered (A2R appended after these).
    first = COUNTERS.index("war_loss_conquest_milli")
    assert COUNTERS[first:first + 4] == ("war_loss_conquest_milli", "war_loss_siege_milli",
                                         "war_loss_occupation_milli", "war_events")
    assert COUNTERS.index("requisition_exempt_region_turns") < COUNTERS.index("war_events")


def test_the_rules_option_is_registered_forwarded_and_omitted_when_unset():
    from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
    from chronicler.feature_catalog import REQUIREMENTS, feature_entries
    assert LV.LIVELIHOODS_CHOICES["household_retail_rules"] == ("2", "1")
    assert LV.LIVELIHOODS_ARG_KEYS[-1] == "household_retail_rules"
    assert "household_retail_rules" in SIMULATION_ARG_KEYS
    assert "household_retail_rules" not in simulation_config(parse([]))
    assert simulation_config(parse(["--household-retail-rules", "1"]))["household_retail_rules"] == "1"
    args = parse(["--household-retail", "--household-retail-rules", "1"])
    assert LV.livelihoods_arguments(args)[-2:] == ["--household-retail", "--household-retail-rules=1"]
    # The catalog lists it as a choice of the retail switch (a choice needs no
    # REQUIREMENTS entry: it requires its switch).
    (entry,) = [e for e in feature_entries() if e["key"] == "household_retail_rules"]
    assert (entry["kind"], entry["choices"], entry["parent"]) == ("choice", ["2", "1"], "household_retail")
    assert entry["requires"][0]["feature"] == "household_retail" and "household_retail_rules" not in REQUIREMENTS


def test_a_rules_change_on_resume_is_refused_before_any_change():
    h = Harness()
    _pilot(h)
    before = h.world.model_dump_json()
    for argv in (V1, ("--household-retail", *V1)):
        with pytest.raises(ValueError, match="conflicts with the saved retail state"):
            configure_livelihoods(h.world, parse(list(argv)), agent_mode="hybrid")
        assert h.world.model_dump_json() == before
    configure_livelihoods(h.world, parse(["--household-retail", "--household-retail-rules", "2"]), agent_mode="hybrid")
    assert h.world.model_dump_json() == before
    assert LV.livelihoods_resume_conflicts(h.world, parse(list(V1)), {}) == [
        "--household-retail-rules '1' conflicts with the checkpoint (saved: '2')"]
    assert LV.livelihoods_resume_conflicts(h.world, parse(["--household-retail-rules", "2"]), {}) == []
    assert LV.livelihoods_resume_conflicts(h.world, parse(list(V1)), {"household_retail_rules": "1"}) == []
    with pytest.raises(ValueError, match="rules version 2"):
        HR.set_household_retail_enabled(h.world, True, args=parse(list(V1)))


# --- a. RL1: two conquests in one turn -----------------------------------------------

def test_two_conquests_in_one_turn_take_the_conquest_share_twice_like_the_commons():
    h = Harness()
    reg = _pilot(h)
    seen = {}

    def two():
        seen["goods"], seen["claims"] = list(reg.goods), dict(reg.claims)
        seen["commons"] = {g: v for g, v in h.world.regions[VERDANT].stockpile.goods.items() if v}
        _conquer(h, VERDANT, KETHANI)                     # from Thornwall
        seen["first"], seen["first_claims"] = list(reg.goods), dict(reg.claims)
        _conquer(h, VERDANT, SELURIAN)                    # from Kethani, the same turn (--no-campaigns)
        seen["second"] = list(reg.goods)
        seen["commons_after"] = dict(h.world.regions[VERDANT].stockpile.goods)
    h.turn(between=two)
    first = _share(seen["goods"], 0.5)
    assert seen["first"] == [v - x for v, x in zip(seen["goods"], first)]
    second = _share(seen["first"], 0.5)
    assert seen["second"] == [v - x for v, x in zip(seen["first"], second)]
    for good, v in seen["commons"].items():                 # the commons: x 0.25, per call
        assert seen["commons_after"][good] == pytest.approx(v * 0.25)
    # Claims pro rata by largest remainder, ties to the smaller id, at each event.
    taken = {k: seen["claims"][k] - seen["first_claims"].get(k, 0) for k in seen["claims"]}
    assert taken == HR.largest_remainder(sum(first), seen["claims"].items())
    records = _war_records(h)
    assert [_who(r) for r in records] == [
        ("conquest", INDEX[KETHANI], KETHANI, INDEX[THORNWALL], THORNWALL),
        ("conquest", INDEX[SELURIAN], SELURIAN, INDEX[KETHANI], KETHANI)]
    assert [r.milli for r in records] == [sum(first), sum(second)]
    assert records[0].note == f"conquered by {KETHANI} from {THORNWALL} (won in war)"
    assert reg.war_events == 2 and h.state.counters["war_events"] == 2 and reg.war_loss_turn == 11
    assert h.frame(VERDANT).flows["war_loss"] == sum(first) + sum(second)
    assert h.state.counters["war_loss_conquest_milli"] == h.state.counters["war_loss_milli"] == sum(first) + sum(second)
    h.turn()
    assert "war_loss" not in h.frame(VERDANT).flows and reg.war_events == 2


def test_rules_1_keeps_the_once_per_turn_conquest_of_checkpoints_2_and_3():
    """The recorded limit RL1, reproduced by version 1: two conquests in one
    turn destroy owned stock once, and the record names the last controller."""
    h = Harness(*V1)
    reg = _pilot(h)
    seen = {}

    def two():
        seen["goods"] = list(reg.goods)
        _conquer(h, VERDANT, KETHANI)
        _conquer(h, VERDANT, SELURIAN)
        seen["after"] = list(reg.goods)                    # version 1 applies nothing at the event
    h.turn(between=two)
    assert seen["after"] == seen["goods"]
    assert h.frame(VERDANT).flows["war_loss"] == sum(_share(seen["goods"], 0.5))
    (record,) = _war_records(h)
    assert record.note == f"conquered by {SELURIAN} on turn 11" and record.cause is None
    assert reg.war_events is None and "war_events" not in h.state.counters


# --- b. duplicate processing -------------------------------------------------------------

def test_one_conquest_seen_at_phase2_and_before_the_tick_is_applied_once():
    h = Harness()
    reg = _pilot(h)
    applied = []

    def conquer():
        before = list(reg.goods)
        _conquer(h, VERDANT, KETHANI)
        applied.append([b - a for b, a in zip(before, reg.goods)])
        assert applied[0] == _share(before, 0.5) and sum(applied[0]) > 0
    h.turn(between=conquer)                                 # checked again before the tick: no second loss
    assert h.frame(VERDANT).flows["war_loss"] == sum(applied[0]) and len(_war_records(h)) == 1
    assert reg.war_loss_turn == 11 and reg.war_events == 1
    h.turn()                                                # Phase 2 and before the tick: nothing new
    assert "war_loss" not in h.frame(VERDANT).flows and len(_war_records(h)) == 1


def test_a_conquest_after_the_agent_tick_is_applied_in_its_own_turn():
    """Version 1 applied it at the next Phase 2; version 2 at the event, in the
    turn's own frame."""
    h = Harness()
    reg = _pilot(h)
    owned = []

    def annex(res):
        owned.extend(reg.goods)
        _conquer(h, VERDANT, KETHANI)
    h.turn(granaries=annex)
    assert h.frame(VERDANT).flows["war_loss"] == sum(_share(owned, 0.5))
    h.turn()
    assert "war_loss" not in h.frame(VERDANT).flows


def test_a_conquest_the_hook_did_not_see_is_refused():
    h = Harness()
    _pilot(h)

    def unseen():
        h.world.regions[VERDANT].last_conquered_turn = h.world.turn     # no apply_region_conquest
    with pytest.raises(HR.RetailAccountingError, match="conquest on turn 11 not observed"):
        h.turn(between=unseen)


def test_a_war_loss_after_the_turns_frame_closed_is_refused():
    h = Harness()
    _pilot(h)
    h.world.turn -= 1                                        # still the turn whose frame is closed
    with pytest.raises(RuntimeError, match="after this turn's frame was closed"):
        _requisition(h.world.regions[VERDANT], 0.85, h.world, cause="siege", actor=_civ(h, KETHANI))


# --- d. RL2: siege and occupation ----------------------------------------------------

@pytest.mark.parametrize("cause, survival", [("siege", 0.85), ("occupation", 0.8)])
def test_a_requisition_takes_the_commons_share_of_owned_stock_once_per_call(cause, survival):
    h = Harness()
    reg = _pilot(h)
    seen = []

    def twice():
        for actor in (KETHANI, SELURIAN):                   # two wars, two calls, one turn
            goods, claims = list(reg.goods), dict(reg.claims)
            commons = {g: v for g, v in h.world.regions[VERDANT].stockpile.goods.items() if g in FOOD_GOODS}
            _requisition(h.world.regions[VERDANT], survival, h.world, cause=cause, actor=_civ(h, actor))
            share = _share(goods, survival)
            assert reg.goods == [v - x for v, x in zip(goods, share)]
            taken = {k: claims[k] - reg.claims.get(k, 0) for k in claims}
            assert {k: v for k, v in taken.items() if v} == HR.largest_remainder(sum(share), claims.items())
            for good, v in commons.items():                 # the same event, the same factor
                assert h.world.regions[VERDANT].stockpile.goods[good] == pytest.approx(v * survival)
            seen.append(sum(share))
    h.turn(between=twice)
    assert all(seen) and h.frame(VERDANT).flows["war_loss"] == sum(seen)
    records = _war_records(h)
    assert [_who(r) for r in records] == [(cause, INDEX[a], a, INDEX[THORNWALL], THORNWALL) for a in (KETHANI, SELURIAN)]
    assert h.state.counters[f"war_loss_{cause}_milli"] == sum(seen) and h.state.counters["war_events"] == 2
    assert "requisition_exempt_region_turns" not in h.state.counters


def test_the_rounding_never_takes_more_than_the_decimal_share():
    goods = [100, 20, 7, 1, 0, 33333]
    assert HR._war_share(goods, 0.85) == [15, 3, 2, 1, 0, 5000]           # 85, 17, floor(5.95), floor(0.85)
    assert HR._war_share(goods, 0.8) == [20, 4, 2, 1, 0, 6667]
    assert HR._war_share(goods, 0.5) == [v - v // 2 for v in goods]
    assert HR._war_share(goods, 1.0) == [0] * 6 and HR._war_share(goods, 0.0) == goods
    with pytest.raises(ValueError):
        HR._war_share(goods, 1.5)


def test_siege_turns_and_an_occupation_start_reach_owned_stock_through_the_war_path():
    from chronicler.war.battles import siege_turn
    from chronicler.war.occupation import start_occupation
    h = Harness()
    reg = _pilot(h)
    world = h.world
    ctx, war = start_war(world, KETHANI, THORNWALL)
    region = world.regions[VERDANT]
    army = place_army(world, KETHANI, region.name, 40, war.war_key)
    steps = []

    def besiege_then_occupy():
        for event in ("siege", "occupation"):
            goods = list(reg.goods)
            if event == "siege":
                assert siege_turn(ctx, war, region, [army], _civ(h, KETHANI), _civ(h, THORNWALL)) is False
                share = _share(goods, 0.85)
            else:
                start_occupation(ctx, region, _civ(h, KETHANI), war, army)
                share = _share(goods, 0.8)
            assert reg.goods == [v - x for v, x in zip(goods, share)]
            steps.append(sum(share))
        # A region outside the pilot (Thornwood, not a capital) holds no owned
        # stock; a pilot region without owned food counts and records the event
        # with no loss (review A5, finding 3).
        assert HR.on_war_loss(world, world.regions[THORNWOOD], 0.85, cause="siege", actor=_civ(h, KETHANI)) == 0
        assert HR.on_war_loss(world, world.regions[ASHARA], 0.85, cause="siege", actor=_civ(h, KETHANI)) == 0
    h.turn(between=besiege_then_occupy)
    records = _war_records(h)
    assert [(r.region, r.cause, r.actor_name, r.victim_name, r.milli) for r in records] == [
        (VERDANT, "siege", KETHANI, THORNWALL, steps[0]), (VERDANT, "occupation", KETHANI, THORNWALL, steps[1]),
        (ASHARA, "siege", KETHANI, SELURIAN, 0)]
    assert [r.note for r in records] == [f"besieged by {KETHANI}", f"occupied by {KETHANI}", f"besieged by {KETHANI}"]
    assert (records[2].actor, records[2].victim) == (INDEX[KETHANI], INDEX[SELURIAN])
    assert h.state.region(ASHARA).war_events == 1 and THORNWOOD not in HR.pilot_regions(world)
    assert reg.war_events == 2 and h.state.counters["war_events"] == 3
    assert {k: h.state.counters.get(f"war_loss_{k}_milli", 0) for k in WAR_CAUSES} == {
        "conquest": 0, "siege": steps[0], "occupation": steps[1]}


def test_a_requisition_of_owned_stock_needs_its_cause():
    h = Harness()
    _pilot(h)
    with pytest.raises(ValueError, match="needs its cause"):
        h.turn(between=lambda: _requisition(h.world.regions[VERDANT], 0.85, h.world))


# --- e, f. war with death and with the loss of the controller -------------------

def test_an_owner_dead_the_same_turn_leaves_the_claim_reduced_by_the_war_to_the_heir():
    h = Harness()
    reg = _pilot(h, people=(1, 2, 3))
    h.sim.add(5, VERDANT, occupation=2, wealth=0.0)          # 1's spouse
    h.sim.marry(1, 5)
    h.sim.die_before = set()
    seen = {}

    def siege():
        claims = dict(reg.claims)
        _requisition(h.world.regions[VERDANT], 0.85, h.world, cause="siege", actor=_civ(h, KETHANI))
        seen["before"], seen["after"] = claims[1], reg.claims[1]
        h.sim.die_before = {1}                              # dies before provisioning: withheld whole
    h.turn(between=siege)
    installed = {(o, r): m for o, r, m in _calls(h.sim, "set_household_retail")[-1][4]}
    assert installed[(1, VERDANT)] == seen["after"] < seen["before"]
    (inherited,) = [r for r in h.state.log if r.kind == "inherited" and r.owner == 1]
    assert (inherited.other, inherited.milli) == (5, seen["after"])
    frame = h.frame(VERDANT)
    assert frame.flows["inherited_in"] == frame.flows["inherited_out"] == seen["after"]
    assert frame.open_milli - sum(v for k, v in frame.flows.items() if k not in ("inherited_in", "inherited_out")
                                  ) == frame.close_milli == sum(reg.claims.values())


def test_a_conquest_then_the_loss_of_the_controller_lose_once_then_close_once():
    h = Harness()
    reg = _pilot(h)

    def conquer_then_abandon():
        _conquer(h, VERDANT, KETHANI)
        h.world.regions[VERDANT].controller = None
    h.turn(between=conquer_then_abandon)
    assert h.frame(VERDANT).flows["war_loss"] > 0 and len(_war_records(h)) == 1
    left = sum(reg.goods)
    h.turn()                                                 # the next Phase 2 closes it to the commons
    frame = h.frame(VERDANT)
    assert "war_loss" not in frame.flows and frame.commons["pilot_closed"] == left > 0
    assert VERDANT not in HR.pilot_regions(h.world) and len(_war_records(h)) == 1
    assert [r.kind for r in h.state.log if r.region == VERDANT][-2:] == ["war_loss", "pilot_closed"]


# --- g. feature off, version 1, record_only, inactive ---------------------------

@pytest.mark.parametrize("case", ["no_livelihoods", "l2_only", "rules_1", "rules_1_record_only", "not_hybrid"])
def test_the_hooks_are_no_ops_outside_an_active_version_2_pilot(case, monkeypatch):
    # Version 2 record_only records each event with no loss: test_record_only_...
    if case == "no_livelihoods":
        world = generate_world(seed=42)
    else:
        flags = {"rules_1": V1, "rules_1_record_only": (*V1, "--household-retail-mode", "record_only")}.get(case, ())
        h = Harness(*flags, retail=case != "l2_only")
        _people(h, VERDANT, (1, 2), wealth=0.0)
        h.turn({VERDANT: {"grain": 6.0}})
        world = h.world
        if case == "not_hybrid":
            world.agent_mode = "shadow"
    monkeypatch.setattr(HR, "_apply_war_loss", lambda *a, **k: pytest.fail("a war loss was applied"))
    retail = getattr(world.livelihoods, "household_retail", None) if world.livelihoods is not None else None
    before = retail.model_dump_json() if retail is not None else None
    rng, np_rng = random.getstate(), np.random.get_state()
    region = world.regions[VERDANT]
    kethani = world.civ_map[KETHANI]
    _requisition(region, 0.85, world, cause="siege", actor=kethani)
    _requisition(region, 0.8, world)                          # no cause: only an active v2 pilot needs one
    from chronicler.action_engine import apply_region_conquest
    apply_region_conquest(kethani, world.civ_map[THORNWALL], region, world, seed=1)
    assert random.getstate() == rng and all(np.array_equal(a, b) if isinstance(a, np.ndarray) else a == b
                                            for a, b in zip(np.random.get_state(), np_rng))
    if retail is not None:
        assert retail.model_dump_json() == before
        assert "war_events" not in retail.counters


# --- h. serialization ------------------------------------------------------------

#: Field orders of the retail models at 8abc1acb (checkpoint 3): a version-1
#: state serializes exactly these keys, in this order.
STATE_KEYS_8ABC = ["schema_version", "enabled", "mode", "boundary", "regions", "last_title_turn",
                   "last_settled_turn", "last_procured_turn", "frame_turn", "frame", "money", "income", "sample",
                   "sample_dropped", "log", "log_dropped", "counters", "income_replaced_total"]
REGION_KEYS_8ABC = ["region", "opened_turn", "reason", "goods", "claims", "totals", "war_loss_turn"]
RECORD_KEYS_8ABC = ["turn", "region", "kind", "milli", "owner", "other", "note"]


def test_a_version_1_state_serializes_exactly_the_checkpoint_3_fields():
    h = Harness(*V1)
    _pilot(h)
    h.turn(between=lambda: _conquer(h, VERDANT, KETHANI))
    state = h.state
    assert any(r.kind == "war_loss" for r in state.log) and state.region(VERDANT).claims
    for dump in (json.loads(state.model_dump_json()), state.model_dump()):
        assert list(dump) == STATE_KEYS_8ABC
        assert all(list(r) == REGION_KEYS_8ABC for r in dump["regions"])
        assert all(list(r) == RECORD_KEYS_8ABC for r in dump["log"])
    assert "rules_version" not in LV.livelihoods_snapshot_fields(h.world)["livelihoods"]["household_retail"]
    world_json = json.loads(h.world.model_dump_json())["livelihoods"]["household_retail"]
    assert list(world_json) == STATE_KEYS_8ABC


#: SHA-256 of the per-turn world JSON and livelihoods snapshot of
#: :func:`_v1_history` written by the reference source 8abc1acb (no rules
#: option: checkpoint 3's only rules), recorded by the A5 review's
#: ``probe_v1_identity.py``; ``--household-retail-rules 1`` must keep the bytes.
V1_HISTORY_SHA256_8ABC = "18d5e35863ca47f1f5bd08f948c7ae00e29041be287cb82f6ff7a486ef1994d3"


def _v1_history(*flags) -> str:
    """A war, death and late-conquest history (the A5 review's probe), as the
    JSON of each turn's world and livelihoods snapshot."""
    from chronicler.war.battles import siege_turn
    from chronicler.war.occupation import start_occupation
    h = Harness(*flags) if flags else Harness()
    out = []

    def dump(tag):
        out.append({"tag": tag, "world": h.world.model_dump_json(),
                    "snap": json.dumps(LV.livelihoods_snapshot_fields(h.world), sort_keys=False)})
    _people(h, VERDANT, (1, 2, 3, 4), wealth=0.0)
    _people(h, ASHARA, (11, 12), wealth=0.0)
    h.sim.add(5, VERDANT, occupation=2, wealth=0.0)
    h.sim.marry(1, 5)
    h.turn({VERDANT: {"grain": 9.0, "fish": 1.3}, ASHARA: {"grain": 4.0}})
    dump("t1")
    world = h.world
    ctx, war = start_war(world, KETHANI, THORNWALL)
    region = world.regions[VERDANT]
    army = place_army(world, KETHANI, region.name, 40, war.war_key)

    def siege_occ():
        siege_turn(ctx, war, region, [army], world.civ_map[KETHANI], world.civ_map[THORNWALL])
        start_occupation(ctx, region, world.civ_map[KETHANI], war, army)
    h.turn({VERDANT: {"grain": 5.0}}, between=siege_occ)
    dump("t2-siege-occ")

    def two():
        _conquer(h, VERDANT, KETHANI)
        _conquer(h, VERDANT, SELURIAN)
    h.sim.die_before = {1}
    h.turn({VERDANT: {"grain": 5.0}}, between=two)
    dump("t3-two-conquests-death")
    h.sim.die_before = set()
    h.turn({VERDANT: {"grain": 5.0}}, granaries=lambda res: _conquer(h, VERDANT, KETHANI))
    dump("t4-late-conquest")
    h.turn({VERDANT: {"grain": 5.0}})
    dump("t5")
    h.turn()
    dump("t6")
    return json.dumps(out)


def test_rules_1_keeps_the_reference_bytes_of_a_war_history():
    """Review A5, finding 6a: bytes, not key orders. The world JSON and the
    snapshot of every turn under ``--household-retail-rules 1`` hash to what
    8abc1acb wrote for the same history; version 2 differs."""
    import hashlib
    assert hashlib.sha256(_v1_history(*V1).encode()).hexdigest() == V1_HISTORY_SHA256_8ABC
    assert hashlib.sha256(_v1_history().encode()).hexdigest() != V1_HISTORY_SHA256_8ABC


def test_the_rules_versions_agree_with_the_option_and_the_state_field():
    """Review A5, nit 1."""
    from typing import get_args
    from chronicler.household_retail_state import RULES_VERSIONS
    assert tuple(str(v) for v in sorted(RULES_VERSIONS, reverse=True)) == LV.LIVELIHOODS_CHOICES[
        "household_retail_rules"]
    assert get_args(HouseholdRetailState.model_fields["rules_version"].annotation) == RULES_VERSIONS
    assert RULES_VERSIONS[-1] == RULES_VERSION


def test_record_only_records_each_war_event_with_no_loss_and_version_1_is_unchanged():
    """Review A5, finding 2: a version-2 ``record_only`` arm holds nothing, but
    each conquest, siege turn and occupation start of a pilot region is counted
    and recorded with its cause, actor and victim (milli 0), so the control arm
    keeps its war exposure. Version 1 still logs its one zero-loss conquest
    record per turn and nothing for the siege."""
    from chronicler.war.battles import siege_turn
    from chronicler.war.occupation import start_occupation
    out = {}
    for name, flags in (("v1", V1), ("v2", ())):
        h = Harness("--household-retail-mode", "record_only", *flags)
        _people(h, VERDANT, (1, 2), wealth=0.0)
        h.turn({VERDANT: {"grain": 6.0}})
        world = h.world
        ctx, war = start_war(world, KETHANI, THORNWALL)
        region = world.regions[VERDANT]
        army = place_army(world, KETHANI, region.name, 40, war.war_key)

        def events():
            siege_turn(ctx, war, region, [army], world.civ_map[KETHANI], world.civ_map[THORNWALL])
            start_occupation(ctx, region, world.civ_map[KETHANI], war, army)
            _conquer(h, VERDANT, KETHANI)
        h.turn(between=events)
        h.turn()                                                       # the observed check passes
        out[name] = ([(r.milli, r.cause, r.actor, r.victim, r.note) for r in _war_records(h)], dict(h.state.counters))
        assert h.state.regions[0].goods == [0] * 5 and not h.state.regions[0].claims
    v1_records, v1_counters = out["v1"]
    assert v1_records == [(0, None, None, None, f"conquered by {KETHANI} on turn 11")]
    assert "war_events" not in v1_counters
    v2_records, v2_counters = out["v2"]
    assert v2_records == [
        (0, "siege", INDEX[KETHANI], INDEX[THORNWALL], f"besieged by {KETHANI} (record_only: nothing held)"),
        (0, "occupation", INDEX[KETHANI], INDEX[THORNWALL], f"occupied by {KETHANI} (record_only: nothing held)"),
        (0, "conquest", INDEX[KETHANI], INDEX[THORNWALL],
         f"conquered by {KETHANI} from {THORNWALL} (won in war) (record_only: nothing held)")]
    assert v2_counters["war_events"] == 3 and "war_loss_milli" not in v2_counters


def test_a_record_only_conquest_then_retail_on_resume_runs_on():
    """Review A5, finding 6b: a ``record_only`` conquest, the next turn, then the
    switch to ``retail`` on a resume (the observed marker followed)."""
    h = Harness("--household-retail-mode", "record_only")
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.turn({VERDANT: {"grain": 6.0}})
    h.turn(between=lambda: _conquer(h, VERDANT, KETHANI))
    h.turn()
    assert h.state.region(VERDANT).war_loss_turn == 11
    h.world = pickle.loads(pickle.dumps(h.world))
    configure_livelihoods(h.world, parse(["--household-retail", "--household-retail-mode", "retail"]),
                          agent_mode="hybrid")
    h.turn({VERDANT: {"grain": 6.0}})
    h.turn()
    assert h.state.mode == "retail" and h.state.region(VERDANT).claims


@pytest.mark.parametrize("via, how", [("consolidated", "annexed after a long occupation"),
                                      ("owner_gone", "annexed as its former rulers vanish"),
                                      ("treaty", "ceded by treaty")])
def test_an_annexation_names_its_path(via, how):
    """Review A5, finding 6c: the annexation paths' notes."""
    from chronicler.action_engine import apply_region_conquest
    h = Harness()
    reg = _pilot(h)
    goods = []

    def annex():
        goods.extend(reg.goods)
        region = h.world.regions[VERDANT]
        apply_region_conquest(_civ(h, KETHANI), _civ(h, THORNWALL), region, h.world, seed=1, via=via)
    h.turn(between=annex)
    (record,) = _war_records(h)
    assert record.note == f"conquered by {KETHANI} from {THORNWALL} ({how})"
    assert (record.cause, record.actor, record.victim, record.milli) == (
        "conquest", INDEX[KETHANI], INDEX[THORNWALL], sum(_share(goods, 0.5)))


def test_a_reconquest_by_the_original_owner_then_an_occupation_in_one_turn():
    """Review A5, finding 6d: Thornwall loses Verdant to Kethani, retakes it,
    and Selurian occupies it, all in one turn: three events, each once, with
    the right actor and victim, and the books close."""
    from chronicler.war.occupation import start_occupation
    h = Harness()
    reg = _pilot(h)
    seen = {}

    def events():
        seen["before"] = list(reg.goods)
        _conquer(h, VERDANT, KETHANI)
        _conquer(h, VERDANT, THORNWALL)
        ctx, war = start_war(h.world, SELURIAN, THORNWALL)
        army = place_army(h.world, SELURIAN, h.world.regions[VERDANT].name, 40, war.war_key)
        start_occupation(ctx, h.world.regions[VERDANT], _civ(h, SELURIAN), war, army)
        seen["after"] = list(reg.goods)
    h.turn(between=events)
    assert [_who(r)[0:2] + (r.victim_name,) for r in _war_records(h)] == [
        ("conquest", INDEX[KETHANI], THORNWALL), ("conquest", INDEX[THORNWALL], KETHANI),
        ("occupation", INDEX[SELURIAN], THORNWALL)]
    first = _share(seen["before"], 0.5)
    second = _share([v - x for v, x in zip(seen["before"], first)], 0.5)
    third = _share([v - x - y for v, x, y in zip(seen["before"], first, second)], 0.8)
    assert seen["after"] == [v - x - y - z for v, x, y, z in zip(seen["before"], first, second, third)]
    assert reg.war_events == 3 and h.frame(VERDANT).flows["war_loss"] == sum(seen["before"]) - sum(seen["after"])
    h.turn()


def test_a_version_2_state_round_trips_json_and_pickle_and_old_pickles_restore_as_version_1():
    from chronicler.models import WorldState
    h = Harness()
    _pilot(h)
    h.turn(between=lambda: _requisition(h.world.regions[VERDANT], 0.85, h.world, cause="siege",
                                        actor=_civ(h, KETHANI)))
    state = h.state
    dump = json.loads(state.model_dump_json())
    assert dump["rules_version"] == 2 and all(r["war_events"] >= 0 for r in dump["regions"])
    (record,) = [r for r in dump["log"] if r["kind"] == "war_loss"]
    assert list(record) == RECORD_KEYS_8ABC + ["cause", "actor", "actor_name", "victim", "victim_name"]
    assert all("cause" not in r for r in dump["log"] if r["kind"] != "war_loss")
    loaded = WorldState.model_validate_json(h.world.model_dump_json())
    assert loaded.livelihoods.household_retail == state and loaded.model_dump_json() == h.world.model_dump_json()
    back = pickle.loads(pickle.dumps(h.world))
    assert back.livelihoods.household_retail == state and back.model_dump_json() == h.world.model_dump_json()
    summary = LV.livelihoods_snapshot_fields(h.world)["livelihoods"]["household_retail"]
    assert summary["rules_version"] == 2 and summary["log"][-1]["cause"] == "siege"
    # Pickles written before A5 lack every new field: they restore as version 1.
    raw = state.__getstate__()
    raw["__dict__"] = {k: v for k, v in raw["__dict__"].items() if k != "rules_version"}
    old = HouseholdRetailState.__new__(HouseholdRetailState)
    old.__setstate__(raw)
    assert old.rules_version == 1
    for model, values in ((RetailRegion, {"region": 0, "opened_turn": 0, "reason": "capital"}),
                          (RetailRecord, {"turn": 0, "region": 0, "kind": "war_loss"})):
        raw = model(**values).__getstate__()
        raw["__dict__"] = {k: v for k, v in raw["__dict__"].items() if k in values}
        restored = model.__new__(model)
        restored.__setstate__(raw)
        assert restored == model(**values)


# --- i. RL3: saved switches outside hybrid ---------------------------------------

def test_a_saved_food_allocation_outside_hybrid_is_refused_cleanly_with_its_hint():
    h = Harness(retail=False)
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.turn({VERDANT: {"grain": 6.0}})
    before = h.world.model_dump_json()
    for mode in ("off", "shadow", "demographics-only"):
        with pytest.raises(LivelihoodsRefusal) as refused:
            configure_livelihoods(h.world, parse([]), agent_mode=mode)
        exc = refused.value
        # A plain ValueError (review A5, finding 4): never a SystemExit.
        assert isinstance(exc, ValueError) and not isinstance(exc, SystemExit)
        assert "this world has it on" in str(exc) and "--no-food-allocation" in str(exc)
        assert exc.code == f"Error: {exc}"
        assert pickle.loads(pickle.dumps(exc)).code == exc.code
        assert h.world.model_dump_json() == before            # refused before any change
    # An explicit request outside hybrid stays the plain refusal it was.
    with pytest.raises(ValueError) as plain:
        configure_livelihoods(generate_world(seed=42), parse(["--food-allocation"]), agent_mode="off")
    assert type(plain.value) is ValueError
    # The hint works: the switch ends, outside hybrid.
    configure_livelihoods(h.world, parse(["--no-food-allocation"]), agent_mode="off")
    assert not h.world.livelihoods.food_allocation.enabled


def test_a_saved_retail_world_outside_hybrid_is_refused_cleanly_with_its_hint():
    h = Harness()
    _pilot(h)
    with pytest.raises(LivelihoodsRefusal, match="pass --no-household-retail to end it") as refused:
        configure_livelihoods(h.world, parse([]), agent_mode="off")
    assert refused.value.code.startswith("Error: --household-retail requires --agents hybrid")
    with pytest.raises(LivelihoodsRefusal, match="--no-food-allocation"):
        configure_livelihoods(h.world, parse(["--no-household-retail"]), agent_mode="off")
    configure_livelihoods(h.world, parse(["--no-household-retail", "--no-food-allocation"]), agent_mode="off")
    assert not h.state.enabled and h.state.regions == []


def test_a_legacy_resume_of_a_saved_retail_world_without_hybrid_exits_without_a_traceback(tmp_path, monkeypatch,
                                                                                          capsys):
    """The CLI path (``main``): the refusal reaches the top level as the plain
    ``ValueError`` it is, before any turn runs or any output is written; the
    interpreter's exception hook, installed by the refusal, prints its one line
    and nothing else (the exit status 1 and the absent traceback of a real
    process are checked in ``test_household_retail_war_native.py``)."""
    from chronicler.main import main
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)       # restored after the test
    h = Harness()
    _pilot(h)
    saved = tmp_path / "state.json"
    h.world.save(saved)
    out = tmp_path / "resumed"
    monkeypatch.setattr(sys, "argv", ["chronicler", "--resume", str(saved), "--simulate-only", "--turns", "14",
                                      "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
    with pytest.raises(LivelihoodsRefusal) as refused:
        main()
    exc = refused.value
    assert not isinstance(exc, SystemExit)
    assert exc.code.startswith("Error: --household-retail requires --agents hybrid and --food-allocation; "
                               "this world has it on: pass --no-household-retail")
    assert not (out / "chronicle_bundle.json").exists() and not (out / "state.json").exists()
    capsys.readouterr()
    sys.excepthook(type(exc), exc, exc.__traceback__)
    assert capsys.readouterr().err == exc.code + "\n"
    # Any other exception still goes to the previous hook (a full traceback).
    try:
        raise ValueError("another")
    except ValueError as other:
        sys.excepthook(type(other), other, other.__traceback__)
    err = capsys.readouterr().err
    assert err.startswith("Traceback") and err.rstrip().endswith("ValueError: another")


def test_a_refusal_in_a_thread_or_task_is_an_ordinary_error(monkeypatch):
    """Review A5, finding 4: a thread reports the refusal (a ``SystemExit``
    would end it silently) and asyncio raises it to its caller."""
    import asyncio
    import threading
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    h = Harness(retail=False)
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.turn({VERDANT: {"grain": 6.0}})
    seen = []
    monkeypatch.setattr(threading, "excepthook", lambda hook_args: seen.append(hook_args.exc_type))
    worker = threading.Thread(target=configure_livelihoods, args=(h.world, parse([])), kwargs={"agent_mode": "off"})
    worker.start()
    worker.join()
    assert seen == [LivelihoodsRefusal]

    async def configure():
        configure_livelihoods(h.world, parse([]), agent_mode="off")
    with pytest.raises(LivelihoodsRefusal):
        asyncio.run(configure())


def test_a_live_lobby_resume_refused_by_a_saved_switch_reopens_the_lobby(tmp_path, monkeypatch):
    """Review A5, finding 4: a lobby ``start`` resuming a saved L2 world under
    a server without --agents hybrid is refused at the lobby (reported to the
    viewer as ``resume_state``), and the server keeps running: the next start
    proceeds. A plain refusal without features still fails the run
    (``test_feature_catalog.py::test_a_refusal_without_features_still_fails_the_run``)."""
    from tests.test_feature_catalog import _LobbyServer, _run_live_until_execute
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    h = Harness(retail=False)
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.turn({VERDANT: {"grain": 6.0}})
    saved = json.loads(h.world.model_dump_json())
    server = _LobbyServer([{"turns": 12, "civs": 4, "regions": 8, "resume_state": saved},
                           {"turns": 3, "civs": 2, "regions": 3, "seed": 7}])
    args, seen = _run_live_until_execute(tmp_path, monkeypatch, server)
    assert server.replies == [None, None]
    (message,) = server.reopened
    assert message.startswith("Start field 'resume_state': --food-allocation requires --agents hybrid; "
                              "this world has it on")
    assert server.status_queue.get_nowait() == {"type": "error", "message": message}
    # The second start, a new world, reached the run.
    assert seen["world"].livelihoods is None and seen["world"].turn == 0


# --- the checkpoint 2-3 screens keep version 1 -----------------------------------

def test_the_checkpoint_2_and_3_screens_rerun_retail_under_rules_1(monkeypatch, tmp_path):
    """Checkpoints 2 and 3 ran retail's only rules, now version 1: their screen
    definitions pass ``--household-retail-rules 1`` to every retail run (after the
    outputs), so a rerun at this source keeps them; arms without retail pass nothing."""
    import importlib.util
    import subprocess
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "productive_recovery_screens.py"
    spec = importlib.util.spec_from_file_location("productive_recovery_screens_a5_under_test", path)
    S = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(S)
    assert S.RULES == {} and S.rules_flags([*S.BASE, "--household-retail"]) == []          # checkpoint 1
    for cp in (S.CP2, S.CP3):
        assert cp.RULES == {"--household-retail": ("--household-retail-rules", "1")}
        S.check_extractor(cp)
        S.check_arm_flags(cp)
    assert S.rules_flags([*S.CP3.BASE, *S.CP3.ARMS["C0"][0]], S.CP3) == ["--household-retail-rules", "1"]
    assert S.rules_flags([*S.CP3.BASE, *S.CP3.ARMS["CH_L2"][0]], S.CP3) == []
    assert S.rules_flags([*S.CP2.BASE, *S.CP2.ARMS["L2"][0]], S.CP2) == []
    called = []
    monkeypatch.setattr(S, "simulate", lambda cmd: called.append(cmd) or subprocess.CompletedProcess(cmd, 1))
    S.run_one(tmp_path, "pilot", "R", "template", 5, [], False, S.CP2)
    assert called[0][-4:-2] == ["--state", str((tmp_path / "runs" / "R-template5" / "state.json").resolve())]
    assert called[0][-2:] == ["--household-retail-rules", "1"]
