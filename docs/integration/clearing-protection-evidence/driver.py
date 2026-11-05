"""RS5 clearing protection: short development runs with the real native extension.

Runs template seeds x arms (switch off, enforced, cost_only) with
``--simulate-only`` in one process, auditing every settled Phase 9:

* every receipt comes from the native tick (``source == "native"``);
* the accumulator ``keep`` treasury debits booked by the settlement equal the
  receipts' charges, per civilization and turn (money closure);
* per region-turn cover change of protected regions (enforced p = 1) against
  controlled, forested, unprotected regions whose clearing was active in the
  same tick (both read from the authoritative native receipts).

Usage (native venv, from the repository root)::

    PYTHONHASHSEED=0 RAYON_NUM_THREADS=1 PYTHONPATH=src python \
        docs/integration/clearing-protection-evidence/driver.py OUT_DIR [--turns 100] [--seeds 1 2 3] \
        [--agents hybrid off]

Writes ``OUT_DIR/metrics.jsonl`` (one row per run) and prints a summary.
Development cohort only: no held seeds, nothing tuned.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def run(seed: int, turns: int, agents: str, mode: str | None, out: Path) -> dict:
    from chronicler import clearing_protection as cp
    from chronicler.main import execute_run

    rows = {"protected": [], "unprotected": []}
    audit = {"turns": 0, "charged": 0, "booked": 0, "mismatches": 0, "non_native": 0}
    real_after = cp.after_ecology

    def after(world, acc):
        state = world.livelihoods.clearing_protection
        plan = state._plan
        post = {rid: world.regions[rid].ecology.forest_cover for rid in range(len(world.regions))}
        protected = {row.protection.region_id: row for row in plan.rows}
        start = acc.checkpoint() if acc is not None else 0
        events = real_after(world, acc)
        booked: dict[int, int] = {}
        for change in (acc._changes[start:] if acc is not None else []):
            assert change.stat == "treasury" and change.category == "keep", change
            booked[change.civ_id] = booked.get(change.civ_id, 0) - int(change.delta)
        charged: dict[int, int] = {}
        for r in state.frame:
            audit["non_native"] += r.source != "native"
            if r.charged:
                charged[r.payer] = charged.get(r.payer, 0) + r.charged
            if r.p_applied == 1.0 and r.clearing_active:
                rows["protected"].append(r.cover_after - r.cover_before)
        audit["mismatches"] += booked != charged
        audit["charged"] += sum(charged.values())
        audit["booked"] += sum(booked.values())
        audit["turns"] += 1
        # Unprotected, controlled regions forested before the tick whose
        # clearing fired (the native receipt): post-tick minus pre-tick cover.
        for rid, (active, _) in enumerate(plan.receipts):
            if rid in protected or not active:
                continue
            pre = plan_covers.get(rid)
            if pre is not None and pre >= cp.MIN_COVER:
                rows["unprotected"].append(post[rid] - pre)
        return events

    plan_covers: dict[int, float] = {}
    real_before = cp.before_ecology

    def before_hook(world, acc):
        plan_covers.clear()
        for rid, region in enumerate(world.regions):
            if region.controller is not None:
                plan_covers[rid] = region.ecology.forest_cover
        return real_before(world, acc)

    cp.after_ecology, cp.before_ecology = after, before_hook
    folder = out / f"seed{seed}_{agents}_{mode or 'off'}"
    args = argparse.Namespace(
        seed=seed, turns=turns, civs=4, regions=8, output=str(folder / "chronicle.md"),
        state=str(folder / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, simulate_only=True, agents=agents, tuning_overrides={},
        clearing_protection=None if mode is None else True, clearing_protection_mode=mode,
    )
    try:
        execute_run(args)
    finally:
        cp.after_ecology, cp.before_ecology = real_after, real_before
    state = json.loads((folder / "state.json").read_text())
    regions = state["regions"]
    events = [e for e in state.get("events_timeline", []) if e.get("event_type") == "terrain_transition"]
    metrics = {
        "seed": seed, "turns": turns, "agents": agents, "mode": mode or "off",
        "final_mean_cover": round(math.fsum(r["ecology"]["forest_cover"] for r in regions) / len(regions), 6),
        "final_capacity": sum(r["carrying_capacity"] for r in regions),
        "forest_regions_final": sum(r["terrain"] == "forest" for r in regions),
        "terrain_transitions": len(events),
    }
    cpst = state.get("livelihoods", {}).get("clearing_protection") if state.get("livelihoods") else None
    if cpst is not None:
        c = cpst["counters"]
        metrics.update({k: c[k] for k in (
            "eligible_region_turns", "adopted", "protected_region_turns", "clearing_active_turns",
            "required", "paid_planned", "charged", "full_funded_turns", "partial_funded_turns",
            "zero_funded_turns", "cover_not_cleared", "cover_would_keep", "adoption_over_limit",
            "adoption_unaffordable", "ended_controller_changed", "ended_cover_lost", "ended_idle",
            "ended_unfunded")})
        metrics["audit"] = audit
        for name, values in rows.items():
            metrics[f"{name}_active_region_turns"] = len(values)
            metrics[f"{name}_mean_cover_change"] = (round(math.fsum(values) / len(values), 6)
                                                    if values else None)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--agents", nargs="+", default=["hybrid", "off"])
    a = parser.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    import chronicler_agents
    from chronicler_agents import chronicler_agents as compiled
    print("extension", compiled.__file__)
    assert isinstance(chronicler_agents.EcologySimulator, type)
    with (a.out / "metrics.jsonl").open("w") as fh:
        for agents in a.agents:
            for seed in a.seeds:
                for mode in (None, "enforced", "cost_only"):
                    m = run(seed, a.turns, agents, mode, a.out / "runs")
                    fh.write(json.dumps(m, sort_keys=True) + "\n")
                    print(json.dumps(m, sort_keys=True))


if __name__ == "__main__":
    main()
