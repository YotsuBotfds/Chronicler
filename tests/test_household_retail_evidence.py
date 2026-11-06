"""A2R: retail evidence for the wage-versus-enrollment question, and RL4/RL5.

Offline, on the stand-in native of ``test_household_retail.py`` (template seed
42 with constructed people):

* the ``schedule`` boundary (``--household-retail-boundary schedule
  --household-retail-schedule PATH``): validation, refusals, the frozen
  schedule and its digest in the state, exact and legacy resumes, and a
  replay of a ``paid_work`` arm's recorded openings;
* ``opened_turn`` (rules version 2) and :func:`household_retail.extract_schedule`
  with ``scripts/retail_schedule.py``;
* RL5: household-group cohorts per provisioned pilot region-turn, exact or
  marked unknown, summing to the region's totals;
* RL4: Phase 10 granaries buy owned grain only within this turn's storage cap
  (version 2; version 1 unchanged).

The real-extension halves (a replay on development worlds, an exact resume,
cohorts on a natural run) are in ``test_household_retail_evidence_native.py``.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import pickle
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from chronicler import household_retail as HR
from chronicler import livelihoods as LV
from chronicler.household_retail_state import COHORT_FIELDS, COHORT_GROUPS, HouseholdRetailState
from chronicler.livelihoods import configure_livelihoods
from chronicler.main import _build_parser
from chronicler.world_gen import generate_world
from tests.test_household_retail import (
    AMBER, ASHARA, FROST, THORNWOOD, VERDANT, Harness, _conquer, _granary_world, _people,
)

parse = _build_parser().parse_args
V1 = ("--household-retail-rules", "1")
ROOT = Path(__file__).resolve().parents[1]


def _schedule_file(tmp_path, schedule, name="schedule.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({str(k): v for k, v in schedule.items()}), encoding="utf-8")
    return path


def _scheduled(tmp_path, schedule, *flags) -> Harness:
    path = _schedule_file(tmp_path, schedule)
    return Harness("--household-retail-boundary", "schedule", "--household-retail-schedule", str(path), *flags)


def _history(h, records):
    records.append({"turn": h.world.turn, "livelihoods": {"household_retail": h.summary()}})


# --- the schedule: validation ------------------------------------------------------

def test_a_schedule_is_canonical_and_its_digest_ignores_layout():
    schedule = HR.parse_schedule({"5": 3, "0": 0, "12": 40}, 16)
    assert list(schedule) == [0, 5, 12]
    assert HR.canonical_schedule(schedule) == b'{"0":0,"5":3,"12":40}'
    assert HR.schedule_digest(schedule) == hashlib.sha256(b'{"0":0,"5":3,"12":40}').hexdigest()
    assert HR.parse_schedule({}, 8) == {}                                # no region ever opens


@pytest.mark.parametrize("data, message", [
    ([[0, 1]], "a JSON object"),
    ({"x": 1}, "not a region index"),
    ({"01": 1}, "not a region index"),
    ({"-1": 1}, "not a region index"),
    ({"1.0": 1}, "not a region index"),
    ({" 1": 1}, "not a region index"),
    ({"8": 1}, "this world has regions 0-7"),
    ({"1": -1}, "non-negative integer"),
    ({"1": 1.0}, "non-negative integer"),
    ({"1": True}, "non-negative integer"),
    ({"1": "2"}, "non-negative integer"),
    ({"1": None}, "non-negative integer"),
])
def test_an_invalid_schedule_is_refused(data, message):
    with pytest.raises(ValueError, match=message):
        HR.parse_schedule(data, 8)


@pytest.mark.parametrize("text, message", [
    ('{"1": 2, "1": 3}', "repeats key"),
    ('{"1": 2', "is not JSON"),
    ("\xff", "is not JSON"),
])
def test_an_unreadable_schedule_file_is_refused(tmp_path, text, message):
    path = tmp_path / "bad.json"
    path.write_bytes(text.encode("latin-1"))
    with pytest.raises(ValueError, match=message):
        HR.load_schedule(path, 8)
    with pytest.raises(ValueError, match="No such file"):
        HR.load_schedule(tmp_path / "missing.json", 8)


# --- the schedule: configuration -----------------------------------------------------

def _configure(world, *argv, agent_mode="hybrid"):
    configure_livelihoods(world, parse(["--food-allocation", *argv]), agent_mode=agent_mode)


@pytest.mark.parametrize("argv, message", [
    (("--household-retail-schedule", "{path}"), "requires --household-retail$"),
    (("--household-retail", "--household-retail-schedule", "{path}"),
     "requires --household-retail-boundary schedule \\(the boundary is market\\)"),
    (("--household-retail", "--household-retail-boundary", "all", "--household-retail-schedule", "{path}"),
     "the boundary is all"),
    (("--household-retail", "--household-retail-boundary", "schedule"), "requires --household-retail-schedule PATH"),
    (("--household-retail", "--household-retail-boundary", "schedule", "--household-retail-schedule", "{bad}"),
     "names region 99"),
    (("--no-household-retail", "--household-retail-schedule", "{path}"), "requires --household-retail$"),
])
def test_the_schedule_option_is_refused_before_any_change(tmp_path, argv, message):
    path = _schedule_file(tmp_path, {VERDANT: 0})
    bad = _schedule_file(tmp_path, {99: 0}, "bad.json")
    world = generate_world(seed=42)
    with pytest.raises(ValueError, match=message):
        _configure(world, *(a.format(path=path, bad=bad) for a in argv))
    assert world.livelihoods is None


def test_a_schedule_is_stored_with_its_digest_and_recorded_in_the_manifest_only_when_given(tmp_path):
    from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
    assert SIMULATION_ARG_KEYS[SIMULATION_ARG_KEYS.index("household_retail_rules") + 1] == "household_retail_schedule"
    path = _schedule_file(tmp_path, {AMBER: 4, VERDANT: 2})
    world = generate_world(seed=42)
    argv = ["--food-allocation", "--household-retail", "--household-retail-boundary", "schedule",
            "--household-retail-schedule", str(path)]
    args = parse(argv)
    configure_livelihoods(world, args, agent_mode="hybrid")
    state = world.livelihoods.household_retail
    assert (state.boundary, state.schedule) == ("schedule", {VERDANT: 2, AMBER: 4})
    assert state.schedule_sha256 == hashlib.sha256(f'{{"{VERDANT}":2,"{AMBER}":4}}'.encode()).hexdigest()
    assert simulation_config(args)["household_retail_schedule"] == str(path)
    assert "household_retail_schedule" not in simulation_config(parse(argv[:-2]))
    assert "household_retail_schedule" not in simulation_config(parse([]))
    # Forwarded to child runs as an absolute path.
    relative = parse([*argv[:-1], "schedule.json"])
    assert LV.livelihoods_arguments(relative)[-1] == f"--household-retail-schedule={Path('schedule.json').resolve()}"
    # The served catalog never offers it: a viewer cannot hand the server a file.
    from chronicler import feature_catalog as fc
    surface = fc.live_surface(parse(["--live", "--agents", "hybrid"]))
    error = fc.validate_features({"food_allocation": True, "household_retail": True,
                                  "household_retail_boundary": "schedule"}, surface)
    assert error == "'household_retail_boundary' must be one of market, paid_work, all"
    # A version-1 state keeps the schedule too (the boundary is not a rules matter).
    v1 = generate_world(seed=42)
    configure_livelihoods(v1, parse([*argv, *V1]), agent_mode="hybrid")
    assert v1.livelihoods.household_retail.schedule == state.schedule
    assert v1.livelihoods.household_retail.opened_turn is None


def test_a_state_without_a_schedule_serializes_no_schedule_field():
    h = Harness()
    dump = json.loads(h.state.model_dump_json())
    assert not {"schedule", "schedule_sha256"} & set(dump) and dump["opened_turn"] == {}
    v1 = Harness(*V1)
    assert not {"schedule", "schedule_sha256", "opened_turn"} & set(json.loads(v1.state.model_dump_json()))
    assert not {"schedule", "opened_turn"} & set(v1.summary())


# --- the schedule: the boundary ------------------------------------------------------

def test_regions_open_from_their_scheduled_turn_while_they_have_a_controller(tmp_path):
    h = _scheduled(tmp_path, {VERDANT: 10, ASHARA: 11, THORNWOOD: 12, FROST: 30})
    for rid in (VERDANT, ASHARA, THORNWOOD):
        _people(h, rid, (rid * 10 + 1, rid * 10 + 2), wealth=0.0)
    h.world.regions[ASHARA].controller = None                         # no controller: not yet
    h.turn({VERDANT: {"grain": 3.0}})
    assert HR.pilot_regions(h.world) == [VERDANT]
    h.world.regions[ASHARA].controller = "Selurian Republic"
    h.turn({VERDANT: {"grain": 3.0}})                                 # turn 11: Ashara now ruled
    assert HR.pilot_regions(h.world) == [VERDANT, ASHARA]
    h.turn({VERDANT: {"grain": 3.0}})
    assert HR.pilot_regions(h.world) == [VERDANT, ASHARA, THORNWOOD]
    assert all(r.reason == "schedule" for r in h.state.regions)
    assert h.state.opened_turn == {VERDANT: 10, ASHARA: 11, THORNWOOD: 12}
    # Sticky closure and reopening are the other boundaries': a region without
    # a controller closes, and reopens once ruled again (its opening stays dated).
    h.world.regions[THORNWOOD].controller = None
    h.turn()
    assert HR.pilot_regions(h.world) == [VERDANT, ASHARA]
    h.world.regions[THORNWOOD].controller = "Thornwall Confederacy"
    h.turn()
    assert HR.pilot_regions(h.world) == [VERDANT, ASHARA, THORNWOOD]
    assert h.state.region(THORNWOOD).opened_turn == 14 and h.state.opened_turn[THORNWOOD] == 12
    summary = h.summary()
    assert summary["opened_turn"] == {str(VERDANT): 10, str(ASHARA): 11, str(THORNWOOD): 12}
    assert summary["schedule"]["sha256"] == h.state.schedule_sha256
    assert summary["schedule"]["turns"] == {str(k): v for k, v in sorted(h.state.schedule.items())}


def test_a_version_2_state_saved_before_a2r_starts_its_opened_turn_map_from_its_open_regions():
    h = Harness()
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.turn({VERDANT: {"grain": 3.0}})
    h.state.opened_turn = None                                        # as A5 saved it
    h.turn()
    assert h.state.opened_turn == {r.region: r.opened_turn for r in h.state.regions} and h.state.opened_turn


# --- opened_turn, extraction and the replay ------------------------------------------

#: Paid crews by turn: a region qualifies for ``paid_work`` from the lanes'
#: last committed frame, so one turn after its first paid crew.
PAID = {9: [VERDANT], 11: [VERDANT, THORNWOOD], 12: [FROST]}


def _paid_work_run(*flags, turns=6, history=None, monkeypatch=None):
    """A ``paid_work`` arm in which paid crews qualify Verdant (turn 10),
    Thornwood (12) and Frostholm (13); with ``flags`` replacing the boundary.
    The lanes' receipts are stood in for by ``_paid_work_regions`` (their
    reading is ``test_household_retail.py::test_paid_work_includes_regions_of_paid_repair_crews``)."""
    monkeypatch.setattr(HR, "_paid_work_regions",
                        lambda world: [(r, "paid_work") for r in sorted(PAID.get(int(world.turn) - 1, []))])
    h = Harness(*(flags or ("--household-retail-boundary", "paid_work")))
    for rid in (VERDANT, THORNWOOD, FROST, AMBER):
        _people(h, rid, (rid * 10 + 1, rid * 10 + 2, rid * 10 + 3), wealth=0.5)
        h.sim.add(rid * 10 + 4, rid, occupation=2, wealth=1.0)
    for _ in range(turns):
        h.turn({rid: {"grain": 4.0, "fish": 1.0} for rid in (VERDANT, THORNWOOD, FROST, AMBER)})
        if history is not None:
            _history(h, history)
    return h


def _pilot_turns(history) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for snap in history:
        for frame in snap["livelihoods"]["household_retail"]["regions"]:
            out.setdefault(frame["region"], []).append(snap["livelihoods"]["household_retail"]["source_turn"])
    return out


def test_replaying_a_paid_work_arms_openings_reproduces_its_pilot_region_turns(tmp_path, monkeypatch):
    """The audit's replay (offline): the openings a ``paid_work`` arm records
    in ``opened_turn``, extracted from its bundle, given back as a schedule,
    reproduce its per-region pilot region-turns, and here (one arm, same
    people) its whole owned-food and money record."""
    history = []
    a = _paid_work_run(history=history, monkeypatch=monkeypatch)
    found = HR.extract_schedule({"history": history})
    assert found["schedule"] == {VERDANT: 10, THORNWOOD: 12, FROST: 13} and found["source"] == "opened_turn"
    assert found["closures"] == [] and found["regions_closed"] == 0
    path = tmp_path / "S_A.json"
    assert HR.write_schedule(path, found["schedule"]) == found["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    replay = []
    b = _paid_work_run("--household-retail-boundary", "schedule", "--household-retail-schedule", str(path),
                       history=replay, monkeypatch=monkeypatch)
    assert _pilot_turns(replay) == _pilot_turns(history) == {VERDANT: [10, 11, 12, 13, 14, 15],
                                                             THORNWOOD: [12, 13, 14, 15], FROST: [13, 14, 15]}

    def comparable(snap):
        rec = json.loads(json.dumps(snap["livelihoods"]["household_retail"]))
        rec.pop("boundary"), rec.pop("schedule", None)
        for frame in rec["regions"]:
            frame.pop("opened_turn")
        rec["log"] = [{k: v for k, v in r.items() if k != "note"} for r in rec["log"]]
        return rec
    assert [comparable(s) for s in replay] == [comparable(s) for s in history]
    assert [r.claims for r in b.state.regions] == [r.claims for r in a.state.regions]


def test_a_version_1_bundle_yields_its_schedule_from_the_frames_and_closures_are_named(tmp_path, monkeypatch):
    history = []
    h = _paid_work_run("--household-retail-boundary", "paid_work", *V1, history=history, monkeypatch=monkeypatch)
    assert "opened_turn" not in history[-1]["livelihoods"]["household_retail"]
    found = HR.extract_schedule({"history": history})
    assert found["source"] == "frames" and found["schedule"] == {VERDANT: 10, THORNWOOD: 12, FROST: 13}
    # A closure is named (a replay may reopen the region at another turn).
    h.world.regions[FROST].controller = None
    h.turn()
    _history(h, history)
    assert HR.extract_schedule({"history": history})["closures"] == [[16, FROST]]
    # opened_turn and the frames must agree.
    bad = json.loads(json.dumps(history))
    bad[-1]["livelihoods"]["household_retail"]["opened_turn"] = {str(VERDANT): 11}
    with pytest.raises(ValueError, match="disagrees with the frames for regions"):
        HR.extract_schedule({"history": bad})
    with pytest.raises(ValueError, match="no household retail record"):
        HR.extract_schedule({"history": [{"turn": 1}]})


def test_the_schedule_script_writes_the_canonical_file(tmp_path, capsys, monkeypatch):
    spec = importlib.util.spec_from_file_location("retail_schedule_under_test", ROOT / "scripts" / "retail_schedule.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    history = []
    _paid_work_run(history=history, turns=4, monkeypatch=monkeypatch)
    bundle = tmp_path / "chronicle_bundle.json"
    bundle.write_text(json.dumps({"history": history}), encoding="utf-8")
    out = tmp_path / "S.json"
    assert script.main([str(bundle), "--output", str(out)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (FROST, VERDANT, THORNWOOD) == (0, 2, 4)
    assert out.read_bytes() == b'{"0":13,"2":10,"4":12}'                 # canonical: compact, ascending region
    assert report["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest() and report["source"] == "opened_turn"
    assert HR.load_schedule(out, 8)[1] == report["sha256"]
    bundle.write_text(json.dumps({"history": []}), encoding="utf-8")
    assert script.main([str(bundle), "--output", str(out)]) == 1
    assert capsys.readouterr().err.startswith("Error:")


# --- the schedule: resumes -----------------------------------------------------------

def test_an_exact_resume_keeps_the_schedule_and_refuses_a_different_one(tmp_path):
    h = _scheduled(tmp_path, {VERDANT: 10})
    world = h.world
    same = _schedule_file(tmp_path, {VERDANT: 10}, "elsewhere.json")
    same.write_text('{ "2" : 10 }', encoding="utf-8")                  # other bytes, same schedule
    other = _schedule_file(tmp_path, {VERDANT: 11}, "other.json")
    recorded = {"household_retail_schedule": str(tmp_path / "schedule.json")}
    assert LV.livelihoods_resume_conflicts(world, parse([]), dict(recorded)) == []
    kept = dict(recorded)
    assert LV.livelihoods_resume_conflicts(world, parse(["--household-retail-schedule", str(same)]), kept) == []
    assert kept == {}                         # identified by its digest: the path is not compared
    (conflict,) = LV.livelihoods_resume_conflicts(world, parse(["--household-retail-schedule", str(other)]),
                                                  dict(recorded))
    assert conflict.startswith(f"--household-retail-schedule {other} (sha256 ") and "which it keeps" in conflict
    (missing,) = LV.livelihoods_resume_conflicts(world, parse(["--household-retail-schedule",
                                                              str(tmp_path / "gone.json")]), {})
    assert "No such file" in missing
    plain = Harness()
    (none,) = LV.livelihoods_resume_conflicts(plain.world, parse(["--household-retail-schedule", str(same)]), {})
    assert none.endswith("(no schedule)")


def test_a_legacy_resume_keeps_the_schedule_and_refuses_a_different_one(tmp_path):
    h = _scheduled(tmp_path, {VERDANT: 10, AMBER: 12})
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.turn({VERDANT: {"grain": 3.0}})
    world = type(h.world).model_validate_json(h.world.model_dump_json())
    state = world.livelihoods.household_retail
    assert (state.schedule, state.schedule_sha256) == (h.state.schedule, h.state.schedule_sha256)
    assert pickle.loads(pickle.dumps(state)) == state
    before = world.model_dump_json()
    other = _schedule_file(tmp_path, {VERDANT: 10}, "other.json")
    with pytest.raises(ValueError, match="conflicts with the saved retail state"):
        configure_livelihoods(world, parse(["--household-retail-schedule", str(other)]), agent_mode="hybrid")
    assert world.model_dump_json() == before
    configure_livelihoods(world, parse(["--household-retail-schedule", str(tmp_path / "schedule.json")]),
                          agent_mode="hybrid")
    configure_livelihoods(world, parse([]), agent_mode="hybrid")
    assert world.livelihoods.household_retail.schedule == {VERDANT: 10, AMBER: 12}
    # Another boundary keeps the schedule stored (unused) and the boundary can come back.
    configure_livelihoods(world, parse(["--household-retail", "--household-retail-boundary", "market"]),
                          agent_mode="hybrid")
    configure_livelihoods(world, parse(["--household-retail", "--household-retail-boundary", "schedule"]),
                          agent_mode="hybrid")
    assert world.livelihoods.household_retail.schedule_sha256 == h.state.schedule_sha256


# --- RL5: household-group cohorts -----------------------------------------------------

def _stage_crews(h, pl3=(), rs2=()):
    """An ``economy`` callback staging this turn's PL3 crew receipts (members
    with their wages) and RS2 repair receipts (crews with a total), as the
    packages' Phase 2 does; the packages themselves are off."""
    from chronicler.recovery_crews_state import RecoveryCrewsState
    from chronicler.repair_projects_state import RepairProjectsState

    def stage(_res):
        lv = h.world.livelihoods
        lv.recovery_crews = lv.recovery_crews or RecoveryCrewsState(enabled=False)
        lv.repair_projects = lv.repair_projects or RepairProjectsState(enabled=False)
        turn = h.world.turn
        lv.recovery_crews._turn = NS(turn=turn, receipts=[
            NS(region=r, kind="granary", members=[NS(agent_id=a, farm_time=0.0, wage_milli=w) for a, w in members])
            for r, members in pl3])
        lv.repair_projects._turn = NS(turn=turn, receipts=[NS(region=r, crew=list(crew), wages_milli=w)
                                                           for r, crew, w in rs2])
    return stage


def _household_world(*flags):
    """Verdant: crew 1 (PL3, wage 300) and crew 2 (RS2, wage 200); 3, a child of
    1; 4, a child alone; 5, a merchant with no cash; 7, a farmer off the crews,
    and 6, 7's child."""
    h = Harness(*flags)
    _people(h, VERDANT, (1, 2, 7), wealth=0.4)
    h.sim.add(3, VERDANT, age=10, parents=(1, 0), wealth=0.0)
    h.sim.add(4, VERDANT, age=8, wealth=0.0)
    h.sim.add(5, VERDANT, occupation=2, wealth=0.0)
    h.sim.add(6, VERDANT, age=12, parents=(7, 0), wealth=0.05)
    h.sim.add(8, VERDANT, occupation=2, wealth=3.0)
    return h, _stage_crews(h, pl3=[(VERDANT, [(1, 300)])], rs2=[(VERDANT, [2], 200)])


def _cohort(h, rid=VERDANT):
    return h.frame(rid).cohorts


def _sums(cohort, field):
    return sum(cohort["groups"][g][field] for g in COHORT_GROUPS)


def test_cohorts_partition_the_provisioned_people_and_sum_to_the_region_totals():
    h, crews = _household_world()
    h.turn({VERDANT: {"grain": 20.0}}, economy=crews)
    h.turn({VERDANT: {"grain": 20.0}}, economy=crews)
    cohort, frame = _cohort(h), h.frame(VERDANT)
    prov = frame.provisioning
    groups = cohort["groups"]
    assert list(groups) == list(COHORT_GROUPS) and all(list(g) == list(COHORT_FIELDS) for g in groups.values())
    assert cohort["unknown"] == {}
    assert {g: groups[g]["persons"] for g in COHORT_GROUPS} == {
        "crew": 2, "crew_children": 1, "children_alone": 1, "nonfarm_adults": 2, "other": 2}
    assert _sums(cohort, "persons") == prov["persons"] == 8
    assert _sums(cohort, "priced_out") == prov["priced_out_persons"] and groups["nonfarm_adults"]["priced_out"] >= 1
    for field in ("paid_milli", "refunded_milli"):
        assert _sums(cohort, field) == prov[field]
    assert _sums(cohort, "credited_milli") + cohort["credited_outside_milli"] == prov["credited_milli"]
    assert prov["paid_milli"] > 0 and groups["nonfarm_adults"]["paid_milli"] > 0           # 8 bought food
    assert _sums(cohort, "income_replaced") == pytest.approx(frame.income_replaced)
    assert groups["nonfarm_adults"]["income_replaced"] == 0.0 and groups["crew"]["income_replaced"] > 0
    assert groups["crew"]["wages_milli"] == 500 and _sums(cohort, "wages_milli") == 500
    # Aggregates only: no stable id leaves.
    summary = h.summary()
    assert summary["regions"][0]["cohorts"] == cohort
    assert set(json.dumps(cohort["groups"])) and "agent" not in json.dumps(cohort)


def test_a_death_before_provisioning_makes_persons_unknown_and_an_orphaned_childs_groups_unknown():
    h, crews = _household_world()
    h.turn({VERDANT: {"grain": 20.0}}, economy=crews)
    h.sim.die_before = {7}                                  # 6's parent, before phase 0.7
    h.turn({VERDANT: {"grain": 20.0}}, economy=crews)
    cohort = _cohort(h)
    groups, why = cohort["groups"], cohort["unknown"]
    assert all(groups[g]["persons"] is None for g in COHORT_GROUPS)
    assert why["persons"] == ("the Phase 2 roster lists 8, the tick provisioned 7: who died before provisioning "
                              "is not recorded")
    # 6 (a farmer child) had income replaced: unknown for the children's and other groups only.
    for g in ("crew_children", "children_alone", "other"):
        assert groups[g]["income_replaced"] is None
    assert groups["crew"]["income_replaced"] > 0 and groups["nonfarm_adults"]["income_replaced"] == 0.0
    assert why["income_replaced"].startswith("unknown for the children's and other groups")
    assert groups["crew"]["wages_milli"] == 500


def test_priced_out_is_unknown_when_the_native_sample_misses_a_priced_out_person(monkeypatch):
    h, crews = _household_world()
    original = h.sim._retail

    def truncated(install):
        frame = list(original(install))
        frame[5] = [row for row in frame[5] if row[5] != 1]           # no priced-out row kept
        frame[6] = 3
        return tuple(frame)
    monkeypatch.setattr(h.sim, "_retail", truncated)
    h.turn({VERDANT: {"grain": 20.0}}, economy=crews)
    cohort = _cohort(h)
    expected = h.frame(VERDANT).provisioning["priced_out_persons"]
    assert expected > 0
    assert all(cohort["groups"][g]["priced_out"] is None for g in COHORT_GROUPS)
    assert cohort["unknown"]["priced_out"] == f"the native sample holds 0 of {int(expected)} priced-out persons"
    assert _sums(cohort, "persons") == h.frame(VERDANT).provisioning["persons"]       # persons stay exact


def test_a_crew_living_in_two_regions_or_without_wages_leaves_wages_unknown():
    h = Harness("--household-retail-boundary", "all")
    _people(h, VERDANT, (1, 2), wealth=0.0)
    _people(h, ASHARA, (11, 12), wealth=0.0)
    crews = _stage_crews(h, rs2=[(VERDANT, [1, 11], 400)])
    h.turn({VERDANT: {"grain": 2.0}, ASHARA: {"grain": 2.0}}, economy=crews)
    for rid in (VERDANT, ASHARA):
        cohort = _cohort(h, rid)
        assert cohort["groups"]["crew"]["wages_milli"] is None
        assert cohort["unknown"]["wages_milli"] == "a paid crew's members live in several regions"
        assert cohort["groups"]["crew"]["persons"] == 1
    # A receipt without a wage field is unknown, never zero.
    h2 = Harness()
    _people(h2, VERDANT, (1, 2), wealth=0.0)

    def no_wage(_res):
        from chronicler.recovery_crews_state import RecoveryCrewsState
        lv = h2.world.livelihoods
        lv.recovery_crews = lv.recovery_crews or RecoveryCrewsState(enabled=False)
        lv.recovery_crews._turn = NS(turn=h2.world.turn, receipts=[
            NS(region=VERDANT, kind="granary", members=[NS(agent_id=1, farm_time=0.0)])])
    h2.turn({VERDANT: {"grain": 2.0}}, economy=no_wage)
    assert _cohort(h2)["groups"]["crew"]["wages_milli"] is None
    assert _cohort(h2)["unknown"]["wages_milli"] == "a crew receipt records no wage"


def _migrant_sellers(*crew):
    """1 and 9 farm in Verdant, then move to Ashara keeping their Verdant
    claims: next turn each sells there and in Ashara (one money row each)."""
    h = Harness("--household-retail-boundary", "all")
    _people(h, VERDANT, (1, 9), wealth=0.0)
    _people(h, VERDANT, (2, 3), occupation=2, wealth=5.0)
    _people(h, ASHARA, (12, 13), occupation=2, wealth=5.0)
    h.sim.moves = {1: ASHARA, 9: ASHARA}
    h.turn({VERDANT: {"grain": 6.0}})
    h.turn({ASHARA: {"grain": 6.0}, VERDANT: {"grain": 6.0}},
           economy=_stage_crews(h, pl3=[(ASHARA, [(a, 0) for a in crew])]) if crew else None)
    return h


def test_sellers_with_claims_in_two_regions_are_attributed_by_the_regions_totals():
    """One money row covers a seller's sales in several regions: each region's
    part is its credit less its one-region sellers', exact as a total, and it
    belongs to the sellers' group when they share one."""
    h = _migrant_sellers()
    for rid in (VERDANT, ASHARA):
        cohort, prov = _cohort(h, rid), h.frame(rid).provisioning
        assert "credited_milli" not in cohort["unknown"]
        assert _sums(cohort, "credited_milli") + cohort["credited_outside_milli"] == prov["credited_milli"]
    # 1 and 9 (farmers off the crews, provisioned in Ashara now) are the only sellers in both
    # regions: credited goes by the claim's region to the seller's group.
    for rid in (VERDANT, ASHARA):
        cohort = _cohort(h, rid)
        assert cohort["groups"]["other"]["credited_milli"] == h.frame(rid).provisioning["credited_milli"] > 0
        assert cohort["credited_outside_milli"] == 0


def test_sellers_of_two_groups_with_claims_in_two_regions_leave_credited_unknown_there():
    h = _migrant_sellers(9)                                  # 9 is on a crew this turn, 1 is not
    for rid in (VERDANT, ASHARA):
        cohort = _cohort(h, rid)
        assert cohort["unknown"].get("credited_milli") == (
            "sellers of several groups also sold claims of other regions this turn")
        assert all(cohort["groups"][g]["credited_milli"] is None for g in COHORT_GROUPS)
        assert cohort["credited_outside_milli"] is None


def test_no_cohorts_in_version_1_record_only_or_free_exchange_money():
    h, crews = _household_world(*V1)
    h.turn({VERDANT: {"grain": 20.0}}, economy=crews)
    assert h.frame(VERDANT).cohorts is None and "cohorts" not in h.summary()["regions"][0]
    assert "cohorts" not in json.loads(h.state.model_dump_json())["frame"][0]
    ro, crews = _household_world("--household-retail-mode", "record_only")
    ro.turn({VERDANT: {"grain": 2.0}}, economy=crews)
    assert ro.frame(VERDANT).cohorts is None
    free, crews = _household_world("--household-retail-mode", "free_exchange")
    free.turn({VERDANT: {"grain": 2.0}}, economy=crews)
    groups = _cohort(free)["groups"]
    assert all(groups[g]["paid_milli"] == 0 == groups[g]["income_replaced"] for g in COHORT_GROUPS)
    assert _sums(_cohort(free), "persons") == free.frame(VERDANT).provisioning["persons"]


def test_cohort_groups_follow_the_roster():
    roster = {1: (0, 30, 0, 0, 0), 2: (0, 30, 2, 0, 0), 3: (0, 9, 0, 1, 0), 4: (0, 9, 0, 0, 0),
              5: (0, 9, 0, 2, 0), 6: (1, 9, 0, 1, 0), 7: (0, 40, 0, 0, 0)}
    alive = {1: None, 2: None, 3: None, 4: None, 5: None, 6: None}
    group = {aid: HR.cohort_group(aid, roster, {1, 7}, alive) for aid in roster}
    assert group == {1: ("crew", True), 2: ("nonfarm_adults", True), 3: ("crew_children", True),
                     4: ("children_alone", True), 5: ("other", True),
                     6: ("children_alone", True),          # its crew parent lives in another region
                     7: ("crew", True)}
    roster[4] = (0, 9, 0, 7, 0)                            # 7 is not alive after the tick
    assert HR.cohort_group(4, roster, set(), alive) == ("other", False)


# --- RL4: owned grain above the storage cap ------------------------------------------------

def _above_cap_market(h):
    """Verdant with a storage cap of 2.5 x 12 = 30 per good, three owners and
    twenty penniless neighbours: this turn's title stays above the cap."""
    _people(h, VERDANT, (1, 2, 3), wealth=0.0)
    _people(h, VERDANT, range(40, 60), occupation=2, wealth=0.0)
    h.world.regions[VERDANT].population = 12


def test_granaries_buy_owned_grain_only_within_this_turns_storage_cap(monkeypatch):
    seen = {}
    for name, flags in (("v2", ()), ("v1", V1)):
        h = Harness(*flags)
        _above_cap_market(h)
        G, _granary = _granary_world(h, monkeypatch)
        h.turn({VERDANT: {"grain": 60.0}})

        def look(res, h=h, name=name):
            owned = h.state.region(VERDANT).goods[0]
            commons = h.world.regions[VERDANT].stockpile.goods.get("grain", 0.0)
            offered = HR.procurement_owned_grain(h.world)
            seen[name] = (owned, commons, offered[VERDANT] if offered else 0.0, h.state._turn.phase2.cap)
            G.tick_grain_reserves(h.world, None, res, None)
        h.turn({VERDANT: {"grain": 60.0}}, granaries=look)
        seen[name] += (h.frame(VERDANT).flows.get("procured", 0), dict(h.state.counters))
    owned, commons, offered, cap, procured, counters = seen["v2"]
    assert cap[VERDANT] == 30.0
    room = math.floor((30.0 - commons) * 1000 + 1e-6)
    assert owned > room >= 0
    assert offered == room / 1000 and procured <= room
    assert counters["owned_grain_above_cap_milli"] == owned - room
    owned1, _c, offered1, cap1, procured1, counters1 = seen["v1"]
    assert offered1 == owned1 / 1000 and cap1 == {} and "owned_grain_above_cap_milli" not in counters1
    assert procured1 > procured                             # version 1 sold grain the cap destroys


def test_owned_grain_within_the_cap_is_offered_whole_and_nothing_is_counted(monkeypatch):
    h = Harness()
    _above_cap_market(h)
    h.world.regions[VERDANT].population = 400                # cap 1000
    G, _ = _granary_world(h, monkeypatch)
    h.turn({VERDANT: {"grain": 60.0}})
    got = {}
    h.turn({VERDANT: {"grain": 60.0}}, granaries=lambda res: got.update(
        offered=HR.procurement_owned_grain(h.world)[VERDANT], owned=h.state.region(VERDANT).goods[0]))
    assert got["offered"] == got["owned"] / 1000 and "owned_grain_above_cap_milli" not in h.state.counters


def test_without_this_turns_phase2_the_cap_comes_from_the_population():
    h = Harness()
    _above_cap_market(h)
    h.turn({VERDANT: {"grain": 60.0}})
    h.state._turn = None
    owned = h.state.region(VERDANT).goods[0]
    commons = h.world.regions[VERDANT].stockpile.goods.get("grain", 0.0)
    assert HR.procurement_owned_grain(h.world)[VERDANT] == min(owned, math.floor((30.0 - commons) * 1000 + 1e-6)) / 1000
