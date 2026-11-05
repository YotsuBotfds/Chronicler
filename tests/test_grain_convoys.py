"""L4 public grain convoys under risk (offline: no native extension).

Direct goods-economy fixtures drive the real granary, shipment and convoy
code through the livelihoods phase hooks, turn by turn, with
``CHRONICLER_CHECK_RESOURCES=1`` so the reserve ledger and the convoy grain
closure are checked every turn. Topology (template world, seed 42): the
buyer Thornwall keeps the granary of Verdant Plains (2) and holds Thornwood
(4); Obsidian Shore (7, Ashkari) and Frostholm Tundra (0, Kethani) border
Thornwood but not Verdant Plains, so they are the multi-hop foreign sources
the one-hop shipment pass skips. Ashara Desert (3, Selurian) borders
Verdant Plains directly (a shipment source).
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import pickle
import random

import pytest

from chronicler import grain_convoys as C
from chronicler import grain_reserves as G
from chronicler import livelihoods as L
from chronicler import public_grain_shipments as S
from chronicler.economy import EconomyResult
from chronicler.grain_convoys_state import COUNTERS, GrainConvoyState
from chronicler.grain_reserves_state import CONVOY_ARRIVED, FLOW_KINDS
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.models import Army, Disposition, WorldState
from chronicler.world_gen import generate_world

DEST, OWN, SOURCE, FAR, DIRECT = 2, 4, 7, 0, 3
BUYER, SELLER, KETHANI, SELURIAN = 2, 0, 1, 3
NO_THREAT = (0.99, 0.0)
THREAT_UNREPELLED = (0.0, 0.99)


def economy(world, sufficiency=1.0):
    result = EconomyResult()
    for region in world.regions:
        result.food_sufficiency[region.name] = sufficiency
        result.market_demand[region.name] = (10.0, 0.0, 0.0, 0.0)
        result.market_supply[region.name] = (10.0 * sufficiency, 0.0, 0.0, 0.0)
        result.slot_output[region.name] = [0.0, 0.0, 0.0]
        result.forage_output[region.name] = 10.0
    return result


def build(monkeypatch, *, source=SOURCE, policy=None, draws=NO_THREAT, convoys=True):
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    monkeypatch.setattr(G, "_observe", lambda *args: None)  # fixed stock target
    if draws is not None:
        monkeypatch.setattr(C, "_draws", lambda world, convoy, forward: draws)
    world = generate_world(seed=42)
    world.agent_mode = "demographics-only"
    world.turn = 30
    for relations in world.relationships.values():
        for relation in relations.values():
            relation.disposition = Disposition.NEUTRAL
    G.set_grain_reserves_enabled(world, True)
    G._ensure(world)
    for civ in world.civilizations:
        civ.treasury = 0
    world.civilizations[BUYER].treasury = 200
    for region in world.regions:
        region.population = 20
        region.stockpile.goods.clear()
    world.regions[source].stockpile.goods["grain"] = 1000.0
    granary = world.grain_reserves.granaries[DEST]
    granary.owner = BUYER
    granary.observed = 24
    granary.target = 40.0
    S.set_public_grain_shipments_enabled(world, True)
    if convoys:
        world.livelihoods = LivelihoodsState()
        args = type("Args", (), {"convoy_route_policy": policy})()
        C.set_grain_convoys_enabled(world, True, args=args, agent_mode=world.agent_mode)
    return world


def step(world, sufficiency=1.0, before=None):
    """One turn's Phase 2 opening and Phase 10 granary/convoy order."""
    result = economy(world, sufficiency)
    G.open_granaries(world, result)
    released = result.food_sufficiency[world.regions[DEST].name]
    if before is not None:
        before(world)
    events = L.phase10_before_reserves(world, economy_result=result)
    events += G.tick_grain_reserves(world, economy_result=result)
    events += L.phase10(world, economy_result=result)
    world.turn += 1
    return released, events


def state(world) -> GrainConvoyState:
    return world.livelihoods.grain_convoys


def frame(world):
    return [(row.operation, row.at, row.status) for row in state(world).frame]


def no_more_orders(world):
    """Keep the in-flight convoy alone: no further procurement."""
    for civ in world.civilizations:
        civ.treasury = 0


def assert_closes(world):
    k = state(world).counters
    placed = math.fsum([k["delivered"], k["captured_grain"], k["lost_grain"], k["returned_grain"],
                        k["stranded_grain"], *(c.cargo for c in state(world).convoys)])
    assert k["committed_net"] == pytest.approx(placed, rel=1e-12, abs=1e-12)
    assert k["sent"] == pytest.approx(k["committed_net"] + k["transit_loss"], rel=1e-12)


def test_uninterrupted_convoy_pays_once_moves_a_leg_per_turn_and_feeds_after_release(monkeypatch):
    world = build(monkeypatch)
    cash = [c.treasury for c in world.civilizations]
    step(world)
    st = state(world)
    assert len(st.convoys) == 1 and S.shipment_state(world).pending == []
    convoy = st.convoys[0]
    assert convoy.route == [SOURCE, OWN, DEST] and convoy.status == "en_route" and not convoy.escorted
    assert convoy.paid == 18 and convoy.sent == pytest.approx(18.0) and convoy.net == pytest.approx(17.1)
    assert world.regions[SOURCE].stockpile.goods["grain"] == pytest.approx(1000.0 - convoy.sent)
    after = [c.treasury for c in world.civilizations]
    assert after[BUYER] == cash[BUYER] - 18 and after[SELLER] == cash[SELLER] + 18
    assert sum(after) == sum(cash)
    no_more_orders(world)
    step(world)
    assert frame(world) == [("advanced", OWN, "en_route")]
    assert world.grain_reserves.granaries[DEST].grain == 0.0
    # Arrival turn: the granary receives the cargo, but nobody eats it yet.
    released, _ = step(world, sufficiency=0.2)
    assert released == 0.2
    assert frame(world) == [("arrived", DEST, "arrived")]
    assert st.convoys == [] and st.frame[0].keeper == BUYER
    assert world.grain_reserves.granaries[DEST].grain == pytest.approx(convoy.net)
    arrivals = [f for f in world.grain_reserves.flows if f.kind == CONVOY_ARRIVED]
    assert len(arrivals) == 1 and arrivals[0].amount == pytest.approx(convoy.net) and arrivals[0].cost == 0
    assert FLOW_KINDS[CONVOY_ARRIVED] == "convoy_arrived" and FLOW_KINDS.index("convoy_arrived") == 9
    assert [c.treasury for c in world.civilizations] == [0, 0, 0, 0]  # no second payment
    # The next opening releases it.
    released, _ = step(world, sufficiency=0.2)
    assert released > 0.2
    assert st.counters["arrived"] == 1 and st.counters["delivered"] == pytest.approx(convoy.net)
    assert_closes(world)


def test_one_hop_shipments_are_unchanged_and_convoys_only_take_the_rest(monkeypatch):
    worlds = []
    for convoys in (False, True):
        world = build(monkeypatch, convoys=convoys)
        world.regions[DIRECT].stockpile.goods["grain"] = 50.0  # a small direct surplus (10)
        step(world)
        worlds.append(world)
    off, on = worlds
    assert ([o.model_dump() for o in S.shipment_state(on).pending]
            == [o.model_dump() for o in S.shipment_state(off).pending])
    assert len(S.shipment_state(on).pending) == 1 and S.shipment_state(on).pending[0].paid == 10
    convoy = state(on).convoys[0]
    assert convoy.paid == 8  # what the granary pass left of the 18 budget
    assert convoy.source == SOURCE and convoy.source not in G._route_graph(on)[DEST]
    assert on.civilizations[BUYER].treasury == off.civilizations[BUYER].treasury - convoy.paid


def test_inbound_convoy_cargo_is_not_ordered_again(monkeypatch):
    world = build(monkeypatch)
    step(world)
    convoy = state(world).convoys[0]
    world.grain_reserves.granaries[DEST].target = convoy.net
    before = [c.treasury for c in world.civilizations]
    step(world)
    assert len(state(world).convoys) == 1 and S.shipment_state(world).pending == []
    assert [c.treasury for c in world.civilizations] == before
    assert C.inbound_by_destination(world)[DEST] == pytest.approx(convoy.net)


def test_closure_before_departure_waits_then_returns_cargo_to_origin_market(monkeypatch):
    world = build(monkeypatch)
    step(world)
    convoy = state(world).convoys[0]
    no_more_orders(world)
    world.regions[SOURCE].route_suspensions["trade_route"] = 9  # every road out of the origin
    origin = world.regions[SOURCE].stockpile.goods["grain"]
    step(world)
    assert frame(world) == [("waited", SOURCE, "waiting")]
    assert state(world).frame[0].closure == "route_closed"
    step(world)
    assert frame(world) == [("waited", SOURCE, "waiting")]
    assert C.inbound_by_destination(world)[DEST] == pytest.approx(convoy.net)
    _, events = step(world)
    assert frame(world) == [("returned", SOURCE, "returned")]
    assert state(world).frame[0].sink == "origin_market"
    assert world.regions[SOURCE].stockpile.goods["grain"] == pytest.approx(origin + convoy.net)
    assert [c.treasury for c in world.civilizations] == [0, 0, 0, 0]  # nothing refunded or paid again
    k = state(world).counters
    assert (k["waits"], k["turned_back"], k["returned"]) == (2, 1, 1)
    assert any(e.event_type == "grain_convoy_returned" for e in events)
    assert world.grain_reserves.granaries[DEST].grain == 0.0
    assert_closes(world)


def test_closure_in_transit_turns_back_along_the_travelled_road(monkeypatch):
    world = build(monkeypatch)
    step(world)
    convoy = state(world).convoys[0]
    no_more_orders(world)
    step(world)
    assert frame(world) == [("advanced", OWN, "en_route")]
    world.regions[DEST].route_suspensions["trade_route"] = 9  # the destination is cut off
    step(world)
    step(world)
    assert frame(world) == [("waited", OWN, "waiting")]
    step(world)
    assert frame(world) == [("turned_back", OWN, "returning")]
    assert C.inbound_by_destination(world)[DEST] == 0.0  # no longer heading there
    step(world)
    assert frame(world) == [("returned", SOURCE, "returned")]
    assert state(world).counters["returned_grain"] == pytest.approx(convoy.net)
    assert_closes(world)


def test_closed_edge_reroutes_over_the_permitted_graph_and_resumes_mid_leg(monkeypatch, tmp_path):
    world = build(monkeypatch)
    step(world)
    no_more_orders(world)
    # Ashkari turns hostile to Thornwall: the merchants' road 7 -> 4 closes;
    # 7 -> 0 -> 4 through Kethani stays open.
    world.relationships["Ashkari Nomads"]["Thornwall Confederacy"].disposition = Disposition.HOSTILE
    step(world)
    convoy = state(world).convoys[0]
    row = state(world).frame[0]
    assert row.rerouted and row.closure == "route_closed" and row.operation == "advanced"
    assert convoy.route == [SOURCE, FAR, OWN, DEST] and convoy.reroutes == 1
    assert (convoy.leg, convoy.progress, convoy.leg_turns) == (0, 1, 2)  # tundra edge: mid-leg
    world.grain_reserves._ledger = None  # a complete-turn boundary
    from chronicler.run_checkpoint import load_world, save_world
    save_world(tmp_path / "w.ckpt", world)
    world.save(tmp_path / "w.json")
    copies = [load_world(tmp_path / "w.ckpt"), WorldState.load(tmp_path / "w.json")]
    for copy in copies:
        assert copy.model_dump_json() == world.model_dump_json()
        assert type(state(copy)) is GrainConvoyState
    for _ in range(4):
        for candidate in (world, *copies):
            step(candidate)
        assert all(copy.model_dump_json() == world.model_dump_json() for copy in copies)
    assert state(world).counters["arrived"] == 1 and state(world).counters["legs"] == 3
    assert world.grain_reserves.granaries[DEST].grain > 0
    assert_closes(world)


def test_interception_captures_cargo_into_the_captors_market_once(monkeypatch):
    world = build(monkeypatch)
    step(world)
    convoy = state(world).convoys[0]
    no_more_orders(world)
    # Thornwall and Kethani go to war; Kethani holds Frostholm (0) beside Thornwood.
    world.active_wars.append(("Thornwall Confederacy", "Kethani Empire"))
    monkeypatch.setattr(C, "_draws", lambda world, convoy, forward: THREAT_UNREPELLED)
    before = world.regions[FAR].stockpile.goods.get("grain", 0.0)
    _, events = step(world)
    row = state(world).frame[0]
    assert (row.operation, row.threat, row.captor, row.sink, row.sink_region) == (
        "captured", "frontier", KETHANI, "captor_market", FAR)
    assert row.threat_risk == pytest.approx(C.FRONTIER_THREAT)
    assert world.regions[FAR].stockpile.goods["grain"] == pytest.approx(before + convoy.net)
    assert state(world).convoys == [] and world.grain_reserves.granaries[DEST].grain == 0.0
    assert any(e.event_type == "grain_convoy_captured" for e in events)
    step(world)
    assert world.regions[FAR].stockpile.goods["grain"] == pytest.approx(before + convoy.net)
    assert state(world).counters["captured_grain"] == pytest.approx(convoy.net)
    assert_closes(world)


def test_brigands_destroy_cargo_into_the_loss_sink_without_refund(monkeypatch):
    world = build(monkeypatch)
    step(world)
    convoy = state(world).convoys[0]
    no_more_orders(world)
    step(world)  # at Thornwood
    # Verdant Plains passes to Selurian (at peace): the last edge ends outside
    # the buyer's land, where only brigands threaten.
    world.regions[DEST].controller = "Selurian Republic"
    monkeypatch.setattr(C, "_draws", lambda world, convoy, forward: THREAT_UNREPELLED)
    markets = [r.stockpile.goods.get("grain", 0.0) for r in world.regions]
    step(world)
    row = state(world).frame[0]
    assert (row.operation, row.threat, row.sink) == ("lost", "brigands", "raid")
    assert [r.stockpile.goods.get("grain", 0.0) for r in world.regions] == markets
    assert world.grain_reserves.granaries[DEST].grain == 0.0
    assert [c.treasury for c in world.civilizations] == [0, 0, 0, 0]  # nothing refunded
    assert state(world).counters["lost_grain"] == pytest.approx(convoy.net)
    assert_closes(world)


def test_destination_owner_change_delivers_and_records_the_keeper(monkeypatch):
    world = build(monkeypatch)
    step(world)
    convoy = state(world).convoys[0]
    no_more_orders(world)
    step(world)
    world.regions[DEST].controller = "Selurian Republic"  # settled by the next opening
    step(world)
    row = state(world).frame[0]
    assert row.operation == "arrived" and row.keeper == SELURIAN != BUYER
    assert world.grain_reserves.granaries[DEST].owner == SELURIAN
    assert world.grain_reserves.granaries[DEST].grain == pytest.approx(convoy.net)
    assert state(world).counters["captured_delivery"] == pytest.approx(convoy.net)


def test_safest_policy_pays_a_disclosed_escort_sink_that_can_be_wasted(monkeypatch):
    world = build(monkeypatch, policy="safest")
    cash = [c.treasury for c in world.civilizations]
    step(world)
    convoy = state(world).convoys[0]
    assert convoy.escorted and convoy.escort_fee == C.ESCORT_FEE_PER_LEG * 2
    assert convoy.paid == 18 - convoy.escort_fee
    after = [c.treasury for c in world.civilizations]
    assert after[SELLER] == cash[SELLER] + convoy.paid  # the fee is nobody's income
    assert sum(cash) - sum(after) == convoy.escort_fee
    assert state(world).frame[0].escort_fee == convoy.escort_fee
    no_more_orders(world)
    step(world)  # mustering: still on the first leg
    assert (state(world).convoys[0].leg, state(world).convoys[0].progress) == (0, 1)
    step(world)
    step(world)
    assert frame(world) == [("arrived", DEST, "arrived")]
    k = state(world).counters
    assert k["escorted"] == 1 and k["escort_paid"] == convoy.escort_fee
    assert k["threats"] == 0 and k["escort_wasted"] == 1 and k["escort_wasted_paid"] == convoy.escort_fee


def test_escort_beats_off_a_threat_and_is_not_wasted(monkeypatch):
    world = build(monkeypatch, policy="safest")
    step(world)
    no_more_orders(world)
    world.active_wars.append(("Thornwall Confederacy", "Kethani Empire"))
    monkeypatch.setattr(C, "_draws", lambda world, convoy, forward: (0.0, 0.0))
    for _ in range(3):
        step(world)
    k = state(world).counters
    assert k["threats"] == 1 and k["repelled"] == 1 and k["arrived"] == 1 and k["escort_wasted"] == 0


@pytest.mark.parametrize("army", [False, True])
def test_adaptive_buys_an_escort_only_when_expected_loss_exceeds_its_fee(monkeypatch, army):
    world = build(monkeypatch)
    world.active_wars.append(("Thornwall Confederacy", "Kethani Empire"))
    if army:
        world.war_state.armies.append(Army(army_id="k1", name="Host", civ="Kethani Empire", war_key="w",
                                           region=world.regions[FAR].name, home_region=world.regions[FAR].name,
                                           soldiers=500))
    step(world)
    convoy = state(world).convoys[0]
    assert convoy.exposed_route == [SOURCE, OWN, DEST]
    risk = C.ARMY_THREAT if army else C.FRONTIER_THREAT
    assert convoy.exposed_risk == pytest.approx(risk)
    value = 18
    expect = (C.ESCORT_FEE_PER_LEG * 2 + risk * (1 - C.ESCORT_PROTECTION) * value) < risk * value
    assert convoy.escorted is expect is army


def test_arrival_versus_loss_changes_the_actual_release(monkeypatch):
    results = {}
    for outcome in ("arrived", "lost"):
        world = build(monkeypatch)
        step(world)
        no_more_orders(world)
        step(world)
        if outcome == "lost":
            world.regions[DEST].controller = "Selurian Republic"
            monkeypatch.setattr(C, "_draws", lambda world, convoy, forward: THREAT_UNREPELLED)
        else:
            world.regions[DEST].controller = "Selurian Republic"
            monkeypatch.setattr(C, "_draws", lambda world, convoy, forward: NO_THREAT)
        step(world, sufficiency=0.2)
        assert state(world).frame[0].operation == outcome
        released, _ = step(world, sufficiency=0.2)
        results[outcome] = (released, world.grain_reserves.counters["released"])
    assert results["lost"] == (0.2, 0.0)
    assert results["arrived"][0] > 0.2 and results["arrived"][1] > 0


def test_escort_delay_shifts_the_release_by_a_turn(monkeypatch):
    released = {}
    for policy in ("cheapest", "safest"):
        world = build(monkeypatch, policy=policy)
        step(world)
        no_more_orders(world)
        released[policy] = [step(world, sufficiency=0.2)[0] for _ in range(4)]
    assert released["cheapest"][:2] == [0.2, 0.2] and released["cheapest"][2] > 0.2
    assert released["safest"][:3] == [0.2, 0.2, 0.2] and released["safest"][3] > 0.2


def test_draws_are_namespaced_deterministic_and_leave_the_global_stream(monkeypatch):
    world = build(monkeypatch, draws=None)
    step(world)
    convoy = state(world).convoys[0]
    random.seed(12345)
    before = random.getstate()
    first = C._draws(world, convoy, True)
    assert first == C._draws(world, convoy, True) and first != C._draws(world, convoy, False)
    assert random.getstate() == before
    for _ in range(3):
        step(world)
    assert random.getstate() == before


def test_never_enabled_explicit_off_has_raw_json_rng_and_payment_parity(monkeypatch):
    from chronicler.main import _build_parser
    base = build(monkeypatch, convoys=False)
    left, right = deepcopy(base), deepcopy(base)
    L.configure_livelihoods(right, _build_parser().parse_args(["--no-grain-convoys"]), agent_mode="hybrid")
    before_rng = random.getstate()
    for world in (left, right):
        for _ in range(3):
            step(world)
    assert right.livelihoods is None and left.model_dump_json() == right.model_dump_json()
    assert random.getstate() == before_rng
    assert "livelihoods" not in json.loads(right.model_dump_json())
    assert [c.treasury for c in left.civilizations] == [c.treasury for c in right.civilizations]


def test_enabled_without_eligible_sources_changes_nothing_but_its_own_record(monkeypatch):
    worlds = []
    for convoys in (False, True):
        world = build(monkeypatch, source=DIRECT, convoys=convoys)
        for _ in range(3):
            step(world)
        worlds.append(json.loads(world.model_dump_json()))
    off, on = worlds
    record = on.pop("livelihoods")["grain_convoys"]
    assert on == off
    assert record["convoys"] == [] and record["counters"]["dispatched"] == 0


def test_disabling_drains_and_the_snapshot_reports_known_and_unknown(monkeypatch):
    world = build(monkeypatch)
    world.turn += 1
    assert C.snapshot_summary(world)["transitions"] is None  # no pass recorded yet
    world.turn -= 1
    step(world)
    C.set_grain_convoys_enabled(world, False)
    assert C.grain_convoys_active(world)
    summary = L.livelihoods_snapshot_fields(world)["livelihoods"]["grain_convoys"]
    assert summary["source_turn"] == 30 and summary["active_count"] == 1
    assert [row["operation"] for row in summary["transitions"]] == ["dispatched"]
    assert summary["active"][0]["route_names"] == ["Obsidian Shore", "Thornwood", "Verdant Plains"]
    step(world)
    step(world)
    assert state(world).counters["dispatched"] == 1 and state(world).convoys == []
    assert C.grain_convoys_active(world)  # the arrival is still reported
    summary = C.snapshot_summary(world)
    assert [row["operation"] for row in summary["transitions"]] == ["arrived"]
    step(world)
    assert C.snapshot_summary(world)["transitions"] == []
    assert not C.grain_convoys_active(world)
    assert "livelihoods" not in L.livelihoods_snapshot_fields(world)


@pytest.mark.parametrize("mutation", ["buyer_name", "route", "cargo", "dest_cap", "counter", "turn"])
def test_invalid_saved_convoys_refuse_before_any_movement(monkeypatch, mutation):
    world = build(monkeypatch)
    step(world)
    st = state(world)
    convoy = st.convoys[0]
    if mutation == "buyer_name":
        convoy.buyer_name = "Somebody else"
    elif mutation == "route":
        convoy.route = [SOURCE, DEST]  # not adjacent
    elif mutation == "cargo":
        convoy.cargo = convoy.net * 2
    elif mutation == "dest_cap":
        st.convoys.extend(convoy.model_copy(update={"convoy": i}) for i in (1, 2))
        st.next_convoy = 3
    elif mutation == "counter":
        st.counters.pop("lost")
    else:
        st.moved_turn = world.turn + 5
    before = world.model_dump_json()
    with pytest.raises(ValueError):
        L.phase10_before_reserves(world, economy_result=economy(world))
    assert world.model_dump_json() == before


def test_stub_state_json_and_pickle_backfill_defaults():
    old = GrainConvoyState.model_validate_json('{"schema_version": 1, "enabled": true}')
    assert old.convoys == [] and list(old.counters) == list(COUNTERS) and old.route_policy == "adaptive"
    raw = GrainConvoyState().__getstate__()
    raw["__dict__"] = {"schema_version": 1, "enabled": False}
    back = GrainConvoyState.__new__(GrainConvoyState)
    back.__setstate__(raw)
    assert back.enabled is False and back.frame_turn is None and list(back.counters) == list(COUNTERS)
    assert pickle.loads(pickle.dumps(back)).model_dump_json() == back.model_dump_json()


def test_cli_policy_prerequisites_and_drain_wiring(monkeypatch):
    from chronicler.main import _build_parser
    parse = _build_parser().parse_args
    world = build(monkeypatch, convoys=False)
    L.configure_livelihoods(world, parse(["--grain-convoys", "--convoy-route-policy", "safest"]),
                            agent_mode="demographics-only")
    assert state(world).enabled and state(world).route_policy == "safest"
    assert L.livelihoods_feature_flags(world) == {"grain_convoys": True}
    L.configure_livelihoods(world, parse(["--no-grain-convoys"]), agent_mode="demographics-only")
    assert not state(world).enabled and state(world).route_policy == "safest"
    bare = generate_world(seed=42)
    with pytest.raises(ValueError, match="public-grain-shipments"):
        L.configure_livelihoods(bare, parse(["--grain-convoys"]), agent_mode="hybrid")


# --- Cost-retaining risk ablation (livelihoods.convoys.threat_scale) -------

def _comparable(world) -> dict:
    data = json.loads(world.model_dump_json())
    data.pop("tuning_overrides", None)
    return data


@pytest.mark.parametrize("policy", ["safest", "adaptive"])
def test_threat_scale_zero_keeps_every_cost_but_draws_no_capture(monkeypatch, policy):
    """CONSTRUCTED: Selurian (Ashara Desert, beside Verdant Plains) is at war
    with the buyer, so only the convoy's last edge is exposed; the risk arm
    meets an unrepelled threat there."""
    real_draws = C._draws
    arms = {}
    random.seed(7)
    before_rng = random.getstate()
    for arm in ("risk", "explicit_one", "ablation"):
        world = build(monkeypatch, policy=policy, draws=None)
        world.active_wars.append(("Thornwall Confederacy", "Selurian Republic"))
        if arm == "ablation":
            world.tuning_overrides[C.K_THREAT_SCALE] = 0.0
            monkeypatch.setattr(C, "_draws", real_draws)  # the real namespaced stream
        else:
            if arm == "explicit_one":
                world.tuning_overrides[C.K_THREAT_SCALE] = 1.0
            monkeypatch.setattr(C, "_draws", lambda world, c, forward:
                                THREAT_UNREPELLED if c.leg == 1 else NO_THREAT)
        step(world)
        no_more_orders(world)
        trace, frames = [_comparable(world)], [list(state(world).frame)]
        for _ in range(4):
            step(world)
            trace.append(_comparable(world))
            frames.append(list(state(world).frame))
        assert random.getstate() == before_rng  # no draw touches any other stream
        arms[arm] = (world, trace, frames)
    risk, risk_trace, risk_frames = arms["risk"]
    ablation, ablation_trace, ablation_frames = arms["ablation"]
    assert arms["explicit_one"][1] == risk_trace  # 1.0 is the default
    # Identical decision, route, fees, muster and movement up to the threat:
    # trace[i] and frames[i] hold the state after simulation turn 30 + i.
    upto = next(i for i, frame in enumerate(risk_frames) if any(row.operation == "captured" for row in frame))
    assert upto >= 2 and ablation_trace[:upto] == risk_trace[:upto]
    captured = next(row for row in risk_frames[upto] if row.operation == "captured")
    arrival = next(row for row in ablation_frames[upto] if row.operation == "arrived")
    assert (arrival.route, arrival.leg, arrival.escorted) == (captured.route, captured.leg + 1, captured.escorted)
    assert captured.threat == "frontier" and arrival.threat is None
    r, a = state(risk).counters, state(ablation).counters
    for key in ("dispatched", "sent", "paid", "escorted", "escort_paid", "waits", "reroutes", "turned_back"):
        assert a[key] == r[key]
    assert r["escorted"] == (policy == "safest") and r["escort_paid"] == 2 * r["escorted"]
    assert (r["threats"], r["captured"], r["arrived"]) == (1, 1, 0)
    assert (a["threats"], a["captured"], a["lost"], a["arrived"]) == (0, 0, 0, 1)
    assert a["legs"] == r["legs"] + 1  # the risk arm stopped one edge short
    assert a["delivered"] == pytest.approx(r["captured_grain"])
    assert a["escort_wasted"] == a["escorted"]  # protection paid, no threat drawn
    assert_closes(risk)
    assert_closes(ablation)


def test_threat_scale_scales_the_drawn_chance_not_the_dispatch_exposure(monkeypatch):
    world = build(monkeypatch, draws=(0.0, 0.99))
    world.active_wars.append(("Thornwall Confederacy", "Selurian Republic"))
    world.tuning_overrides[C.K_THREAT_SCALE] = 0.5
    step(world)
    convoy = state(world).convoys[0]
    assert convoy.exposed_risk == pytest.approx(C.FRONTIER_THREAT)  # unscaled at dispatch
    no_more_orders(world)
    step(world)
    step(world)
    row = state(world).frame[0]
    assert row.operation == "captured" and row.threat_risk == pytest.approx(0.5 * C.FRONTIER_THREAT)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 1.5, True, None])
def test_invalid_threat_scale_refuses_before_any_movement(monkeypatch, bad):
    world = build(monkeypatch)
    step(world)
    world.tuning_overrides[C.K_THREAT_SCALE] = bad
    before = world.model_dump_json()
    with pytest.raises(ValueError, match="threat_scale"):
        L.phase10_before_reserves(world, economy_result=economy(world))
    assert world.model_dump_json() == before


def test_delay_alone_changes_the_actual_release_of_the_same_grain(monkeypatch):
    """CONSTRUCTED pair: the same paid cargo, once carried by a two-edge
    convoy (risk ablated) and once delivered to the same granary at the end
    of its dispatch turn. Only the arrival time differs."""
    carried = build(monkeypatch)
    carried.tuning_overrides[C.K_THREAT_SCALE] = 0.0
    step(carried)
    no_more_orders(carried)
    convoy = state(carried).convoys[0]
    direct = deepcopy(carried)
    st = state(direct)
    st.convoys.clear()  # counterfactual: delivered at once, same grain, same payment
    st.counters["arrived"] += 1
    st.counters["delivered"] += convoy.cargo
    direct.grain_reserves.granaries[DEST].grain += convoy.cargo
    rows = []
    for _ in range(4):
        late, _ = step(carried, sufficiency=0.2)
        early, _ = step(direct, sufficiency=0.2)
        rows.append((late, early, carried.grain_reserves.counters["released"],
                     direct.grain_reserves.counters["released"]))
        assert [c.treasury for c in carried.civilizations] == [c.treasury for c in direct.civilizations]
    # Turns 31 and 32: the convoy is on the road (it arrives in turn 32's
    # Phase 10), so only the undelayed grain feeds people.
    for late, early, _, _ in rows[:2]:
        assert late == 0.2 and early > 0.2
    assert rows[2][0] > 0.2  # turn 33: the convoy's grain is released at last
    assert rows[1][2] == 0.0 and rows[1][3] > 0.0
    arrived = [f.amount for f in carried.grain_reserves.flows if f.kind == CONVOY_ARRIVED]
    assert state(carried).counters["delivered"] == pytest.approx(convoy.cargo) == state(direct).counters["delivered"]
    assert arrived == [] or arrived == [pytest.approx(convoy.cargo)]
    assert_closes(carried)
    assert_closes(direct)
