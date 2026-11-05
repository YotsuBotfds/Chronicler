"""RS2 repair projects on the real compiled extension.

Natural activation: template seed 11 (8 regions, 4 civs) with operate-mode
workshops and granary storage. Its granaries wear from turn 0 (storage
policy ``neglect``), sieges and an occupation seize grain from turn 2 and a
conquest damages a workshop site at turn 36, so granary wear and war
projects open early and a named workshop repair crew works from turn 37
(docs/integration/repair-projects.md, "Development measurement").
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

FLAGS = ["--agents", "hybrid", "--simulate-only", "--workshops", "--grain-reserves", "--grain-storage",
         "--repair-projects"]


def _cli(monkeypatch, folder, *argv):
    import chronicler.main as main_mod
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                      "--state", str(folder / "state.json")])
    main_mod.main()


def _run(monkeypatch, folder, *extra, seed=11, turns=60):
    from chronicler.bundle_codec import load_bundle
    _cli(monkeypatch, folder, "--seed", str(seed), "--turns", str(turns), *FLAGS, *extra)
    return load_bundle(folder / "chronicle_bundle.json")


def test_projects_reserve_pay_and_close_their_books_on_the_real_extension(tmp_path, monkeypatch):
    from chronicler import repair_projects as RP
    from chronicler import workshops as W
    seen = {"crew": 0, "transfers": 0, "deductions": 0, "turns": 0}
    finish, original_native = RP.finish_phase2, RP._native

    def checked_finish(world, economy_result, agent_bridge, acc):
        out = finish(world, economy_result, agent_bridge, acc)
        sim = agent_bridge._sim
        turn = world.turn
        registry = {aid: (cat, frac) for aid, cat, frac in sim.work_reservations(turn)}
        assert sim.work_reservation_conflicts(turn) == []
        l1 = {aid for r in world.livelihoods.workshops.frame for aid in r.crew}
        snap = sim.get_snapshot()
        cols = {n: snap.column(n).to_pylist() for n in ("id", "age", "occupation", "settlement_id", "region")}
        rows = {cols["id"][i]: i for i in range(len(cols["id"]))}
        for r in world.livelihoods.repair_projects._turn.receipts:
            for aid in r.crew:
                cat, frac = registry[aid]
                assert cat == RP.CATEGORY_REPAIR and frac == pytest.approx(r.share)
                assert aid not in l1                       # never also L1 crew
                i = rows[aid]
                site = next(s for s in world.livelihoods.workshops.sites if s.site == r.asset)
                assert cols["occupation"][i] == 0 and cols["age"][i] >= 20
                assert (cols["settlement_id"][i], cols["region"][i]) == (site.settlement_id, site.region)
                seen["crew"] += 1
        seen["turns"] += 1
        return out

    class Checked:
        def __init__(self, sim):
            self._sim = sim

        def __getattr__(self, name):
            return getattr(self._sim, name)

        def transfer_wealth(self, turn, purpose, batch, rows):
            assert purpose == RP.PURPOSE_REPAIR_WAGE
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

    monkeypatch.setattr(RP, "finish_phase2", checked_finish)
    monkeypatch.setattr(RP, "_native", lambda bridge: Checked(original_native(bridge)))
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    bundle = _run(monkeypatch, tmp_path)
    totals = {"granary": 0.0, "workshop": 0.0, "charged": 0, "wages": 0, "damages": set()}
    for snap in bundle["history"]:
        record = snap["livelihoods"]["repair_projects"]
        assert record["stage"] == "RS2" and record["mode"] == "repair"
        storage = {r["region"]: r for r in snap["grain_reserves"]["storage"]["receipts"]} \
            if (snap.get("grain_reserves") or {}).get("storage") else {}
        for r in record["receipts"] or []:
            assert 0.0 <= r["delivered"] <= r["requested"] + 1e-9 and r["credited"] == r["delivered"]
            assert r["timber_held"] == pytest.approx(r["timber_used"] + r["timber_returned"], abs=1e-6)
            assert r["timber_used"] == pytest.approx(r["delivered"], rel=1e-6, abs=1e-9)
            assert r["condition_after"] <= 1.0
            assert r["wages_milli"] + r["wage_residual_milli"] == r["wages_due_milli"]
            assert (r["status"] == "stalled") == (r["delivered"] == 0)
            if r["kind"] == "granary" and storage:
                assert storage[r["region"]]["requested"] == 0.0 and storage[r["region"]]["delivered"] == 0.0
            totals[r["kind"]] += r["delivered"]
        for row in record["ledger"] or []:
            RP.check_ledger(RP.CivLedger.model_validate(row))
            totals["charged"] += row["charged"]
            totals["wages"] += row["wages_applied_milli"]
        totals["damages"].update((d["event"], d["war_key"] is not None) for d in record["damages"])
    final = bundle["history"][-1]["livelihoods"]["repair_projects"]["counters"]
    assert final["charged"] == totals["charged"] and totals["granary"] > 0 and totals["workshop"] > 0
    assert seen["crew"] > 0 and seen["transfers"] > 0 and totals["wages"] > 0 and seen["turns"] == 60
    assert ("seizure", True) in totals["damages"] and ("conquest", True) in totals["damages"]
    assert final["income_replaced"] > 0
    # The lump repair was never billed: project work alone moved workshop condition.
    for snap in bundle["history"]:
        for r in snap["livelihoods"]["workshops"]["receipts"] or []:
            assert "repair" not in (r.get("paid") or {})


def _world(*, treasury=1000):
    from chronicler.grain_reserves import _ensure, set_grain_reserves_enabled
    from chronicler.grain_storage import enable_storage
    from chronicler.grain_storage_state import StorageAsset
    from chronicler import repair_projects as RP
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
        r.population = 100
        r.carrying_capacity = 100
        r.adjacencies = [w.regions[j].name for j in range(3) if j != i]
        r.stockpile.goods = {"timber": 100.0, "grain": 1000.0}
        r.resource_types = [255, 255, 255]
        r.resource_base_yields = [0.0, 0.0, 0.0]
    civ.population = 300
    set_grain_reserves_enabled(w, True)
    state = _ensure(w)
    for g in state.granaries:
        g.owner, g.grain = 0, 0
    state.granaries[0].grain = 500
    storage = enable_storage(w)
    storage.assets = [StorageAsset(capacity=1000, condition=0.5 if i == 0 else 1.0, owner=0) for i in range(3)]
    w.livelihoods = LivelihoodsState()
    RP.set_repair_projects_enabled(w, True, args=None)
    return w


def _tick(w, b):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn_result
    engine = ActionEngine(w)
    return run_turn_result(w, lambda c, world: engine.select_action(c, seed=world.seed), lambda *_: "",
                           seed=w.seed + w.turn, agent_bridge=b)


def test_constructed_granary_rebuild_moves_real_work_timber_and_coins(monkeypatch):
    """Constructed: one worn granary. The project opens after the first tick,
    then the real storage channel delivers its work while the granary's
    ordinary request is suspended; the goods balance closes with its timber."""
    from chronicler.agent_bridge import AgentBridge
    from chronicler.grain_reserves_state import BOUGHT, RELEASED, SPOILED
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    world = _world()
    bridge = AgentBridge(world, mode="hybrid")
    try:
        _tick(world, bridge)
        state = world.livelihoods.repair_projects
        (p,) = state.projects
        assert (p.kind, p.asset, p.cause) == ("granary", 0, "wear") and p.scope == pytest.approx(0.51 * 40)

        def total():
            return (sum(sum(r.stockpile.goods.values()) for r in world.regions)
                    + sum(g.grain for g in world.grain_reserves.granaries))
        before, treasury = total(), world.civilizations[0].treasury
        condition = world.grain_reserves.storage.assets[0].condition
        result = _tick(world, bridge)
        (r,) = state.receipts
        assert r.requested == 4.0 and r.delivered == 4.0 and r.timber_used == 4.0
        assert world._economy_result.granary_work_delivered[0] == 4.0
        storage = {x.region: x for x in world.grain_reserves.storage.receipts}
        assert storage[0].requested == 0.0 and storage[0].delivered == 0.0
        assert world.grain_reserves.storage.assets[0].condition == pytest.approx(condition - 0.01 + 0.1)
        (ledger,) = state.ledger
        assert (ledger.charged, ledger.coin_cost_milli) == (8, 8000)
        c = world._economy_result.conservation
        flows = world.grain_reserves.flows
        public = sum(f.amount for f in flows if f.kind in (RELEASED, SPOILED))
        public += sum(f.sent - f.amount for f in flows if f.kind == BOUGHT)
        used = r.timber_used + sum(x.timber_used for x in world.grain_reserves.storage.receipts)
        expected = (before + c["production"] + c["clamp_floor_loss"] - c["consumption"] - c["storage_loss"]
                    - c["cap_overflow"] - c["transit_loss"] - c["in_transit_delta"] - used - public)
        assert total() == pytest.approx(expected, rel=2e-6, abs=1e-5)
        assert result is not None
        # A failed economy tick charges nothing and returns the held timber.
        timber = [r.stockpile.goods["timber"] for r in world.regions]
        treasury = world.civilizations[0].treasury
        snapshot = state.model_dump_json()
        sim = bridge._sim
        monkeypatch.setattr(bridge, "_sim", _Failing(sim))
        with pytest.raises(RuntimeError, match="economy failed"):
            _tick(world, bridge)
        monkeypatch.setattr(bridge, "_sim", sim)
        assert [r.stockpile.goods["timber"] for r in world.regions] == timber
        assert world.civilizations[0].treasury == treasury and state.model_dump_json() == snapshot
        assert state._turn is None
    finally:
        bridge.close()


class _Failing:
    """The native simulator whose economy kernel raises."""

    def __init__(self, sim):
        self._sim = sim

    def __getattr__(self, name):
        return getattr(self._sim, name)

    def tick_economy(self, *args, **kwargs):
        raise RuntimeError("economy failed")


def test_exact_checkpoint_resume_inside_live_projects(tmp_path, monkeypatch):
    from chronicler.bundle_codec import load_bundle
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", "11", "--turns", "46", *FLAGS, "--checkpoint-turns", "40")
    ckpt = straight / "checkpoint_turn_40.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = (load_bundle(p / "chronicle_bundle.json") for p in (straight, resumed))
    for bundle in (a, b):
        bundle["metadata"].pop("generated_at", None)
    record = a["history"][39]["livelihoods"]["repair_projects"]
    assert record["projects"], "the checkpoint must hold open projects"
    assert any(p["kind"] == "workshop" and p["last_crew"] for p in record["projects"])
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()


def test_cost_only_and_the_damage_ablation_on_a_real_run(tmp_path, monkeypatch):
    """cost_only pays and uses timber but never moves condition; the tuning
    key at 0 records no war damage."""
    tuning = tmp_path / "tuning.yaml"
    tuning.write_text("repair_projects:\n  war_damage: 0.0\n", encoding="utf-8")
    control = _run(monkeypatch, tmp_path / "control", "--repair-mode", "cost_only", "--tuning", str(tuning),
                   turns=40)
    paid = 0
    for snap in control["history"]:
        record = snap["livelihoods"]["repair_projects"]
        assert record["mode"] == "cost_only" and record["damages"] == []
        for r in record["receipts"] or []:
            assert r["credited"] == 0.0 and r["condition_after"] <= r["condition_before"] + 1e-12
        paid += sum(row["charged"] for row in record["ledger"] or [])
    assert paid > 0
    assert json.dumps(control["history"][-1]["livelihoods"]["repair_projects"]["parameters"]["war_damage"]) == "0.0"


def test_rebuilt_pool_clears_saved_crews():
    from chronicler import repair_projects as RP
    from chronicler.livelihoods import bind_native_pool
    world = _world()
    state = world.livelihoods.repair_projects
    state.projects = [RP.RepairProject(pid=0, kind="granary", asset=0, region=0, cause="wear", opened_turn=0,
                                       opened_condition=0.5, controller=0, scope=20.0, last_crew=[1, 2])]
    a, b = deepcopy(world), deepcopy(world)
    from chronicler.agent_bridge import AgentBridge
    bridge = AgentBridge(a, mode="hybrid")
    try:
        bind_native_pool(a, bridge)                        # a new pool: saved ids are strangers
        assert a.livelihoods.repair_projects.projects[0].last_crew == []
        bind_native_pool(b, bridge, reset=False)           # an exact checkpoint re-binds
        assert b.livelihoods.repair_projects.projects[0].last_crew == [1, 2]
    finally:
        bridge.close()
