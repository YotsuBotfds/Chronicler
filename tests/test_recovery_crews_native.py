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
