"""Contact & trade-flow ledger: decay, API, consumers, determinism, save/load, dormancy."""
from __future__ import annotations

import argparse
import json
import math

import pytest

from chronicler.bundle_codec import load_bundle
import chronicler.contact_ledger as cl
from chronicler.action_engine import ActionEngine
from chronicler.models import (
    Disposition, Movement, PandemicRegion, Relationship, TurnSnapshot, WorldState,
)
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world


def _world(seed: int = 42, *, ledger: bool = True, campaigns: bool = True) -> WorldState:
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.campaigns_enabled = campaigns
    cl.set_contact_ledger_enabled(world, ledger)
    return world


def _advance(world: WorldState, turns: int, *, bridge=None) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn, agent_bridge=bridge)
    return world


def _cross_civ_pair(world: WorldState) -> tuple[int, int]:
    """Two adjacent regions held by different civs."""
    index = {r.name: i for i, r in enumerate(world.regions)}
    for i, r in enumerate(world.regions):
        if r.controller is None:
            continue
        for adj in r.adjacencies:
            j = index[adj]
            other = world.regions[j].controller
            if other is not None and other != r.controller:
                return i, j
    raise AssertionError("fixture has no cross-civ border")


def _owned(world: WorldState, civ_name: str) -> list[int]:
    return [i for i, r in enumerate(world.regions) if r.controller == civ_name]


def _push(world: WorldState, src: int, dst: int, channel: int, amount: float) -> None:
    cl._pending(world).append((src, dst, channel, amount))


# --- ledger mechanics ----------------------------------------------------------------

def test_decay_fold_prune_and_civ_aggregates():
    world = _world(ledger=True)
    a, b = _cross_civ_pair(world)
    ca, cb = world.regions[a].controller, world.regions[b].controller
    _push(world, a, b, cl.TRADE, 4.0)
    _push(world, b, a, cl.PEOPLE, 2.0)
    cl.update_contact_ledger(world)
    assert cl.flow(world, a, b, "trade", directed=True) == 4.0
    assert cl.flow(world, b, a, "trade", directed=True) == 0.0
    assert cl.flow(world, a, b, "people") == 2.0  # undirected sum
    assert cl.civ_flow(world, ca, cb) == cl.civ_flow(world, cb, ca) == 4.0
    assert cl.civ_flow(world, ca, cb, "people") == 2.0
    # Transient inputs are consumed exactly once.
    assert world._contact_pending is None
    cl.update_contact_ledger(world)
    assert cl.flow(world, a, b, "trade") == pytest.approx(4.0 * cl.DECAY[cl.TRADE])
    assert cl.flow(world, a, b, "people") == pytest.approx(2.0 * cl.DECAY[cl.PEOPLE])
    # trade_volume is the rounded decayed goods flow, both directions.
    assert world.relationships[ca][cb].trade_volume == round(4.0 * cl.DECAY[cl.TRADE])
    assert world.relationships[cb][ca].trade_volume == round(4.0 * cl.DECAY[cl.TRADE])
    for _ in range(80):
        cl.update_contact_ledger(world)
    assert world.contact_ledger.edges == []  # pruned: the matrix stays sparse
    assert cl.civ_flow(world, ca, cb) == 0.0
    assert world.relationships[ca][cb].trade_volume == 0


def test_dependence_top_partners_and_partner_count():
    world = _world(ledger=True)
    a, b = _cross_civ_pair(world)
    ca, cb = world.regions[a].controller, world.regions[b].controller
    own = _owned(world, ca)
    internal = [j for j in own if j != a]
    _push(world, a, b, cl.TRADE, 6.0)
    if internal:
        _push(world, a, internal[0], cl.TRADE, 4.0)
    cl.update_contact_ledger(world)
    commerce = world.contact_ledger.commerce[ca]
    assert commerce == (10.0 if internal else 6.0)
    assert cl.dependence(world, ca, cb) == pytest.approx(min(1.0, 6.0 / max(cl.COMMERCE_FLOOR, commerce)))
    # The partner's whole commerce is this pair, so it fully depends on it.
    assert cl.dependence(world, cb, ca) == 1.0
    assert cl.top_partners(world, ca) == [(cb, 6.0)]
    assert cl.trade_partner_count(world, ca) == 1
    assert cl.trade_partner_count(world, ca, min_flow=7.0) == 0
    assert cl.region_partners(world, a) == sorted({b} | ({internal[0]} if internal else set()))


def test_end_of_turn_inputs_armies_pilgrims_hostages():
    from chronicler.models import Army
    world = _world(ledger=True)
    a, b = _cross_civ_pair(world)
    civ = world.civ_map[world.regions[a].controller]
    world.war_state.armies.append(Army(
        army_id="x1", name="Host", civ=civ.name, war_key="k", region=world.regions[b].name,
        home_region=world.regions[a].name, soldiers=12,
    ))
    cl.update_contact_ledger(world)
    assert cl.flow(world, a, b, "soldiers", directed=True) == 12.0
    assert world.contact_ledger.last_inflow[cl.SOLDIERS] == 12.0


def test_trade_action_records_a_bump_instead_of_incrementing():
    from chronicler.action_engine import resolve_trade
    world = _world(ledger=True)
    a, b = _cross_civ_pair(world)
    c1 = world.civ_map[world.regions[a].controller]
    c2 = world.civ_map[world.regions[b].controller]
    resolve_trade(c1, c2, world)
    assert world.relationships[c1.name][c2.name].trade_volume == 0  # derived at turn end
    cl.update_contact_ledger(world)
    assert cl.civ_flow(world, c1.name, c2.name) == cl.TRADE_ACTION_VALUE
    off = _world(ledger=False)
    resolve_trade(off.civ_map[c1.name], off.civ_map[c2.name], off)
    assert off.relationships[c1.name][c2.name].trade_volume == 1  # base semantics unchanged


# --- consumers -----------------------------------------------------------------------

def _set_pair_flow(world, ca: str, cb: str, trade: float, people: float = 0.0) -> None:
    key = (ca, cb) if ca < cb else (cb, ca)
    world.contact_ledger.pairs = sorted(
        [row for row in world.contact_ledger.pairs if (row[0], row[1]) != key]
        + [(key[0], key[1], trade, people, 0.0, 0.0)]
    )
    world.contact_ledger.commerce[ca] = max(world.contact_ledger.commerce.get(ca, 0.0), trade)
    world.contact_ledger.commerce[cb] = max(world.contact_ledger.commerce.get(cb, 0.0), trade)
    world.contact_ledger.invalidate()


def test_movement_spread_follows_contact_not_trade_volume():
    from chronicler.movements import _process_spread
    world = _world(ledger=True)
    origin, target = world.civilizations[0], world.civilizations[1]
    target.values = list(origin.values)
    world.movements = [Movement(id="movement_0", origin_civ=origin.name, origin_turn=0,
                                value_affinity=origin.values[0], adherents={origin.name: 0})]
    # trade_volume alone no longer spreads ideas when the ledger is on.
    world.relationships[origin.name][target.name].trade_volume = 99
    for turn in range(30):
        world.turn = turn
        _process_spread(world)
    assert set(world.movements[0].adherents) == {origin.name}
    # Strong contact (here: migrants, no goods) spreads it.
    _set_pair_flow(world, origin.name, target.name, trade=0.0, people=100.0)
    for turn in range(30, 60):
        world.turn = turn
        _process_spread(world)
    assert target.name in world.movements[0].adherents
    assert cl.movement_adoption_pct(world, origin.name, target.name, 100) == cl.MOVEMENT_MAX_PCT


def test_merchant_trigger_counts_living_partners_with_real_flow():
    from chronicler.traditions import update_event_counts
    world = generate_world(seed=5, num_regions=12, num_civs=4)
    cl.set_contact_ledger_enabled(world, True)
    hub = world.civilizations[0]
    partners = world.civilizations[1:1 + cl.MERCHANT_HUB_PARTNERS]
    for other in partners:
        _set_pair_flow(world, hub.name, other.name, trade=2.0)
        # Stale cumulative trade_volume is ignored.
        world.relationships[hub.name][other.name].trade_volume = 0
    update_event_counts(world)
    assert hub.event_counts["high_trade_route_turns"] == 1
    _set_pair_flow(world, hub.name, partners[-1].name, trade=0.5)  # below the partner floor
    world.relationships[hub.name][partners[-1].name].trade_volume = 50  # ever traded, no live flow
    update_event_counts(world)
    assert hub.event_counts["high_trade_route_turns"] == 0
    # A dead partner does not count.
    _set_pair_flow(world, hub.name, partners[-1].name, trade=2.0)
    partners[-1].regions = []
    update_event_counts(world)
    assert hub.event_counts["high_trade_route_turns"] == 0


def test_merchant_hub_threshold_scales_with_living_civs():
    # Every other living civ, and at least three: with four living civs or
    # fewer this is the template world's rule (three partners).
    def needed(living, total=12):
        world = generate_world(seed=5, num_regions=24, num_civs=total, worldgen="procedural")
        for civ in world.civilizations[living:]:
            civ.regions = []
        return cl.merchant_hub_partners(world)

    assert [needed(n) for n in (1, 2, 3, 4)] == [3, 3, 3, 3]
    assert [needed(n) for n in (5, 6, 10, 12)] == [4, 5, 9, 11]


def test_merchant_trigger_in_a_ten_civ_world_needs_every_partner():
    from chronicler.traditions import update_event_counts
    world = generate_world(seed=5, num_regions=24, num_civs=10, worldgen="procedural")
    cl.set_contact_ledger_enabled(world, True)
    hub = world.civilizations[0]
    others = world.civilizations[1:]
    for other in others[:8]:
        _set_pair_flow(world, hub.name, other.name, trade=2.0)
    update_event_counts(world)
    assert cl.merchant_hub_partners(world) == 9
    assert hub.event_counts.get("high_trade_route_turns", 0) == 0
    _set_pair_flow(world, hub.name, others[8].name, trade=2.0)
    update_event_counts(world)
    assert hub.event_counts["high_trade_route_turns"] == 1


def test_trade_warmth_upgrades_up_to_friendly_only():
    world = _world(ledger=True)
    a, b = world.civilizations[0].name, world.civilizations[1].name
    for x, y in ((a, b), (b, a)):
        world.relationships[x][y].disposition = Disposition.SUSPICIOUS
        world.relationships[x][y].disposition_drift = 0
    _set_pair_flow(world, a, b, trade=3.0)
    for _ in range(30):
        cl.apply_trade_warmth(world)
    assert world.relationships[a][b].disposition == Disposition.FRIENDLY
    assert world.relationships[b][a].disposition == Disposition.FRIENDLY
    for _ in range(30):
        cl.apply_trade_warmth(world)
    assert world.relationships[a][b].disposition == Disposition.FRIENDLY  # capped


def test_embargo_and_war_shocks_scale_with_dependence():
    world = _world(ledger=True)
    a, b = world.civilizations[0], world.civilizations[1]
    assert cl.embargo_dependence_damage(world, a.name, b.name) == (0, 0)
    _set_pair_flow(world, a.name, b.name, trade=20.0)
    world.contact_ledger.commerce[a.name] = 40.0  # a: D = 0.5; b: D = 1.0
    world.contact_ledger.commerce[b.name] = 20.0
    assert cl.embargo_dependence_damage(world, a.name, b.name) == (
        round(cl.EMBARGO_DEPENDENCE_STABILITY * 1.0), round(cl.EMBARGO_DEPENDENCE_STABILITY * 0.5))
    sa, sb = a.stability, b.stability
    cl.apply_war_trade_shock(world, a.name, b.name)
    assert a.stability == max(0, sa - round(cl.WAR_DEPENDENCE_STABILITY * 0.5))
    assert b.stability == max(0, sb - cl.WAR_DEPENDENCE_STABILITY)
    off = _world(ledger=False)
    s0 = off.civilizations[0].stability
    cl.apply_war_trade_shock(off, off.civilizations[0].name, off.civilizations[1].name)
    assert off.civilizations[0].stability == s0


def test_pandemic_spreads_along_contact_not_plain_adjacency():
    from chronicler.emergence import tick_pandemic
    world = _world(ledger=True)
    a, b = _cross_civ_pair(world)
    world.pandemic_state = [PandemicRegion(region_name=world.regions[a].name, severity=1, turns_remaining=5)]
    # Adjacent trade partners but no recorded contact: no spread.
    tick_pandemic(world, routes=[tuple(sorted((world.regions[a].controller, world.regions[b].controller)))])
    assert world.regions[b].name not in {p.region_name for p in world.pandemic_state}
    # Heavy recorded contact (no route at all): spread is near certain.
    _push(world, a, b, cl.PEOPLE, 500.0)
    cl.update_contact_ledger(world)
    contact = cl.region_contact(world, a, b)
    assert contact == 500.0 * cl.CONTACT_WEIGHTS[cl.PEOPLE]
    assert cl.pandemic_spread_probability(world, a, b) == pytest.approx(
        1 - math.exp(-contact / cl.PANDEMIC_CONTACT_SCALE))
    tick_pandemic(world, routes=[])
    assert world.regions[b].name in {p.region_name for p in world.pandemic_state}


# --- determinism, save/load, switch --------------------------------------------------

def _fingerprint(world: WorldState) -> str:
    return world.model_dump_json()


def test_off_mode_ledger_runs_are_deterministic_and_live():
    w1 = _advance(_world(11), 40)
    w2 = _advance(_world(11), 40)
    assert _fingerprint(w1) == _fingerprint(w2)
    assert w1.contact_ledger.edges, "route proxy recorded goods flows"
    assert w1.contact_ledger.last_update_turn == 39


def test_save_load_round_trip_continues_identically(tmp_path):
    straight = _advance(_world(7), 40)
    first = _advance(_world(7), 20)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.contact_ledger == first.contact_ledger
    _advance(resumed, 20)
    assert resumed.contact_ledger.model_dump() == straight.contact_ledger.model_dump()
    assert _fingerprint(resumed) == _fingerprint(straight)


def test_feature_off_never_runs_ledger_code(monkeypatch):
    # Import before patching: these modules bind ledger functions at import
    # time, and a first import under the patch would keep the forbidden stub
    # (and monkeypatch would "restore" it) for later tests in this process.
    import chronicler.movements as movements
    import chronicler.traditions as traditions

    def forbidden(*args, **kwargs):
        raise AssertionError("contact ledger invoked while disabled")

    for name in ("update_contact_ledger", "observe_phase2", "apply_trade_warmth",
                 "movement_adoption_pct", "trade_partner_count", "record_trade_action"):
        monkeypatch.setattr(cl, name, forbidden)
    monkeypatch.setattr(movements, "movement_adoption_pct", forbidden)
    monkeypatch.setattr(traditions, "trade_partner_count", forbidden)
    world = _advance(_world(42, ledger=False), 40)
    assert world.contact_ledger is None
    assert "contact_ledger" not in world.model_dump(mode="json")


def test_dormant_fields_are_omitted_and_old_saves_load():
    world = _world(ledger=False)
    assert "contact_ledger" not in json.loads(world.model_dump_json())
    snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert "contact" not in snap.model_dump()
    snap.contact = {"edges": 0}
    assert snap.model_dump()["contact"] == {"edges": 0}
    on = _world(ledger=True)
    raw = json.loads(on.model_dump_json())
    assert raw["contact_ledger"]["edges"] == []
    raw.pop("contact_ledger")
    assert WorldState.model_validate(raw).contact_ledger is None
    assert Relationship().trade_volume == 0


def _cli_args(tmp_path, *, ledger, turns=12, agents="off"):
    return argparse.Namespace(
        seed=42, turns=turns, civs=4, regions=8, output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, pause_every=None, simulate_only=True, agents=agents, contact_ledger=ledger,
    )


def test_cli_flag_persists_and_bundle_carries_contact_history(tmp_path):
    from chronicler.analytics import generate_report
    from chronicler.main import _build_parser, execute_run
    assert _build_parser().parse_args(["--contact-ledger"]).contact_ledger is True
    assert _build_parser().parse_args(["--no-contact-ledger"]).contact_ledger is False
    assert _build_parser().parse_args([]).contact_ledger is None
    execute_run(_cli_args(tmp_path, ledger=True))
    state = json.loads((tmp_path / "state.json").read_text())
    assert "contact_ledger" in state
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    assert all("contact" in snap for snap in bundle["history"])
    assert set(bundle["history"][-1]["contact"]) == {
        "edges", "contact_pairs", "trade_pairs", "inflow", "stock", "top_trade_pairs"}
    metrics = cl.extract_contact_metrics([bundle])
    assert metrics["runs"] == 1 and metrics["by_seed"][0]["turns"] == len(bundle["history"])
    assert cl.extract_contact_metrics([{"history": [{}]}]) == {}
    batch = tmp_path / "batch"
    for name in ("seed_1", "seed_2"):
        (batch / name).mkdir(parents=True)
        (batch / name / "chronicle_bundle.json").write_text(json.dumps(bundle))
    assert generate_report(batch)["contact_ledger"]["runs"] == 2


def test_gate_runner_forwards_the_switch_only_when_explicit():
    from scripts.m53b_run_validation import _contact_ledger_args
    assert _contact_ledger_args(argparse.Namespace(contact_ledger=None)) == []
    assert _contact_ledger_args(argparse.Namespace(contact_ledger=True)) == ["--contact-ledger"]
    assert _contact_ledger_args(argparse.Namespace(contact_ledger=False)) == ["--no-contact-ledger"]
    assert _contact_ledger_args(argparse.Namespace()) == []


def test_new_worlds_follow_default_and_resume_keeps_saved_setting(tmp_path):
    from chronicler.main import execute_run
    fresh = tmp_path / "fresh"
    execute_run(_cli_args(fresh, ledger=None, turns=3))
    saved = json.loads((fresh / "state.json").read_text())
    assert ("contact_ledger" in saved) is cl.DEFAULT_ENABLED_FOR_NEW_WORLDS
    on = tmp_path / "on"
    execute_run(_cli_args(on, ledger=True, turns=3))
    resumed = _cli_args(on, ledger=None, turns=5)
    resumed.resume = str(on / "state.json")
    resumed.state = str(on / "resumed.json")
    execute_run(resumed)
    assert "contact_ledger" in json.loads((on / "resumed.json").read_text())
    off = tmp_path / "off"
    execute_run(_cli_args(off, ledger=False, turns=3))
    assert "contact_ledger" not in json.loads((off / "state.json").read_text())


# --- agent modes (native) ------------------------------------------------------------

def _hybrid(seed: int):
    pytest.importorskip("chronicler_agents")
    from chronicler.agent_bridge import AgentBridge
    world = _world(seed)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    return world, bridge


@pytest.mark.native
def test_native_pending_arrivals_getter_is_read_only():
    agents = pytest.importorskip("chronicler_agents")
    sim = agents.AgentSimulator(3, 42)
    batch = sim.get_pending_arrivals()
    assert batch.num_rows == 0
    assert list(batch.schema.names) == ["source_region", "dest_region", "good_slot", "qty"]


@pytest.mark.native
def test_hybrid_ledger_records_merchants_and_migrants_deterministically():
    w1, b1 = _hybrid(7)
    w2, b2 = _hybrid(7)
    _advance(w1, 25, bridge=b1)
    _advance(w2, 25, bridge=b2)
    assert w1.contact_ledger.model_dump() == w2.contact_ledger.model_dump()
    stock = [0.0, 0.0, 0.0, 0.0]
    for row in w1.contact_ledger.edges:
        for c in range(4):
            stock[c] += row[2 + c]
    assert stock[cl.TRADE] > 0, "merchant deliveries recorded"
    assert stock[cl.PEOPLE] > 0, "migrations recorded"
