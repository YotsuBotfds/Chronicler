"""H-40: Test that --agents=off produces deterministic (bit-identical) output.

The documented guarantee is that aggregate-only mode is fully deterministic:
same seed, same turn count, same number of civs/regions => identical outputs.
"""
import pytest
from chronicler.world_gen import generate_world
from chronicler.simulation import run_turn
from chronicler.action_engine import ActionEngine
from chronicler.models import Resource, ResourceType


def _run_aggregate_simulation(seed, num_turns=15, num_civs=3, num_regions=6):
    """Run a pure aggregate-mode (agents=off) simulation and return snapshot data."""
    world = generate_world(seed=seed, num_regions=num_regions, num_civs=num_civs)
    world.agent_mode = "off"

    # Ensure deterministic resource assignments for tech advancement
    for r in world.regions:
        if r.controller is not None:
            r.resource_types = [ResourceType.ORE, ResourceType.TIMBER, ResourceType.GRAIN]

    def stub_narrator(w, events):
        return "Turn narrative."

    for turn_num in range(num_turns):
        engine = ActionEngine(world)
        action_selector = lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn)
        run_turn(world, action_selector, stub_narrator, seed=world.seed + turn_num)

    # Extract comprehensive state snapshot
    snapshot = {
        "turn": world.turn,
        "civ_count": len(world.civilizations),
        "civs": [],
        "events_count": len(world.events_timeline),
        "named_events_count": len(world.named_events),
        "active_conditions_count": len(world.active_conditions),
        "active_wars": [sorted(list(w)) for w in world.active_wars],
    }
    for civ in world.civilizations:
        snapshot["civs"].append({
            "name": civ.name,
            "population": civ.population,
            "military": civ.military,
            "economy": civ.economy,
            "culture": civ.culture,
            "stability": civ.stability,
            "treasury": civ.treasury,
            "tech_era": civ.tech_era.value,
            "regions": sorted(civ.regions),
            "asabiya": civ.asabiya,
            "prestige": civ.prestige,
        })
    # Sort civs by name for stable comparison
    snapshot["civs"].sort(key=lambda c: c["name"])
    return snapshot


class TestAgentsOffDeterminism:
    """Verify that --agents=off mode is deterministic."""

    def test_same_seed_identical_output(self):
        """Two runs with the same seed should produce bit-identical state."""
        snap_a = _run_aggregate_simulation(seed=42)
        snap_b = _run_aggregate_simulation(seed=42)

        assert snap_a["turn"] == snap_b["turn"]
        assert snap_a["civ_count"] == snap_b["civ_count"]
        assert snap_a["events_count"] == snap_b["events_count"]
        assert snap_a["named_events_count"] == snap_b["named_events_count"]

        for ca, cb in zip(snap_a["civs"], snap_b["civs"]):
            assert ca == cb, (
                f"Civ state mismatch for {ca['name']}:\n"
                f"  Run A: {ca}\n"
                f"  Run B: {cb}"
            )

    def test_different_seeds_produce_different_output(self):
        """Different seeds should produce different civilizations."""
        snap_a = _run_aggregate_simulation(seed=42)
        snap_b = _run_aggregate_simulation(seed=99)

        # Different seeds should produce at least some different stats
        all_same = True
        for ca, cb in zip(snap_a["civs"], snap_b["civs"]):
            if ca != cb:
                all_same = False
                break
        # If all civs somehow match exactly with different seeds, check events
        if all_same:
            all_same = snap_a["events_count"] == snap_b["events_count"]
        assert not all_same, "Different seeds produced identical output"

    def test_specific_phase_outputs_identical(self):
        """Verify that specific phase outputs (treasury, military, tech_era)
        are identical between two runs."""
        snap_a = _run_aggregate_simulation(seed=77, num_turns=10)
        snap_b = _run_aggregate_simulation(seed=77, num_turns=10)

        for ca, cb in zip(snap_a["civs"], snap_b["civs"]):
            assert ca["treasury"] == cb["treasury"], (
                f"Treasury mismatch for {ca['name']}: {ca['treasury']} vs {cb['treasury']}"
            )
            assert ca["military"] == cb["military"], (
                f"Military mismatch for {ca['name']}: {ca['military']} vs {cb['military']}"
            )
            assert ca["tech_era"] == cb["tech_era"], (
                f"Tech era mismatch for {ca['name']}: {ca['tech_era']} vs {cb['tech_era']}"
            )
            assert ca["stability"] == cb["stability"], (
                f"Stability mismatch for {ca['name']}: {ca['stability']} vs {cb['stability']}"
            )
            assert ca["regions"] == cb["regions"], (
                f"Regions mismatch for {ca['name']}: {ca['regions']} vs {cb['regions']}"
            )

    def test_multiple_runs_all_identical(self):
        """Three consecutive runs should all produce the same output."""
        snaps = [_run_aggregate_simulation(seed=123, num_turns=10) for _ in range(3)]

        for i in range(1, len(snaps)):
            assert snaps[0]["civs"] == snaps[i]["civs"], (
                f"Run {i} diverged from run 0"
            )
            assert snaps[0]["events_count"] == snaps[i]["events_count"]

    def test_single_civ_world_remains_deterministic(self):
        """Single-civ aggregate worlds should still run and remain deterministic."""
        snap_a = _run_aggregate_simulation(seed=321, num_turns=12, num_civs=1, num_regions=3)
        snap_b = _run_aggregate_simulation(seed=321, num_turns=12, num_civs=1, num_regions=3)

        assert snap_a == snap_b
        assert snap_a["civ_count"] == 1
        assert len(snap_a["civs"]) == 1


def _off_turns_with_staged_signals(seed, num_turns, stage):
    """Run off-mode turns; ``stage(world)`` sets signals before each turn.
    Returns the world and each turn's end-of-turn region signal values."""
    from chronicler.utils import stage_region_catastrophe_deaths

    world = generate_world(seed=seed, num_regions=5, num_civs=2)
    world.agent_mode = "off"
    seen = []
    for turn_num in range(num_turns):
        if stage:
            stage_region_catastrophe_deaths(world.regions[0], 9 + turn_num)
            world.regions[1]._raided_this_turn = True
        engine = ActionEngine(world)
        run_turn(world, lambda civ, w, eng=engine: eng.select_action(civ, seed=w.seed + w.turn),
                 lambda w, events: "Turn narrative.", seed=world.seed + turn_num)
        seen.append([(r._catastrophe_deaths_this_turn, r._raided_this_turn,
                      r._controller_changed_this_turn, r._war_won_this_turn,
                      r._seceded_this_turn, r.schism_convert_from, r.schism_convert_to,
                      hasattr(r, "_culture_investment_active"))
                     for r in world.regions])
    return world, seen


class TestAgentsOffTransientSignals:
    """FIX-3: an --agents off turn clears every one-turn region signal, as the
    agent bridge does after reading them; nothing in off mode reads them."""

    def test_staged_catastrophe_and_raid_clear_after_each_turn(self):
        _, seen = _off_turns_with_staged_signals(seed=42, num_turns=3, stage=True)
        cleared = (0, False, False, False, False, 0xFF, 0xFF, False)
        for turn_values in seen:
            assert turn_values == [cleared] * len(turn_values)

    def test_staged_signals_do_not_change_off_mode_outcomes(self):
        staged, _ = _off_turns_with_staged_signals(seed=42, num_turns=3, stage=True)
        plain, _ = _off_turns_with_staged_signals(seed=42, num_turns=3, stage=False)
        assert staged.model_dump(mode="json") == plain.model_dump(mode="json")
