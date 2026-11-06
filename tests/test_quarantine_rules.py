"""Quarantine rules (connected-world C1): a real, dated trade restriction and its costs.

Offline: no native extension, network or child process (the bounded offline
lane's ``connected-world-c`` chunk). The agent-merchant and hybrid resume
cases are in ``tests/test_quarantine_rules_native.py``. Numbered sections
follow AUDIT-C section 7 (tests 1-6).
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import pytest

import chronicler.contact_ledger as cl
import chronicler.epidemiology as ep
import chronicler.quarantine_rules as qr
from chronicler.action_engine import ActionEngine
from chronicler.models import WorldState
from chronicler.resources import _compute_active_trade_routes, get_active_trade_routes
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world


# --- helpers -----------------------------------------------------------------------------

def _world(mode: str = "closure", seed: int = 42) -> WorldState:
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.campaigns_enabled = True
    cl.set_contact_ledger_enabled(world, True)
    ep.set_epidemiology_enabled(world, True)
    if mode != "legacy":
        world.epidemics.quarantine_rules = qr.QuarantineRulesState(mode=mode)
    return world


def _isolate(world: WorldState) -> None:
    """No reservoirs and no ledger contact: only what a test seeds."""
    world.epidemics.initialized_turn = world.turn
    world.epidemics.homelands = []
    world.contact_ledger.edges = []
    world.contact_ledger.invalidate()


def _contact(world: WorldState, a: int, b: int, amount: float, channel: int = cl.PEOPLE) -> None:
    cl._pending(world).append((a, b, channel, amount))
    cl.update_contact_ledger(world)


def _outbreak(world: WorldState, region: int, pathogen: int = ep.PLAGUE, people: float = 30.0):
    row = ep._row_for(world.epidemics, region, pathogen, world.regions[region].population)
    row.n = world.regions[region].population
    ep._seed(row, people, cause="", virgin=True)
    return row


def _civ(world: WorldState, name: str) -> int:
    return world.civ_index_map[name]


def _border(world: WorldState) -> tuple[int, int, str, str]:
    """Adjacent regions (a, b) of two polities with an open adjacency route between them."""
    routes = set(_compute_active_trade_routes(world))
    index = {r.name: i for i, r in enumerate(world.regions)}
    for i, region in enumerate(world.regions):
        for adj in region.adjacencies:
            j = index.get(adj)
            if j is None:
                continue
            ca, cb = region.controller, world.regions[j].controller
            if ca and cb and ca != cb and tuple(sorted((ca, cb))) in routes:
                return i, j, ca, cb
    raise AssertionError("fixture world has no cross-polity adjacency route")


def _closing_world(mode: str, seed: int = 42):
    """An outbreak in region a (polity A) reported to polity B next door, in contact."""
    world = _world(mode, seed)
    _isolate(world)
    a, b, name_a, name_b = _border(world)
    for j in (a, b):
        world.regions[j].population = world.regions[j].carrying_capacity = 300
        world.regions[j].famine_cooldown = 0
    closer = world.civilizations[_civ(world, name_b)]
    closer.stability, closer.treasury = 80, 50
    _contact(world, a, b, 100.0)
    _outbreak(world, a)
    return world, a, b, _civ(world, name_a), _civ(world, name_b)


def _close(world: WorldState, civ: int, target: int) -> qr.QuarantineRulesState:
    """Install one closure directly (route-level units)."""
    rules = world.epidemics.quarantine_rules
    rules.closures = [qr.QuarantineClosure(id=rules.next_closure_id, civ=civ, target=target,
                                           opened_turn=world.turn, last_renewed_turn=world.turn)]
    rules.next_closure_id += 1
    rules.receipt = qr.QuarantineReceipt(turn=world.turn)
    world.invalidate_trade_route_cache()
    return rules


def _pair(world: WorldState, i: int, j: int) -> tuple[str, str]:
    return tuple(sorted((world.civilizations[i].name, world.civilizations[j].name)))


def _cli_args(folder: Path, turns: int, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=7, turns=turns, civs=4, regions=8, output=str(folder / "chronicle.md"),
        state=str(folder / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, pause_every=None, simulate_only=True, agents="off", tuning_overrides={},
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


@pytest.fixture
def pure_python_runtimes(monkeypatch):
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)


def _advance(world: WorldState, turns: int) -> None:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn)


# --- 1. feature-off identity (in-suite part; the matrices run turn_speed_identity) -------

def test_legacy_world_keeps_no_rules_and_its_outputs_keep_their_shape():
    world = _world("legacy")
    assert qr.rules_of(world) is None and qr.effective_mode(world) == "legacy"
    assert "quarantine_rules" not in world.epidemics.model_dump_json()
    assert "quarantine_rules" not in world.model_dump_json()
    ep.tick_epidemics(world)
    assert set(ep.snapshot_summary(world)) == {
        "active", "deaths", "deaths_by_pathogen", "deaths_total", "quarantine", "strains"}
    assert qr.effective_mode(_world("closure")) == "closure"
    off = generate_world(seed=42, num_regions=8, num_civs=4)
    assert qr.effective_mode(off) is None and qr.closed_pairs(off) == set()


def test_the_legacy_path_never_runs_the_rules(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("quarantine rules ran on the legacy path")

    for name in ("decide", "filter_closed_routes", "merchant_route_graph", "snapshot_summary"):
        monkeypatch.setattr(qr, name, boom)
    world = _world("legacy", seed=7)
    _advance(world, 12)
    from chronicler.agent_bridge import _quarantine_route_graph
    from chronicler.economy import build_merchant_route_graph
    batch = build_merchant_route_graph(world)
    assert _quarantine_route_graph(world, batch) is batch


def test_an_old_pickle_without_the_field_loads_and_runs_the_legacy_rule():
    world = _world("legacy")
    del world.epidemics.__dict__["quarantine_rules"]
    restored = pickle.loads(pickle.dumps(world))
    assert "quarantine_rules" not in restored.epidemics.__dict__
    assert getattr(restored.epidemics, "quarantine_rules", None) is None
    assert qr.rules_of(restored) is None
    assert "quarantine_rules" not in restored.model_dump_json()
    ep.tick_epidemics(restored)  # the legacy multiplier path reads the field with getattr
    assert "quarantine_rules" not in ep.snapshot_summary(restored)


def test_a_saved_legacy_state_loads_without_rules(tmp_path):
    world = _world("legacy", seed=7)
    _advance(world, 3)
    path = tmp_path / "state.json"
    world.save(path)
    assert "quarantine_rules" not in json.loads(path.read_text())["epidemics"]
    loaded = WorldState.load(path)
    assert loaded.epidemics.quarantine_rules is None


def test_explicit_legacy_is_the_omitted_option(tmp_path, pure_python_runtimes):
    from chronicler.main import execute_run
    execute_run(_cli_args(tmp_path / "omitted", 8))
    execute_run(_cli_args(tmp_path / "legacy", 8, quarantine_mode="legacy"))
    assert (tmp_path / "omitted/state.json").read_bytes() == (tmp_path / "legacy/state.json").read_bytes()


# --- 2. mode units -----------------------------------------------------------------------

def test_none_mode_decides_nothing_and_charges_nothing():
    world, a, b, ia, ib = _closing_world("none")
    events = ep.tick_epidemics(world)
    rules = world.epidemics.quarantine_rules
    assert not [e for e in events if e.event_type == "quarantine"]
    assert world.epidemics.quarantine == [] and rules.closures == []
    assert world.civilizations[ib].treasury == 50
    assert rules.receipt.turn == world.turn and rules.receipt.decided == []


@pytest.mark.parametrize("mode", ["none", "cost_only", "closure"])
def test_new_modes_apply_no_import_multiplier(mode):
    """With the ledger unchanged, pressure into a closing polity is the open pressure."""
    def imports(world_mode: str, quarantined: bool) -> list[str]:
        out = []
        for seed in range(30):
            world = _world(world_mode, seed)
            _isolate(world)
            a = next(i for i, r in enumerate(world.regions) if r.controller is not None)
            b = next(i for i, r in enumerate(world.regions)
                     if r.controller not in (None, world.regions[a].controller))
            for j in (a, b):
                world.regions[j].population = world.regions[j].carrying_capacity = 300
            row = ep._row_for(world.epidemics, a, ep.PLAGUE, 300)
            row.s, row.i, row.burden = 0.8, 0.2, 0.2
            _contact(world, a, b, 10.0)
            world.epidemics.quarantine = [_civ(world, world.regions[b].controller)] if quarantined else []
            rows = {(r.region, r.pathogen): r for r in world.epidemics.rows}
            ep._introduce(world, world.epidemics, rows, [ep._modifiers(r) for r in world.regions])
            out.append(json.dumps(sorted(r.model_dump_json() for r in rows.values())))
        return out

    open_ = imports("legacy", False)
    assert imports(mode, True) == open_
    legacy_closed = imports("legacy", True)
    assert legacy_closed != open_  # the legacy multiplier does cut (the reference)


def test_cost_only_decides_and_pays_as_closure_but_leaves_routes_open():
    worlds = {mode: _closing_world(mode) for mode in ("cost_only", "closure")}
    base = _world("legacy")
    open_routes = _compute_active_trade_routes(base)
    seen = {}
    for mode, (world, a, b, ia, ib) in worlds.items():
        assert _compute_active_trade_routes(world) == open_routes
        events = ep.tick_epidemics(world)
        rules = world.epidemics.quarantine_rules
        closure = [e for e in events if e.event_type == "quarantine"]
        assert [e.actors for e in closure] == [[world.civilizations[ib].name]]
        seen[mode] = (rules.receipt.decided, rules.receipt.enforcement, world.civilizations[ib].treasury,
                      world.epidemics.quarantine, [(c.id, c.civ, c.target) for c in rules.closures])
        assert rules.receipt.decided == [(ib, ia)]
        assert world.civilizations[ib].treasury == 50 - qr.ENFORCEMENT_COST
    assert seen["cost_only"] == seen["closure"]
    cost_world, _, _, ia, ib = worlds["cost_only"]
    close_world = worlds["closure"][0]
    assert _compute_active_trade_routes(cost_world) == open_routes
    assert qr.closed_pairs(cost_world) == set()
    assert set(_compute_active_trade_routes(close_world)) == set(open_routes) - {_pair(close_world, ia, ib)}
    assert "closing no route" in next(e for e in ep.tick_epidemics(cost_world)
                                      if e.event_type == "quarantine").description


def test_closure_targets_only_polities_with_reported_outbreaks():
    world, a, b, ia, ib = _closing_world("closure")
    # An outbreak in an uncontrolled region is foreign but has no route to close.
    world.regions[a].controller = None
    events = ep.tick_epidemics(world)
    assert not [e for e in events if e.event_type == "quarantine"]
    assert world.epidemics.quarantine == [] and world.civilizations[ib].treasury == 50
    # A poor or unstable polity cannot enforce a closure (the legacy trigger).
    for field, value in (("stability", ep.QUARANTINE_MIN_STABILITY - 1), ("treasury", qr.ENFORCEMENT_COST - 1)):
        world, a, b, ia, ib = _closing_world("closure")
        setattr(world.civilizations[ib], field, value)
        assert not [e for e in ep.tick_epidemics(world) if e.event_type == "quarantine"]
        assert world.epidemics.quarantine_rules.closures == []


def test_closure_removes_every_route_kind_of_closed_pairs_only(monkeypatch):
    world = _world("closure")
    names = [c.name for c in world.civilizations]
    routes = set(_compute_active_trade_routes(world))
    a, b = next(iter(sorted(routes)))
    # A federation route between two other polities, and a techniques-extended one.
    others = [n for n in names if n not in (a, b)]
    from chronicler.models import Federation
    world.federations = [Federation(name="League", members=sorted([a, others[0]]), founded_turn=0)]
    import chronicler.techniques as techniques

    def extend(world_, routes_, embargo_set, region_map):
        routes_.add(tuple(sorted((b, others[1]))))
    monkeypatch.setattr(techniques, "extend_trade_routes", extend)
    monkeypatch.setattr("chronicler.resources.techniques_on", lambda w: True)
    world.invalidate_trade_route_cache()
    before = set(_compute_active_trade_routes(world))
    fed, tech = tuple(sorted([a, others[0]])), tuple(sorted((b, others[1])))
    assert {(a, b), fed, tech} <= before
    for pair in ((a, b), fed, tech):
        _close(world, names.index(pair[0]), names.index(pair[1]))
        after = set(_compute_active_trade_routes(world))
        assert after == before - {pair}
    # Two polities closed against each other lose the pair once.
    rules = world.epidemics.quarantine_rules
    rules.closures = [qr.QuarantineClosure(id=9, civ=names.index(a), target=names.index(b), opened_turn=0,
                                           last_renewed_turn=0),
                      qr.QuarantineClosure(id=10, civ=names.index(b), target=names.index(a), opened_turn=0,
                                           last_renewed_turn=0)]
    assert set(_compute_active_trade_routes(world)) == before - {(a, b)}


def test_two_hop_routes_of_closed_pairs_are_removed():
    world = _world("closure")
    index = {r.name: i for i, r in enumerate(world.regions)}
    for r1 in world.regions:
        if r1.controller is None:
            continue
        for mid_name in r1.adjacencies:
            mid = world.regions[index[mid_name]]
            for hop2_name in mid.adjacencies:
                hop2 = world.regions[index[hop2_name]]
                if hop2.controller in (None, r1.controller) or hop2_name in r1.adjacencies:
                    continue
                pair = tuple(sorted((r1.controller, hop2.controller)))
                if pair in set(_compute_active_trade_routes(world)):
                    continue
                mid.terrain = "coast"
                world.civ_map[r1.controller].active_focus = "navigation"
                for x, y in (pair, pair[::-1]):
                    world.relationships[x][y].disposition = world.relationships[x][y].disposition.__class__("friendly")
                world.invalidate_trade_route_cache()
                if pair not in set(_compute_active_trade_routes(world)):
                    continue
                _close(world, _civ(world, pair[0]), _civ(world, pair[1]))
                assert pair not in set(_compute_active_trade_routes(world))
                return
    raise AssertionError("no two-hop candidate in the fixture world")


def test_trade_action_cannot_choose_a_closed_partner(monkeypatch):
    from chronicler import action_engine
    world = _world("closure")
    a, b = sorted(_compute_active_trade_routes(world))[0]
    ia, ib = _civ(world, a), _civ(world, b)
    civ = world.civilizations[ia]
    # B is A's friendliest partner and A's only route partner.
    for other in world.civilizations:
        if other.name not in (a, b):
            for x, y in ((a, other.name), (other.name, a)):
                world.relationships[x][y].disposition = world.relationships[x][y].disposition.__class__("hostile")
    for x, y in ((a, b), (b, a)):
        world.relationships[x][y].disposition = world.relationships[x][y].disposition.__class__("allied")
    world.invalidate_trade_route_cache()
    traded = []
    monkeypatch.setattr(action_engine, "resolve_trade", lambda c1, c2, w, acc=None: traded.append(c2.name))
    open_event = action_engine._resolve_trade_action(civ, world)
    assert traded == [b] and b in open_event.actors
    traded.clear()
    _close(world, ib, ia)
    closed_event = action_engine._resolve_trade_action(civ, world)
    assert traded == [] and b not in closed_event.actors


def test_forgone_income_is_two_per_closed_goods_route_per_side():
    from chronicler.economy import filter_goods_trade_routes
    from chronicler.simulation import apply_automatic_effects

    def treasuries(world):
        for civ in world.civilizations:
            civ.economy, civ.military, civ.treasury = 0, 0, 100  # isolate trade income
        apply_automatic_effects(world)
        return [c.treasury for c in world.civilizations]

    open_world, closed_world = _world("closure"), _world("closure")
    a, b = sorted(filter_goods_trade_routes(open_world, _compute_active_trade_routes(open_world)))[0]
    ia, ib = _civ(closed_world, a), _civ(closed_world, b)
    rules = _close(closed_world, ia, ib)
    _close(open_world, ia, ib).closures = []
    open_t, closed_t = treasuries(open_world), treasuries(closed_world)
    diff = {i: o - c for i, (o, c) in enumerate(zip(open_t, closed_t)) if o != c}
    assert diff == {ia: qr.ROUTE_INCOME, ib: qr.ROUTE_INCOME}
    receipt = rules.receipt
    assert receipt.phase2_observed and receipt.routes_removed == [tuple(sorted((ia, ib)))]
    assert dict(receipt.forgone_income) == diff


def test_reopening_restores_routes_and_the_route_cache_is_invalidated():
    world, a, b, ia, ib = _closing_world("closure")
    pair = _pair(world, ia, ib)
    assert pair in get_active_trade_routes(world)            # seeds this turn's cache
    assert world._trade_route_cache_turn == world.turn
    ep.tick_epidemics(world)                                  # decides the closure
    assert world._trade_route_cache_turn is None              # invalidated by the decision
    assert pair not in get_active_trade_routes(world)
    world.epidemics.rows = []                                 # the outbreak is over
    ep.tick_epidemics(world)
    assert world.epidemics.quarantine_rules.closures == []
    assert pair in get_active_trade_routes(world)


# --- 3. double-count guards ----------------------------------------------------------------

def test_a_closed_pairs_trade_stock_decays_without_a_second_cut():
    from chronicler.economy import filter_goods_trade_routes
    world = _world("closure")
    _isolate(world)
    a, b, name_a, name_b = _border(world)
    assert (min(name_a, name_b), max(name_a, name_b)) in filter_goods_trade_routes(
        world, _compute_active_trade_routes(world))
    _contact(world, a, b, 10.0, cl.TRADE)
    _contact(world, b, a, 10.0, cl.TRADE)
    open_world = world.model_copy(deep=True)
    _close(world, _civ(world, name_b), _civ(world, name_a))

    def step(w):
        routes = get_active_trade_routes(w, emit_events=True)
        cl.observe_phase2(w, routes)                           # the aggregate route proxy
        cl.update_contact_ledger(w)
        w.turn += 1

    def trade(w, key):
        return w.contact_ledger.edge_map()[key][cl.TRADE]

    start = {key: trade(world, key) for key in ((a, b), (b, a))}
    for k in range(1, 6):
        step(world)
        step(open_world)
        world.epidemics.quarantine_rules.receipt.turn = world.turn
        for key in ((a, b), (b, a)):
            # Only the decay: no inflow, and no multiplier cutting the stock again.
            assert trade(world, key) == pytest.approx(start[key] * cl.DECAY[cl.TRADE] ** k, abs=1e-5)
            assert trade(open_world, key) > trade(world, key)   # the open border keeps adding flow


def test_the_techniques_bonus_is_not_applied_in_new_modes(monkeypatch):
    import chronicler.techniques as techniques
    from chronicler.techniques import set_techniques_enabled

    def boom(*args, **kwargs):
        raise AssertionError("lazaret/law-code efficacy read")

    monkeypatch.setattr(techniques, "quarantine_efficacy", boom)
    for mode in ("legacy", "cost_only", "closure"):
        world = _world(mode)
        set_techniques_enabled(world, True)
        a, b, name_a, name_b = _border(world)
        world.epidemics.quarantine = [_civ(world, name_b)]
        rows = {(r.region, r.pathogen): r for r in world.epidemics.rows}
        mods = [ep._modifiers(r) for r in world.regions]
        if mode == "legacy":
            with pytest.raises(AssertionError, match="efficacy"):
                ep._introduce(world, world.epidemics, rows, mods)
        else:
            ep._introduce(world, world.epidemics, rows, mods)


def test_embargo_and_closure_remove_a_route_once_and_attribute_no_income():
    world = _world("closure")
    a, b = sorted(_compute_active_trade_routes(world))[0]
    world.embargoes = [(a, b)]
    world.invalidate_trade_route_cache()
    embargoed = set(_compute_active_trade_routes(world))
    assert (a, b) not in embargoed
    rules = _close(world, _civ(world, a), _civ(world, b))
    assert set(get_active_trade_routes(world, emit_events=True)) == embargoed
    assert rules.receipt.phase2_observed
    assert rules.receipt.routes_removed == [] and rules.receipt.forgone_income == []


# --- 4. dated effect (aggregate; the hybrid chain is native) --------------------------------

def test_aggregate_closure_at_t_stops_the_proxy_flow_of_t_and_lowers_contact_at_t1():
    arms = {}
    for mode in ("cost_only", "closure"):
        world, a, b, ia, ib = _closing_world(mode)
        _contact(world, a, b, 10.0, cl.TRADE)
        stock = world.contact_ledger.edge_map()[(a, b)]
        t = world.turn
        _advance(world, 1)
        decided = world.epidemics.quarantine_rules
        assert decided.receipt.turn == t and (ib, ia) in decided.receipt.decided
        arms[mode] = (world, a, b, stock)
    closure, a, b, stock = arms["closure"]
    cost, *_ = arms["cost_only"]
    receipt = closure.epidemics.quarantine_rules.receipt
    assert receipt.phase2_observed and receipt.routes_removed
    # The closure world's border edge only decayed during t: no proxy flow of t.
    after = closure.contact_ledger.edge_map()[(a, b)]
    assert after[cl.TRADE] == pytest.approx(stock[cl.TRADE] * cl.DECAY[cl.TRADE], abs=1e-6)
    assert cost.contact_ledger.edge_map()[(a, b)][cl.TRADE] > after[cl.TRADE]
    # What the import step of t+1 reads (the decayed stock): lower under closure.
    assert cl.region_contact(closure, a, b) < cl.region_contact(cost, a, b)


# --- 5. checkpoint and resume -------------------------------------------------------------

def test_ids_are_stable_and_a_lapse_then_reclosure_gets_a_new_id_across_a_save(tmp_path):
    world, a, b, ia, ib = _closing_world("closure")
    ep.tick_epidemics(world)
    rules = world.epidemics.quarantine_rules
    assert [c.id for c in rules.closures] == [1] and rules.receipt.opened == [1]
    first_cause = rules.closures[0].cause
    assert first_cause
    world.turn += 1
    _outbreak(world, a)
    ep.tick_epidemics(world)                       # still reported: renewed, same id
    assert rules.receipt.renewed == [1] and rules.closures[0].opened_turn == world.turn - 1
    assert rules.closures[0].last_renewed_turn == world.turn
    world.turn += 1
    world.epidemics.rows = []
    ep.tick_epidemics(world)                       # trigger gone: lapses
    assert rules.receipt.lapsed == [1] and rules.closures == [] and world.epidemics.quarantine == []
    path = tmp_path / "lapsed.json"
    world.save(path)
    loaded = WorldState.load(path)
    assert loaded.epidemics.quarantine_rules.next_closure_id == 2
    for w in (world, loaded):
        w.turn += 1
        _outbreak(w, a)
        ep.tick_epidemics(w)
        assert [c.id for c in w.epidemics.quarantine_rules.closures] == [2]
    assert loaded.epidemics.quarantine_rules.model_dump() == world.epidemics.quarantine_rules.model_dump()
    totals = world.epidemics.quarantine_rules.totals
    assert (totals.receipts, totals.closures_opened, totals.closures_lapsed) == (3, 1, 1)


def test_leaked_deliveries_count_every_tick_a_pair_was_closed_including_the_last():
    """Deliveries read at T were made in the tick of T-1: a pair closed then counts even
    when its closure lapsed at T (review m2)."""
    world, a, b, ia, ib = _closing_world("closure")
    ep.tick_epidemics(world)                                   # closure opens at T
    pair = tuple(sorted((ia, ib)))
    world.turn += 1
    world.epidemics.rows = []
    ep.tick_epidemics(world)                                   # the trigger is gone: lapses at T+1
    receipt = world.epidemics.quarantine_rules.receipt
    assert receipt.lapsed == [1] and receipt.continued == [] and receipt.closed_last_tick == [pair]
    other = next(j for j, r in enumerate(world.regions) if r.controller not in (
        None, world.regions[a].controller, world.regions[b].controller))
    qr.observe_deliveries(world, [(a, b, 2.0), (b, a, 0.5), (a, a, 9.0), (other, b, 3.0), (a, b, 0.0)])
    assert receipt.leaked_deliveries == 2 and receipt.leaked_quantity == 2.5
    # Not closure: nothing is counted (cost_only closes nothing).
    cost, a2, b2, *_ = _closing_world("cost_only")
    ep.tick_epidemics(cost)
    cost.turn += 1
    ep.tick_epidemics(cost)
    qr.observe_deliveries(cost, [(a2, b2, 2.0)])
    assert cost.epidemics.quarantine_rules.receipt.leaked_deliveries is None
    assert cost.epidemics.quarantine_rules.receipt.closed_last_tick == []


def test_json_save_mid_closure_continues_identically(tmp_path):
    world = _world("closure", seed=7)
    for _ in range(40):
        _advance(world, 1)
        if world.epidemics.quarantine_rules.closures:
            break
    assert world.epidemics.quarantine_rules.closures, "seed 7 should close within 40 turns"
    path = tmp_path / "mid.json"
    world.save(path)
    loaded = WorldState.load(path)
    _advance(world, 6)
    _advance(loaded, 6)
    assert loaded.model_dump_json() == world.model_dump_json()
    assert world.epidemics.quarantine_rules.totals.receipts > 0


def test_exact_aggregate_checkpoint_mid_closure_resumes_identically(tmp_path, pure_python_runtimes):
    import chronicler.run_checkpoint as rc
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import execute_run

    def outputs(folder):
        out = {}
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.suffix != ".ckpt":
                if p.name == "chronicle_bundle.json":
                    data = load_bundle(p)
                    data["metadata"].pop("generated_at", None)
                    out[p.name] = json.dumps(data, sort_keys=True)
                else:
                    out[p.relative_to(folder).as_posix()] = p.read_bytes()
        return out

    straight = tmp_path / "straight"
    execute_run(_cli_args(straight, 18, quarantine_mode="closure", checkpoint_every=3,
                          checkpoint=str(straight / "ckpt" / "turn_{turn:03d}.ckpt")))
    live = []
    for path in sorted((straight / "ckpt").glob("*.ckpt")):
        loaded = rc.read_checkpoint(path)
        if loaded.state.world.epidemics.quarantine_rules.closures:
            live.append(path)
    assert live, "no checkpoint fell inside an active closure"
    for path in live[:2]:
        resumed = tmp_path / path.stem
        execute_run(_cli_args(resumed, 18), checkpoint_resume=rc.read_checkpoint(path))
        expected, got = outputs(straight), outputs(resumed)
        assert got.keys() == expected.keys()
        assert [name for name in got if got[name] != expected[name]] == []


def test_resume_with_a_conflicting_mode_is_refused(tmp_path, pure_python_runtimes):
    import chronicler.run_checkpoint as rc
    from chronicler.main import _adopt_checkpoint_args, _build_parser, execute_run

    straight = tmp_path / "straight"
    execute_run(_cli_args(straight, 6, quarantine_mode="closure", checkpoint_every=3,
                          checkpoint=str(straight / "c{turn}.ckpt")))
    parser = _build_parser()
    loaded = rc.read_checkpoint(straight / "c3.ckpt")
    assert loaded.state.run_config["simulation_args"]["quarantine_mode"] == "closure"
    args = parser.parse_args(["--resume", str(straight / "c3.ckpt"), "--quarantine-mode", "cost_only"])
    conflicts = _adopt_checkpoint_args(parser, args, rc.read_checkpoint(straight / "c3.ckpt"))
    assert any("--quarantine-mode 'cost_only' conflicts" in line for line in conflicts)
    same = parser.parse_args(["--resume", str(straight / "c3.ckpt"), "--quarantine-mode", "closure"])
    assert _adopt_checkpoint_args(parser, same, rc.read_checkpoint(straight / "c3.ckpt")) == []
    omitted = parser.parse_args(["--resume", str(straight / "c3.ckpt")])
    assert _adopt_checkpoint_args(parser, omitted, rc.read_checkpoint(straight / "c3.ckpt")) == []
    assert omitted.quarantine_mode == "closure"
    # A legacy checkpoint (mode never given) refuses a new mode from the retained state.
    legacy = tmp_path / "legacy"
    execute_run(_cli_args(legacy, 6, checkpoint_every=3, checkpoint=str(legacy / "c{turn}.ckpt")))
    assert "quarantine_mode" not in rc.read_checkpoint(legacy / "c3.ckpt").state.run_config["simulation_args"]
    args = parser.parse_args(["--resume", str(legacy / "c3.ckpt"), "--quarantine-mode", "closure"])
    conflicts = _adopt_checkpoint_args(parser, args, rc.read_checkpoint(legacy / "c3.ckpt"))
    assert any("--quarantine-mode 'closure' conflicts with the checkpoint (saved: 'legacy')" in line
               for line in conflicts)
    keep = parser.parse_args(["--resume", str(legacy / "c3.ckpt"), "--quarantine-mode", "legacy"])
    assert _adopt_checkpoint_args(parser, keep, rc.read_checkpoint(legacy / "c3.ckpt")) == []


def test_legacy_json_resume_is_defined(tmp_path, pure_python_runtimes):
    """A saved world keeps its rules; a different explicit mode is refused."""
    from chronicler.main import execute_run
    legacy = tmp_path / "legacy"
    execute_run(_cli_args(legacy, 4))
    resumed = _cli_args(tmp_path / "resumed", 8, resume=str(legacy / "state.json"))
    execute_run(resumed)                                           # continues the legacy rule
    assert "quarantine_rules" not in json.loads((tmp_path / "resumed/state.json").read_text())["epidemics"]
    refused = _cli_args(tmp_path / "refused", 8, resume=str(legacy / "state.json"), quarantine_mode="closure")
    with pytest.raises(ValueError, match=r"--quarantine-mode closure conflicts with the saved world \(saved: legacy\)"):
        execute_run(refused)
    closure = tmp_path / "closure"
    execute_run(_cli_args(closure, 4, quarantine_mode="closure"))
    kept = _cli_args(tmp_path / "kept", 8, resume=str(closure / "state.json"))
    execute_run(kept)
    assert json.loads((tmp_path / "kept/state.json").read_text())["epidemics"]["quarantine_rules"]["mode"] == "closure"
    with pytest.raises(ValueError, match=r"conflicts with the saved world \(saved: closure\)"):
        execute_run(_cli_args(tmp_path / "x", 8, resume=str(closure / "state.json"), quarantine_mode="cost_only"))


# --- 6. catalog and invalid combinations -------------------------------------------------

@pytest.mark.parametrize("flags, ok", [
    ({}, True),
    ({"epidemiology": False}, False),
    ({"contact_ledger": False}, False),
    ({"epidemiology": True, "contact_ledger": False}, False),
])
@pytest.mark.parametrize("mode", qr.QUARANTINE_MODES)
def test_an_explicit_mode_needs_epidemiology_and_the_ledger(tmp_path, pure_python_runtimes, flags, ok, mode):
    """none, cost_only and closure need both; an explicit legacy needs nothing (lead decision m4)."""
    from chronicler.main import execute_run
    args = _cli_args(tmp_path / "given", 2, quarantine_mode=mode, **flags)
    if flags.get("epidemiology") is True and flags.get("contact_ledger") is False:
        # Epidemiology's own requirement refuses first, the option given or not.
        for given in (args, _cli_args(tmp_path / "omitted", 2, **flags)):
            with pytest.raises(ValueError, match="Epidemiology spreads along the contact ledger"):
                execute_run(given)
    elif ok or mode == "legacy":
        execute_run(args)
        saved = json.loads((tmp_path / "given/state.json").read_text()).get("epidemics")
        assert (saved or {}).get("quarantine_rules", {}).get("mode", "legacy") == mode
        if mode == "legacy":
            # Exactly the option omitted, with epidemics on or off.
            execute_run(_cli_args(tmp_path / "omitted", 2, **flags))
            assert (tmp_path / "given/state.json").read_bytes() == (tmp_path / "omitted/state.json").read_bytes()
    else:
        with pytest.raises(ValueError, match="epidemiology and the contact ledger"):
            execute_run(args)


def test_a_json_resume_cannot_switch_off_what_saved_rules_need(tmp_path, pure_python_runtimes):
    """Refused explicitly, as the exact-checkpoint path refuses (review m1)."""
    from chronicler.main import execute_run
    closure = tmp_path / "closure"
    execute_run(_cli_args(closure, 6, quarantine_mode="closure"))
    for flag, field in (("--no-epidemiology", "epidemiology"), ("--no-contact-ledger", "contact_ledger")):
        args = _cli_args(tmp_path / field, 10, resume=str(closure / "state.json"), **{field: False})
        with pytest.raises(ValueError, match=rf"{flag} conflicts with this world's saved quarantine rules "
                                             r"\(--quarantine-mode closure\)"):
            execute_run(args)
        assert not (tmp_path / field / "state.json").exists()
    # Explicit legacy is no escape hatch on a world with other saved rules.
    with pytest.raises(ValueError, match=r"--quarantine-mode legacy conflicts with the saved world \(saved: closure\)"):
        execute_run(_cli_args(tmp_path / "legacy", 10, resume=str(closure / "state.json"), quarantine_mode="legacy"))
    # A legacy world keeps its old freedom: the ledger may be switched off on resume.
    legacy = tmp_path / "plain"
    execute_run(_cli_args(legacy, 4))
    execute_run(_cli_args(tmp_path / "plain_off", 8, resume=str(legacy / "state.json"), contact_ledger=False))
    # The setters themselves refuse (the guard lives below every entry point).
    world = WorldState.load(closure / "state.json")
    with pytest.raises(ValueError, match="--no-epidemiology"):
        ep.set_epidemiology_enabled(world, False)
    with pytest.raises(ValueError, match="--no-contact-ledger"):
        cl.set_contact_ledger_enabled(world, False)
    assert world.epidemics.quarantine_rules.mode == "closure" and world.contact_ledger is not None


def test_exact_resume_accepts_explicit_legacy_on_an_epidemics_off_checkpoint(tmp_path, pure_python_runtimes):
    import chronicler.run_checkpoint as rc
    from chronicler.main import _adopt_checkpoint_args, _build_parser, execute_run
    off = tmp_path / "off"
    execute_run(_cli_args(off, 6, epidemiology=False, checkpoint_every=3, checkpoint=str(off / "c{turn}.ckpt")))
    parser = _build_parser()
    legacy = parser.parse_args(["--resume", str(off / "c3.ckpt"), "--quarantine-mode", "legacy"])
    assert _adopt_checkpoint_args(parser, legacy, rc.read_checkpoint(off / "c3.ckpt")) == []
    closure = parser.parse_args(["--resume", str(off / "c3.ckpt"), "--quarantine-mode", "closure"])
    assert any("saved: epidemiology off" in line
               for line in _adopt_checkpoint_args(parser, closure, rc.read_checkpoint(off / "c3.ckpt")))


@pytest.mark.parametrize("agents", ["off", "demographics-only", "shadow", "hybrid"])
def test_every_agent_mode_accepts_the_mode(agents, monkeypatch):
    from chronicler import agent_bridge, main
    from chronicler.main import _build_parser

    class Accepted(Exception):
        pass

    def accepted(*args, **kwargs):
        raise Accepted

    monkeypatch.setattr(agent_bridge, "AgentBridge", accepted)
    monkeypatch.setattr(main, "_create_ecology_runtime", accepted)
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    args = _build_parser().parse_args(["--agents", agents, "--quarantine-mode", "closure", "--simulate-only"])
    with pytest.raises(Accepted):
        main._configure_run(args, world, True, Path("unused/chronicle.md"))
    assert world.epidemics.quarantine_rules.mode == "closure"


def test_all_enabled_selection_with_closure_is_valid_in_the_catalog():
    from chronicler import feature_catalog as fc
    from chronicler.main import _build_parser
    selection = {}
    for entry in fc.feature_entries():
        if entry["kind"] == "bool":
            selection[entry["key"]] = True
    selection["household_retail_boundary"] = "all"
    selection["quarantine_mode"] = "closure"
    # A live surface (--live): the world-dependent --watershed is offered there too.
    surface = fc.live_surface(_build_parser().parse_args(["--agents", "hybrid", "--live"]))
    assert fc.validate_features(selection, surface) is None
    off = fc.live_surface(_build_parser().parse_args(["--agents", "hybrid", "--no-epidemiology"]))
    assert "epidemiology with the contact ledger" in fc.validate_features({"quarantine_mode": "closure"}, off)
    # An explicit legacy is the option omitted: valid without epidemiology (m4).
    assert fc.validate_features({"quarantine_mode": "legacy"}, off) is None


def test_forwarding_and_manifest_record_an_explicit_mode_only():
    import scripts.m53b_run_validation as gate
    from chronicler.batch_manifest import simulation_config
    from chronicler.expansion_features import add_expansion_arguments, expansion_arguments
    from chronicler.main import _build_parser
    parser = _build_parser()
    omitted, given = parser.parse_args([]), parser.parse_args(["--quarantine-mode", "cost_only"])
    assert "quarantine_mode" not in simulation_config(omitted)
    assert simulation_config(given)["quarantine_mode"] == "cost_only"
    assert expansion_arguments(omitted) == [] and expansion_arguments(given) == ["--quarantine-mode=cost_only"]
    # The gate runner forwards it through the same expansion seam.
    runner = argparse.ArgumentParser()
    add_expansion_arguments(runner, forwarding=True)
    forwarded = runner.parse_args(["--quarantine-mode", "closure"])
    assert gate.expansion_arguments is expansion_arguments
    assert gate.expansion_arguments(forwarded) == ["--quarantine-mode=closure"]
    assert parser.parse_args(gate.expansion_arguments(forwarded)).quarantine_mode == "closure"
    with pytest.raises(ValueError):
        qr.quarantine_arguments(argparse.Namespace(quarantine_mode="sometimes"))


def test_bundle_snapshot_and_analytics_carry_the_receipts(tmp_path, pure_python_runtimes):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import execute_run
    execute_run(_cli_args(tmp_path / "closure", 30, quarantine_mode="closure"))
    execute_run(_cli_args(tmp_path / "legacy", 30))
    closure = load_bundle(tmp_path / "closure/chronicle_bundle.json")
    legacy = load_bundle(tmp_path / "legacy/chronicle_bundle.json")
    assert all("quarantine_rules" not in s["epidemics"] for s in legacy["history"])
    records = [s["epidemics"]["quarantine_rules"] for s in closure["history"]]
    assert all(r["mode"] == "closure" and r["import_multiplier"] is False for r in records)
    closed = [r for r in records if r["closures"]]
    assert closed, "seed 7 closes within 30 turns"
    receipt = closed[0]["receipt"]
    assert receipt["phase2_observed"] is True and receipt["merchant_edges_removed"] is None  # no agent graph
    assert sorted(records[-1]["exempt"]) == sorted(qr.EXEMPT)
    metrics = ep.extract_epidemic_metrics([closure])["by_seed"][0]["quarantine_rules"]
    assert metrics["mode"] == "closure" and metrics["closed_pair_turns"] == records[-1]["totals"]["closed_pair_turns"]
    assert metrics["turns_with_decision"] == len(closed)
    assert "quarantine_rules" not in ep.extract_epidemic_metrics([legacy])["by_seed"][0]
    state = json.loads((tmp_path / "closure/state.json").read_text())["epidemics"]["quarantine_rules"]
    assert state["next_closure_id"] == records[-1]["totals"]["closures_opened"] + 1
