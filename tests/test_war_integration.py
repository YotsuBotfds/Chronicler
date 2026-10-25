"""Multi-turn campaign integration: invariants, determinism, save/load, mode coverage."""
from __future__ import annotations

import argparse
import json

import pytest

from chronicler.bundle_codec import load_bundle
from chronicler.action_engine import ActionEngine
from chronicler.models import WorldState
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world

CAMPAIGN_EVENT_TYPES = {"war_declared", "army_raised", "siege_begun", "occupation", "annexation",
                        "peace_treaty", "liberation", "occupation_revolt", "army_destroyed",
                        "army_disbanded", "war_ended", "general_fallen", "civ_conquered"}


def _world(seed: int, campaigns: bool = True) -> WorldState:
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.campaigns_enabled = campaigns
    return world


def _advance(world: WorldState, turns: int, *, bridge=None, check=None) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn, agent_bridge=bridge)
        if check is not None:
            check(world)
    return world


def _invariants(world: WorldState) -> None:
    state = world.war_state
    region_names = {r.name for r in world.regions}
    war_keys = {w.war_key for w in state.wars}
    for army in state.armies:
        assert army.region in region_names
        assert army.soldiers >= 0 and army.morale in range(0, 1001)
        assert 0 <= army.rations <= army.soldiers * 6
        assert world.civ_map[army.civ].regions, "dead civs keep no armies"
        if army.roster:
            assert len(army.roster) == army.soldiers
    occupied = {o.region: o for o in state.occupations}
    assert len(occupied) == len(state.occupations), "one occupation per region"
    for region in world.regions:
        occ = occupied.get(region.name)
        assert region.occupied_by == (occ.occupier if occ else None)
        if occ:
            assert occ.owner == region.controller
            assert occ.war_key in war_keys
            assert 0 <= occ.unrest <= 1000
    # Records may trail active_wars by one turn (a congress or Phase 10
    # politics can end a war after the campaign tick; the next tick closes it).
    for war in state.wars:
        assert -100 <= war.score <= 100
    for region in world.regions:
        if region.controller is not None:
            assert region.name in world.civ_map[region.controller].regions


def _fingerprint(world: WorldState) -> str:
    return json.dumps({
        "war": world.war_state.model_dump(mode="json"),
        "control": [(r.name, r.controller, r.occupied_by, r.population) for r in world.regions],
        "events": [e.model_dump(mode="json") for e in world.events_timeline],
        "named": [e.model_dump(mode="json") for e in world.named_events],
        "civs": [(c.name, c.military, c.treasury, c.stability, list(c.regions)) for c in world.civilizations],
    }, sort_keys=True)


def test_multi_turn_campaigns_fight_occupy_and_make_peace():
    totals = {"battles": 0, "occupations": 0, "treaties": 0, "sieges": 0, "armies": 0}
    for seed in (3, 11, 42):
        world = _advance(_world(seed), 80, check=_invariants)
        events = {e.event_type for e in world.events_timeline}
        totals["battles"] += len(world.war_state.battles)
        totals["occupations"] += sum(e.event_type == "occupation" for e in world.events_timeline)
        totals["sieges"] += sum(e.event_type == "siege_begun" for e in world.events_timeline)
        totals["treaties"] += sum(t.kind != "external" for t in world.war_state.treaties)
        totals["armies"] += sum(e.event_type == "army_raised" for e in world.events_timeline)
        assert events & CAMPAIGN_EVENT_TYPES
        # Every battle is narrated as a war event with a classic outcome token.
        war_events = [e for e in world.events_timeline if e.event_type == "war"
                      and any(t in e.description for t in ("attacker_wins", "defender_wins", "stalemate"))]
        assert len(war_events) == len(world.war_state.battles)
    assert all(v > 0 for v in totals.values()), totals


def test_campaigns_are_deterministic_for_the_same_seed():
    a = _advance(_world(42), 60)
    b = _advance(_world(42), 60)
    assert _fingerprint(a) == _fingerprint(b)
    assert a.war_state.battles  # the comparison covered real fighting


def test_save_load_round_trip_continues_identically(tmp_path):
    straight = _advance(_world(11), 50)
    first = _advance(_world(11), 25)
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.war_state == first.war_state
    assert resumed.campaigns_enabled
    _advance(resumed, 25)
    assert resumed.war_state.model_dump() == straight.war_state.model_dump()
    assert [(r.controller, r.occupied_by) for r in resumed.regions] == \
        [(r.controller, r.occupied_by) for r in straight.regions]


def test_feature_off_never_touches_campaign_state(monkeypatch):
    import chronicler.war.runtime as runtime

    def forbidden(*args, **kwargs):
        raise AssertionError("campaign layer invoked while disabled")

    monkeypatch.setattr(runtime, "tick_campaigns", forbidden)
    monkeypatch.setattr(runtime, "declare_or_press_war", forbidden)
    world = _advance(_world(42, campaigns=False), 40)
    assert world.war_state.model_dump() == WorldState(name="x", seed=0).war_state.model_dump()
    assert all(r.occupied_by is None for r in world.regions)
    assert not {e.event_type for e in world.events_timeline} & CAMPAIGN_EVENT_TYPES


def test_snapshot_campaign_field_is_dormant_when_off():
    from chronicler.models import TurnSnapshot
    snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert "campaign" not in snap.model_dump()
    snap.campaign = {"armies": []}
    assert snap.model_dump()["campaign"] == {"armies": []}


def _cli_args(tmp_path, *, campaigns, turns=12, agents="off"):
    return argparse.Namespace(
        seed=42, turns=turns, civs=4, regions=8, output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, pause_every=None, simulate_only=True, agents=agents, campaigns=campaigns,
    )


def test_cli_flag_persists_and_bundle_carries_campaign_history(tmp_path):
    from chronicler.main import _build_parser, execute_run
    assert _build_parser().parse_args(["--campaigns"]).campaigns is True
    assert _build_parser().parse_args(["--no-campaigns"]).campaigns is False
    assert _build_parser().parse_args([]).campaigns is None
    execute_run(_cli_args(tmp_path, campaigns=True))
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["campaigns_enabled"] is True
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    assert all("campaign" in snap for snap in bundle["history"])
    assert set(bundle["history"][-1]["campaign"]) == {"armies", "battles", "occupations", "wars"}
    assert "war_state" in bundle["world_state"]


def test_new_worlds_default_to_campaigns_and_resume_keeps_saved_setting(tmp_path):
    from chronicler.main import execute_run
    from chronicler.war.params import CAMPAIGNS_DEFAULT_FOR_NEW_WORLDS
    fresh = tmp_path / "fresh"
    execute_run(_cli_args(fresh, campaigns=None, turns=3))
    assert json.loads((fresh / "state.json").read_text())["campaigns_enabled"] is CAMPAIGNS_DEFAULT_FOR_NEW_WORLDS
    legacy = tmp_path / "legacy"
    execute_run(_cli_args(legacy, campaigns=False, turns=3))
    assert json.loads((legacy / "state.json").read_text())["campaigns_enabled"] is False
    resumed = _cli_args(legacy, campaigns=None, turns=5)
    resumed.resume = str(legacy / "state.json")
    resumed.state = str(legacy / "resumed.json")
    execute_run(resumed)
    assert json.loads((legacy / "resumed.json").read_text())["campaigns_enabled"] is False
    # States saved before M60 have no flag at all and load with it off.
    raw = json.loads((legacy / "state.json").read_text())
    raw.pop("campaigns_enabled")
    raw.pop("war_state")
    assert WorldState.model_validate(raw).campaigns_enabled is False


# --- agent modes (native) ------------------------------------------------------------

def _hybrid(seed: int, mode: str = "hybrid"):
    pytest.importorskip("chronicler_agents")
    from chronicler.agent_bridge import AgentBridge
    world = _world(seed)
    world.agent_mode = mode
    bridge = AgentBridge(world, mode=mode)
    return world, bridge


def _roster_check(bridge):
    def check(world):
        live = set(bridge.get_snapshot().column("id").to_pylist())
        for army in world.war_state.armies:
            assert len(army.roster) == army.soldiers
            assert all(aid in live for aid, _ in army.roster)
        assert bridge._sim.pending_targeted_death_count() == 0
        _invariants(world)
    return check


@pytest.mark.native
@pytest.mark.parametrize("mode", ["hybrid", "demographics-only"])
def test_agent_mode_enlists_real_agents_and_reconciles_deaths(mode):
    world, bridge = _hybrid(42, mode)
    _advance(world, 30, bridge=bridge, check=_roster_check(bridge))
    raised = [e for e in world.events_timeline if e.event_type == "army_raised"]
    assert raised
    assert world.war_state.battles or world.war_state.armies


@pytest.mark.native
def test_hybrid_campaigns_are_deterministic():
    w1, b1 = _hybrid(7)
    w2, b2 = _hybrid(7)
    _advance(w1, 25, bridge=b1)
    _advance(w2, 25, bridge=b2)
    assert _fingerprint(w1) == _fingerprint(w2)


@pytest.mark.native
def test_hybrid_resume_rebinds_rosters_to_new_pool(tmp_path):
    from chronicler.agent_bridge import AgentBridge
    world, bridge = _hybrid(42)
    _advance(world, 12, bridge=bridge)
    path = tmp_path / "state.json"
    world.save(path)
    resumed = WorldState.load(path)
    resumed.agent_mode = "hybrid"
    fresh = AgentBridge(resumed, mode="hybrid")
    _advance(resumed, 6, bridge=fresh, check=_roster_check(fresh))
