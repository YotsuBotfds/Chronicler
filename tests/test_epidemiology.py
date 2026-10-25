"""Regional SEIRS epidemiology: dynamics, introductions, deaths, responses, switch."""
from __future__ import annotations

import argparse
import copy
import json
import math

import pytest

from chronicler.bundle_codec import load_bundle
import chronicler.contact_ledger as cl
import chronicler.epidemiology as ep
from chronicler.action_engine import ActionEngine
from chronicler.models import Event, TurnSnapshot, WorldState
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world


def _world(seed: int = 42, *, epidemics: bool = True, ledger: bool = True) -> WorldState:
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.campaigns_enabled = True
    cl.set_contact_ledger_enabled(world, ledger)
    ep.set_epidemiology_enabled(world, epidemics)
    return world


def _advance(world: WorldState, turns: int, *, bridge=None, each=None) -> WorldState:
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, ev: "", seed=world.seed + world.turn, agent_bridge=bridge)
        if each is not None:
            each(world)
    return world


def _row(world: WorldState, region: int, pathogen: int) -> ep.RegionInfection | None:
    for row in world.epidemics.rows:
        if row.region == region and row.pathogen == pathogen:
            return row
    return None


def _shares_ok(world: WorldState) -> None:
    for row in world.epidemics.rows:
        for value in (row.s, row.e, row.i, row.r):
            assert 0.0 <= value <= 1.0
        assert abs(row.s + row.e + row.i + row.r - 1.0) < 1e-8
        assert row.n > 0  # rows of empty regions are dropped


# --- registry and the within-region recursion -------------------------------------

def test_registry_order_is_identity_and_parameters_are_probabilities():
    assert [p.name for p in ep.PATHOGENS] == ["plague", "pox", "fever", "flux", "pestilence"]
    assert ep.PATHOGEN_INDEX == {p.name: i for i, p in enumerate(ep.PATHOGENS)}
    for p in ep.PATHOGENS:
        assert p.r0 > 1.0
        for prob in (p.onset, p.recovery, p.cfr, p.escape):
            assert 0.0 <= prob <= 1.0
        assert p.immunity_turns >= 0 and p.mutation >= 0 and p.spillover >= 0
    # The black-swan pestilence never emerges on its own.
    assert ep.PATHOGENS[ep.PESTILENCE].spillover == 0.0


def test_step_conserves_people_and_burns_out_like_seir():
    pathogen = ep.PATHOGENS[ep.PLAGUE]
    row = ep.RegionInfection(region=0, pathogen=ep.PLAGUE, n=1000)
    ep._seed(row, 10.0, cause="", virgin=False)
    dead = cases = 0.0
    prevalence = []
    for _ in range(30):
        before = row.s + row.e + row.i + row.r
        share = ep._step(row, pathogen, (1.0, 1.0, False))
        # Each recursion step moves people between compartments or kills them.
        assert row.s + row.e + row.i + row.r + share == pytest.approx(before, abs=1e-12)
        dead += share
        cases += row.cases / row.n
        prevalence.append(row.burden)
        total = row.s + row.e + row.i + row.r
        row.s, row.e, row.i, row.r = (v / total for v in (row.s, row.e, row.i, row.r))
    peak = prevalence.index(max(prevalence))
    assert 0 < peak < 6, "an epidemic rises, peaks and falls within a few turns"
    assert min(prevalence[8:20]) < 1e-4, "then it burns out (the tick ends it below half a person)"
    # Final size of an SEIR epidemic with R0 = 2.4 is about 0.88 (immunity
    # wanes over 30 turns, so a second wave starts at the end of the window).
    assert 0.8 < cases < 1.2
    assert dead == pytest.approx(cases * pathogen.cfr, rel=0.05)


def test_famine_and_crowding_raise_susceptibility_and_fatality():
    world = _world()
    region = world.regions[0]
    region.carrying_capacity = 100
    region.population = 50
    region.famine_cooldown = 0
    assert ep._modifiers(region) == (1.0, 1.0, False)
    region.population = 130  # 1.3x capacity
    susc, cfr, famine = ep._modifiers(region)
    assert susc == pytest.approx(1.0 + ep.CROWDING_SUSCEPTIBILITY * 0.5) and cfr == 1.0
    region.famine_cooldown = 3
    susc2, cfr2, famine2 = ep._modifiers(region)
    assert famine2 and susc2 == pytest.approx(susc + ep.FAMINE_SUSCEPTIBILITY)
    assert cfr2 == pytest.approx(1.0 + ep.FAMINE_CFR)


# --- whole runs: conservation, determinism, resume ----------------------------------

def test_seirs_conservation_and_death_accounting_over_a_run():
    world = _world(42)
    seen_active = []
    recorded = []

    def check(w):
        _shares_ok(w)
        recorded.append(sum(d for _, _, d in w.epidemics.last_deaths))
        seen_active.append(bool(ep.active_region_names(w)))

    _advance(world, 120, each=check)
    assert any(seen_active), "the run has epidemics"
    assert world.epidemics.deaths_total == sum(recorded) > 0
    assert world.epidemics.last_tick_turn == 119
    # Rows are sorted by (region, pathogen) and unique.
    keys = [(r.region, r.pathogen) for r in world.epidemics.rows]
    assert keys == sorted(set(keys))


def test_runs_are_deterministic():
    a = _advance(_world(11), 80)
    b = _advance(_world(11), 80)
    assert a.model_dump_json() == b.model_dump_json()
    assert a.epidemics.deaths_total > 0


def test_save_load_mid_epidemic_resumes_identically(tmp_path):
    turns = 70
    active_after: list[bool] = []
    straight = _advance(_world(5), turns,
                        each=lambda w: active_after.append(any(r.e + r.i > 0 for r in w.epidemics.rows)))
    split = next(t + 1 for t, active in enumerate(active_after) if t >= 10 and active)
    assert split < turns, "an outbreak is running at some turn boundary"
    first = _advance(_world(5), split)
    assert any(r.e + r.i > 0 for r in first.epidemics.rows), "saved mid-epidemic"
    path = tmp_path / "state.json"
    first.save(path)
    resumed = WorldState.load(path)
    assert resumed.epidemics == first.epidemics
    _advance(resumed, turns - split)
    assert resumed.epidemics.model_dump() == straight.epidemics.model_dump()
    assert resumed.model_dump_json() == straight.model_dump_json()


# --- the switch ------------------------------------------------------------------------

def test_feature_off_never_runs_epidemiology_code(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("epidemiology invoked while disabled")

    for name in ("tick_epidemics", "seed_pandemic", "seed_injection", "snapshot_summary",
                 "mmp_labour_relief", "_initialize"):
        monkeypatch.setattr(ep, name, forbidden)
    world = _advance(_world(42, epidemics=False), 60)
    assert world.epidemics is None
    assert "epidemics" not in world.model_dump(mode="json")
    # The hazard plague still runs with the switch off.
    assert any(e.event_type == "plague" for e in world.events_timeline)
    assert not any(e.event_type in ("epidemic", "epidemic_arrival", "quarantine")
                   for e in world.events_timeline)


def test_dormant_fields_are_omitted_and_old_saves_load():
    world = _world(epidemics=False)
    assert "epidemics" not in json.loads(world.model_dump_json())
    snap = TurnSnapshot(turn=1, civ_stats={}, region_control={}, relationships={})
    assert "epidemics" not in snap.model_dump()
    snap.epidemics = {"active": []}
    assert snap.model_dump()["epidemics"] == {"active": []}
    raw = json.loads(_world(epidemics=True).model_dump_json())
    assert raw["epidemics"]["rows"] == []
    raw.pop("epidemics")
    assert WorldState.model_validate(raw).epidemics is None
    assert not ep.epidemiology_enabled(object())


def test_switch_on_replaces_hazard_plague_and_m18_pandemic(monkeypatch):
    from chronicler.emergence import _apply_pandemic_origin
    from chronicler.simulation import apply_injected_event, phase_environment

    world = _world(3)
    world.event_probabilities["plague"] = 1.0  # a certain hazard plague, were it rolled
    events = phase_environment(world, seed=world.seed)
    assert not [e for e in events if e.event_type == "plague"]

    # Black swan: a novel strain of the great pestilence, not an M18 timer.
    monkeypatch.setattr("chronicler.emergence._count_trade_partners", lambda name, w: 3)
    out = _apply_pandemic_origin(world, world.seed)
    assert [e.event_type for e in out] == ["pandemic"]
    assert world.pandemic_state == []
    origin = next(i for i, r in enumerate(world.regions) if r.name == out[0].region)
    row = _row(world, origin, ep.PESTILENCE)
    assert row is not None and row.e > 0 and row.virgin
    assert row.cause == out[0].event_id
    assert world.epidemics.strains[ep.PESTILENCE] == 1

    # Injection seeds the plague in the civ's capital; no fixed toll.
    civ = world.civilizations[0]
    pops = [r.population for r in world.regions]
    injected = apply_injected_event("plague", civ.name, world)
    assert [r.population for r in world.regions] == pops
    capital = next(i for i, r in enumerate(world.regions) if r.name == civ.capital_region)
    row = _row(world, capital, ep.PLAGUE)
    assert row.e > 0 and row.cause == injected[0].event_id
    assert any(c.condition_type == "plague" and civ.name in c.affected_civs
               for c in world.active_conditions)


def _cli_args(tmp_path, *, epidemiology, turns=12, agents="off", ledger=None):
    return argparse.Namespace(
        seed=42, turns=turns, civs=4, regions=8, output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, pause_every=None, simulate_only=True, agents=agents,
        epidemiology=epidemiology, contact_ledger=ledger,
    )


def test_cli_flag_persists_and_bundle_carries_epidemic_history(tmp_path):
    from chronicler.analytics import generate_report
    from chronicler.main import _build_parser, execute_run
    assert _build_parser().parse_args(["--epidemiology"]).epidemiology is True
    assert _build_parser().parse_args(["--no-epidemiology"]).epidemiology is False
    assert _build_parser().parse_args([]).epidemiology is None
    execute_run(_cli_args(tmp_path, epidemiology=True, turns=40))
    state = json.loads((tmp_path / "state.json").read_text())
    assert "epidemics" in state
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    assert all("epidemics" in snap for snap in bundle["history"])
    assert set(bundle["history"][-1]["epidemics"]) == {
        "active", "deaths", "deaths_by_pathogen", "deaths_total", "quarantine", "strains"}
    metrics = ep.extract_epidemic_metrics([bundle])
    assert metrics["runs"] == 1 and metrics["by_seed"][0]["turns"] == len(bundle["history"])
    assert metrics["by_seed"][0]["deaths"] == state["epidemics"]["deaths_total"]
    assert ep.extract_epidemic_metrics([{"history": [{}]}]) == {}
    batch = tmp_path / "batch"
    for name in ("seed_1", "seed_2"):
        (batch / name).mkdir(parents=True)
        (batch / name / "chronicle_bundle.json").write_text(json.dumps(bundle))
    assert generate_report(batch)["epidemiology"]["runs"] == 2


def test_new_worlds_follow_default_resume_keeps_setting_and_ledger_is_required(tmp_path):
    from chronicler.main import execute_run
    fresh = tmp_path / "fresh"
    execute_run(_cli_args(fresh, epidemiology=None, turns=3))
    saved = json.loads((fresh / "state.json").read_text())
    assert ("epidemics" in saved) is ep.DEFAULT_ENABLED_FOR_NEW_WORLDS
    on = tmp_path / "on"
    execute_run(_cli_args(on, epidemiology=True, turns=3))
    resumed = _cli_args(on, epidemiology=None, turns=5)
    resumed.resume = str(on / "state.json")
    resumed.state = str(on / "resumed.json")
    execute_run(resumed)
    assert "epidemics" in json.loads((on / "resumed.json").read_text())
    off = tmp_path / "off"
    execute_run(_cli_args(off, epidemiology=False, turns=3))
    assert "epidemics" not in json.loads((off / "state.json").read_text())
    with pytest.raises(ValueError, match="contact ledger"):
        execute_run(_cli_args(tmp_path / "noledger", epidemiology=True, turns=3, ledger=False))


def test_gate_runner_forwards_the_switch_only_when_explicit():
    from scripts.m53b_run_validation import _epidemiology_args
    assert _epidemiology_args(argparse.Namespace(epidemiology=None)) == []
    assert _epidemiology_args(argparse.Namespace(epidemiology=True)) == ["--epidemiology"]
    assert _epidemiology_args(argparse.Namespace(epidemiology=False)) == ["--no-epidemiology"]
    assert _epidemiology_args(argparse.Namespace()) == []


# --- introductions: reservoirs, contact, first contact ------------------------------------

def test_homelands_follow_disease_vectors_and_start_half_immune():
    world = _world(42)
    state = world.epidemics
    ep._initialize(world, state)
    assert state.homelands and state.seen == state.homelands
    for j, k in state.homelands:
        p = ep.PATHOGENS[k]
        assert p.spillover > 0
        if p.vector != "crowd":
            assert ep._vector(world.regions[j]) == p.vector
        row = _row(world, j, k)
        assert row.r == pytest.approx(ep.HOMELAND_IMMUNITY)
    assert all(k != ep.PESTILENCE for _, k in state.homelands)
    # Deterministic: a second initialization chooses the same reservoirs.
    again = _world(42)
    ep._initialize(again, again.epidemics)
    assert again.epidemics.homelands == state.homelands


def _two_region_contact(world: WorldState, a: int, b: int, people: float) -> None:
    cl._pending(world).append((a, b, cl.PEOPLE, people))
    cl.update_contact_ledger(world)


def _isolate(world: WorldState) -> None:
    """No reservoirs and no ledger contact: only what a test seeds."""
    world.epidemics.initialized_turn = world.turn
    world.epidemics.homelands = []
    world.contact_ledger.edges = []
    world.contact_ledger.invalidate()


def test_first_contact_brings_a_virgin_soil_epidemic():
    world = _world(42)
    _isolate(world)
    a, b, c = 0, 1, 2
    for j in (a, b, c):
        world.regions[j].population = 400
        world.regions[j].carrying_capacity = 400
        world.regions[j].famine_cooldown = 0
    # Region a has long known the plague (half immune); b and c never had it.
    world.epidemics.seen = [(a, ep.PLAGUE)]
    row = ep._row_for(world.epidemics, a, ep.PLAGUE, 400)
    row.s, row.r = 0.4, 0.6
    ep._seed(row, 40.0, cause="", virgin=False)
    _two_region_contact(world, a, b, 200.0)  # heavy migration a -> b; nothing reaches c
    timeline: list[Event] = []
    cases = {a: 0.0, b: 0.0}
    for _ in range(14):
        timeline += ep.tick_epidemics(world)
        for j in cases:
            row_j = _row(world, j, ep.PLAGUE)
            cases[j] += row_j.cases if row_j is not None else 0.0
        world.turn += 1
    arrivals = [e for e in timeline if e.event_type == "epidemic_arrival"]
    assert [e.region for e in arrivals] == [world.regions[b].name]
    assert "never known it" in arrivals[0].description
    assert arrivals[0].description.startswith("Migrants from")
    onset_b = next(e for e in timeline if e.event_type == "epidemic" and e.region == world.regions[b].name)
    assert onset_b.causes[0] == arrivals[0].event_id
    assert "never known it" in onset_b.description
    assert _row(world, c, ep.PLAGUE) is None, "no contact, no epidemic"
    # Virgin soil: with no immunity far more fall sick than in the source,
    # and more of the sick die.
    assert cases[b] > 1.5 * cases[a]
    pathogen = ep.PATHOGENS[ep.PLAGUE]
    virgin_row = ep.RegionInfection(region=b, pathogen=ep.PLAGUE, n=400, virgin=True)
    known_row = ep.RegionInfection(region=a, pathogen=ep.PLAGUE, n=400, virgin=False)
    assert ep._effective_cfr(virgin_row, pathogen, 1.0) == pytest.approx(
        ep.VIRGIN_SOIL_CFR * ep._effective_cfr(known_row, pathogen, 1.0))
    assert (b, ep.PLAGUE) in world.epidemics.seen
    assert not _row(world, b, ep.PLAGUE).virgin, "once it subsides, the land knows it"


def test_virgin_soil_kills_more_for_the_same_attack():
    def outbreak(virgin: bool) -> int:
        world = _world(42)
        _isolate(world)
        region = world.regions[0]
        region.population = region.carrying_capacity = 500
        region.famine_cooldown = 0
        if not virgin:
            world.epidemics.seen = [(0, ep.PLAGUE)]
        row = ep._row_for(world.epidemics, 0, ep.PLAGUE, 500)
        ep._seed(row, 5.0, cause="", virgin=virgin)
        for _ in range(10):
            ep.tick_epidemics(world)
            world.turn += 1
        return world.epidemics.deaths_total

    known, virgin = outbreak(False), outbreak(True)
    assert known > 0
    assert virgin > known * 1.3


def test_imports_need_contact_and_scale_with_it():
    pressures = []
    for people in (0.0, 5.0, 500.0):
        hits = 0
        for seed in range(20):
            world = _world(seed)
            _isolate(world)
            for j in (0, 1):
                world.regions[j].population = world.regions[j].carrying_capacity = 300
            row = ep._row_for(world.epidemics, 0, ep.PATHOGEN_INDEX["fever"], 300)
            row.burden = 0.2
            row.s, row.i = 0.8, 0.2
            if people:
                _two_region_contact(world, 0, 1, people)
            rows = {(r.region, r.pathogen): r for r in world.epidemics.rows}
            ep._introduce(world, world.epidemics, rows, [ep._modifiers(r) for r in world.regions])
            hits += (1, 2) in rows
        pressures.append(hits)
    assert pressures[0] == 0
    assert pressures[0] < pressures[1] <= pressures[2]
    assert pressures[2] == 20


# --- mortality, civ responses and second-order effects ------------------------------------

def _big_outbreak(world: WorldState, region_idx: int, pathogen: int = 0, people: float = 60.0):
    row = ep._row_for(world.epidemics, region_idx, pathogen, world.regions[region_idx].population)
    row.n = world.regions[region_idx].population
    ep._seed(row, people, cause="", virgin=True)
    return row


def test_deaths_use_the_plague_death_path_and_civ_suffers_an_outbreak():
    from chronicler.accumulator import StatAccumulator
    world = _world(42)
    _isolate(world)
    world.agent_mode = "demographics-only"  # an agent pool that tracks population
    civ_idx, civ = 0, world.civilizations[0]
    region_idx = next(i for i, r in enumerate(world.regions) if r.name == civ.capital_region)
    region = world.regions[region_idx]
    region.population = 200
    _big_outbreak(world, region_idx)
    acc = StatAccumulator()
    events = []
    for _ in range(3):
        before = region.population
        staged_before = int(getattr(region, "_catastrophe_deaths_this_turn", 0) or 0)
        events += ep.tick_epidemics(world, acc=acc)
        died = sum(d for j, _, d in world.epidemics.last_deaths if j == region_idx)
        assert before - region.population == died
        assert region._catastrophe_deaths_this_turn - staged_before == died
        world.turn += 1
    assert world.epidemics.deaths_total > 0
    plague = [e for e in events if e.event_type == "plague"]
    assert len(plague) == 1 and plague[0].actors == [civ.name]
    assert plague[0] in world._hazard_events, "feeds the hazard cascade like the old plague"
    cond = [c for c in world.active_conditions if c.condition_type == "plague"]
    assert len(cond) == 1 and cond[0].affected_civs == [civ.name] and cond[0].duration >= 2
    assert any(c.civ_id == civ_idx and c.stat == "stability" and c.delta < 0
               and c.category == "signal" for c in acc._changes)
    assert ep.labour_scarcity(world, civ_idx) > 0


def test_mortality_is_bounded_per_turn():
    world = _world(42)
    _isolate(world)
    region = world.regions[0]
    region.population = 1000
    row = _big_outbreak(world, 0, ep.PESTILENCE, people=600.0)
    row.virgin = True
    region.famine_cooldown = 5
    ep.tick_epidemics(world)
    assert world.epidemics.deaths_total <= ep.MAX_TURN_MORTALITY * 1000 + 1
    _shares_ok(world)


def test_labour_scarcity_decays_and_eases_popular_immiseration():
    from chronicler.governance_runtime import _advance_psi, _build_context, set_governance_enabled
    world = _world(42)
    set_governance_enabled(world, True)
    _advance(world, 3)
    civ_idx, civ = next((i, c) for i, c in enumerate(world.civilizations) if c.regions)
    world.epidemics.scarcity = [(civ_idx, 0.1)]
    assert ep.mmp_labour_relief(world, civ_idx) == pytest.approx(1 + ep.LABOUR_WAGE_GAIN * 0.1)
    ctx = _build_context(world, None)
    plain, relieved = copy.deepcopy(civ.governance), copy.deepcopy(civ.governance)
    world.epidemics.scarcity = []
    _advance_psi(world, civ_idx, civ, plain, ctx)
    world.epidemics.scarcity = [(civ_idx, 0.1)]
    _advance_psi(world, civ_idx, civ, relieved, ctx)
    assert relieved.mmp_raw == pytest.approx(plain.mmp_raw / (1 + ep.LABOUR_WAGE_GAIN * 0.1))
    # Scarcity decays each tick and vanishes below the floor.
    _isolate(world)
    world.epidemics.rows = []
    ep.tick_epidemics(world)
    assert ep.labour_scarcity(world, civ_idx) == pytest.approx(0.1 * ep.LABOUR_DECAY)


def _foreign_pair(world: WorldState) -> tuple[int, int, int]:
    """Regions a, b held by different civs, and the index of b's civ."""
    a = next(i for i, r in enumerate(world.regions) if r.controller is not None)
    owner = world.regions[a].controller
    b = next(i for i, r in enumerate(world.regions) if r.controller not in (None, owner))
    civ_b = next(i for i, c in enumerate(world.civilizations) if c.name == world.regions[b].controller)
    return a, b, civ_b


def test_states_quarantine_against_a_foreign_epidemic():
    world = _world(42)
    _isolate(world)
    a, b, nb_idx = _foreign_pair(world)
    neighbour = world.civilizations[nb_idx]
    neighbour.stability = 80
    neighbour.treasury = 50
    world.regions[a].population = 300
    _two_region_contact(world, a, b, 100.0)
    _big_outbreak(world, a, ep.PLAGUE, people=30.0)
    events = ep.tick_epidemics(world)
    closure = next(e for e in events if e.event_type == "quarantine" and e.actors == [neighbour.name])
    assert nb_idx in world.epidemics.quarantine
    assert neighbour.treasury == 50 - ep.QUARANTINE_COST
    report = next(e for e in events if e.event_type == "epidemic" and e.region == world.regions[a].name)
    assert closure.causes == [report.event_id]
    # A poor or unstable state cannot close its borders.
    world.epidemics.quarantine = []
    neighbour.stability = ep.QUARANTINE_MIN_STABILITY - 1
    ep._decide_quarantine(world, world.epidemics, {(a, ep.PLAGUE): report}, None)
    assert nb_idx not in world.epidemics.quarantine
    # Once the epidemic is gone the border reopens.
    neighbour.stability = 80
    world.epidemics.rows = []
    ep.tick_epidemics(world)
    assert world.epidemics.quarantine == []


def test_quarantine_cuts_foreign_imports():
    def imports(closed: bool) -> int:
        hits = 0
        for seed in range(40):
            world = _world(seed)
            _isolate(world)
            a, b, nb_idx = _foreign_pair(world)
            for j in (a, b):
                world.regions[j].population = world.regions[j].carrying_capacity = 300
            row = ep._row_for(world.epidemics, a, ep.PLAGUE, 300)
            row.s, row.i, row.burden = 0.8, 0.2, 0.2
            _two_region_contact(world, a, b, 10.0)
            world.epidemics.quarantine = [nb_idx] if closed else []
            rows = {(r.region, r.pathogen): r for r in world.epidemics.rows}
            ep._introduce(world, world.epidemics, rows, [ep._modifiers(r) for r in world.regions])
            hits += (b, ep.PLAGUE) in rows
        return hits

    open_, closed = imports(False), imports(True)
    assert open_ > 0
    assert closed < open_ * 0.6


def test_a_new_strain_escapes_old_immunity(monkeypatch):
    k = ep.PATHOGEN_INDEX["fever"]

    def run(mutate: bool):
        world = _world(42)
        _isolate(world)
        world.regions[0].population = world.regions[1].population = 400
        immune = ep._row_for(world.epidemics, 1, k, 400)
        immune.s, immune.r = 0.2, 0.8
        _big_outbreak(world, 0, k, people=40.0)
        monkeypatch.setattr(ep, "_draw", lambda ns, w, *parts: (
            0.0 if mutate and ns == "epidemic_mutation" else 0.99))
        return world, ep.tick_epidemics(world)

    plain, plain_events = run(False)
    world, events = run(True)
    assert not [e for e in plain_events if e.event_type == "pathogen_mutation"]
    mutation = [e for e in events if e.event_type == "pathogen_mutation"]
    assert len(mutation) == 1 and "strain 1" in mutation[0].description
    assert world.epidemics.strains[k] == 1 and plain.epidemics.strains[k] == 0
    assert _row(world, 1, k).r == pytest.approx(
        _row(plain, 1, k).r * (1 - ep.PATHOGENS[k].escape), abs=1e-6)


# --- provenance -----------------------------------------------------------------------

def test_epidemics_are_chronic_episodes_with_resolvable_causes():
    world = _advance(_world(42), 150)
    timeline = world.events_timeline
    ids = {e.event_id for e in timeline}
    kinds = ("epidemic", "epidemic_arrival", "epidemic_ended", "plague", "quarantine",
             "quarantine_ended", "pathogen_mutation")
    disease = [e for e in timeline if e.event_type in kinds]
    assert {e.event_type for e in disease} >= {"epidemic", "epidemic_arrival", "epidemic_ended", "plague"}
    for ev in disease:
        for cause in ev.causes:
            assert cause in ids, (ev.event_id, cause)
    onsets = [e for e in timeline if e.event_type == "epidemic"]
    assert all(e.episode == "onset" and e.region and e.shock_category for e in onsets)
    by_id = {e.event_id: e for e in timeline}
    arrival_led = [e for e in onsets if e.causes and by_id[e.causes[0]].event_type == "epidemic_arrival"]
    assert arrival_led, "contact arrivals cause onsets"
    for e in arrival_led:
        arrival = by_id[e.causes[0]]
        assert arrival.region == e.region and arrival.turn == e.turn
    ended = [e for e in timeline if e.event_type == "epidemic_ended"]
    assert all(e.episode == "end" and e.causes and by_id[e.causes[0]].event_type == "epidemic"
               for e in ended)
    civ_outbreaks = [e for e in timeline if e.event_type == "plague"]
    assert all(by_id[e.causes[0]].event_type == "epidemic" for e in civ_outbreaks)


# --- agent modes (native) ------------------------------------------------------------

def _hybrid(seed: int):
    pytest.importorskip("chronicler_agents")
    from chronicler.agent_bridge import AgentBridge
    world = _world(seed)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    return world, bridge


@pytest.mark.native
def test_hybrid_epidemic_deaths_reach_the_agent_pool():
    world, bridge = _hybrid(42)
    _isolate(world)
    region_idx = max(range(len(world.regions)), key=lambda j: world.regions[j].population)
    region = world.regions[region_idx]
    agents_before = sum(1 for r in bridge.get_snapshot().column("region").to_pylist() if r == region_idx)
    assert agents_before == region.population > 20
    _big_outbreak(world, region_idx, ep.PESTILENCE, people=region.population * 0.4)
    ep.tick_epidemics(world)
    died = sum(d for j, _, d in world.epidemics.last_deaths if j == region_idx)
    assert died > 0
    assert region._catastrophe_deaths_this_turn == died
    world.turn += 1
    bridge.tick(world)
    deaths = [e for e in world.agent_events_raw if e.event_type == "death" and e.region == region_idx]
    assert len(deaths) >= died, "the staged epidemic deaths killed real agents"
    assert region.population <= agents_before - died
    assert region._catastrophe_deaths_this_turn == 0, "the transient is cleared once read"
    # The next turn's batch carries no stale deaths when no epidemic tick ran.
    from chronicler.agent_bridge import build_region_batch
    assert set(build_region_batch(world).column("catastrophe_deaths_this_turn").to_pylist()) == {0}
    # A second epidemic tick stages only its own deaths.
    ep.tick_epidemics(world)
    again = sum(d for j, _, d in world.epidemics.last_deaths if j == region_idx)
    assert region._catastrophe_deaths_this_turn == again


@pytest.mark.native
def test_hybrid_runs_with_epidemics_are_deterministic():
    w1, b1 = _hybrid(7)
    w2, b2 = _hybrid(7)
    _advance(w1, 40, bridge=b1)
    _advance(w2, 40, bridge=b2)
    assert w1.epidemics.model_dump() == w2.epidemics.model_dump()
    assert w1.epidemics.deaths_total > 0


@pytest.mark.slow
@pytest.mark.parametrize("agents", ["off", "hybrid"])
def test_worlds_survive_two_hundred_turns_with_epidemics(agents):
    for seed in (42, 43, 44, 45, 46, 47):
        if agents == "off":
            world, bridge = _world(seed), None
        else:
            world, bridge = _hybrid(seed)
        _advance(world, 200, bridge=bridge)
        assert sum(r.population for r in world.regions) > 0
        assert any(c.regions for c in world.civilizations)
        assert world.epidemics.deaths_total > 0
