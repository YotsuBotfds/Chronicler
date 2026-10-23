"""Live Phase 8 governance: integration, persistence, determinism and consumers."""
from __future__ import annotations

import json
import random

import pytest

from chronicler import governance_runtime as gr
from chronicler import governance_stress as stress
from chronicler import institutions as g01
from chronicler.accumulator import StatAccumulator
from chronicler.action_engine import ActionEngine
from chronicler.governance_state import CivGovernance, GovernanceInstitution
from chronicler.models import ActionType, FactionType, WorldState
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world

try:
    from chronicler_agents import AgentSimulator as _AgentSimulator
    _AGENTS_AVAILABLE = isinstance(_AgentSimulator, type)
except Exception:  # pragma: no cover - depends on the optional extension
    _AGENTS_AVAILABLE = False

GOVERNANCE_EVENTS = {
    "institution_enacted", "institution_repealed", "ambition_declared", "ambition_fulfilled",
    "ambition_failed", "psi_crisis", "revolt", "secession_suppressed", "fiscal_crisis",
    "elite_overproduction", "cognomen_awarded",
}


def _advance(world, turns, *, seed=None, agent_bridge=None, start=0):
    seed = world.seed if seed is None else seed

    def select(civ, w, _seed=seed):
        return ActionEngine(w).select_action(civ, seed=_seed + w.turn)

    for i in range(start, start + turns):
        run_turn(world, select, lambda w, e: "", seed=seed + i, agent_bridge=agent_bridge)
    return world


def _world(seed=11, *, governance=True, civs=4, regions=10):
    world = generate_world(seed=seed, num_regions=regions, num_civs=civs)
    if governance:
        gr.set_governance_enabled(world, True)
    return world


def _gov_state(world):
    return [c.governance.model_dump(mode="json") if c.governance else None for c in world.civilizations]


# --- dormancy --------------------------------------------------------------

def test_disabled_world_never_serializes_governance_and_skips_ticks(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("governance ran while disabled")

    monkeypatch.setattr(gr, "tick_governance", forbidden)
    monkeypatch.setattr(gr, "fund_institutions_phase2", forbidden)
    world = _advance(_world(governance=False), 8)
    dumped = world.model_dump_json(indent=2)
    assert "governance" not in dumped
    assert all(c.governance is None for c in world.civilizations)


def test_disabled_runs_match_never_enabled_runs_exactly():
    a = _advance(_world(seed=5, governance=False), 12)
    b = _world(seed=5, governance=True)
    gr.set_governance_enabled(b, False)
    b = _advance(b, 12)
    assert a.model_dump_json() == b.model_dump_json()


def test_old_saves_without_governance_load_and_can_enable(tmp_path):
    world = _advance(_world(seed=3, governance=False), 4)
    path = tmp_path / "state.json"
    world.save(path)
    payload = json.loads(path.read_text())
    assert "governance" not in payload
    loaded = WorldState.load(path)
    assert loaded.governance is None
    gr.set_governance_enabled(loaded, True)
    _advance(loaded, 3, start=4)
    living = [c for c in loaded.civilizations if c.regions]
    assert living and all(c.governance is not None for c in living)
    # Partial governance payloads (older versions) fill defaults.
    civ_payload = loaded.civilizations[0].model_dump(mode="json")
    civ_payload["governance"] = {"ruler_legitimacy": 0.7}
    from chronicler.models import Civilization
    restored = Civilization.model_validate(civ_payload)
    assert restored.governance.ruler_legitimacy == 0.7
    assert restored.governance.institutions == []


# --- multi-turn integration (aggregate / --agents off) -----------------------

@pytest.fixture(scope="module")
def governed_run():
    world = _advance(_world(seed=11), 80)
    return world


def test_every_living_civ_carries_current_epoch_state(governed_run):
    world = governed_run
    living = [(i, c) for i, c in enumerate(world.civilizations) if c.regions]
    assert living
    for _, civ in living:
        gov = civ.governance
        assert gov is not None
        # Late Phase 10 of turn N publishes state effective at N+1 == world.turn.
        assert gov.institutions_effective_turn == world.turn
        assert gov.governance_effective_turn == world.turn
        assert gov.ratchet_turn == world.turn - 1
        assert 0.0 <= gov.ruler_legitimacy <= 1.0
        assert 0.0 <= gov.political_capital <= float(gr.MAX_POLITICAL_CAPITAL)
        assert len(gov.institutions) <= g01.MAX_ACTIVE_INSTITUTIONS
        assert gov.reign_id is not None and gov.ruler_name == civ.leader.name
        assert set(gov.legitimacy_sources) == {"base", "dynasty", "institutions", "victories",
                                               "ambitions", "faction_alignment", "succession"}
        assert gov.psi > 0.0 and len(gov.psi_history) > 0
        assert gov.institutional_regime in {"nascent", "inert", "transitional", "frozen_stable",
                                            "highly_fluctuating", "complex_cycling"}


def test_governance_events_reach_the_timeline(governed_run):
    types = {e.event_type for e in governed_run.events_timeline}
    assert types & GOVERNANCE_EVENTS
    assert "ambition_declared" in types
    assert "institution_enacted" in types


def test_institutions_respect_conflicts_and_kernel_validation(governed_run):
    for civ in governed_run.civilizations:
        if civ.governance is None:
            continue
        snapshot = gr._institution_snapshot(civ.governance, civ.governance.institutions_effective_turn)
        types = {i.institution_type for i in snapshot.institutions}
        for t in types:
            assert not (g01.INSTITUTION_CONFLICTS[t] & types)


def test_same_seed_is_deterministic():
    a = _advance(_world(seed=21), 30)
    b = _advance(_world(seed=21), 30)
    assert a.model_dump_json() == b.model_dump_json()
    assert _gov_state(a) == _gov_state(b)


def test_governance_changes_outcomes():
    off = _advance(_world(seed=21, governance=False), 40)
    on = _advance(_world(seed=21), 40)
    assert [c.stability for c in off.civilizations] != [c.stability for c in on.civilizations] or \
        [c.treasury for c in off.civilizations] != [c.treasury for c in on.civilizations]


def test_save_load_round_trip_continues_identically():
    straight = _advance(_world(seed=17), 30)
    first = _advance(_world(seed=17), 15)
    restored = WorldState.model_validate_json(first.model_dump_json())
    _advance(restored, 15, start=15)
    assert _gov_state(restored) == _gov_state(straight)
    assert [c.stability for c in restored.civilizations] == [c.stability for c in straight.civilizations]


# --- phase-level contracts -----------------------------------------------

def _single_civ_world():
    world = _world(seed=8, civs=3, regions=8)
    world.turn = 5
    civ = world.civilizations[0]
    civ.governance = CivGovernance(initialized_turn=0, institutions_effective_turn=5,
                                   governance_effective_turn=5, ratchet_turn=4)
    return world, civ


def test_phase2_funding_record_pays_and_is_consumed_once():
    world, civ = _single_civ_world()
    civ.governance.institutions = [GovernanceInstitution(
        institution_type="education", enacted_turn=2, legitimacy=1.0, enforcement_cost=4.0,
        opposing_faction="clergy")]
    civ.treasury = 2
    acc = StatAccumulator()
    events = gr.fund_institutions_phase2(world, acc)
    gov = civ.governance
    assert gov.funding_turn == 5
    assert gov.last_institution_enforcement_cost == 4.0
    assert gov.last_enforcement_paid == 2 and gov.last_institution_funding_ratio == 0.5
    assert any(e.event_type == "fiscal_crisis" for e in events)
    snapshot = gr._institution_snapshot(gov, 5)
    record = gr._funding_record(gov, snapshot, civ, 5)
    assert record.policy is g01.FundingPolicy.EXTERNAL_AGGREGATE_RECORD
    assert record.last_institution_funding_ratio == 0.5
    # A record from another turn is never reused: the next turn synthesizes "unpaid".
    stale = gr._funding_record(gov, gr._institution_snapshot(gov, 6), civ, 6)
    assert stale.last_institution_funding_ratio == 0.0 and gov.funding_turn == 6


def test_underfunded_institutions_erode_and_low_capital_blocks_enactment():
    world, civ = _single_civ_world()
    gov = civ.governance
    gov.institutions = [GovernanceInstitution(
        institution_type="written_law", enacted_turn=1, legitimacy=0.1, enforcement_cost=2.0,
        opposing_faction="military")]
    gov.funding_turn = 5
    gov.last_institution_enforcement_cost = 2.0
    gov.last_institution_funding_ratio = 0.0
    gov.political_capital = 0.0
    for ft in FactionType:
        civ.factions.influence[ft] = 0.1
    civ.factions.influence[FactionType.CULTURAL] = 0.7
    ctx = gr._build_context(world, None)
    events = gr._tick_civ(world, 0, civ, None, ctx)
    # Legitimacy 0.1 - erosion 0.08 < 0.05 collapse threshold -> neglect repeal.
    assert any(e.event_type == "institution_repealed" and "neglect" in e.description for e in events)
    assert civ.governance.institutions == []
    assert not any(e.event_type == "institution_enacted" for e in events)


def test_capital_funds_enactment_and_is_debited():
    world, civ = _single_civ_world()
    gov = civ.governance
    gov.political_capital = 0.5
    for ft in FactionType:
        civ.factions.influence[ft] = 0.1
    civ.factions.influence[FactionType.CULTURAL] = 0.7
    world_rng_state = random.getstate()
    original = gr.INSTITUTION_COEFFICIENTS
    gr.INSTITUTION_COEFFICIENTS = g01.InstitutionCoefficients(1.0, original.legitimacy_erosion_rate,
                                                              original.legitimacy_recovery_rate, original.rules)
    try:
        events = gr._tick_civ(world, 0, civ, None, gr._build_context(world, None))
    finally:
        gr.INSTITUTION_COEFFICIENTS = original
    assert random.getstate() == world_rng_state  # no global RNG consumption
    enacted = [e for e in events if e.event_type == "institution_enacted"]
    assert len(enacted) == 1
    assert len(civ.governance.institutions) == 1
    assert g01.alignment(g01.InstitutionType(civ.governance.institutions[0].institution_type)) is g01.Faction.CULTURAL
    assert civ.governance.capital_spent_total == pytest.approx(0.10)


def test_secession_suppression_spends_capital_and_raises_stability():
    world, civ = _single_civ_world()
    while len(civ.regions) < 3:
        free = next(r for r in world.regions if r.controller is None)
        free.controller = civ.name
        civ.regions.append(free.name)
    civ.founded_turn = 0
    civ.stability = 5
    civ.governance.political_capital = 0.3
    before = civ.stability
    events = gr._tick_civ(world, 0, civ, None, gr._build_context(world, None))
    assert any(e.event_type == "secession_suppressed" for e in events)
    assert civ.governance.secession_suppressions == 1
    assert civ.stability > before
    # Cooldown: an immediate second tick cannot suppress again.
    world.turn += 1
    events = gr._tick_civ(world, 0, civ, None, gr._build_context(world, None))
    assert not any(e.event_type == "secession_suppressed" for e in events)


def test_accession_starts_a_new_reign_with_ambitions_and_archives_the_old():
    world, civ = _single_civ_world()
    gr._tick_civ(world, 0, civ, None, gr._build_context(world, None))
    first = civ.governance.reign_id
    assert first is not None and civ.governance.ambitions is not None
    civ.leader = civ.leader.model_copy(update={"name": "Queen Test", "reign_start": 6,
                                                "succession_type": "usurper"})
    world.turn = 6
    events = gr._tick_civ(world, 0, civ, None, gr._build_context(world, None))
    gov = civ.governance
    assert gov.reign_id != first and gov.reign_archive[-1].reign_id == first
    assert gov.legitimacy_sources["succession"] < 0  # contested accession
    assert any(tag == "succession_contested" for _, tag in gov.recent_tags)
    assert any(e.event_type == "ambition_declared" for e in events) or not gov.ambitions


# --- consumers ---------------------------------------------------------------

def test_weight_bucket_is_clamped_to_ceiling():
    world, civ = _single_civ_world()
    gov = civ.governance
    gov.institutions = [
        GovernanceInstitution(institution_type=t, enacted_turn=1, legitimacy=1.0, enforcement_cost=0.0,
                              opposing_faction=gr._OPPOSITION_AND_COST[g01.InstitutionType(t)][0].value)
        for t in ("military_acclamation", "conscription", "martial_law")]
    from chronicler.governance_state import GovernanceAmbition
    gov.ambitions = [GovernanceAmbition(ambition_type="conquer_region", target="x", generated_turn=0,
                                        deadline_turn=30, generated_event_cursor=0)]
    gov.ruler_legitimacy = 0.1
    mods = gr.governance_weight_modifiers(civ, world)
    assert mods[ActionType.WAR] == pytest.approx(gr.GOVERNANCE_WEIGHT_CEILING)
    assert all(1 / gr.GOVERNANCE_WEIGHT_CEILING <= m <= gr.GOVERNANCE_WEIGHT_CEILING for m in mods.values())


def test_global_weight_cap_still_applies_with_governance(monkeypatch):
    world, civ = _single_civ_world()
    monkeypatch.setattr(gr, "governance_weight_modifiers",
                        lambda c, w: {a: 1.5 for a in ActionType})
    from chronicler.action_engine import ACTION_WEIGHT_BASE
    weights = ActionEngine(world).compute_weights(civ)
    assert max(weights.values()) <= ACTION_WEIGHT_BASE * 2.5 + 1e-9


def test_crisis_multiplier_tracks_legitimacy():
    world, civ = _single_civ_world()
    civ.governance.ruler_legitimacy = 0.9
    strong = gr.governance_crisis_multiplier(civ, world)
    civ.governance.ruler_legitimacy = 0.1
    weak = gr.governance_crisis_multiplier(civ, world)
    assert weak > 1.0 > strong


def test_snapshot_and_bundle_fields(governed_run):
    civ = next(c for c in governed_run.civilizations if c.regions)
    snap = gr.governance_snapshot(civ)
    for key in ("institutions", "ruler_legitimacy", "political_capital", "psi", "mmp", "emp", "sfd",
                "psi_crisis", "institutional_regime", "cycle_phase", "elite_positions"):
        assert key in snap
    from chronicler.models import CivSnapshot
    dormant = CivSnapshot(population=1, military=1, economy=1, culture=1, stability=1, treasury=1,
                          asabiya=0.5, tech_era=civ.tech_era, trait="bold", regions=[], leader_name="x",
                          alive=True)
    assert "governance" not in dormant.model_dump(mode="json")
    assert CivSnapshot.model_validate(dormant.model_dump() | {"governance": snap}).governance == snap
    lines = gr.governance_context_lines(governed_run)
    assert lines and "legitimacy" in lines[0]


def test_execute_run_cli_flag_produces_bundle_stats(tmp_path):
    import argparse
    from chronicler.main import execute_run
    args = argparse.Namespace(seed=4, turns=12, civs=3, regions=8, output=str(tmp_path / "chronicle.md"),
                              state=str(tmp_path / "state.json"), resume=None, reflection_interval=10,
                              llm_actions=False, scenario=None, simulate_only=True, agents="off",
                              governance=True)
    execute_run(args)
    bundle = json.loads((tmp_path / "chronicle_bundle.json").read_text())
    stats = [c.get("governance") for s in bundle["history"] for c in s["civ_stats"].values() if c["regions"]]
    assert stats and all(g is not None for g in stats[len(stats) // 2:])
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["governance"]["enabled"] is True


# --- PSI and regime classifiers -------------------------------------------

def test_psi_composition_needs_co_occurrence():
    cal = stress.DEFAULT_STRESS
    baseline = stress.compose_psi(0, 0, 0, cal)
    single = stress.compose_psi(cal.subindex_cap, 0, 0, cal)
    joint = stress.compose_psi(1.5, 1.5, 1.5, cal)
    assert baseline == pytest.approx(cal.floor ** 3)
    assert single < cal.crisis_threshold < joint


def test_crisis_hysteresis():
    cal = stress.DEFAULT_STRESS
    assert stress.update_crisis(False, cal.crisis_threshold + 0.01, cal)
    assert stress.update_crisis(True, cal.recovery_threshold + 0.01, cal)
    assert not stress.update_crisis(True, cal.recovery_threshold - 0.01, cal)
    assert not stress.update_crisis(False, cal.crisis_threshold, cal)


def test_mmp_and_sfd_formulas():
    mmp, wage, urban, youth = stress.mmp_from_agents([1, 1, 1, 9], [20, 40, 25, 60], [0, 3, 3, 0])
    assert wage == pytest.approx(1.0 / 3.0)
    assert urban == 0.5 and youth == 0.5
    assert mmp == pytest.approx(3.0 * 0.5 * 0.5)
    assert stress.sfd_raw(10, 100, 0, 1.0) == pytest.approx(0.1)
    assert stress.sfd_raw(10, 100, 20, 0.5) == pytest.approx(0.1 * 1.1)
    assert stress.sfd_raw(10, 0, 0, 1.0) == pytest.approx(10.0)


@pytest.mark.parametrize("log, active, expected", [
    ([], {"tax_code": 0}, "frozen_stable"),
    ([], {}, "inert"),
    ([[t, "free_trade", "enacted" if k % 2 == 0 else "repealed"] for k, t in enumerate(range(30, 110, 4))],
     {}, "highly_fluctuating"),
    ([[30, "tax_code", "enacted"], [50, "free_trade", "enacted"], [80, "tax_code", "repealed"]],
     {"free_trade": 50}, "complex_cycling"),
    # Changes before the trailing window do not count.
    ([[10, "tax_code", "enacted"], [15, "tax_code", "repealed"]], {}, "inert"),
])
def test_institutional_regime_labels(log, active, expected):
    assert stress.classify_institutional_regime(log, active, 120, 0).label == expected


def test_regime_is_nascent_for_young_polities():
    assert stress.classify_institutional_regime([], {}, 10, 0).label == "nascent"


def test_cycle_phase_labels():
    cal = stress.DEFAULT_STRESS
    assert stress.classify_cycle_phase([3.0], True, 50, None, cal) == "crisis"
    assert stress.classify_cycle_phase([1.0], False, 50, 40, cal) == "depression"
    assert stress.classify_cycle_phase([1.0], False, 150, 80, cal) == "recovery"
    rising = [0.5] * 9 + [cal.crisis_threshold * 0.8]
    assert stress.classify_cycle_phase(rising, False, 300, None, cal) == "stagflation"
    assert stress.classify_cycle_phase([0.3] * 10, False, 300, None, cal) == "integrative"


# --- hybrid (native agents) ----------------------------------------------

@pytest.mark.native
@pytest.mark.skipif(not _AGENTS_AVAILABLE, reason="Rust agent extension not available")
def test_hybrid_mode_uses_agent_rows_and_is_deterministic():
    from chronicler.agent_bridge import AgentBridge

    def run():
        world = _world(seed=33, civs=3, regions=8)
        world.agent_mode = "hybrid"
        bridge = AgentBridge(world, mode="hybrid")
        _advance(world, 25, agent_bridge=bridge)
        return world

    a, b = run(), run()
    assert _gov_state(a) == _gov_state(b)
    living = [c for c in a.civilizations if c.regions and c.governance]
    assert living
    # Agent-backed elites: qualifiers come from snapshot rows, not the off-mode proxy.
    assert any(c.governance.elite_qualifier_count > 0 for c in living)
    assert all(c.governance.ratchet_turn == a.turn - 1 for c in living)
