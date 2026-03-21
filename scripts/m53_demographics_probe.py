"""M53 Demographics Probe — isolate causes of agent population collapse.

Runs short simulations with per-turn demographic debug output.
Supports three probe modes:
  A: disease zeroed (endemic_severity = 0 each turn)
  B: MORTALITY_ADULT halved (requires Rust constant change + rebuild)
  C: fertility bumped (requires Rust constant change + rebuild)
  baseline: current constants, no modifications

Usage:
  PYTHONPATH=src python scripts/m53_demographics_probe.py --probe baseline --seeds 5 --turns 100
  PYTHONPATH=src python scripts/m53_demographics_probe.py --probe A --seeds 5 --turns 100
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chronicler.world_gen import generate_world
from chronicler.models import WorldState
from chronicler.simulation import run_turn
from chronicler.action_engine import ActionEngine


def null_narrator(world, events):
    """Stub narrator callable that returns empty string."""
    return ""


def setup_world(seed: int) -> WorldState:
    """Generate a default world for probing."""
    return generate_world(seed=seed, num_regions=8, num_civs=4)


def zero_disease(world: WorldState) -> None:
    """Probe A: set endemic_severity to 0 for all regions."""
    for region in world.regions:
        region.endemic_severity = 0.0
        region.disease_baseline = 0.0


def run_probe(seed: int, turns: int, probe: str, verbose: bool = False):
    """Run a single-seed probe and return per-turn data."""
    world = setup_world(seed)

    # Set up agent bridge
    from chronicler.agent_bridge import AgentBridge
    bridge = AgentBridge(world, mode="hybrid")
    sim = bridge._sim

    engine = ActionEngine(world)
    action_selector = lambda civ, w: engine.select_action(civ, seed=w.seed + w.turn)
    narrator = null_narrator

    # Initial age histogram (after first set_region_state)
    bridge.tick(world)  # first tick to initialize
    age_hist = sim.get_age_histogram()

    results = []

    for turn_num in range(turns):
        world.turn = turn_num

        # Probe A: zero disease before each turn
        if probe == "A":
            zero_disease(world)

        # Run the simulation turn (10 phases)
        run_turn(world, action_selector, narrator, seed=seed, agent_bridge=bridge)

        # Collect diagnostics
        debug = sim.get_demographic_debug()
        hist = sim.get_age_histogram()

        row = {
            "turn": turn_num,
            "alive": sim.last_tick_alive,
            "deaths": sim.last_tick_deaths,
            "births": sim.last_tick_births,
            "deaths_young": int(debug.get("deaths_young", 0)),
            "deaths_adult": int(debug.get("deaths_adult", 0)),
            "deaths_elder": int(debug.get("deaths_elder", 0)),
            "deaths_disease": int(debug.get("deaths_with_disease", 0)),
            "deaths_war": int(debug.get("deaths_soldier_at_war", 0)),
            "deaths_eco": int(debug.get("deaths_eco_stress_gt1", 0)),
            "mean_endemic": round(debug.get("mean_endemic", 0), 4),
            "max_endemic": round(debug.get("max_endemic", 0), 4),
            "fertile_total": int(debug.get("fertile_age_total", 0)),
            "fertile_farmer": int(debug.get("fertile_farmer", 0)),
            "fertile_soldier": int(debug.get("fertile_soldier", 0)),
            "fertile_merchant": int(debug.get("fertile_merchant", 0)),
            "fertile_scholar": int(debug.get("fertile_scholar", 0)),
            "fertile_priest": int(debug.get("fertile_priest", 0)),
            "expected_deaths": round(debug.get("expected_deaths", 0), 2),
            "expected_births": round(debug.get("expected_births", 0), 2),
            "sat_near_thresh": int(debug.get("sat_near_threshold", 0)),
            "young": hist.get("young_0_19", 0),
            "adult": hist.get("adult_20_59", 0),
            "elder": hist.get("elder_60_plus", 0),
            "fertile_range": hist.get("fertile_range_16_45", 0),
        }
        results.append(row)

        if verbose and turn_num % 10 == 0:
            fertile_eligible = sum(row[f"fertile_{o}"] for o in ["farmer", "soldier", "merchant", "scholar", "priest"])
            print(f"  T{turn_num:3d}: alive={row['alive']:4d} d={row['deaths']:3d} b={row['births']:3d} "
                  f"E[d]={row['expected_deaths']:6.1f} E[b]={row['expected_births']:5.2f} "
                  f"endemic={row['mean_endemic']:.3f}/{row['max_endemic']:.3f} "
                  f"fertile={fertile_eligible}/{row['fertile_range']} "
                  f"sat_near={row['sat_near_thresh']}")

        # Early exit on extinction
        if sim.last_tick_alive == 0:
            if verbose:
                print(f"  EXTINCTION at turn {turn_num}")
            break

    return age_hist, results


def print_age_histogram(hist: dict, label: str):
    total = hist.get("total_alive", 1)
    print(f"\n{label}:")
    print(f"  Young (0-19):       {hist.get('young_0_19', 0):5d} ({hist.get('young_0_19', 0)/total*100:.1f}%)")
    print(f"  Adult (20-59):      {hist.get('adult_20_59', 0):5d} ({hist.get('adult_20_59', 0)/total*100:.1f}%)")
    print(f"  Elder (60+):        {hist.get('elder_60_plus', 0):5d} ({hist.get('elder_60_plus', 0)/total*100:.1f}%)")
    print(f"  Fertile (16-45):    {hist.get('fertile_range_16_45', 0):5d} ({hist.get('fertile_range_16_45', 0)/total*100:.1f}%)")
    print(f"  Total:              {total:5d}")


def print_summary(all_results: list[list[dict]], probe: str, seeds: list[int]):
    """Print cross-seed summary statistics."""
    print(f"\n{'='*80}")
    print(f"SUMMARY — Probe {probe} — {len(seeds)} seeds")
    print(f"{'='*80}")

    extinction_turns = []
    alive_at_50 = []
    alive_at_100 = []
    birth_death_ratio_20 = []

    for results in all_results:
        # Extinction turn
        last_alive = max((r["turn"] for r in results if r["alive"] > 0), default=0)
        if results[-1]["alive"] == 0:
            extinction_turns.append(last_alive)

        # Population at turn 50
        t50 = [r for r in results if r["turn"] == 50]
        if t50:
            alive_at_50.append(t50[0]["alive"])

        # Population at turn 100
        t100 = [r for r in results if r["turn"] == 99]
        if t100:
            alive_at_100.append(t100[0]["alive"])

        # Birth/death ratio after first 20 turns (skip transient)
        after_20 = [r for r in results if 20 <= r["turn"] < 40]
        if after_20:
            total_births = sum(r["births"] for r in after_20)
            total_deaths = sum(r["deaths"] for r in after_20)
            if total_deaths > 0:
                birth_death_ratio_20.append(total_births / total_deaths)

    if extinction_turns:
        print(f"  Extinctions: {len(extinction_turns)}/{len(seeds)} seeds")
        print(f"  Extinction turn: mean={sum(extinction_turns)/len(extinction_turns):.0f} "
              f"min={min(extinction_turns)} max={max(extinction_turns)}")
    else:
        print(f"  Extinctions: 0/{len(seeds)} seeds")

    if alive_at_50:
        print(f"  Alive at T50: mean={sum(alive_at_50)/len(alive_at_50):.0f} "
              f"min={min(alive_at_50)} max={max(alive_at_50)}")
    if alive_at_100:
        print(f"  Alive at T100: mean={sum(alive_at_100)/len(alive_at_100):.0f} "
              f"min={min(alive_at_100)} max={max(alive_at_100)}")
    if birth_death_ratio_20:
        mean_ratio = sum(birth_death_ratio_20) / len(birth_death_ratio_20)
        print(f"  Birth/death ratio (T20-40): mean={mean_ratio:.3f} "
              f"min={min(birth_death_ratio_20):.3f} max={max(birth_death_ratio_20):.3f}")

    # Mean endemic severity across seeds at turn 10
    endemic_at_10 = []
    for results in all_results:
        t10 = [r for r in results if r["turn"] == 10]
        if t10:
            endemic_at_10.append(t10[0]["mean_endemic"])
    if endemic_at_10:
        print(f"  Mean endemic at T10: {sum(endemic_at_10)/len(endemic_at_10):.4f}")

    # Mean expected rates at turn 10
    exp_d = []
    exp_b = []
    for results in all_results:
        t10 = [r for r in results if r["turn"] == 10]
        if t10:
            exp_d.append(t10[0]["expected_deaths"])
            exp_b.append(t10[0]["expected_births"])
    if exp_d:
        print(f"  Expected deaths at T10: {sum(exp_d)/len(exp_d):.1f}")
        print(f"  Expected births at T10: {sum(exp_b)/len(exp_b):.2f}")


def main():
    parser = argparse.ArgumentParser(description="M53 Demographics Probe")
    parser.add_argument("--probe", choices=["baseline", "A", "B", "C"], default="baseline",
                        help="Probe type: baseline, A (no disease), B (lower mortality), C (higher fertility)")
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.probe in ("B", "C"):
        print(f"Probe {args.probe} requires Rust constant changes + rebuild.")
        print("  B: MORTALITY_ADULT 0.01 → 0.005 in agent.rs:31")
        print("  C: FERTILITY_BASE_FARMER 0.03 → 0.05, FERTILITY_BASE_OTHER 0.015 → 0.03 in agent.rs:41-42")
        print("Rebuild with: cargo build --release, then deploy DLL.")
        response = input("Constants already changed? (y/n): ").strip().lower()
        if response != "y":
            print("Aborting. Change constants first, rebuild, then re-run.")
            sys.exit(1)

    seeds = list(range(args.seeds))
    all_results = []
    all_histograms = []

    for seed in seeds:
        print(f"\n--- Seed {seed} (probe={args.probe}) ---")
        age_hist, results = run_probe(seed, args.turns, args.probe, verbose=args.verbose)
        all_histograms.append(age_hist)
        all_results.append(results)

        # Print initial age histogram for first seed
        if seed == 0:
            print_age_histogram(age_hist, "Initial age distribution (seed 0)")

        # Print first 5 turns detailed
        print("\n  Turn | Alive | Deaths (Y/A/E) | Births | E[D]   | E[B]  | Endemic    | Fertile | SatNear")
        print("  " + "-" * 95)
        for r in results[:5]:
            fertile_elig = sum(r[f"fertile_{o}"] for o in ["farmer", "soldier", "merchant", "scholar", "priest"])
            print(f"  {r['turn']:4d} | {r['alive']:5d} | {r['deaths']:3d} ({r['deaths_young']:2d}/{r['deaths_adult']:2d}/{r['deaths_elder']:2d}) "
                  f"| {r['births']:3d}    | {r['expected_deaths']:6.1f} | {r['expected_births']:5.2f} "
                  f"| {r['mean_endemic']:.3f}/{r['max_endemic']:.3f} "
                  f"| {fertile_elig:3d}/{r['fertile_range']:3d} | {r['sat_near_thresh']:3d}")

        # Print turns 10, 50
        for t in [10, 50]:
            matching = [r for r in results if r["turn"] == t]
            if matching:
                r = matching[0]
                fertile_elig = sum(r[f"fertile_{o}"] for o in ["farmer", "soldier", "merchant", "scholar", "priest"])
                print(f"  {r['turn']:4d} | {r['alive']:5d} | {r['deaths']:3d} ({r['deaths_young']:2d}/{r['deaths_adult']:2d}/{r['deaths_elder']:2d}) "
                      f"| {r['births']:3d}    | {r['expected_deaths']:6.1f} | {r['expected_births']:5.2f} "
                      f"| {r['mean_endemic']:.3f}/{r['max_endemic']:.3f} "
                      f"| {fertile_elig:3d}/{r['fertile_range']:3d} | {r['sat_near_thresh']:3d}")

    print_summary(all_results, args.probe, seeds)


if __name__ == "__main__":
    main()
