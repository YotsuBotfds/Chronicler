"""PL3 recovery crews and the RS2 ``no_people`` correction on the real
compiled extension.

Natural activation: procedural development world 32x10 seed 31 with
operate-mode workshops and granary storage. Its granaries wear from turn 0,
so granary projects with named, paid crews work from the first turns, and a
granary region empties of farmers (``no_people``) within 60 turns on this
source (docs/integration/recovery-crews.md, "Evidence").
"""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

FLAGS = ["--agents", "hybrid", "--simulate-only", "--workshops", "--grain-reserves", "--grain-storage",
         "--repair-projects", "--recovery-crews"]
PROCEDURAL = ("--worldgen", "procedural", "--civs", "10", "--regions", "32")


def _cli(monkeypatch, folder, *argv):
    import chronicler.main as main_mod
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                      "--state", str(folder / "state.json")])
    main_mod.main()


def test_paid_granary_wages_reach_named_people_once_and_the_books_close(tmp_path, monkeypatch):
    from chronicler import recovery_crews as RC
    from chronicler import repair_projects as RP
    from chronicler.bundle_codec import load_bundle
    seen = {"wages": 0, "rows": 0, "members": 0, "turns": 0, "paid_ids": set()}
    original_native, record = RP._native, RC.record

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
                # The wage is in that person's wealth, once.
                assert after[aid] - before[aid] == pytest.approx(applied / 1000, abs=2e-5)
                if batch == RC.GRANARY_WAGE_BATCH:
                    seen["wages"] += applied
                    seen["rows"] += 1
                    seen["paid_ids"].add(aid)
            with pytest.raises(ValueError, match="already applied"):
                self._sim.transfer_wealth(turn, purpose, batch, rows)
            return out

    def checked_record(world, w, *, sim, turn, delivered, coin_cost_milli, paid=None):
        record(world, w, sim=sim, turn=turn, delivered=delivered, coin_cost_milli=coin_cost_milli, paid=paid)
        if w.kind != "granary" or not w.named:
            return
        registry = {aid: (cat, frac) for aid, cat, frac in sim.work_reservations(turn)}
        assert sim.work_reservation_conflicts(turn) == []
        snap = sim.get_snapshot()
        cols = {n: snap.column(n).to_pylist() for n in ("id", "age", "occupation", "region")}
        rows = {cols["id"][i]: i for i in range(len(cols["id"]))}
        for aid, _origin, share, _veteran in w.named:
            cat, frac = registry[aid]
            assert cat == RP.CATEGORY_REPAIR and frac == pytest.approx(share)
            i = rows[aid]
            assert (cols["occupation"][i], cols["region"][i]) == (0, w.region) and cols["age"][i] >= 20
            seen["members"] += 1
        # The named crew's farm time is the request the native step delivered.
        assert delivered <= w.request + 1e-6
        assert delivered == pytest.approx(min(w.request, sum(s for _a, _o, s, _v in w.named)), abs=1e-5)
        seen["turns"] += 1

    monkeypatch.setattr(RP, "_native", lambda bridge: Checked(original_native(bridge)))
    monkeypatch.setattr(RC, "record", checked_record)
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    _cli(monkeypatch, tmp_path, "--seed", "31", "--turns", "60", *FLAGS, *PROCEDURAL)
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    total, members, no_people = 0, set(), {"unmet": 0, "stalled": 0}
    for snap in bundle["history"]:
        crews = snap["livelihoods"]["recovery_crews"]
        rs2 = snap["livelihoods"]["repair_projects"]
        assert crews["stage"] == "PL3" and crews["mode"] == "paid"
        coin = {}
        for r in rs2["receipts"] or []:
            if r["kind"] == "granary":
                coin[r["pid"]] = r["coin_cost_milli"]
                assert r["crew"] == []                         # RS2's own receipt stays anonymous
                no_people["stalled"] += r["reasons"] == ["no_people"]
        no_people["unmet"] += sum(u["reason"] == "no_people" for u in rs2["unmet"] or [])
        for r in crews["receipts"] or []:
            if r["kind"] != "granary":
                continue
            # Wages are the granary's coins of the delivered work, by delivered share.
            assert r["wages_due_milli"] == r["coin_cost_milli"] == coin[r["pid"]]
            assert r["wages_milli"] + r["wage_residual_milli"] == r["wages_due_milli"]
            assert r["coin_cost_milli"] == r["wages_milli"] + r["sunk_milli"]
            assert sum(m["wage_milli"] for m in r["members"]) == r["wages_milli"]
            total += r["wages_milli"]
            members.update(m["agent_id"] for m in r["members"] if m["wage_milli"] > 0)
        for row in crews["ledger"] or []:
            RC.check_ledger(RC.CivCrewLedger.model_validate(row))
    counters = bundle["history"][-1]["livelihoods"]["recovery_crews"]["counters"]
    assert seen["turns"] > 10 and seen["members"] > 0 and seen["rows"] > 0
    assert total == seen["wages"] == counters["granary_wages_milli"] > 0
    assert members == seen["paid_ids"]
    assert counters["income_replaced"] > 0
    # The RS2 correction acts natively in this world.
    assert no_people["unmet"] > 0 and no_people["stalled"] > 0


def test_exact_checkpoint_resume_inside_live_crews(tmp_path, monkeypatch):
    from chronicler.bundle_codec import load_bundle
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", "31", "--turns", "46", *FLAGS, *PROCEDURAL, "--checkpoint-turns", "39")
    ckpt = straight / "checkpoint_turn_39.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = (load_bundle(p / "chronicle_bundle.json") for p in (straight, resumed))
    for bundle in (a, b):
        bundle["metadata"].pop("generated_at", None)
    at = a["history"][38]["livelihoods"]
    assert any(p["kind"] == "granary" for p in at["repair_projects"]["projects"]), "an open granary project"
    assert any(r["kind"] == "granary" and r["members"] for r in at["recovery_crews"]["receipts"])
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()


MAINTENANCE = ["--local-budgets", "--maintenance-obligation"]


def test_maintenance_reservations_close_and_split_on_the_real_extension(tmp_path, monkeypatch):
    """L9 with the maintenance obligation (and paid crews), procedural seed 31,
    60 turns, ``CHRONICLER_CHECK_RESOURCES=1``: every reservation L9 records is
    this package's decision; RS2 never charges beyond envelope plus
    reservation; each civ's charge splits pro rata (``split_charge``) and its
    rows close; each settled repairs envelope spent exactly its part."""
    from chronicler import maintenance_obligation as MO
    from chronicler.bundle_codec import load_bundle
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    _cli(monkeypatch, tmp_path, "--seed", "31", "--turns", "60", *FLAGS, *PROCEDURAL, *MAINTENANCE)
    history = load_bundle(tmp_path / "chronicle_bundle.json")["history"]
    seen = {"reserved": 0, "used": 0, "split": 0, "settled": 0}
    decided: dict[int, dict[int, int]] = {}
    for snap in history:
        lv = snap["livelihoods"]
        mo, l9, rs2 = lv["maintenance_obligation"], lv["local_budgets"], lv["repair_projects"]
        assert mo["stage"] == "PL3" and mo["mode"] == "reserve"
        source = mo["source_turn"]
        if mo["decisions"] is not None:
            assert l9["decisions"] is not None
            recorded = {d["civ"]: d["reserved"].get("maintenance", 0) for d in l9["decisions"]}
            mine = {d["civ"]: d["reserved"] for d in mo["decisions"]}
            assert {c: v for c, v in recorded.items() if v} == {c: v for c, v in mine.items() if v}
            for d in mo["decisions"]:
                assert d["reserved"] == min(d["planned"], d["cap"]) and d["cap"] == d["budget_before"] // 2
            decided[source] = mine
        if mo["uses"] is None:
            continue
        charged = {row["civ"]: row["charged"] for row in rs2["ledger"] or []}
        settled = {c["civ"]: c for c in l9["settled"] or [] if c["service"] == "repairs"}
        for u in mo["uses"]:
            MO.check_use(MO.ReservationUse.model_validate(u))
            assert u["reserved"] == decided.get(source - 1, {}).get(u["civ"], 0)
            assert u["charged"] == charged.get(u["civ"], 0)
            assert u["charged"] <= u["reserved"] + (u["envelope"] or 0)
            used, share = MO.split_charge(u["charged"], u["reserved"], u["envelope"] or 0)
            assert (u["used"], u["envelope_share"]) == (used, pytest.approx(share))
            if u["civ"] in settled:
                assert settled[u["civ"]]["spent"] == u["envelope_spent"]
                seen["settled"] += 1
            seen["reserved"] += u["reserved"]
            seen["used"] += u["used"]
            seen["split"] += bool(u["used"] and u["envelope_spent"])
    assert seen["reserved"] > 0 and seen["used"] > 0 and seen["split"] > 0 and seen["settled"] > 0


def test_exact_checkpoint_resume_across_a_live_reservation(tmp_path, monkeypatch):
    from chronicler.bundle_codec import load_bundle
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", "31", "--turns", "46", *FLAGS, *PROCEDURAL, *MAINTENANCE,
         "--checkpoint-turns", "39")
    ckpt = straight / "checkpoint_turn_39.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = (load_bundle(p / "chronicle_bundle.json") for p in (straight, resumed))
    for bundle in (a, b):
        bundle["metadata"].pop("generated_at", None)
    # The decision of turn 38 reserves coins for turn 39 across the checkpoint.
    (snap,) = [s for s in a["history"] if s["livelihoods"]["maintenance_obligation"]["source_turn"] == 38]
    assert sum(d["reserved"] for d in snap["livelihoods"]["maintenance_obligation"]["decisions"]) > 0
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()
