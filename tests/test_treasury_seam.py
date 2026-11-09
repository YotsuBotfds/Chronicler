"""Treasury seam (turn-loop consolidation, CON-3).

The golden ``tests/fixtures/turn_loop/accumulator_trace.json`` was recorded
with ``tests/support/accumulator_trace.py`` before the seam existed: every
``StatAccumulator.add`` and the end-of-turn civ stats of 12 ``--agents off``
turns per case. Every treasury refactor must reproduce it unchanged.

Also: ``treasury_delta`` against the literal dual-path expressions it
replaces, ``apply``/``apply_keep`` against their bodies before the shared
``_apply_change``, and ``queued_changes`` against each private-field fold.
"""
from __future__ import annotations

import copy
import inspect
import json
import random

import pytest

from chronicler.accumulator import ROUTING_CATEGORIES, StatAccumulator, UNBOUNDED_STATS
from chronicler.models import Civilization, Leader, StatChange, TechEra
from chronicler.treasury import TREASURY_REASON_KINDS, TREASURY_REASONS, treasury_delta
from chronicler.utils import STAT_FLOOR, civ_index
from tests.support import accumulator_trace as AT

TRACE = AT.load()
TRACE_CASES = [(kind, seed, techniques) for kind, techniques in AT.CASES for seed in AT.SEEDS]


def _case_name(kind, seed, techniques):
    return f"{kind}_s{seed}" + ("_techniques" if techniques else "")


def test_accumulator_trace_golden_shape():
    assert TRACE["schema_version"] == AT.SCHEMA_VERSION
    assert TRACE["turns"] == AT.TURNS
    assert TRACE["stats"] == list(AT.TRACE_STATS)
    assert list(TRACE["cases"]) == [_case_name(*case) for case in TRACE_CASES]
    for rows in TRACE["cases"].values():
        assert [row[1] for row in rows if row[0] == "end"] == list(range(AT.TURNS))
        assert any(row[0] == "add" and row[3] == "treasury" for row in rows)


@pytest.mark.parametrize("kind,seed,techniques", TRACE_CASES,
                         ids=[_case_name(*case) for case in TRACE_CASES])
def test_accumulator_trace_matches_golden(kind, seed, techniques):
    records = AT.trace_run(AT.build_world(kind, seed, techniques), seed)
    assert json.loads(json.dumps(records)) == TRACE["cases"][_case_name(kind, seed, techniques)]


# --- treasury_delta: the helper against the literal dual-path expressions ----

DELTAS = (0, 7, -3, -500, 2.5, -0.5)


def _world():
    return AT.sample_world(42)


def _ghost():
    return Civilization(name="Ghost", population=10, military=10, economy=10, culture=10,
                        stability=10, tech_era=TechEra.IRON, treasury=5,
                        leader=Leader(name="Nobody", trait="cautious", reign_start=0), regions=[])


@pytest.mark.parametrize("delta", DELTAS)
@pytest.mark.parametrize("floor0", [False, True])
@pytest.mark.parametrize("given_index", [False, True])
def test_treasury_delta_accumulator_branch_is_the_old_add(delta, floor0, given_index):
    old_world, new_world = _world(), _world()
    old_acc, new_acc = StatAccumulator(), StatAccumulator()
    for idx in (1, 0):
        old_civ, new_civ = old_world.civilizations[idx], new_world.civilizations[idx]
        old_acc.add(civ_index(old_world, old_civ.name), old_civ, "treasury", delta, "keep")
        treasury_delta(new_world, new_acc, new_civ, delta, reason="test", floor0=floor0,
                       civ_idx=idx if given_index else None)
    assert new_acc._changes == old_acc._changes  # zero deltas are recorded too
    assert [c.treasury for c in new_world.civilizations] == [c.treasury for c in old_world.civilizations]


@pytest.mark.parametrize("delta", DELTAS)
@pytest.mark.parametrize("start", [0, 4, 120])
def test_treasury_delta_direct_branch_is_the_old_write(delta, start):
    old_civ, new_civ, floored_civ, old_floored = _ghost(), _ghost(), _ghost(), _ghost()
    for civ in (old_civ, new_civ, floored_civ, old_floored):
        civ.treasury = start
    old_civ.treasury += delta
    old_floored.treasury = max(0, old_floored.treasury + delta)
    # The Ghost is in no world: a direct write never looks its index up.
    treasury_delta(None, None, new_civ, delta, reason="test")
    treasury_delta(None, None, floored_civ, delta, reason="test", floor0=True)
    assert (new_civ.treasury, type(new_civ.treasury)) == (old_civ.treasury, type(old_civ.treasury))
    assert ((floored_civ.treasury, type(floored_civ.treasury))
            == (old_floored.treasury, type(old_floored.treasury)))


def test_treasury_delta_index_is_lazy_and_reason_required():
    world, acc, ghost = _world(), StatAccumulator(), _ghost()
    treasury_delta(world, None, ghost, -2, reason="test")  # not in the map: no lookup
    assert ghost.treasury == 3
    treasury_delta(None, acc, ghost, -2, reason="test", civ_idx=0)  # given index: no lookup
    assert acc._changes == [StatChange(0, "treasury", -2, "keep", 3)]
    with pytest.raises(ValueError):  # as civ_index(world, name) raised before
        treasury_delta(world, acc, ghost, -2, reason="test")
    with pytest.raises(TypeError):
        treasury_delta(world, None, ghost, -2)
    assert inspect.signature(treasury_delta).parameters["reason"].kind is inspect.Parameter.KEYWORD_ONLY


def test_treasury_reasons_use_the_declared_kinds():
    assert TREASURY_REASON_KINDS == ("fiat", "sink", "transfer", "restore")
    assert set(TREASURY_REASONS.values()) <= set(TREASURY_REASON_KINDS)


# --- StatAccumulator.apply / apply_keep: unchanged by the shared helper ------

def _old_apply(acc, world):
    """Verbatim body of StatAccumulator.apply before _apply_change."""
    for c in acc._changes:
        civ = world.civilizations[c.civ_id]
        current = getattr(civ, c.stat)
        new_val = current + c.delta
        if c.stat in UNBOUNDED_STATS:
            new_val = max(new_val, 0)
        else:
            floor = STAT_FLOOR.get(c.stat, 0)
            new_val = max(floor, min(100, new_val))
        setattr(civ, c.stat, type(current)(new_val))


def _old_apply_keep(acc, world):
    """Verbatim body of StatAccumulator.apply_keep before _apply_change."""
    start = acc._keep_applied_up_to
    for i in range(start, len(acc._changes)):
        c = acc._changes[i]
        if c.category != "keep":
            continue
        civ = world.civilizations[c.civ_id]
        current = getattr(civ, c.stat)
        new_val = current + c.delta
        if c.stat in UNBOUNDED_STATS:
            new_val = max(new_val, 0)
        else:
            floor = STAT_FLOOR.get(c.stat, 0)
            new_val = max(floor, min(100, new_val))
        setattr(civ, c.stat, type(current)(new_val))
    acc._keep_applied_up_to = len(acc._changes)


APPLY_STATS = ("treasury", "asabiya", "prestige", "population", "military", "economy",
               "culture", "stability")


def _script(rng):
    """Random adds with flushes in between: ("add", civ, stat, delta, category) | ("keep",)."""
    steps = []
    for _ in range(rng.randrange(5, 60)):
        if rng.random() < 0.15:
            steps.append(("keep",))
            continue
        delta = rng.choice((rng.randint(-120, 120), round(rng.uniform(-30, 30), 3), 0))
        steps.append(("add", rng.randrange(2), rng.choice(APPLY_STATS), delta,
                      rng.choice(sorted(ROUTING_CATEGORIES))))
    return steps


def _stats(world):
    return [[(getattr(c, s), type(getattr(c, s))) for s in APPLY_STATS] for c in world.civilizations]


def _replay(steps, keep, final):
    world, acc = _world(), StatAccumulator()
    for step in steps:
        if step[0] == "keep":
            keep(acc, world)
        else:
            _, idx, stat, delta, category = step
            acc.add(idx, world.civilizations[idx], stat, delta, category)
    final(acc, world)
    return _stats(world), list(acc._changes), acc._keep_applied_up_to


@pytest.mark.parametrize("seed", range(40))
def test_apply_and_apply_keep_match_the_old_bodies(seed):
    steps = _script(random.Random(seed))
    new_keep, old_keep = StatAccumulator.apply_keep, _old_apply_keep
    adds = [step for step in steps if step[0] == "add"]
    # Aggregate mode: one apply() at the end.
    assert _replay(adds, new_keep, StatAccumulator.apply) == _replay(adds, old_keep, _old_apply)
    # Agent modes: repeated apply_keep() flushes (the watermark), then a last one.
    assert _replay(steps, new_keep, new_keep) == _replay(steps, old_keep, old_keep)


# --- queued_changes: the public reader against each private-field fold -------
# Each oracle is the fold's body as of this commit; each "new" spelling is the
# same arithmetic over acc.queued_changes(...), as the call sites will read it.

def _war_old(world, civ, acc):  # war/common.py projected_treasury
    value = float(civ.treasury)
    if acc is not None:
        idx = civ_index(world, civ.name)
        start = getattr(acc, "_keep_applied_up_to", 0)
        for change in getattr(acc, "_changes", ())[start:]:
            if change.civ_id == idx and change.stat == "treasury" and change.category == "keep":
                value += change.delta
    return int(value)


def _diplomacy_old(world, civ, acc):  # diplomacy.py _projected_treasury
    value = float(civ.treasury)
    if acc is not None:
        idx = civ_index(world, civ.name)
        start = getattr(acc, "_keep_applied_up_to", 0)
        for change in getattr(acc, "_changes", ())[start:]:
            if change.civ_id == idx and change.stat == "treasury" and change.category == "keep":
                value += change.delta
    return int(value)


def _unfloored_new(world, civ, acc):  # war/common.py and diplomacy.py
    value = float(civ.treasury)
    if acc is not None:
        for change in acc.queued_changes(civ_index(world, civ.name), "treasury"):
            value += change.delta
    return int(value)


def _gp_agendas_old(world, civ, acc):  # gp_agendas.py _projected_treasury (after COR-10)
    civ_idx = civ_index(world, civ.name)
    projected = int(civ.treasury)
    if acc is None:
        return projected
    start = getattr(acc, "_keep_applied_up_to", 0)
    for change in getattr(acc, "_changes", ())[start:]:
        if change.civ_id == civ_idx and change.category == "keep" and change.stat == "treasury":
            projected += change.delta
    return projected


def _gp_agendas_new(world, civ, acc):
    projected = int(civ.treasury)
    if acc is None:
        return projected
    for change in acc.queued_changes(civ_index(world, civ.name), "treasury"):
        projected += change.delta
    return projected


def _clearing_old(world, civ, acc):  # clearing_protection.py projected_treasury
    civ_idx = civ_index(world, civ.name)
    civ = world.civilizations[civ_idx]
    budget = civ.treasury
    if acc is None:
        return float(budget)
    every = getattr(world, "agent_mode", None) in (None, "off")
    start = 0 if every else acc._keep_applied_up_to
    for change in acc._changes[start:]:
        if change.civ_id == civ_idx and change.stat == "treasury" and (every or change.category == "keep"):
            budget = type(civ.treasury)(max(0, budget + change.delta))
    return float(budget)


def _clearing_new(world, civ, acc):
    civ_idx = civ_index(world, civ.name)
    civ = world.civilizations[civ_idx]
    budget = civ.treasury
    if acc is None:
        return float(budget)
    every = getattr(world, "agent_mode", None) in (None, "off")
    for change in acc.queued_changes(civ_idx, "treasury", None if every else "keep",
                                     unapplied_only=not every):
        budget = type(civ.treasury)(max(0, budget + change.delta))
    return float(budget)


def _mutual_aid_old(world, civ, acc):  # mutual_aid.py _treasury_budget
    budget = float(civ.treasury)
    if acc is not None:
        civ_idx = world.civ_index_map[civ.name]
        for change in acc._changes[acc._keep_applied_up_to:]:
            if (change.civ_id == civ_idx and change.stat == "treasury"
                    and change.category == "keep"):
                budget = type(civ.treasury)(max(0.0, budget + change.delta))
    return budget


def _mutual_aid_new(world, civ, acc):
    budget = float(civ.treasury)
    if acc is not None:
        for change in acc.queued_changes(world.civ_index_map[civ.name], "treasury"):
            budget = type(civ.treasury)(max(0.0, budget + change.delta))
    return budget


def _finance_old(world, acc):  # finance.py _projections
    proj = [int(c.treasury) for c in world.civilizations]
    if acc is None:
        return proj
    start = getattr(acc, "_keep_applied_up_to", 0)
    for change in acc._changes[start:]:
        if change.stat == "treasury" and change.category == "keep" and change.civ_id < len(proj):
            proj[change.civ_id] = int(max(proj[change.civ_id] + change.delta, 0))
    return proj


def _finance_new(world, acc):
    proj = [int(c.treasury) for c in world.civilizations]
    if acc is None:
        return proj
    for change in acc.queued_changes(None, "treasury"):
        if change.civ_id < len(proj):
            proj[change.civ_id] = int(max(proj[change.civ_id] + change.delta, 0))
    return proj


def _finance_turn_old(world, civ, acc):  # finance.py _turn_revenue and _turn_spending
    civ_idx = civ_index(world, civ.name)
    revenue = spending = 0.0
    for change in acc._changes:
        if (change.civ_id == civ_idx and change.stat == "treasury"
                and change.category == "keep" and change.delta > 0):
            revenue += change.delta
    for change in acc._changes:
        if (change.civ_id == civ_idx and change.stat == "treasury"
                and change.category == "keep" and change.delta < 0):
            spending -= change.delta
    return int(revenue), int(spending)


def _finance_turn_new(world, civ, acc):
    civ_idx = civ_index(world, civ.name)
    revenue = spending = 0.0
    for change in acc.queued_changes(civ_idx, "treasury", unapplied_only=False):
        if change.delta > 0:
            revenue += change.delta
    for change in acc.queued_changes(civ_idx, "treasury", unapplied_only=False):
        if change.delta < 0:
            spending -= change.delta
    return int(revenue), int(spending)


PER_CIV_FOLDS = {
    "war": (_war_old, _unfloored_new),
    "diplomacy": (_diplomacy_old, _unfloored_new),
    "gp_agendas": (_gp_agendas_old, _gp_agendas_new),
    "clearing_protection": (_clearing_old, _clearing_new),
    "mutual_aid": (_mutual_aid_old, _mutual_aid_new),
    "finance_turn": (_finance_turn_old, _finance_turn_new),
}


def _queued_world(rng, mode):
    world = _world()
    world.agent_mode = mode
    acc = StatAccumulator()
    for civ in world.civilizations:
        civ.treasury = rng.randint(0, 60)
    for _ in range(rng.randrange(0, 50)):
        idx = rng.randrange(2)
        stat = rng.choice(("treasury", "treasury", "treasury", "stability", "prestige"))
        delta = rng.choice((rng.randint(-40, 40), round(rng.uniform(-9, 9), 2), 0))
        acc.add(idx, world.civilizations[idx], stat, delta, rng.choice(sorted(ROUTING_CATEGORIES)))
    if rng.random() < 0.3:  # an index outside world.civilizations (finance guards it)
        acc._changes.insert(rng.randrange(len(acc._changes) + 1),
                            StatChange(7, "treasury", 5, "keep", 0))
    acc._keep_applied_up_to = rng.randrange(len(acc._changes) + 1)
    return world, acc


@pytest.mark.parametrize("mode", [None, "off", "hybrid", "shadow"])
@pytest.mark.parametrize("seed", range(30))
def test_queued_changes_reproduces_every_private_fold(seed, mode):
    world, acc = _queued_world(random.Random(seed), mode)
    before = (copy.deepcopy(acc._changes), acc._keep_applied_up_to)
    for name, (old, new) in PER_CIV_FOLDS.items():
        for civ in world.civilizations:
            expected, actual = old(world, civ, acc), new(world, civ, acc)
            assert (actual, type(actual)) == (expected, type(expected)), name
            if name != "finance_turn":
                assert new(world, civ, None) == old(world, civ, None), name
    assert _finance_new(world, acc) == _finance_old(world, acc)
    assert _finance_new(world, None) == _finance_old(world, None)
    assert (acc._changes, acc._keep_applied_up_to) == before  # reading changes nothing


def test_queued_changes_filters_and_watermark():
    world, acc = _world(), StatAccumulator()
    kethani, dorrathi = world.civilizations
    acc.add(0, kethani, "treasury", 5, "keep")
    acc.add(1, dorrathi, "treasury", 6, "keep")
    acc.apply_keep(world)
    acc.add(0, kethani, "treasury", -2, "keep")
    acc.add(0, kethani, "treasury", -3, "guard")
    acc.add(0, kethani, "stability", -4, "keep")
    acc.add(1, dorrathi, "treasury", 7, "keep")

    def deltas(*args, **kwargs):
        return [change.delta for change in acc.queued_changes(*args, **kwargs)]

    assert deltas(0, "treasury") == [-2]
    assert deltas(0, "treasury", None) == [-2, -3]
    assert deltas(0, "treasury", unapplied_only=False) == [5, -2]
    assert deltas(None, "treasury") == [-2, 7]
    assert deltas(None, "treasury", None, unapplied_only=False) == [5, 6, -2, -3, 7]
    assert deltas(0, "stability") == [-4]
    assert inspect.isgeneratorfunction(StatAccumulator.queued_changes)
