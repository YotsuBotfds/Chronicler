"""A2R on the real compiled extension: the schedule replay, an exact resume
with the schedule boundary, and household-group cohorts on natural runs.

Development worlds only (template 7 and 23, procedural 7 at 32 x 10), the
checkpoint-3 base flags, retail rules version 2 (the default of a new state).
``CH`` is checkpoint 3's chain (PL1 woodcutting, PL3 crews paid, remittances),
``U`` the same with PL3 crews unpaid: payment decides which regions the
``paid_work`` boundary enrolls (audit A, D6), so the wage is compared at a
frozen enrollment by replaying one arm's recorded openings in the other.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("chronicler_agents")

from chronicler import household_retail as HR
from chronicler.household_retail_state import COHORT_FIELDS, COHORT_GROUPS

pytestmark = pytest.mark.native

CP3 = ["--grain-reserves", "--public-grain-shipments", "--scholarship", "--techniques", "--academy-services",
       "--grain-storage", "--food-allocation", "--workshops", "--operating-wear", "--repair-projects", "--timber-stock"]
CH = ["--timber-supply", "--recovery-crews", "--remittances"]
U = ["--timber-supply", "--recovery-crews", "--recovery-crew-mode", "unpaid", "--remittances"]
PAID_WORK = ["--household-retail", "--household-retail-boundary", "paid_work"]
WORLDS = {
    "t7": ["--seed", "7", "--civs", "4", "--regions", "8"],
    "t23": ["--seed", "23", "--civs", "4", "--regions", "8"],
    "p7": ["--seed", "7", "--worldgen", "procedural", "--regions", "32", "--civs", "10"],
}
TURNS = "80"


def _ready():
    from chronicler_agents import AgentSimulator
    return all(callable(getattr(AgentSimulator, name, None)) for name in HR.NATIVE_METHODS)


READY = _ready()


def _argv(world: str, *extra: str) -> list[str]:
    return [*WORLDS[world], "--turns", TURNS, "--agents", "hybrid", "--simulate-only", *CP3, *extra]


def _run(out: Path, argv: list[str]) -> dict:
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    execute_run(_build_parser().parse_args([*argv, "--output", str(out / "chronicle.md"),
                                            "--state", str(out / "state.json")]))
    return load_bundle(out / "chronicle_bundle.json")


def _schedule(path: Path) -> list[str]:
    return ["--household-retail", "--household-retail-boundary", "schedule", "--household-retail-schedule", str(path)]


def _records(bundle) -> list[dict]:
    return [s["livelihoods"]["household_retail"] for s in bundle["history"]
            if (s.get("livelihoods") or {}).get("household_retail")]


def _pilot_turns(bundle) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for record in _records(bundle):
        for frame in record["regions"] or ():
            out.setdefault(frame["region"], []).append(record["source_turn"])
    return out


def _masked(bundle) -> list:
    """The history with what names the boundary left out (the boundary, the
    schedule summary and the record notes)."""
    out = []
    for snap in bundle["history"]:
        snap = json.loads(json.dumps(snap))
        record = (snap.get("livelihoods") or {}).get("household_retail")
        if record:
            record.pop("boundary")
            record.pop("schedule", None)
            record["log"] = [{k: v for k, v in r.items() if k != "note"} for r in record["log"]]
        out.append(snap)
    return out


def _masked_world(bundle) -> dict:
    """The final world with the retail state's boundary labels left out
    (boundary, schedule, each entry's opening reason, record notes)."""
    world = json.loads(json.dumps(bundle["world_state"]))
    retail = world["livelihoods"]["household_retail"]
    for key in ("boundary", "schedule", "schedule_sha256"):
        retail.pop(key, None)
    for entry in retail["regions"]:
        entry.pop("reason")
    retail["log"] = [{k: v for k, v in r.items() if k != "note"} for r in retail["log"]]
    return world


def _check_cohorts(bundle) -> tuple[int, int]:
    """Every cohort record sums to its region's totals where exact; returns
    (provisioned region-turns, region-turns with every field exact)."""
    seen = exact = 0
    for record in _records(bundle):
        assert record.get("rules_version") == 2
        for frame in record["regions"] or ():
            prov, cohort = frame["provisioning"], frame.get("cohorts")
            if prov is None:
                assert cohort is None
                continue
            seen += 1
            # Aggregates only: named groups and fields, no id anywhere.
            assert set(cohort) == {"groups", "credited_outside_milli", "unknown"}
            assert list(cohort["groups"]) == list(COHORT_GROUPS)
            assert all(list(cell) == list(COHORT_FIELDS) for cell in cohort["groups"].values())
            why = cohort["unknown"]
            exact += not why

            def total(field):
                cells = [cohort["groups"][g][field] for g in COHORT_GROUPS]
                return None if None in cells else sum(cells)
            for field in COHORT_FIELDS:
                if total(field) is None:
                    assert field in why, (record["source_turn"], frame["region"], field)
            for field, column in (("persons", "persons"), ("priced_out", "priced_out_persons"),
                                  ("paid_milli", "paid_milli"), ("refunded_milli", "refunded_milli")):
                if total(field) is not None:
                    assert total(field) == prov[column], (record["source_turn"], frame["region"], field)
            if total("credited_milli") is not None:
                assert total("credited_milli") + cohort["credited_outside_milli"] == prov["credited_milli"]
            if total("income_replaced") is not None:
                assert total("income_replaced") == pytest.approx(frame["income_replaced"] or 0.0, abs=1e-5)
    return seen, exact


if READY:

    @pytest.mark.parametrize("world", sorted(WORLDS))
    def test_replaying_the_paid_arms_openings_in_the_unpaid_arm_reproduces_its_enrollment(world, tmp_path):
        """The audit's replay with the real option: ``U`` given ``CH``'s recorded
        openings (``opened_turn``, extracted from the bundle) has ``CH``'s pilot
        regions on exactly ``CH``'s turns, though the wage differs. On template
        7 ``CH`` replaying its own openings reproduces its whole history; on
        template 23 the reverse direction (``CH`` at ``U``'s openings) too."""
        paid = _run(tmp_path / "CH_pw", _argv(world, *PAID_WORK, *CH))
        found = HR.extract_schedule(paid)
        assert found["source"] == "intervals" and found["exact"] and found["schedule"] and found["closures"] == []
        s_a = tmp_path / "S_A.json"
        HR.write_schedule(s_a, found["schedule"])
        unpaid_at_a = _run(tmp_path / "U_sA", _argv(world, *_schedule(s_a), *U))
        assert _pilot_turns(unpaid_at_a) == _pilot_turns(paid)
        assert _records(unpaid_at_a)[-1]["schedule"]["sha256"] == found["sha256"]
        seen, _exact = _check_cohorts(unpaid_at_a)
        assert seen > 0
        if world == "t7":
            itself = _run(tmp_path / "CH_sA", _argv(world, *_schedule(s_a), *CH))
            assert _masked(itself) == _masked(paid)
            assert _masked_world(itself) == _masked_world(paid)
        if world == "t23":
            unpaid = _run(tmp_path / "U_pw", _argv(world, *PAID_WORK, *U))
            s_b = tmp_path / "S_B.json"
            HR.write_schedule(s_b, HR.extract_schedule(unpaid)["schedule"])
            paid_at_b = _run(tmp_path / "CH_sB", _argv(world, *_schedule(s_b), *CH))
            assert _pilot_turns(paid_at_b) == _pilot_turns(unpaid)

    def test_an_exact_resume_keeps_the_schedule_and_refuses_another(tmp_path, monkeypatch, capsys):
        """Template 7 with a frozen schedule: resumes at turns 6 and 9 equal the
        straight run (the same schedule given again from another path is no
        conflict); a different schedule is refused before anything runs."""
        from chronicler.bundle_codec import load_bundle
        from chronicler.main import main
        from chronicler.run_checkpoint import read_checkpoint
        schedule = tmp_path / "S.json"
        schedule.write_text(json.dumps({"7": 0, "1": 4, "3": 8}), encoding="utf-8")
        argv = [*WORLDS["t7"], "--turns", "14", "--agents", "hybrid", "--simulate-only", *CP3,
                *_schedule(schedule), *CH]
        ck = tmp_path / "ck"
        straight = _run(tmp_path / "straight", [*argv, "--checkpoint-every", "1",
                                                "--checkpoint", str(ck / "turn_{turn:04d}.ckpt")])
        assert _pilot_turns(straight)[3][0] == 8 and _pilot_turns(straight)[7][0] == 0
        copy = tmp_path / "copy.json"
        copy.write_text('{"1": 4, "3": 8, "7": 0}\n', encoding="utf-8")         # another file, the same schedule
        for turn, extra in ((6, []), (9, ["--household-retail-schedule", str(copy)])):
            state = read_checkpoint(ck / f"turn_{turn:04d}.ckpt").state
            retail = state.world.livelihoods.household_retail
            assert retail.schedule == {1: 4, 3: 8, 7: 0} and retail.schedule_sha256 == HR.load_schedule(schedule, 8)[1]
            state.agent_bridge.close()
            out = tmp_path / f"resumed_{turn}"
            monkeypatch.setattr(sys, "argv", ["chronicler", "--resume", str(ck / f"turn_{turn:04d}.ckpt"), *extra,
                                              "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
            main()
            resumed = load_bundle(out / "chronicle_bundle.json")
            assert resumed["history"] == straight["history"] and resumed["world_state"] == straight["world_state"]
        other = tmp_path / "other.json"
        other.write_text(json.dumps({"7": 0, "1": 5}), encoding="utf-8")
        out = tmp_path / "refused"
        monkeypatch.setattr(sys, "argv", ["chronicler", "--resume", str(ck / "turn_0006.ckpt"),
                                          "--household-retail-schedule", str(other),
                                          "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")])
        capsys.readouterr()
        with pytest.raises(SystemExit) as exited:
            main()
        assert exited.value.code == 2
        err = capsys.readouterr().err
        assert f"--household-retail-schedule {other} (sha256 " in err and "which it keeps" in err
        assert not (out / "chronicle_bundle.json").exists()

    def test_cohorts_on_a_natural_paid_work_run_are_exact_or_marked_unknown(tmp_path):
        """Procedural development world 7 (80 turns, the paid arm): every
        provisioned pilot region-turn has a cohort record; each exact field sums
        to the region's totals and each unknown one names its reason; crew
        wages appear where PL3 paid granary crews."""
        bundle = _run(tmp_path, _argv("p7", *PAID_WORK, *CH))
        seen, exact = _check_cohorts(bundle)
        assert seen > 100 and exact > 0
        wages = [f["cohorts"]["groups"]["crew"]["wages_milli"] for r in _records(bundle) for f in r["regions"] or ()
                 if f.get("cohorts")]
        assert any(w for w in wages if w)
