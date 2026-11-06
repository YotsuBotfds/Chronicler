"""A3 workshop economics on the real compiled extension (template seed 1).

Development world only (template seed 1): with the academy flags, firms open
with owner capital from about turn 34, buy inputs, sell to households and
close ``idle`` at turns 117 and 118; a city falls at turn 121. Without the
academy flags, with payroll ``no_customer`` and ``free_inputs``, a firm owes
wages from turn 74 and closes insolvent at turn 79.
"""
from __future__ import annotations

import math
import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

BASE = ["--agents", "hybrid", "--simulate-only", "--workshops", "--workshop-payroll", "--workshop-economics"]
ACADEMY = ["--grain-reserves", "--public-grain-shipments", "--scholarship", "--techniques", "--academy-services"]
WARES_PURCHASE = 7


def _cli(monkeypatch, folder, *argv):
    import chronicler.main as main_mod
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                      "--state", str(folder / "state.json")])
    main_mod.main()


class _CheckedSim:
    """Delegates to the native simulator; checks every keyed transfer (wages
    and households' wares purchases) against the live pool and that a repeated
    key is refused unchanged."""

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
        for (aid, requested, applied, residual, status), (_, sent) in zip(out, rows, strict=True):
            assert requested == sent and applied + residual == requested
            if purpose == WARES_PURCHASE:
                # A household pays exactly what it was charged, never more than it held.
                assert sent < 0 and applied == sent and status == 0
                assert before[aid] * 1000 >= -sent
                self._seen["wares_rows"] += 1
                self._seen["wares_paid"] += -applied
            if status != 2:
                assert after[aid] - before[aid] == pytest.approx(applied / 1000, abs=2e-5)
                assert 0.0 <= after[aid] <= 100.0
        with pytest.raises(ValueError, match="already applied"):
            self._sim.transfer_wealth(turn, purpose, batch, rows)
        assert self._wealth() == after
        self._seen["transfers"] += 1
        return out


def test_firms_buy_inputs_sell_to_households_and_close_their_books(tmp_path, monkeypatch):
    from chronicler import workshop_payroll as P
    from chronicler.bundle_codec import load_bundle
    from chronicler_agents import AgentSimulator
    assert AgentSimulator.wealth_transfer_purposes()[WARES_PURCHASE] == "wares_purchase"
    seen = {"transfers": 0, "wares_rows": 0, "wares_paid": 0}
    original = P._native
    monkeypatch.setattr(P, "_native", lambda bridge: _CheckedSim(original(bridge), seen))
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    _cli(monkeypatch, tmp_path, "--seed", "1", "--turns", "122", *BASE, *ACADEMY, "--wealth-accounting")
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    charged = household = operated = 0
    firm_sites: set[int] = set()
    for snap in bundle["history"]:
        lv = snap["livelihoods"]
        econ, payroll, ws = lv["workshop_economics"], lv["workshop_payroll"], lv["workshops"]
        assert econ["stage"] == "A3" and econ["mode"] == "market"
        for firm in payroll["firms"] + payroll["closed"]:
            P.check_firm(P.WorkshopFirm.model_validate(firm))
        sites = {r["site"]: r for r in ws["receipts"] or []}
        open_before = set(firm_sites)
        firm_sites = {f["firm"] for f in econ["firms"]}
        # No native craft output in a site region without a firm (no free-input production).
        for site, w in sites.items():
            if site not in open_before | firm_sites | {f["firm"] for f in econ["closed"]}:
                assert not w["region_craft_output"], (snap["turn"], site)
        for r in econ["receipts"] or []:
            inputs = r["inputs"]
            if r["operating"]:
                operated += 1
                w = sites[r["firm"]]
                used = w["region_craft_input"]["timber"] + w["region_craft_input"]["ore"]
                assert used <= w["craft_ceiling"] + 1e-6
                if inputs["capacity_milli"] is not None:
                    assert w["craft_ceiling"] * 1000 <= inputs["capacity_milli"] + 1
                if used > 0:
                    assert inputs["cost_milli"] == math.ceil(used * inputs["price_milli"] - 1e-9)
                    assert inputs["charged_milli"] == min(inputs["cost_milli"], inputs["budget_milli"])
                    assert inputs["charged_milli"] <= inputs["budget_milli"]
                charged += inputs["charged_milli"]
            h = r["households"]
            if h:
                household += h["paid_milli"]
                assert h["bought_milli"] <= h["offered_milli"] <= h["gap_milli"]
        ledger = lv["wealth_accounting"]["frame"]
        if ledger is not None:
            assert all(c["closes"] for c in ledger["closures"]), ledger["closures"]
            assert ledger["continuity"]["status"] in ("exact", "unchecked")
    counters = bundle["history"][-1]["livelihoods"]["workshop_economics"]["counters"]
    assert counters["firms_opened"] >= 1 and operated > 0 and charged > 0 and household > 0
    assert counters["inputs_charged"] == charged and counters["household_sales"] == household
    assert seen["wares_paid"] == household and seen["wares_rows"] > 0 and seen["transfers"] > 0
    assert counters["closed_idle"] >= 1


def _resume_identical(tmp_path, monkeypatch, flags, turns, k):
    from chronicler.bundle_codec import load_bundle
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", "1", "--turns", str(turns), *flags, "--checkpoint-turns", str(k))
    ckpt = straight / f"checkpoint_turn_{k}.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = (load_bundle(p / "chronicle_bundle.json") for p in (straight, resumed))
    for bundle in (a, b):
        bundle["metadata"].pop("generated_at", None)
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()
    return a


def test_exact_resume_before_idle_closures_and_a_city_fall(tmp_path, monkeypatch):
    a = _resume_identical(tmp_path, monkeypatch, [*BASE, *ACADEMY, "--wealth-accounting"], 122, 116)
    econ = a["history"][116]["livelihoods"]["workshop_economics"]
    assert econ["firms"] and max(f["idle_run"] for f in econ["firms"]) >= 4      # live idle runs at the checkpoint
    reasons = [f["closed_reason"] for f in a["history"][-1]["livelihoods"]["workshop_economics"]["closed"]]
    assert reasons.count("idle") == 2 and "city_fell" in reasons


def test_exact_resume_inside_wage_arrears_before_an_insolvent_closure(tmp_path, monkeypatch):
    flags = [*BASE, "--workshop-payroll-mode", "no_customer", "--workshop-economics-mode", "free_inputs"]
    a = _resume_identical(tmp_path, monkeypatch, flags, 82, 76)
    firms = a["history"][76]["livelihoods"]["workshop_payroll"]["firms"]
    assert any(f["owed"] for f in firms)                                     # arrears live at the checkpoint
    closed = a["history"][-1]["livelihoods"]["workshop_economics"]["closed"]
    assert any(f["closed_reason"] == "insolvent" for f in closed)
