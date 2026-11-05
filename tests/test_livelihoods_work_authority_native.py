"""Adversarial checks of the one-work-commitment authority on the real extension.

Derived from the contracts in ``docs/integration/workshops.md`` (one native
work registry; crews exclude army rosters; observe mode employs nobody and
leaves the trajectory unchanged), ``learning-cohorts.md`` and
``workshop-finance.md``. Native pools, registry, rosters and ticks are real.
"""
from __future__ import annotations

import pyarrow as pa
import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native


def _run(tmp_path, *extra, seed=7, turns=30):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    args = _build_parser().parse_args([
        "--seed", str(seed), "--turns", str(turns), "--civs", "4", "--regions", "8",
        "--agents", "hybrid", "--simulate-only",
        "--output", str(tmp_path / "chronicle.md"), "--state", str(tmp_path / "state.json"), *extra])
    execute_run(args)
    return load_bundle(tmp_path / "chronicle_bundle.json")


def test_army_recruitment_never_drafts_a_person_already_holding_work_this_turn():
    """Workshop crews are reserved in Phase 2, before Phase 5 actions and M60
    campaigns raise armies. Military service is a work commitment: a draft in
    the same turn must not take someone the shared registry already holds
    (otherwise one person is a paid crew member and a soldier for one turn)."""
    from chronicler.agent_bridge import AgentBridge
    from chronicler.war.armies import select_recruits
    from chronicler.war.common import build_context
    from chronicler.world_gen import generate_world

    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    sim = bridge._sim
    rows = pa.record_batch(sim.get_snapshot()).to_pylist()
    civ_index = next(i for i, c in enumerate(world.civilizations)
                     if any(r["civ_affinity"] == i and r["occupation"] == 0 and r["age"] >= 20 for r in rows))
    civ = world.civilizations[civ_index]
    farmers = sorted(r["id"] for r in rows if r["civ_affinity"] == civ_index and r["occupation"] == 0
                     and r["age"] >= 20 and world.regions[r["region"]].controller == civ.name)
    assert len(farmers) >= 4
    held = farmers[:4]
    # The same registry `plan_workshop_crews(..., turn)` reserves crews in.
    sim.reserve_work(world.turn, 0, [(aid, 0.3) for aid in held])
    assert sorted(r[0] for r in sim.work_reservations(world.turn)) == held
    world.livelihoods = __import__("chronicler.livelihoods_state", fromlist=["LivelihoodsState"]).LivelihoodsState()
    ctx = build_context(world, None, bridge=bridge)
    staging = world.regions[next(r["region"] for r in rows if r["id"] == held[0])].name
    recruits = select_recruits(ctx, civ, staging, len(rows))
    assert recruits, "the civilization must have recruitable agents"
    drafted = {aid for aid, _ in recruits}
    assert not drafted & set(held), "a registry holder was drafted in the turn of its work commitment"
    # Without a commitment the same people are draftable (the check is not vacuous).
    assert set(farmers[4:]) & drafted


def test_observe_mode_reserves_nobody_in_the_shared_work_registry(tmp_path, monkeypatch):
    """Observe mode 'employs nobody ... and leaves the trajectory unchanged'.
    Its resolved crews are available, not employed (``allocated`` 0), so they
    must not hold this turn's work commitment: a registry entry would exclude
    them from L5 learning and teaching and change trajectories with
    ``--learning-cohorts``."""
    from chronicler import workshops as W
    seen = {"crew": 0, "held": 0}
    original = W.finish_phase2

    def checked_finish(world, economy_result, agent_bridge, acc):
        plan = world.livelihoods.workshops._plan
        seen["crew"] += sum(len(p.row["crew"]) for p in plan.sites)
        seen["held"] += len(agent_bridge._sim.work_reservations(world.turn))
        return original(world, economy_result, agent_bridge, acc)

    monkeypatch.setattr(W, "finish_phase2", checked_finish)
    _run(tmp_path, "--workshops", "--workshop-mode", "observe", turns=20)
    assert seen["crew"] > 0
    assert seen["held"] == 0, "observe-mode crews hold work reservations"


def test_operate_crews_hold_one_commitment_against_learners_rosters_and_paid_work(tmp_path, monkeypatch):
    """Real run with the per-person work consumers on (workshop crews, rural
    health care, academy teaching, L5 learners, relocation, food allocation;
    campaigns are on by default). Immediately before each native agent tick
    (after L5 reserved its learners and teaching was prepared): the registry
    has no duplicate and no conflict with health or teaching; no learner is
    on an army roster or a crew; every crew member holds exactly one workshop
    reservation. After each successful tick the registry is empty."""
    from chronicler.agent_bridge import AgentBridge
    stats = {"ticks": 0, "crew": 0, "learners": 0}
    original = AgentBridge.tick_agents

    def checked(self, world, *args, **kwargs):
        sim, turn = self._sim, world.turn
        held = sim.work_reservations(turn)
        ids = [row[0] for row in held]
        assert len(ids) == len(set(ids))
        assert sim.work_reservation_conflicts(turn) == []
        crew = {aid for aid, category, _ in held if category == 0}
        learners = {aid for aid, category, _ in held if category == 1}
        enlisted = {aid for army in world.war_state.armies for aid, _ in army.roster}
        assert not learners & enlisted and not crew & learners
        planned = {aid for r in world.livelihoods.workshops.frame if r.turn == turn for aid in r.crew}
        assert crew <= planned
        stats["ticks"] += 1
        stats["crew"] += len(crew)
        stats["learners"] += len(learners)
        result = original(self, world, *args, **kwargs)
        assert sim.work_reservations(turn) == []
        return result

    monkeypatch.setattr(AgentBridge, "tick_agents", checked)
    bundle = _run(tmp_path, "--workshops", "--health-care", "--scholarship", "--techniques",
                  "--academy-services", "--learning-cohorts", "--relocation-costs", "--food-allocation",
                  seed=1, turns=40)
    assert len(bundle["history"]) == 40
    assert stats["ticks"] == 40 and stats["crew"] > 0


def _academy_world():
    """The L5 native tests' declared academy (seed 42), with learning cohorts on."""
    from chronicler.agent_bridge import AgentBridge
    from chronicler.cities import set_cities_enabled
    from chronicler.learning_services import set_learning_services_enabled
    from chronicler.livelihoods import configure_livelihoods
    from chronicler.main import _build_parser
    from chronicler.scholarship_state import ACADEMY, ScholarshipState, Seat
    from chronicler.world_gen import generate_world

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
    configure_livelihoods(world, _build_parser().parse_args(["--learning-cohorts"]), agent_mode="hybrid")
    return world, bridge, region


def _academy_turn(world, bridge, region):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn_result
    goods = world.regions[region].stockpile.goods
    goods["crafts"] = goods.get("crafts", 0.0) + 20.0
    engine = ActionEngine(world)
    run_turn_result(world, lambda c, w: engine.select_action(c, seed=w.seed),
                    lambda w, events: "", seed=world.seed + world.turn, agent_bridge=bridge)
    return world.livelihoods.learning_cohorts


def test_a_failed_agent_tick_releases_the_learners_work_commitment(monkeypatch):
    """Contract (failed-tick rollback): when the agent tick raises, pending
    reservations are released and nothing is charged. L5 reserves its
    learners in the shared registry and installs a native attendance plan
    immediately before the tick; academy services already cancel their
    teaching reservation on failure. The learners' attendance and registry
    rows must be released the same way, and no Python plan may stay pending."""
    from chronicler.agent_bridge import AgentBridge
    world, bridge, region = _academy_world()
    _academy_turn(world, bridge, region)                  # supplies bought
    state = _academy_turn(world, bridge, region)          # cohort formed and attended
    assert state.cohorts and state.cohorts[0].members
    sim = bridge._sim
    seen = {}

    def failing_tick(self, world, *args, **kwargs):
        seen["held"] = sim.work_reservations(world.turn)
        seen["pending"] = sim.has_pending_learning_attendance()
        raise RuntimeError("injected agent tick failure")

    monkeypatch.setattr(AgentBridge, "tick_agents", failing_tick)
    turn = world.turn
    with pytest.raises(RuntimeError, match="injected agent tick failure"):
        _academy_turn(world, bridge, region)
    assert seen["pending"] and any(category == 1 for _, category, _ in seen["held"])
    assert not sim.has_pending_teaching_work()            # academy services' precedent
    assert not sim.has_pending_learning_attendance(), "learning attendance left pending after a failed tick"
    assert sim.work_reservations(turn) == [], "learners still hold work after a failed tick"
    assert state._pending is None
    bridge.close()
