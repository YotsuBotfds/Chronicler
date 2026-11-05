"""RS0 recovery-skills groundwork on the real compiled extension.

The appended registry categories and transfer purposes, ``extend_paid_work``
merged into an L6a-style install and consumed by the real wealth phase, the
crew planner's keyword-only ``priority_ids`` (direct and through the
``workshops`` seam) and the inertness of the five stub switches in a real
hybrid run.
"""
from __future__ import annotations

import importlib

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

RS_FLAGS = ["--apprenticeship", "--repair-projects", "--veteran-reintegration", "--remittances",
            "--clearing-protection"]


def test_the_extension_is_the_compiled_build_with_the_rs0_methods():
    compiled = importlib.import_module("chronicler_agents.chronicler_agents")
    assert compiled.__file__.endswith((".so", ".pyd"))
    from chronicler_agents import AgentSimulator
    assert isinstance(AgentSimulator, type)
    for name in ("extend_paid_work", "install_paid_work", "plan_workshop_crews", "reserve_work"):
        assert callable(getattr(AgentSimulator, name)), name
    assert AgentSimulator.wealth_transfer_purposes() == [
        "workshop_wage", "relocation_fare", "apprentice_stipend", "repair_wage", "remittance"]


@pytest.fixture
def live():
    from chronicler.action_engine import ActionEngine
    from chronicler.agent_bridge import AgentBridge
    from chronicler.simulation import run_turn
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    engine = ActionEngine(world)

    def turn():
        run_turn(world, lambda c, w: engine.select_action(c, seed=w.seed), lambda w, e: "",
                 seed=world.seed, agent_bridge=bridge)

    turn()
    return world, bridge, turn


def _ids(sim):
    return sim.get_snapshot().column("id").to_pylist()


def test_appended_categories_share_the_registry_and_purposes_transfer(live):
    world, bridge, _ = live
    sim = bridge._sim
    a, b, c = _ids(sim)[:3]
    t = world.turn
    sim.reserve_work(t, 2, [(a, 0.25)])            # apprentice
    sim.reserve_work(t, 3, [(b, 0.5)])             # repair
    assert sorted(sim.work_reservations(t)) == sorted([(a, 2, 0.25), (b, 3, 0.5)])
    for category in (0, 1, 2, 3):
        with pytest.raises(ValueError, match="already holds work"):
            sim.reserve_work(t, category, [(a, 0.1)])
    with pytest.raises(ValueError, match="category"):
        sim.reserve_work(t, 4, [(c, 0.1)])
    assert sim.work_reservation_conflicts(t) == []
    for purpose in (2, 3, 4):
        out = sim.transfer_wealth(t, purpose, 0, [(c, 10)])
        assert out[0][2] == 10 and out[0][4] == 0
    with pytest.raises(ValueError, match="purpose"):
        sim.transfer_wealth(t, 5, 0, [(c, 10)])


def test_extend_paid_work_merges_refuses_and_is_consumed_once_by_the_tick(live):
    world, bridge, turn = live
    sim = bridge._sim
    a, b, c, d = _ids(sim)[:4]
    t = world.turn
    sim.reserve_work(t, 0, [(a, 0.3)])
    sim.reserve_work(t, 2, [(b, 0.25)])
    sim.reserve_work(t, 3, [(c, 0.5)])
    sim.install_paid_work(t, [(a, 0.3)])            # the L6a install comes first
    for rows, match in (([(b, 0.0)], "share"), ([(b, 0.2), (b, 0.1)], "duplicate"),
                        ([(4_000_000_000, 0.1)], "living"), ([(a, 0.1)], "already has"),
                        ([(b, 0.3)], "reservation"), ([(d, 0.1)], "reservation")):
        with pytest.raises(ValueError, match=match):
            sim.extend_paid_work(t, rows)
    with pytest.raises(ValueError, match="another turn"):
        sim.extend_paid_work(t + 1, [(b, 0.25)])
    sim.extend_paid_work(t, [(b, 0.25)])
    sim.extend_paid_work(t, [(c, 0.4)])
    with pytest.raises(ValueError, match="already has"):
        sim.extend_paid_work(t, [(c, 0.1)])
    with pytest.raises(ValueError, match="pending"):
        sim.install_paid_work(t, [(d, 0.1)])        # install keeps refusing a pending share
    turn()
    got = sim.take_paid_work_receipt()
    assert got is not None and got[0] == t
    rows = {aid: (share, ordinary, deducted) for aid, share, ordinary, deducted in got[1]}
    assert set(rows) <= {a, b, c}
    expected = {a: 0.3, b: 0.25, c: 0.4}
    for aid, (share, ordinary, deducted) in rows.items():
        assert share == pytest.approx(expected[aid])
        assert deducted == pytest.approx(share * ordinary, rel=1e-6)
    assert sim.take_paid_work_receipt() is None
    assert sim.work_reservations(t) == []           # the tick cleared the registry
    # Nothing pending now: an extension arms a fresh install for the next turn.
    t = world.turn
    sim.reserve_work(t, 3, [(d, 0.5)])
    sim.extend_paid_work(t, [(d, 0.5)])
    with pytest.raises(ValueError, match="pending"):
        sim.install_paid_work(t, [(d, 0.5)])
    assert sim.cancel_paid_work() is True and sim.cancel_paid_work() is False


def _run(tmp_path, *extra, seed=7, turns=40):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    args = _build_parser().parse_args([
        "--seed", str(seed), "--turns", str(turns), "--civs", "4", "--regions", "8",
        "--agents", "hybrid", "--simulate-only",
        "--output", str(tmp_path / "chronicle.md"), "--state", str(tmp_path / "state.json"), *extra])
    execute_run(args)
    return load_bundle(tmp_path / "chronicle_bundle.json")


def test_priority_ids_reach_the_native_planner_through_the_workshop_seam(tmp_path, monkeypatch):
    """Veteran priority lists (here: each site's default crew, reversed, after
    an unknown id) come first in the listed order; the keyword is accepted
    only by name and duplicates are refused."""
    from chronicler import veteran_reintegration as VR
    from chronicler import workshops as W
    held = {"sim": None}
    expected: dict[int, list[int]] = {}
    seen = {"sites": 0, "reordered": 0}
    prepare, finish = W.prepare_phase2, W.finish_phase2

    def checked_prepare(world, region_input, agent_bridge, snapshot, acc):
        held["sim"] = agent_bridge._sim
        expected.clear()
        return prepare(world, region_input, agent_bridge, snapshot, acc)

    def priority(world, region):
        sim = held["sim"]
        site = next(s for s in world.livelihoods.workshops.sites if s.region == region)
        request = [(site.site, site.region, site.settlement_id, 0.2, 8)]
        base = list(sim.plan_workshop_crews(request, W._enlisted(world))[0][8])   # read-only (no turn)
        listed = list(reversed(base))
        if base:
            assert list(sim.plan_workshop_crews(request, W._enlisted(world), priority_ids=listed)[0][8]) == listed
            with pytest.raises(TypeError):
                sim.plan_workshop_crews(request, W._enlisted(world), None, listed)
            with pytest.raises(ValueError, match="duplicate"):
                sim.plan_workshop_crews(request, W._enlisted(world), priority_ids=[base[0], base[0]])
        expected[region] = listed
        return [4_000_000_000, *listed]

    def checked_finish(world, economy_result, agent_bridge, acc):
        for site_plan in world.livelihoods.workshops._plan.sites:
            row = site_plan.row
            assert row["crew"] == expected[row["region"]]
            seen["sites"] += 1
            seen["reordered"] += len(row["crew"]) >= 2
        return finish(world, economy_result, agent_bridge, acc)

    monkeypatch.setattr(W, "prepare_phase2", checked_prepare)
    monkeypatch.setattr(W, "finish_phase2", checked_finish)
    monkeypatch.setattr(VR, "priority_ids", priority)
    _run(tmp_path, "--workshops", "--workshop-mode", "observe", "--veteran-reintegration", turns=30)
    assert seen["sites"] > 0 and seen["reordered"] > 0


#: Packages whose lane replaced the inert RS0 stub.
IMPLEMENTED = {"clearing_protection", "remittances", "veteran_reintegration"}


def test_the_stub_switches_leave_a_real_operating_run_unchanged(tmp_path):
    # Only switches whose lane has not replaced the inert RS0 stub yet.
    rs = tuple(name for name in ("apprenticeship", "repair_projects", "veteran_reintegration", "remittances",
                                 "clearing_protection") if name not in IMPLEMENTED)
    if not rs:
        pytest.skip("every recovery-skills switch is implemented; each package has its own identity test")
    base = _run(tmp_path / "base", "--workshops", turns=40)
    stubs = _run(tmp_path / "stubs", "--workshops", *[f"--{n.replace('_', '-')}" for n in rs], turns=40)
    assert len(base["history"]) == len(stubs["history"])
    for a, b in zip(base["history"], stubs["history"], strict=True):
        b = dict(b)
        livelihoods = dict(b.pop("livelihoods"))
        a = dict(a)
        a_livelihoods = a.pop("livelihoods")
        for name in rs:
            assert livelihoods.pop(name)["stage"] == "RS0"
        assert livelihoods == a_livelihoods
        assert a == b
    ws = dict(stubs["world_state"])
    saved = dict(ws.pop("livelihoods"))
    base_ws = dict(base["world_state"])
    base_saved = base_ws.pop("livelihoods")
    for name in rs:
        assert saved.pop(name)["enabled"] is True
    assert saved == base_saved and ws == base_ws
