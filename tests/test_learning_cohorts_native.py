"""L5 learning cohorts on the real compiled extension.

Constructed controls on the fixed seed-42 world with a declared academy (the
academy-services fixture): an initial craft market, a 500-coin treasury and
a declared exogenous restock of 20 crafts before each turn, so the academy
can keep buying supplies. Native scholars, learners, teaching, attendance,
income and skill are not mocked. Natural template worlds are in the
development evidence, not here.
"""
from __future__ import annotations

import math
import random

import pyarrow as pa
import pytest

pytest.importorskip("chronicler_agents")

from chronicler import learning_cohorts as L
from chronicler.agent_bridge import AgentBridge, build_signals
from chronicler.learning_cohorts_state import ATTENDANCE_OUTCOMES
from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
from chronicler.world_gen import generate_world

pytestmark = pytest.mark.native

RESTOCK = 20.0


def _academy_world(mode: str | None = "learn"):
    from chronicler.cities import set_cities_enabled
    from chronicler.learning_services import set_learning_services_enabled
    from chronicler.livelihoods import configure_livelihoods
    from chronicler.main import _build_parser
    from chronicler.scholarship_state import ACADEMY, ScholarshipState, Seat

    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    set_cities_enabled(world, True)
    bridge = AgentBridge(world, mode="hybrid")
    rows = pa.record_batch(bridge._sim.get_snapshot()).to_pylist()
    person = next(row for row in rows if row["occupation"] == 3 and row["age"] >= 20
                  and world.regions[row["region"]].controller is not None)
    region = person["region"]
    owner = world.civ_index_map[world.regions[region].controller]
    for r in world.regions:
        r.stockpile.goods = {"grain": 100.0}
    world.regions[region].stockpile.goods["crafts"] = 100.0
    world.civilizations[owner].treasury = 500
    world.scholarship = ScholarshipState(seats=[Seat(region=region, kind=ACADEMY,
        name="Declared Academy", founded_turn=world.turn, founder=owner, lord=owner)])
    set_learning_services_enabled(world, True)
    if mode is not None:
        configure_livelihoods(world, _build_parser().parse_args(
            ["--learning-cohorts", "--learning-cohort-mode", mode]), agent_mode="hybrid")
    return world, bridge, region


def _turn(world, bridge, region):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn_result
    goods = world.regions[region].stockpile.goods
    goods["crafts"] = goods.get("crafts", 0.0) + RESTOCK
    engine = ActionEngine(world)
    run_turn_result(world, lambda c, w: engine.select_action(c, seed=w.seed),
                    lambda w, events: "", seed=world.seed + world.turn, agent_bridge=bridge)
    return world.livelihoods.learning_cohorts if world.livelihoods is not None else None


def _agents(sim):
    return {row["id"]: row for row in pa.record_batch(sim.get_snapshot()).to_pylist()}


def _needs(sim):
    return {row["agent_id"]: row for row in pa.record_batch(sim.get_all_needs()).to_pylist()}


def _without_livelihoods(world):
    data = world.model_dump(mode="json")
    data.pop("livelihoods", None)
    return data


def _check_receipts(state, services, turn):
    teaching = {r.seat_id: r for r in services.teaching_receipts if r.source_turn == turn}
    for r in state.frame:
        assert r.turn == turn
        assert set(r.attended) | set(r.no_seat) | set(r.absent) == set(r.reserved)
        if r.attended:
            t = teaching[r.seat_id]
            assert t.work_delivered > 0 and len(r.attended) <= math.floor(t.learners_delivered + 1e-6)
            assert r.teaching_learners_delivered == t.learners_delivered
            assert r.supplies_used == len(r.attended) and r.supplies_used <= t.crafts_used + 1e-6
            assert r.income_charged > 0 and r.session
        else:
            assert r.income_charged == 0.0 and not r.session


def test_attendance_is_seated_by_delivered_teaching_and_withholds_ordinary_income():
    """Exact one-tick cost against an identical native control."""
    import chronicler_agents as ca
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    sim = bridge._sim
    rows = pa.record_batch(sim.get_snapshot()).to_pylist()
    region = next(r["region"] for r in rows if r["occupation"] == 3 and r["age"] >= 20)
    # Soldiers and priests first: their ordinary income is flat before any economy tick.
    candidates = sorted((r["occupation"] not in (1, 4), r["id"]) for r in rows
                        if r["region"] == region and r["occupation"] != 3 and r["age"] >= 20)
    learners = [aid for _, aid in candidates[:6]]
    assert len(learners) == 6
    requests = [0.0] * len(world.regions)
    requests[region] = 0.5                       # half a Scholar-day: four seats
    control = ca.AgentSimulator.from_checkpoint_state(sim.checkpoint_state())
    sim.prepare_teaching_work(world.turn, requests, [])
    control.prepare_teaching_work(world.turn, requests, [])
    with pytest.raises(ValueError):           # all or none: an unknown id refuses the call
        sim.reserve_learning_attendance(world.turn, 8.0, [(learners[0], region, 0.5), (2**31, region, 0.5)])
    assert not sim.has_pending_learning_attendance() and sim.work_reservations(world.turn) == []
    sim.reserve_learning_attendance(world.turn, 8.0, [(aid, region, 0.5) for aid in learners])
    assert sim.has_pending_learning_attendance()
    assert sorted(r[0] for r in sim.work_reservations(world.turn)) == sorted(learners)
    assert {r[1] for r in sim.work_reservations(world.turn)} == {1}
    with pytest.raises(ValueError, match="prepared for this tick"):
        sim.tick(world.turn + 1, build_signals(world))
    signals = build_signals(world)
    sim.tick(world.turn, signals)
    control.tick(world.turn, signals)
    assert sim.take_learning_attendance(world.turn + 1) is None
    delivered, attendance = sim.take_learning_attendance(world.turn)
    assert sim.take_learning_attendance(world.turn) is None and not sim.has_pending_learning_attendance()
    teaching = sim.get_teaching_work_result()
    assert delivered[region] == (teaching[1][region][4], 4)
    outcomes = [ATTENDANCE_OUTCOMES[row[3]] for row in attendance]
    assert outcomes == ["attended"] * 4 + ["no_seat"] * 2
    a, b = _agents(sim), _agents(control)
    for aid, _region, fraction, code, income, charged in attendance:
        assert aid in a and aid in b
        if ATTENDANCE_OUTCOMES[code] == "attended":
            assert charged == pytest.approx(income * fraction, rel=1e-6)
            # The withheld share of ordinary income, after the model's 0.98 decay.
            assert b[aid]["wealth"] - a[aid]["wealth"] == pytest.approx(charged * 0.98, abs=1e-6)
        else:
            assert charged == 0.0 and a[aid]["wealth"] == b[aid]["wealth"]
    assert sum(row[5] for row in attendance) > 0
    assert sim.work_reservations(world.turn) == []      # the tick clears the registry
    bridge.close()


def test_grant_reaches_the_civ_capacity_consumer():
    """A granted trade skill is what the hybrid write-back reads (military)."""
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    sim = bridge._sim
    before = {r["civ_id"]: r for r in pa.record_batch(sim.get_aggregates()).to_pylist()}
    rows = pa.record_batch(sim.get_snapshot()).to_pylist()
    civ = next(c for c in sorted(before) if any(r["occupation"] == 1 and r["civ_affinity"] == c for r in rows))
    soldiers = [r["id"] for r in rows if r["occupation"] == 1 and r["civ_affinity"] == civ
                and world.regions[r["region"]].controller == world.civilizations[civ].name][:8]
    assert soldiers and before[civ]["military"] < 100
    read = sim.grant_learning_skill([(aid, 1, 0.0) for aid in soldiers])
    assert all(alive and b == a for _, _, alive, b, a in read)
    assert pa.record_batch(sim.get_aggregates()).to_pylist() == list(before.values())
    granted = sim.grant_learning_skill([(aid, 1, L.COMPLETION_GAIN) for aid in soldiers])
    assert all(after == pytest.approx(min(1.0, b + L.COMPLETION_GAIN)) for _, _, _, b, after in granted)
    after = {r["civ_id"]: r for r in pa.record_batch(sim.get_aggregates()).to_pylist()}
    assert after[civ]["military"] > before[civ]["military"]
    assert {k: v for k, v in after.items() if k != civ} == {k: v for k, v in before.items() if k != civ}
    snap = _agents(sim)
    assert all(snap[aid]["skill"] == pytest.approx(min(1.0, b + L.COMPLETION_GAIN)) for aid, _, _, b, _ in granted)
    bridge.close()


def test_cohort_completes_and_only_the_learning_arm_changes_capability():
    """learn vs no_learning: identical worlds and costs until completion, then
    the graduates' trade skill and the purpose-need consumer differ."""
    arms = {mode: _academy_world(mode) for mode in ("learn", "no_learning")}
    completion = None
    for _ in range(L.SESSIONS_TO_COMPLETE + 2):
        for mode, (world, bridge, region) in arms.items():
            state = _turn(world, bridge, region)
            _check_receipts(state, world.scholarship.learning_services, world.turn - 1)
        (lw, lb, _), (nw, nb, _) = arms["learn"], arms["no_learning"]
        ls, ns = lw.livelihoods.learning_cohorts, nw.livelihoods.learning_cohorts
        if completion is None:
            assert _without_livelihoods(lw) == _without_livelihoods(nw)
            for key in ("learner_turns_attended", "attendance_income_charged", "supplies_used_by_attendees",
                        "sessions", "completions"):
                assert ls.counters.get(key) == ns.counters.get(key), key
            if ls.counters.get("completions"):
                completion = lw.turn - 1
            else:
                assert lb._sim.checkpoint_state() == nb._sim.checkpoint_state()
    assert completion == L.SESSIONS_TO_COMPLETE      # formed in turn 1, a session every turn
    ls, ns = arms["learn"][0].livelihoods.learning_cohorts, arms["no_learning"][0].livelihoods.learning_cohorts
    assert ls.counters["capability_changes"] == ls.counters["completions"] > 0
    assert ns.counters.get("capability_changes", 0) == 0 and ns.counters.get("skill_granted", 0) == 0
    graduates = {g.agent_id: g for g in ls.graduates if g.completed_turn == completion}
    controls = {g.agent_id: g for g in ns.graduates if g.completed_turn == completion}
    assert set(graduates) == set(controls)
    for aid, g in graduates.items():
        c = controls[aid]
        assert g.skill_before == c.skill_before == c.skill_after
        assert g.skill_after == pytest.approx(min(1.0, g.skill_before + L.COMPLETION_GAIN))
    # Two turns later: the graduates still practising the learned trade carry
    # the extra skill and the purpose need reads it.
    la, na = _agents(arms["learn"][1]._sim), _agents(arms["no_learning"][1]._sim)
    ln, nn = _needs(arms["learn"][1]._sim), _needs(arms["no_learning"][1]._sim)
    practising = [aid for aid, g in graduates.items() if aid in la and aid in na
                  and la[aid]["occupation"] == na[aid]["occupation"] == g.occupation]
    assert practising
    for aid in practising:
        assert la[aid]["skill"] > na[aid]["skill"]
        assert ln[aid]["purpose"] > nn[aid]["purpose"]
    # A graduate who has left the academy's region keeps the learned skill.
    moved = [aid for aid in practising if la[aid]["region"] != graduates[aid].region]
    assert moved and all(la[aid]["skill"] > na[aid]["skill"] for aid in moved)
    for _, bridge, _ in arms.values():
        bridge.close()


def test_no_teacher_means_no_seat_no_cost_and_no_progress():
    world, bridge, region = _academy_world()
    _turn(world, bridge, region)                     # turn 0: the academy buys supplies
    rows = pa.record_batch(bridge._sim.get_snapshot()).to_pylist()
    scholars = [r["id"] for r in rows if r["region"] == region and r["occupation"] == 3]
    assert scholars
    bridge._sim.queue_targeted_deaths(scholars)      # every teacher dies at the start of the tick
    state = _turn(world, bridge, region)
    teaching = next(r for r in world.scholarship.learning_services.teaching_receipts if r.seat_id == 0)
    assert teaching.work_requested > 0 and teaching.work_delivered == 0
    r = state.frame[0]
    assert r.reserved and r.attended == [] and r.no_seat == r.reserved
    assert not r.session and r.no_session_reason == "no_teacher" and r.income_charged == 0.0
    assert all(m.attended == 0 for m in state.cohorts[0].members)
    bridge.close()


def test_no_student_time_reserves_nobody(monkeypatch):
    world, bridge, region = _academy_world()
    _turn(world, bridge, region)
    state = _turn(world, bridge, region)
    members = [m.agent_id for m in state.cohorts[0].members]
    assert all(m.attended == 1 for m in state.cohorts[0].members)
    original = L.before_agent_tick

    def other_work_first(world, agent_bridge, economy_result):
        # Another consumer (a workshop crew) already holds everyone this turn.
        agent_bridge._sim.reserve_work(world.turn, 0, [(aid, 0.2) for aid in members])
        return original(world, agent_bridge, economy_result)

    monkeypatch.setattr(L, "before_agent_tick", other_work_first)
    state = _turn(world, bridge, region)
    r = state.frame[0]
    assert r.reserved == [] and r.unavailable == {"assigned": len(members)}
    assert r.no_session_reason == "no_available_member" and r.income_charged == 0.0
    assert all(m.attended == 1 and m.absent_streak == 1 for m in state.cohorts[0].members)
    bridge.close()


def test_interrupted_cohort_member_death():
    world, bridge, region = _academy_world()
    _turn(world, bridge, region)
    state = _turn(world, bridge, region)
    victim = state.cohorts[0].members[0].agent_id
    bridge._sim.queue_targeted_deaths([victim])
    state = _turn(world, bridge, region)
    assert victim in state.frame[0].absent and victim not in state.frame[0].attended
    state = _turn(world, bridge, region)
    assert state.frame[0].exited.get("died") == [victim]
    member = next(m for m in state.cohorts[0].members if m.agent_id == victim)
    assert (member.status, member.exit_reason, member.attended) == ("exited", "died", 1)
    assert all(m.attended == 3 for m in state.cohorts[0].members if m.status == "active")
    bridge.close()


def test_replacement_academy_starts_a_new_cohort_without_carrying_progress():
    from chronicler.scholarship_state import ACADEMY, Seat
    world, bridge, region = _academy_world()
    _turn(world, bridge, region)
    state = _turn(world, bridge, region)
    old = state.cohorts[0]
    seat = world.scholarship.seats[0]
    # Declared replacement: the academy falls and its ruler founds another
    # in the same region (not a simulated sack).
    seat.fallen_turn = world.turn
    world.scholarship.seats.append(Seat(region=region, kind=ACADEMY, name="Second Academy",
                                        founded_turn=world.turn, founder=seat.lord, lord=seat.lord))
    state = _turn(world, bridge, region)
    closed = next(c for c in state.archive if c.cohort_id == old.cohort_id)
    assert closed.closed_reason == "academy_lost"
    assert all(m.exit_reason == "academy_lost" and m.attended == 1 for m in closed.members)
    for _ in range(3):
        if state.cohorts:
            break
        state = _turn(world, bridge, region)
    new = state.cohorts[0]
    assert new.cohort_id > old.cohort_id and new.seat_id == 1 and new.seat_name == "Second Academy"
    assert all(m.attended <= 1 for m in new.members)
    bridge.close()


def test_open_cohort_resumes_exactly_from_a_checkpoint(tmp_path):
    world, bridge, region = _academy_world()
    for _ in range(3):
        state = _turn(world, bridge, region)
    assert state.cohorts and state.cohorts[0].sessions == 2
    assert not bridge._sim.has_pending_learning_attendance() and state._pending is None
    path = tmp_path / "cohort.ckpt"
    write_checkpoint(path, RunState(world=world, agent_bridge=bridge, memories={}, history=[],
                                    chronicle_entries=[], era_reflections={}, pending_injections=[],
                                    start_turn=0, seed=world.seed, num_turns=8))
    loaded = read_checkpoint(path)
    assert loaded.exact
    restored, resumed = loaded.state.world, loaded.state.agent_bridge
    assert restored.livelihoods.learning_cohorts == state
    rng = random.getstate()
    for _ in range(3):
        _turn(world, bridge, region)
    after = random.getstate()
    random.setstate(rng)
    for _ in range(3):
        _turn(restored, resumed, region)
    assert random.getstate() == after
    assert restored.model_dump_json() == world.model_dump_json()
    assert resumed._sim.checkpoint_state() == bridge._sim.checkpoint_state()
    assert restored.livelihoods.learning_cohorts.counters.get("completions", 0) > 0
    bridge.close()
    resumed.close()


def _run(tmp_path, *extra, seed=2, turns=30):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    args = _build_parser().parse_args([
        "--seed", str(seed), "--turns", str(turns), "--civs", "4", "--regions", "8",
        "--agents", "hybrid", "--simulate-only", "--cities", "--scholarship", "--techniques",
        "--academy-services", "--output", str(tmp_path / "chronicle.md"),
        "--state", str(tmp_path / "state.json"), *extra])
    execute_run(args)
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    bundle["metadata"].pop("generated_at")
    return bundle


def test_feature_off_identity_and_dormant_switch(tmp_path):
    off = _run(tmp_path / "off")
    disabled = _run(tmp_path / "disabled", "--no-learning-cohorts")
    assert off == disabled                     # never enabled: no container, key or flag
    assert all("livelihoods" not in snap for snap in off["history"])
    on = _run(tmp_path / "on", "--learning-cohorts")
    assert len(on["history"]) == len(off["history"])
    for a, b in zip(off["history"], on["history"], strict=True):
        b = dict(b)
        record = b.pop("livelihoods")["learning_cohorts"]
        assert record["stage"] == "L5" and record["mode"] == "learn"
        assert record["counters"].get("cohorts_formed", 0) == 0     # this world never forms one
        assert a == b
