"""Declared local-release tradeoffs and existing paid-cargo disruption rules.

Constructed seed42 mechanics fixtures, never a policy efficacy claim. Native
runtime/default neutrality and same-horizon resumes are recorded separately.
"""
from __future__ import annotations

import copy
import random
import warnings

import pytest

import chronicler.grain_reserves as G
import chronicler.public_grain_shipments as S
from chronicler.grain_reserves_state import ARRIVED, RELEASED
from chronicler.models import Disposition
from chronicler.tuning import K_GRAIN_RESERVES_FULL_MEAL_RELEASE as KEY, load_tuning
from test_grain_reserves import VERDANT, THORNWOOD, _economy, _granary, _world
from test_public_grain_shipments import (
    DEST, SOURCE, BUYER, SELLER, dispatch, economy, world,
    test_delivery_title_and_existing_keeper_settlement as _assert_existing_keeper,
    test_real_kernel_misses_one_opening_then_delivers_and_releases as _assert_existing_timing,
)

ACTUAL_ROUTE_GRAPH = G._route_graph


def _release(world, sufficiency):
    result = _economy(world, sufficiency, pop={VERDANT: 20, THORNWOOD: 20})
    before = [g.grain for g in G._ensure(world).granaries]
    cash = [c.treasury for c in world.civilizations]
    events = G.open_granaries(world, result)
    flows = world.grain_reserves.flows
    for rid, granary in enumerate(world.grain_reserves.granaries):
        removed = sum(f.amount for f in flows if f.region == rid and f.kind in (RELEASED, G.SPOILED))
        assert granary.grain == pytest.approx(before[rid] - removed)
        released = sum(f.amount for f in flows if f.region == rid and f.kind == RELEASED)
        if released:
            demand = result.market_demand[world.regions[rid].name][0]
            assert result.food_sufficiency[world.regions[rid].name] == pytest.approx(sufficiency.get(rid, 1.0) + released / demand)
    assert [c.treasury for c in world.civilizations] == cash  # no release-time charge
    return result, events


def test_two_local_stocks_repeated_shortages_show_present_relief_and_future_cost(monkeypatch):
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    arms = []
    for policy in (0, 1):
        candidate = _world()
        candidate.tuning_overrides[KEY] = policy
        for rid, stock in ((VERDANT, 8.0), (THORNWOOD, 1.0)):
            granary = _granary(candidate, rid)
            granary.grain, granary.target = stock, 20.0
        first, _ = _release(candidate, {VERDANT: 0.7, THORNWOOD: 0.2})
        stocks = [_granary(candidate, rid).grain for rid in (VERDANT, THORNWOOD)]
        # Close the resource frame without procurement; the next direct Phase2
        # fixture deliberately retains targets/demand and introduces no resupply.
        G.tick_grain_reserves(candidate, economy_result=None)
        candidate.turn += 1
        second, _ = _release(candidate, {VERDANT: 0.0, THORNWOOD: 0.0})
        G.tick_grain_reserves(candidate, economy_result=None)
        arms.append((first.food_sufficiency, stocks, second.food_sufficiency))
    name = _world().regions[VERDANT].name
    other = _world().regions[THORNWOOD].name
    assert arms[0][0][name] == 0.7 and arms[1][0][name] == 1.0
    assert arms[0][1] == pytest.approx([7.76, 0.0])
    assert arms[1][1] == pytest.approx([4.85, 0.0])
    assert arms[0][2][name] == pytest.approx(0.6)
    assert arms[1][2][name] == pytest.approx(0.485)
    # No reserve from A can teleport into B, even with the same owner.
    assert arms[0][0][other] == arms[1][0][other] == pytest.approx(0.3)
    assert arms[0][2][other] == arms[1][2][other] == 0.0


@pytest.mark.parametrize("case", ["well_stocked", "fed", "empty", "unowned", "no_population", "no_demand", "severely_scarce"])
def test_declared_noop_conditions_keep_full_meal_option_locally_neutral(case):
    outcomes = []
    for policy in (0, 1):
        candidate = _world()
        candidate.tuning_overrides[KEY] = policy
        granary = _granary(candidate, VERDANT)
        granary.grain, granary.target = 8.0, 20.0
        sufficiency = 0.4
        if case == "well_stocked": granary.grain = 20.0
        elif case == "fed": sufficiency = 1.0
        elif case == "empty": granary.grain = 0.0
        elif case == "unowned": candidate.regions[VERDANT].controller = None
        elif case == "no_population": candidate.regions[VERDANT].population = 0
        elif case == "severely_scarce": granary.grain, sufficiency = 1.0, 0.0
        result = _economy(candidate, {VERDANT: sufficiency})
        if case == "no_demand": result.market_demand[candidate.regions[VERDANT].name] = (0.0, 0.0, 0.0, 0.0)
        events = G.open_granaries(candidate, result)
        candidate.tuning_overrides.pop(KEY)
        outcomes.append((candidate.model_dump_json(warnings=False), result, events))
    assert outcomes[0] == outcomes[1]


def test_missing_and_explicit_zero_preserve_world_events_and_rng_exactly():
    candidate = _world()
    _granary(candidate, VERDANT).grain, _granary(candidate, VERDANT).target = 8.0, 20.0
    original = copy.deepcopy(candidate)
    rng = random.getstate()
    outcomes = []
    for policy in (None, 0):
        arm = copy.deepcopy(original)
        if policy is not None: arm.tuning_overrides[KEY] = policy
        result, events = _release(arm, {VERDANT: 0.7})
        arm.tuning_overrides.pop(KEY, None)
        outcomes.append((arm.model_dump_json(warnings=False), result, events))
        assert random.getstate() == rng
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize("value", [-1, 2, float("nan"), float("inf"), "1", True, None])
def test_invalid_active_policy_refuses_before_owners_stock_or_flows_mutate(value):
    candidate = _world()
    candidate.tuning_overrides[KEY] = value
    before = copy.deepcopy(candidate)
    result = _economy(candidate)
    with pytest.raises(ValueError, match="full_meal_release must be 0 or 1"):
        G.open_granaries(candidate, result)
    assert candidate.model_dump_json(warnings=False) == before.model_dump_json(warnings=False)


def test_invalid_legacy_override_stays_inert_without_active_granaries():
    for mode, enabled in (("off", True), ("hybrid", False)):
        candidate = _world(mode)
        if not enabled: G.set_grain_reserves_enabled(candidate, False)
        candidate.tuning_overrides[KEY] = "legacy unknown value"
        before = candidate.model_dump_json(warnings=False)
        assert G.open_granaries(candidate, _economy(candidate)) == []
        assert candidate.model_dump_json(warnings=False) == before


def test_registered_yaml_policy_accepts_zero_one_and_only_active_consumers_reject_other_numbers(tmp_path):
    path = tmp_path / "release.yaml"
    for value in (0, 1):
        path.write_text(f"grain_reserves:\n  full_meal_release: {value}\n")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert load_tuning(path) == {KEY: float(value)}
        assert not caught
    for value in ("2", ".nan", ".inf"):
        path.write_text(f"grain_reserves:\n  full_meal_release: {value}\n")
        loaded = load_tuning(path)  # preserve generic/legacy YAML loading
        active = _world()
        active.tuning_overrides.update(loaded)
        before = active.model_dump_json(warnings=False)
        with pytest.raises(ValueError, match="must be 0 or 1"):
            G.open_granaries(active, _economy(active))
        assert active.model_dump_json(warnings=False) == before
        active.agent_mode = "off"
        assert G.open_granaries(active, _economy(active)) == []


@pytest.mark.parametrize("policy", [0, 1])
@pytest.mark.parametrize("disruption", ["route_closure", "supplier_loss"])
def test_paid_public_cargo_survives_existing_disruption_and_recovery(world, monkeypatch, policy, disruption):
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    world.tuning_overrides[KEY] = policy
    monkeypatch.setattr(G, "_route_graph", ACTUAL_ROUTE_GRAPH)
    world.active_wars, world.embargoes = [], []
    for row in world.relationships.values():
        for relation in row.values(): relation.disposition = Disposition.NEUTRAL
    assert SOURCE in G._route_graph(world)[DEST]
    dispatch(world)
    order = world.grain_reserves.shipments.pending[0]
    cash = [c.treasury for c in world.civilizations]
    seller = world.civilizations[SELLER]
    prior_regions = list(seller.regions)
    if disruption == "route_closure": world.regions[SOURCE].route_suspensions["trade_route"] = 2
    else:
        world.regions[SOURCE].controller = None
        world.regions[SOURCE]._controller_changed_this_turn = True
        seller.regions.clear()
    assert SOURCE not in G._route_graph(world).get(DEST, ())
    world.turn += 1
    G.open_granaries(world, economy(world))
    events = S.settle_arrivals(world)
    assert len(events) == 1
    assert [c.treasury for c in world.civilizations] == cash
    assert world.grain_reserves.granaries[DEST].grain == pytest.approx(order.net)
    assert not world.grain_reserves.shipments.pending
    assert sum(f.amount for f in world.grain_reserves.flows if f.kind == ARRIVED) == pytest.approx(order.net)
    # The policy cannot eat paid cargo before arrival; this tick was already fed.
    assert world.grain_reserves.counters["released"] == 0
    G.tick_grain_reserves(world, economy_result=economy(world))
    assert not world.grain_reserves.shipments.pending  # no new route-backed supply
    world.regions[SOURCE].route_suspensions.clear()
    world.regions[SOURCE].controller = seller.name
    world.regions[SOURCE]._controller_changed_this_turn = True
    seller.regions[:] = prior_regions
    world.turn += 1
    G.open_granaries(world, economy(world))
    G.tick_grain_reserves(world, economy_result=economy(world))
    assert world.grain_reserves.shipments.pending  # a viable offer recovers
    assert world.grain_reserves.shipments.next_order > order.order + 1
    assert world.grain_reserves.shipments.counters["delivered"] == pytest.approx(order.net)
    assert world.grain_reserves.shipments.counters["transit_loss"] == pytest.approx(
        world.grain_reserves.shipments.counters["sent"] - world.grain_reserves.shipments.counters["committed_net"])


@pytest.mark.parametrize("policy", [0, 1])
@pytest.mark.parametrize("custody", ["conquest_before_open", "conquest_after_open", "dead_buyer", "unguarded"])
def test_release_option_keeps_existing_arrival_custody_rules(world, policy, custody):
    world.tuning_overrides[KEY] = policy
    _assert_existing_keeper(world, custody)


@pytest.mark.parametrize("policy", [0, 1])
def test_release_option_never_feeds_agents_from_pending_cargo(world, monkeypatch, policy):
    world.tuning_overrides[KEY] = policy
    _assert_existing_timing(world, monkeypatch)


@pytest.mark.native
@pytest.mark.parametrize("policy", [0, 1])
def test_native_policy_midtransit_checkpoint_matches_same_terminal_horizon(tmp_path, monkeypatch, policy):
    # Deliberately require the real binary: no importorskip or skip fallback.
    import chronicler_agents.chronicler_agents as compiled
    from chronicler import live
    from test_live_checkpoints_native import _public_grain_live_checkpoint
    assert isinstance(compiled.AgentSimulator, type)
    original = live._live_world

    def initial_world(args, params):
        candidate, scenario = original(args, params)
        candidate.tuning_overrides[KEY] = policy
        return candidate, scenario

    monkeypatch.setattr(live, "_live_world", initial_world)
    # Existing finite-stock native fixture, horizon8 in both uninterrupted and
    # resumed paths; no shorter terminal run is compared to an earlier checkpoint.
    _public_grain_live_checkpoint(tmp_path, monkeypatch, prefill_sellers=True)


def test_source_inverse_preserves_frozen_parent_and_rejects_changed_policy_and_unrelated_edits():
    import hashlib
    from pathlib import Path
    from scripts.testing.grain_release_witness import _LAYERS, before_grain_release
    root = Path(__file__).resolve().parents[1]
    for path, row in _LAYERS.items():
        source = (root / path).read_text()
        assert hashlib.sha256(before_grain_release(source, path).encode()).hexdigest() == row["sha256"]
        for patch in row["patches"]:
            with pytest.raises(AssertionError):
                before_grain_release(source.replace(patch["new"], patch["old"], 1), path)
            with pytest.raises(AssertionError):
                before_grain_release(source + patch["new"], path)
        with pytest.raises(AssertionError):
            before_grain_release(source + "\n# unrelated source mutation\n", path)
    source = (root / "src/chronicler/grain_reserves.py").read_text()
    with pytest.raises(AssertionError):
        before_grain_release(source.replace("full or full_meal_release", "full"), "src/chronicler/grain_reserves.py")
