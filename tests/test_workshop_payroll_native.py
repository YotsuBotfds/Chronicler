"""L6a workshop payroll on the real compiled extension (template seed 1).

Seed 1 grows an academy whose ruler controls workshop regions from about
turn 68 (docs/integration/workshop-finance.md, "Evidence"); firms open
around its orders from turn 70.
"""
from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

FLAGS = ["--agents", "hybrid", "--simulate-only", "--grain-reserves", "--public-grain-shipments",
         "--scholarship", "--techniques", "--academy-services", "--workshops"]


def _cli(monkeypatch, folder, *argv):
    import chronicler.main as main_mod
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                      "--state", str(folder / "state.json")])
    main_mod.main()


def _run(monkeypatch, folder, *extra, seed=1, turns=90):
    from chronicler.bundle_codec import load_bundle
    _cli(monkeypatch, folder, "--seed", str(seed), "--turns", str(turns), *FLAGS, *extra)
    return load_bundle(folder / "chronicle_bundle.json")


class _CheckedSim:
    """Delegates to the native simulator and checks every wage transfer and
    paid-work receipt against the live pool."""

    def __init__(self, sim, seen):
        self._sim, self._seen = sim, seen

    def __getattr__(self, name):
        return getattr(self._sim, name)

    def _wealth(self):
        snap = self._sim.get_snapshot()
        return dict(zip(snap.column("id").to_pylist(), snap.column("wealth").to_pylist(), strict=True))

    def transfer_wealth(self, turn, purpose, batch, rows):
        before = self._wealth()
        out = self._sim.transfer_wealth(turn, purpose, batch, rows)
        after = self._wealth()
        assert [r[0] for r in out] == [r[0] for r in rows]
        for (aid, requested, applied, residual, status), (_, sent) in zip(out, rows, strict=True):
            assert requested == sent and applied + residual == requested
            if status == 2:
                assert aid not in after and applied == 0
            else:
                assert after[aid] - before[aid] == pytest.approx(applied / 1000, abs=2e-5)
                assert after[aid] <= 100.0
                assert status == (0 if residual == 0 else 1)
            self._seen["transfers"] += 1
        # The same key is refused, unchanged.
        with pytest.raises(ValueError, match="already applied"):
            self._sim.transfer_wealth(turn, purpose, batch, rows)
        assert self._wealth() == after
        return out

    def take_paid_work_receipt(self):
        got = self._sim.take_paid_work_receipt()
        if got is not None:
            for aid, share, ordinary, deducted in got[1]:
                assert 0.0 < share <= 1.0 and deducted == pytest.approx(share * ordinary, rel=1e-5, abs=1e-7)
                self._seen["deductions"] += 1
        assert self._sim.take_paid_work_receipt() is None       # taken once
        return got


def test_firms_sell_pay_and_close_their_books_on_the_real_extension(tmp_path, monkeypatch):
    from chronicler import workshop_payroll as P
    seen = {"transfers": 0, "deductions": 0}
    original = P._native
    monkeypatch.setattr(P, "_native", lambda bridge: _CheckedSim(original(bridge), seen))
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    bundle = _run(monkeypatch, tmp_path, "--workshop-payroll")
    sales = wages = 0
    for snap in bundle["history"]:
        record = snap["livelihoods"]["workshop_payroll"]
        assert record["stage"] == "L6a" and record["mode"] == "paid"
        workshops = {r["site"]: r for r in snap["livelihoods"]["workshops"]["receipts"] or []}
        for firm in record["firms"] + record["closed"]:
            P.check_firm(P.WorkshopFirm.model_validate(firm))
        for r in record["receipts"] or []:
            assert r["cash_close"] >= 0 and r["inventory_close"] >= 0
            assert r["cash_close"] == (r["cash_open"] + r["sales"] - r["wages_paid"] - r["distributed"]
                                       - r["written_off"])
            assert r["inventory_close"] == (r["inventory_open"] + r["titled"] - r["sold"] - r["worn"]
                                            - r["returned"])
            if r["operating"]:
                w = workshops[r["site"]]
                assert w["crew"] == r["crew"] and w["affected_ordinary_income_share"] == pytest.approx(r["shares"][0])
                assert r["titled"] <= round(w["region_craft_output"] * 1000)
            sales += r["sales"]
            wages += r["wages_paid"]
        transfers = record["transfers"]
        if transfers:
            money = {m["kind"] for m in transfers["money"]}
            assert money <= {"sale", "wage", "distribution", "write_off"}
    final = bundle["history"][-1]["livelihoods"]["workshop_payroll"]["counters"]
    assert final["firms_opened"] >= 1 and final["sales_paid"] > 0 and sales > 0 and wages > 0
    assert seen["transfers"] > 0 and seen["deductions"] > 0
    # Academy inventory still balances with the deliveries counted as purchases.
    balance = bundle["world_state"]["scholarship"]["learning_services"]["material_balance"]
    assert balance["residual"] == pytest.approx(0.0, abs=1e-6)


def test_payroll_without_an_order_changes_nothing(tmp_path, monkeypatch):
    """No academies (no --scholarship): no firm opens, nothing is titled,
    withheld or paid, and the trajectory equals the run without payroll."""
    from chronicler.bundle_codec import load_bundle
    flags = ["--seed", "1", "--turns", "50", "--agents", "hybrid", "--simulate-only", "--workshops"]
    _cli(monkeypatch, tmp_path / "off", *flags)
    _cli(monkeypatch, tmp_path / "on", *flags, "--workshop-payroll")
    off = load_bundle(tmp_path / "off" / "chronicle_bundle.json")
    on = load_bundle(tmp_path / "on" / "chronicle_bundle.json")
    assert len(off["history"]) == len(on["history"]) == 50
    for a, b in zip(off["history"], on["history"], strict=True):
        b = json.loads(json.dumps(b))
        record = b["livelihoods"].pop("workshop_payroll")
        assert not record["firms"] and record["counters"].get("titled", 0) == 0
        assert a == b
    assert on["history"][-1]["livelihoods"]["workshop_payroll"]["counters"]["operating_without_order"] > 0
    ws = json.loads(json.dumps(on["world_state"]))
    ws["livelihoods"].pop("workshop_payroll")
    assert ws == off["world_state"]


def test_exact_checkpoint_resume_with_open_firms(tmp_path, monkeypatch):
    from chronicler.bundle_codec import load_bundle
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", "1", "--turns", "82", *FLAGS, "--workshop-payroll",
         "--checkpoint-turns", "76")
    ckpt = straight / "checkpoint_turn_76.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = (load_bundle(p / "chronicle_bundle.json") for p in (straight, resumed))
    for bundle in (a, b):
        bundle["metadata"].pop("generated_at", None)
    firms = a["history"][75]["livelihoods"]["workshop_payroll"]["firms"]
    assert firms, "the checkpoint must hold open firms"
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()


def test_wealth_transfer_contract_on_a_live_pool():
    from chronicler.action_engine import ActionEngine
    from chronicler.agent_bridge import AgentBridge
    from chronicler.simulation import run_turn
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    engine = ActionEngine(world)
    run_turn(world, lambda c, w: engine.select_action(c, seed=w.seed), lambda w, e: "",
             seed=world.seed, agent_bridge=bridge)
    sim = bridge._sim
    assert sim.wealth_transfer_purposes()[0] == "workshop_wage"      # append-only codes
    snap = sim.get_snapshot()
    ids = snap.column("id").to_pylist()
    wealth = dict(zip(ids, snap.column("wealth").to_pylist(), strict=True))
    a, b = ids[0], ids[1]
    room = int((100.0 - wealth[b]) * 1000) // 1
    out = sim.transfer_wealth(5, 0, 1, [(a, 1500), (b, room + 5000), (4_000_000_000, 7)])
    assert out[0][2:] == (1500, 0, 0)
    assert out[1][3] >= 5000 and out[1][4] == 1
    assert out[2] == (4_000_000_000, 7, 0, 7, 2)
    after = dict(zip(*(sim.get_snapshot().column(c).to_pylist() for c in ("id", "wealth")), strict=True))
    assert after[a] == pytest.approx(wealth[a] + 1.5, abs=2e-5) and after[b] <= 100.0
    for bad in ([(a, 1), (a, 2)], [(a, 10**13)]):
        with pytest.raises(ValueError):
            sim.transfer_wealth(6, 0, 1, bad)
    with pytest.raises(ValueError, match="purpose"):
        sim.transfer_wealth(6, 9, 1, [(a, 1)])
    with pytest.raises(ValueError, match="already applied"):
        sim.transfer_wealth(5, 0, 1, [(a, 1)])
    debit = sim.transfer_wealth(6, 0, 1, [(a, -10**9)])
    assert debit[0][4] == 1 and debit[0][2] < 0 and debit[0][2] + debit[0][3] == -10**9
    # Paid work must sit inside a work reservation of the turn; cancel drops it.
    with pytest.raises(ValueError, match="reservation"):
        sim.install_paid_work(world.turn, [(a, 0.2)])
    sim.reserve_work(world.turn, 0, [(a, 0.25)])
    sim.install_paid_work(world.turn, [(a, 0.25)])
    with pytest.raises(ValueError, match="pending"):
        sim.install_paid_work(world.turn, [(a, 0.25)])
    assert sim.cancel_paid_work() is True and sim.cancel_paid_work() is False
    assert sim.take_paid_work_receipt() is None
