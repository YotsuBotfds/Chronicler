"""PL1 timber supply on the real compiled extension.

Development activation (template seed 3, 8 regions x 4 civs): the civ that
holds the world's forests opens RS2 granary projects it cannot supply from
its stockpile, so named crews cut at the forest, carry the timber home and
RS2 draws on the store (docs/integration/timber-supply.md). A constructed
world with an uninhabited forest shows the L3 debit exactly, and the
cost-retaining control on it cuts nothing.
"""
from __future__ import annotations

import math
import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

FLAGS = ["--agents", "hybrid", "--simulate-only", "--grain-reserves", "--public-grain-shipments",
         "--grain-storage", "--workshops", "--repair-projects", "--timber-stock", "--timber-supply"]
SEED, TURNS = 3, 60


def _cli(monkeypatch, folder, *argv):
    import chronicler.main as main_mod
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                      "--state", str(folder / "state.json")])
    main_mod.main()


def _instrument(monkeypatch, seen):
    """Check every settled turn against the native registry, the economy's
    woodcut results and conservation, and the L3 account."""
    from chronicler import timber_supply as TSU
    finish, original_native = TSU.finish_phase2, TSU._native

    def checked(world, economy_result, agent_bridge, acc):
        out = finish(world, economy_result, agent_bridge, acc)
        t = world.livelihoods.timber_supply._turn
        sim = agent_bridge._sim
        turn = world.turn
        registry = {aid: (cat, frac) for aid, cat, frac in sim.work_reservations(turn)}
        assert sim.work_reservation_conflicts(turn) == []
        if t.columns:
            cut = economy_result.woodcut_output
            assert economy_result.conservation["woodcut_outflow"] == pytest.approx(math.fsum(cut.values()),
                                                                                    rel=1e-12, abs=1e-12)
            seen["outflow"] += economy_result.conservation["woodcut_outflow"]
        else:
            assert "woodcut_outflow" not in economy_result.conservation
            assert not economy_result.woodcut_output
        ledger = {(r.region_id, r.slot): r for r in world.livelihoods.timber_stock.ledger}
        snap = sim.get_snapshot()
        cols = {n: snap.column(n).to_pylist() for n in ("id", "region", "occupation", "age")}
        rows = {cols["id"][i]: i for i in range(len(cols["id"]))}
        for r in t.receipts:
            for aid in r.crew:
                assert registry[aid] == (TSU.CATEGORY_REPAIR, pytest.approx(1.0))
                i = rows[aid]
                assert cols["region"][i] == r.home and cols["age"][i] >= 20 and cols["occupation"][i] != 1
            assert 0.0 <= r.away_delivered <= r.away_requested + 1e-6
            assert r.wages_milli + r.wage_residual_milli == r.wages_due_milli
            if r.cut > 0:
                row = ledger[(r.forest, r.slot)]
                name = world.regions[r.forest].name
                # The crew's harvest is slot output, and the L3 account debits all of it.
                assert row.extraction == economy_result.slot_output[name][r.slot]
                assert row.extraction >= r.cut
                assert (r.stock_before, r.stock_after) == (row.opening - row.cleared, row.stock)
                seen["cut"] += r.cut
                seen["resident"].append(row.extraction - r.cut)
            seen["crew"] += len(r.crew)
        seen["turns"] += 1
        return out

    class Checked:
        def __init__(self, sim):
            self._sim = sim

        def __getattr__(self, name):
            return getattr(self._sim, name)

        def transfer_wealth(self, turn, purpose, batch, rows):
            assert (purpose, batch) == (TSU.PURPOSE_REPAIR_WAGE, TSU.WAGE_BATCH)
            snap = self._sim.get_snapshot()
            before = dict(zip(snap.column("id").to_pylist(), snap.column("wealth").to_pylist(), strict=True))
            out = self._sim.transfer_wealth(turn, purpose, batch, rows)
            snap = self._sim.get_snapshot()
            after = dict(zip(snap.column("id").to_pylist(), snap.column("wealth").to_pylist(), strict=True))
            for (aid, requested, applied, residual, status), (_, sent) in zip(out, rows, strict=True):
                assert requested == sent and applied + residual == requested and status in (0, 1)
                assert after[aid] - before[aid] == pytest.approx(applied / 1000, abs=2e-5)
                seen["transfers"] += 1
            with pytest.raises(ValueError, match="already applied"):
                self._sim.transfer_wealth(turn, purpose, batch, rows)
            return out

    monkeypatch.setattr(TSU, "finish_phase2", checked)
    monkeypatch.setattr(TSU, "_native", lambda bridge: Checked(original_native(bridge)))


def test_expeditions_cut_carry_deliver_and_feed_rs2_with_closed_books(tmp_path, monkeypatch):
    from chronicler import timber_supply as TSU
    from chronicler.bundle_codec import load_bundle
    from chronicler.timber_supply_state import StoreRow, WageLedger
    seen = {"turns": 0, "crew": 0, "transfers": 0, "cut": 0.0, "outflow": 0.0, "resident": []}
    _instrument(monkeypatch, seen)
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    _cli(monkeypatch, tmp_path, "--seed", str(SEED), "--turns", str(TURNS), *FLAGS)
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    charged = 0
    for snap in bundle["history"]:
        record = snap["livelihoods"]["timber_supply"]
        assert record["stage"] == "PL1" and record["mode"] == "supply"
        for row in record["ledger"] or []:
            TSU.check_ledger(WageLedger.model_validate(row))
            charged += row["charged"]
        for row in record["stores"] or []:
            TSU.check_store(StoreRow.model_validate(row))
        for e in record["closed"]:
            # Cut timber never vanishes: only transit decay is lost.
            assert e["cut"] == pytest.approx(e["cargo"] + e["delivered"] + e["lost"] + e["abandoned"], abs=1e-9)
            assert e["lost"] == pytest.approx(e["delivered"] / 0.99 ** e["return_hops"] - e["delivered"], abs=1e-9)
    final = bundle["history"][-1]["livelihoods"]["timber_supply"]
    counters = final["counters"]
    assert counters["charged"] == charged > 0
    assert counters["delivered_expeditions"] >= 1 and counters["delivered"] > 0
    # Timber that arrived went to the store and RS2 held it from there.
    assert counters["store_held"] > 0
    assert counters["cut"] == pytest.approx(seen["cut"]) == pytest.approx(seen["outflow"])
    assert counters["cut"] == pytest.approx(counters["delivered"] + counters.get("lost", 0.0)
                                            + counters.get("abandoned_cargo", 0.0)
                                            + sum(e["cargo"] for e in final["expeditions"]), abs=1e-9)
    assert final["per_expedition"]["ended"] == counters["ended"] > 0
    assert counters["wages_milli"] + counters["wage_residual_milli"] == counters["wages_due_milli"]
    assert counters["income_withheld"] > 0 and counters["away_delivered"] <= counters["away_requested"] + 1e-6
    assert seen["turns"] == TURNS and seen["crew"] > 0 and seen["transfers"] > 0
    assert all(r >= 0 for r in seen["resident"])


def _world(*, mode=None, treasury=1000):
    """Three regions of one civ: a home with a worn granary and no timber, an
    uninhabited forest one hop away and a third region."""
    from types import SimpleNamespace
    from chronicler import repair_projects as RP
    from chronicler import timber_stock as TS
    from chronicler import timber_supply as TSU
    from chronicler.grain_reserves import _ensure, set_grain_reserves_enabled
    from chronicler.grain_storage import enable_storage
    from chronicler.grain_storage_state import StorageAsset
    from chronicler.livelihoods_state import LivelihoodsState
    from chronicler.world_gen import generate_world
    w = generate_world(seed=42, num_regions=3, num_civs=1)
    w.agent_mode = "hybrid"
    civ = w.civilizations[0]
    civ.regions = [r.name for r in w.regions]
    civ.capital_region = w.regions[0].name
    civ.treasury = treasury
    for i, r in enumerate(w.regions):
        r.controller = civ.name
        r.population = 100 if i != 1 else 0
        r.carrying_capacity = 100
        r.adjacencies = [w.regions[j].name for j in range(3) if j != i]
        r.stockpile.goods = {"timber": 0.0, "grain": 1000.0}
        r.resource_types = [255, 255, 255]
        r.resource_base_yields = [0.0, 0.0, 0.0]
    forest = w.regions[1]
    forest.terrain = "forest"
    forest.ecology.forest_cover = 0.9
    forest.resource_types = [1, 255, 255]
    forest.resource_base_yields = [2.0, 0.0, 0.0]
    civ.population = 200
    set_grain_reserves_enabled(w, True)
    state = _ensure(w)
    for g in state.granaries:
        g.owner, g.grain = 0, 0
    storage = enable_storage(w)
    storage.assets = [StorageAsset(capacity=1000, condition=0.5 if i == 0 else 1.0, owner=0) for i in range(3)]
    w.livelihoods = LivelihoodsState()
    TS.set_timber_stock_enabled(w, True)
    RP.set_repair_projects_enabled(w, True, args=None)
    TSU.set_timber_supply_enabled(w, True, args=SimpleNamespace(timber_supply_mode=mode))
    return w


def _tick(w, b):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn_result
    engine = ActionEngine(w)
    return run_turn_result(w, lambda c, world: engine.select_action(c, seed=world.seed), lambda *_: "",
                           seed=w.seed + w.turn, agent_bridge=b)


def _constructed(monkeypatch, mode=None, turns=7):
    from chronicler.agent_bridge import AgentBridge
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    world = _world(mode=mode)
    bridge = AgentBridge(world, mode="hybrid")
    rows = []
    try:
        for _ in range(turns):
            _tick(world, bridge)
            snap = bridge._sim.get_snapshot()
            forest_farmers = sum(1 for reg, occ in zip(snap.column("region").to_pylist(),
                                                       snap.column("occupation").to_pylist(), strict=True)
                                 if reg == 1 and occ == 0)
            state = world.livelihoods.timber_supply
            stock = {(r.region_id, r.slot): r for r in world.livelihoods.timber_stock.ledger}
            rows.append(dict(turn=world.turn - 1, receipts=[r.model_copy() for r in (state.receipts or [])],
                             l3=stock.get((1, 0)), forest_farmers=forest_farmers,
                             economy=world._economy_result, store=dict(state.store),
                             rp=[r.model_copy() for r in (world.livelihoods.repair_projects.receipts or [])]))
    finally:
        bridge.close()
    return world, rows


def test_constructed_uninhabited_forest_is_debited_exactly_by_the_crew(monkeypatch):
    world, rows = _constructed(monkeypatch)
    state = world.livelihoods.timber_supply
    cutting = [(row, r) for row in rows for r in row["receipts"] if r.stage == "cutting"]
    assert len(cutting) == 3
    for row, r in cutting:
        assert row["forest_farmers"] == 0
        l3 = row["l3"]
        econ = row["economy"]
        assert r.cut > 0 and r.crew_labor == len(r.crew)
        # Nobody lives in the forest: its whole extraction is the crew's harvest...
        assert l3.extraction == r.cut == econ.woodcut_output[1]
        assert econ.slot_output[world.regions[1].name][0] == r.cut
        # ... the account debits it exactly, and none of it reached the forest's stockpile.
        assert l3.stock == pytest.approx(l3.opening - l3.cleared - r.cut + l3.regrowth, rel=1e-12)
        assert econ.conservation["woodcut_outflow"] == r.cut
    (exp,) = [e for e in state.closed if e.eid == 0]
    assert exp.status == "delivered" and exp.hops == 1
    assert exp.delivered == pytest.approx(exp.cut * 0.99, rel=1e-12)
    assert exp.lost == pytest.approx(exp.cut * 0.01, rel=1e-9)
    # RS2 holds from the store the turn after the delivery.
    last = rows[-1]
    assert any(r.timber_held > 0 for r in last["rp"])
    assert state.counters["store_held"] > 0


def test_constructed_cost_only_cuts_nothing_but_pays_and_takes_the_same_crew(monkeypatch):
    world_s, rows_s = _constructed(monkeypatch)
    world_c, rows_c = _constructed(monkeypatch, mode="cost_only")
    s, c = world_s.livelihoods.timber_supply, world_c.livelihoods.timber_supply
    # The first expedition is the same in both arms (the control, supplied
    # nothing, then launches another).
    receipts_c = [r for row in rows_c for r in row["receipts"] if r.eid == 0]
    receipts_s = [r for row in rows_s for r in row["receipts"] if r.eid == 0]
    assert len(receipts_s) == 5
    assert [(r.stage, r.crew, r.away_requested, r.wages_due_milli) for r in receipts_c] == \
        [(r.stage, r.crew, r.away_requested, r.wages_due_milli) for r in receipts_s]
    assert all(r.cut == 0.0 and r.crew_labor == 0.0 for r in receipts_c)
    assert all(row["l3"].extraction == 0.0 for row in rows_c)
    assert all(row["store"] == {} for row in rows_c)
    assert c.counters.get("cut", 0.0) == 0.0 and c.counters.get("delivered", 0.0) == 0.0
    assert sum(r.wages_milli for r in receipts_c) == sum(r.wages_milli for r in receipts_s) > 0
    assert c.counters["launched"] > s.counters["launched"]


def test_exact_checkpoint_resume_inside_a_live_expedition(tmp_path, monkeypatch):
    from chronicler.bundle_codec import load_bundle
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", str(SEED), "--turns", "56", *FLAGS, "--checkpoint-turns", "52")
    ckpt = straight / "checkpoint_turn_52.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = (load_bundle(p / "chronicle_bundle.json") for p in (straight, resumed))
    for bundle in (a, b):
        bundle["metadata"].pop("generated_at", None)
    record = a["history"][51]["livelihoods"]["timber_supply"]
    assert record["expeditions"], "the checkpoint must hold a live expedition"
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()
