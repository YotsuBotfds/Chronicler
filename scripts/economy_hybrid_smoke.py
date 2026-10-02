"""Deterministic full-hybrid stock-accounting smoke test, with no narration.

Unlike economy_coupling_experiment.py's isolated abstract-trade interventions,
this runs complete turns with the actual native merchant travel/delivery path.
The wrapper only observes the Phase 2 boundary; it does not replace any logic.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler.action_engine import ActionEngine
from chronicler.agent_bridge import AgentBridge
import chronicler.economy as economy
from chronicler.economy import FIXED_GOODS
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world


def run(seed: int, turns: int = 30) -> dict:
    world = generate_world(seed=seed)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    initial = sum(r.population for r in world.regions)
    observations = []
    reconstruct = economy.reconstruct_economy_result

    def stock_total():
        return sum(r.stockpile.goods.get(g, 0.0) for r in world.regions for g in FIXED_GOODS)

    def observed_reconstruction(*args, **kwargs):
        before = stock_total()
        result = reconstruct(*args, **kwargs)
        after = stock_total()
        c = result.conservation
        sinks = sum((c[k] or 0.0) for k in (
            "consumption", "transit_loss", "storage_loss", "cap_overflow", "in_transit_delta",
        ))
        residual = before + c["production"] + c["clamp_floor_loss"] - after - sinks
        observations.append({
            "turn": world.turn,
            "mean_food_sufficiency": sum(result.food_sufficiency.values()) / len(result.food_sufficiency),
            "production": c["production"], "consumption": c["consumption"],
            "food_imports": sum(v["food"] for v in result.imports_by_region.values()),
            "stock_total": after, "ledger_residual": residual,
            "floor_clamp": c["clamp_floor_loss"],
            "physical_delivery_ledger": c["in_transit_delta"] is not None,
        })
        assert abs(residual) < 0.002, (seed, world.turn, residual)
        assert c["clamp_floor_loss"] < 0.00001, (seed, world.turn, c)
        assert all(math.isfinite(v) and v >= 0 for r in world.regions for v in r.stockpile.goods.values())
        return result

    with patch("chronicler.economy.reconstruct_economy_result", side_effect=observed_reconstruction):
        for turn in range(turns):
            engine = ActionEngine(world)
            run_turn(
                world, lambda civ, w: engine.select_action(civ, seed=w.seed),
                lambda w, events: "", seed=seed + turn, agent_bridge=bridge,
            )
    # Cold-start and later ticks must both use the physical ledger; falling
    # back to abstract trade would create imports before any merchant traveled.
    physical_ticks = sum(o["physical_delivery_ledger"] for o in observations)
    assert physical_ticks == turns, "A hybrid tick fell back to abstract trade"
    events = Counter(event.event_type for event in world.events_timeline)
    return {
        "seed": seed, "turns": turns, "initial_population": initial,
        "final_population": sum(r.population for r in world.regions),
        "famine_events": events["famine"],
        "max_ledger_residual": max(abs(o["ledger_residual"]) for o in observations),
        "max_floor_clamp": max(o["floor_clamp"] for o in observations),
        "food_imports": sum(o["food_imports"] for o in observations),
        "physical_delivery_ticks": physical_ticks,
        "observations": observations,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 42])
    parser.add_argument("--turns", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.turns <= 0:
        parser.error("--turns must be positive")
    rows = [run(seed, args.turns) for seed in args.seeds]
    assert run(args.seeds[-1], args.turns) == rows[-1], "Same-seed hybrid replay diverged"
    report = {"mode": "native full hybrid", "repeat_last_seed_exact": True, "runs": rows}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    summary = {**report, "runs": [{k: v for k, v in row.items() if k != "observations"} for row in rows]}
    print(json.dumps(summary, indent=2))
