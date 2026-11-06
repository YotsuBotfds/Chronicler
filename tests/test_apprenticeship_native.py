"""RS1 apprenticeship on the real compiled extension (template seed 7, 8 regions).

Natural activation (simulation turns): seed 7's workshop sites operate from
turn 22; the first service qualification comes at turn 40, apprentices are
seated from turn 41 and the first apprenticeship completes at turn 73
(docs/integration/apprenticeship.md, "Development measurement").

These cases pin RS1 rules version 1 (``RULES_VERSION`` 1 for the new state):
the merged rules, which a state saved before PL2 resumes under. Version 2 runs
on the real extension in ``tests/test_apprenticeship_v2_native.py``.
"""
from __future__ import annotations

import importlib
import json

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

BASE = ["--civs", "4", "--regions", "8", "--agents", "hybrid", "--simulate-only"]


@pytest.fixture(autouse=True)
def _rules_version_1(monkeypatch):
    from chronicler import apprenticeship as A
    monkeypatch.setattr(A, "RULES_VERSION", 1)


def _run(folder, *extra, seed=7, turns=60):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    args = _build_parser().parse_args([
        "--seed", str(seed), "--turns", str(turns), *BASE,
        "--output", str(folder / "chronicle.md"), "--state", str(folder / "state.json"), *extra])
    execute_run(args)
    return load_bundle(folder / "chronicle_bundle.json")


def test_the_extension_is_the_compiled_build_with_the_seams():
    compiled = importlib.import_module("chronicler_agents.chronicler_agents")
    assert compiled.__file__.endswith((".so", ".pyd"))
    from chronicler_agents import AgentSimulator
    for name in ("plan_workshop_crews", "reserve_work", "work_reservations", "extend_paid_work",
                 "transfer_wealth", "take_paid_work_receipt"):
        assert callable(getattr(AgentSimulator, name)), name
    assert AgentSimulator.wealth_transfer_purposes()[2] == "apprentice_stipend"


def test_seats_crews_registry_and_crew_time_on_a_live_pool(tmp_path, monkeypatch):
    """Every seated apprentice is a living adult urban farmer of the site's
    city, holds only an apprentice reservation and never sits on a crew;
    crew time splits exactly into craft, upkeep and teaching; the receipts
    obey the wear bounds."""
    from chronicler import apprenticeship as A
    from chronicler import workshops as W
    seen = {"seats": 0, "attended": 0, "turns": 0, "mentored": 0}
    before, finish = A.before_crews, A.finish_phase2

    def checked_before(world, sim, requests):
        before(world, sim, requests)
        p = world.livelihoods.apprenticeship._pending
        snap = sim.get_snapshot()
        cols = {n: snap.column(n).to_pylist() for n in ("id", "age", "occupation", "settlement_id", "region")}
        row = {cols["id"][i]: i for i in range(len(cols["id"]))}
        held = {aid: cat for aid, cat, _f in sim.work_reservations(world.turn)}
        qualified = {q.agent_id for q in world.livelihoods.apprenticeship.qualifications}
        for st in p.sites.values():
            for aid, _new, _vet in st.seats:
                i = row[aid]
                assert cols["age"][i] >= 20 and cols["occupation"][i] == 0
                assert (cols["settlement_id"][i], cols["region"][i]) == (st.settlement, st.region)
                assert held[aid] == A.CATEGORY_APPRENTICE and aid not in qualified
                seen["seats"] += 1
            assert len(st.seats) <= st.capacity <= A.PER_SITE

    def checked_finish(world, economy_result, agent_bridge, acc):
        sim = agent_bridge._sim
        reg = sim.work_reservations(world.turn)
        assert sim.work_reservation_conflicts(world.turn) == []
        assert len({aid for aid, _c, _f in reg}) == len(reg)
        apprentices = {aid for aid, cat, f in reg if cat == A.CATEGORY_APPRENTICE and f == pytest.approx(0.5)}
        crews = {aid for r in world.livelihoods.workshops.frame for aid in r.crew}
        assert not apprentices & crews
        out = finish(world, economy_result, agent_bridge, acc)
        p = world.livelihoods.apprenticeship._pending
        attending = {aid for st in p.sites.values() for aid in st.attending}
        assert attending <= apprentices
        seen["attended"] += len(attending)
        seen["turns"] += 1
        return out

    monkeypatch.setattr(A, "before_crews", checked_before)
    monkeypatch.setattr(A, "finish_phase2", checked_finish)
    bundle = _run(tmp_path, "--workshops", "--apprenticeship", turns=60)
    for snap in bundle["history"]:
        rec = snap["livelihoods"]["apprenticeship"]
        assert rec["stage"] == "RS1" and rec["source_turn"] == snap["turn"] - 1
        workshops = {r["site"]: r for r in snap["livelihoods"]["workshops"]["receipts"] or []}
        for r in rec["receipts"] or []:
            w = workshops[r["site"]]
            assert r["crew"] == (w["crew"] if r["operating"] else [])
            assert 0.0 <= r["upkeep_offset"] <= r["wear"] <= A.OPERATING_WEAR
            assert r["net_wear"] == pytest.approx(r["wear"] - r["upkeep_offset"])
            assert set(r["qualified_on_crew"]) <= set(r["crew"])
            assert 0.0 <= (r["condition_after"] if r["condition_after"] is not None else 0.0) <= 1.0
            if r["operating"]:
                assert r["craft_work"] + r["upkeep_work"] + r["teaching_work"] == pytest.approx(r["crew_work"])
                assert w["allocated"] == pytest.approx(r["craft_work"])
                assert w["craft_ceiling"] == pytest.approx(W.K_RAW_PER_WORK * r["craft_work"], rel=1e-5)
                assert w["realized"] <= w["allocated"] + 1e-6
            seated = {s["agent_id"] for s in r["seats"] if s["share"] > 0}
            assert not seated & set(r["crew"])
            seen["mentored"] += len(r["mentors"])
    final = bundle["history"][-1]["livelihoods"]["apprenticeship"]["counters"]
    assert final["qualified_service"] > 0 and final["apprentice_turns_attended"] > 0
    assert seen["seats"] > 0 and seen["attended"] > 0 and seen["mentored"] > 0 and seen["turns"] == 60
    assert final["income_forgone"] > 0


def test_the_control_matches_train_until_the_first_completion(tmp_path):
    train = _run(tmp_path / "train", "--workshops", "--apprenticeship", turns=78)
    control = _run(tmp_path / "control", "--workshops", "--apprenticeship", "--apprenticeship-mode",
                   "no_qualification", turns=78)
    first = next((i for i, snap in enumerate(train["history"])
                  if snap["livelihoods"]["apprenticeship"]["counters"].get("completions", 0)), None)
    assert first is not None, "seed 7 completes an apprenticeship within 78 turns (first at turn 73)"
    for a, b in zip(train["history"][:first + 1], control["history"][:first + 1], strict=True):
        a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
        ra, rb = a["livelihoods"].pop("apprenticeship"), b["livelihoods"].pop("apprenticeship")
        assert (ra.pop("mode"), rb.pop("mode")) == ("train", "no_qualification")
        if ra["counters"].get("completions"):
            # The completing turn differs only by the grant.
            assert ra["counters"]["completions_granted"] == ra["counters"]["completions"]
            assert rb["counters"].get("completions_granted", 0) == 0
            assert [x for x in ra["archive"] if x["ended_reason"] == "completed"][0]["granted"] is True
            assert [x for x in rb["archive"] if x["ended_reason"] == "completed"][0]["granted"] is False
        else:
            assert ra == rb
        assert a == b
    ctrl = control["history"][-1]["livelihoods"]["apprenticeship"]
    assert not any(q["via"] == "apprenticeship" for q in ctrl["qualifications"] + ctrl["retired"])
    assert ctrl["counters"]["completions"] >= 1


def test_exact_checkpoint_resume_inside_live_apprenticeships(tmp_path, monkeypatch):
    import sys

    import chronicler.main as main_mod
    from chronicler.bundle_codec import load_bundle

    def cli(folder, *argv):
        monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                          "--state", str(folder / "state.json")])
        main_mod.main()

    straight = tmp_path / "straight"
    cli(straight, "--seed", "7", "--turns", "60", *BASE, "--workshops", "--apprenticeship",
        "--checkpoint-turns", "52")
    ckpt = straight / "checkpoint_turn_52.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    cli(resumed, "--resume", str(ckpt))
    a, b = (load_bundle(p / "chronicle_bundle.json") for p in (straight, resumed))
    for bundle in (a, b):
        bundle["metadata"].pop("generated_at", None)
    live = a["history"][51]["livelihoods"]["apprenticeship"]
    assert live["apprenticeships"] and live["qualifications"], "the checkpoint must hold live records"
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()


def test_stipends_move_firm_cash_to_apprentices_once_constructed(tmp_path, monkeypatch):
    """Constructed: firms open without an academy order and receive a fixed
    working cash top-up (a test-only sales credit, so the firm's books close)
    each turn; no customer buys. Wages and stipends then move real native
    wealth by stable id, once per (turn, purpose, site)."""
    from chronicler import workshop_payroll as P
    seen = {"stipend_rows": 0, "stipend_milli": 0}
    monkeypatch.setattr(P, "_open_orders", lambda world: {i: 0 for i in range(len(world.civilizations))})
    monkeypatch.setattr(P, "_customers", lambda world: [])
    prepare, native = P.prepare_phase2, P._native

    def seeded_prepare(world, region_input, agent_bridge, snapshot, acc):
        for firm in world.livelihoods.workshop_payroll.firms:      # before the turn's receipt opens
            top = max(0, 3000 - firm.cash)
            firm.cash += top
            firm.totals["sales"] = firm.totals.get("sales", 0) + top
        return prepare(world, region_input, agent_bridge, snapshot, acc)

    class Checked:
        def __init__(self, sim):
            self._sim = sim

        def __getattr__(self, name):
            return getattr(self._sim, name)

        def transfer_wealth(self, turn, purpose, batch, rows):
            snap = self._sim.get_snapshot()
            before = dict(zip(snap.column("id").to_pylist(), snap.column("wealth").to_pylist(), strict=True))
            out = self._sim.transfer_wealth(turn, purpose, batch, rows)
            snap = self._sim.get_snapshot()
            after = dict(zip(snap.column("id").to_pylist(), snap.column("wealth").to_pylist(), strict=True))
            for aid, requested, applied, residual, status in out:
                assert applied + residual == requested
                if status != 2:
                    assert after[aid] - before[aid] == pytest.approx(applied / 1000, abs=2e-5)
                if purpose == 2:
                    seen["stipend_rows"] += 1
                    seen["stipend_milli"] += applied
            with pytest.raises(ValueError, match="already applied"):
                self._sim.transfer_wealth(turn, purpose, batch, rows)
            return out

    monkeypatch.setattr(P, "prepare_phase2", seeded_prepare)
    monkeypatch.setattr(P, "_native", lambda bridge: Checked(native(bridge)))
    from chronicler import apprenticeship as A
    phase10 = A.phase10

    def checked_phase10(world, acc, economy_result, agent_bridge):
        return phase10(world, acc, economy_result, SimpleBridge(Checked(agent_bridge._sim)))

    monkeypatch.setattr(A, "phase10", checked_phase10)
    bundle = _run(tmp_path, "--workshops", "--workshop-payroll", "--workshop-payroll-mode", "paid",
                  "--apprenticeship", turns=60)
    paid = 0
    for snap in bundle["history"]:
        payroll = snap["livelihoods"]["workshop_payroll"]
        for firm in payroll["firms"] + payroll["closed"]:
            P.check_firm(P.WorkshopFirm.model_validate(firm))
        for r in payroll["receipts"] or []:
            assert r["cash_close"] == (r["cash_open"] + r["sales"] - r["wages_paid"] - r["distributed"]
                                       - r["written_off"] - r.get("stipends", 0))
        rec = snap["livelihoods"]["apprenticeship"]
        for r in rec["receipts"] or []:
            for s in r["seats"]:
                if s["outcome"] == "attended":
                    assert s["stipend_status"] in ("paid", "partial", "no_cash", "no_firm", "absent")
                    paid += s["stipend_paid"]
    final = bundle["history"][-1]["livelihoods"]["apprenticeship"]["counters"]
    assert final["stipends_paid"] == paid == seen["stipend_milli"] > 0
    assert final["stipends_paid"] + final["stipends_residual"] == final["stipends_due"]


class SimpleBridge:
    def __init__(self, sim):
        self._sim = sim
