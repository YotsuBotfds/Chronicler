#!/usr/bin/env python3
"""Synthetic worlds for the ablation oracles (needs method 7, cohort method 4).

Each world draws replicate batches of seeds forked as the gate forks them
(``chronicler.ablation_arms``) and, per fork, the agents of each cohort (a
need below its threshold; a community member), their frailty, and their
events over the window in the plain arm and in the ablated arm. The plain
arm's hazard is the ablated arm's times ``1 + effect`` for the cohort (the
term's effect); nothing else differs between the arms in expectation.

The arms share their random numbers at the fork (the decision draws are the
same until behaviour differs) and drift apart over the window: each turn an
agent's draw is shared with probability ``exp(-(t-1) / tau)``, and each arm
gets its own world-level shock per turn (log-normal, its spread growing as
the draws decorrelate: wars, famines and uprisings that happen in one arm
only). Seeds and forks differ in their base rates. Exposure (how often a
fork has a cohort and how large) and base rates come from the gate worlds'
probes (docs/integration/ablation-oracles.md, section 4).

The verdict reads only the per-seed tallies (cohort size, plain events,
ablated events): ``validation_ablation.ablation_ratio`` and ``judge`` score
them exactly as the oracles do. ``--check-pipeline`` also builds sidecar and
arm structures for a few batches and checks that the oracle components
(``needs_ablation_component``, ``cohort_ablation_result``) give the same
tallies and verdicts.

Usage: synth_ablation_oracles.py [--replicates N] [--scales a,b] [--worlds a,b]
                                 [--out report.json] [--check-pipeline]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chronicler.ablation_arms import ABLATION_WINDOW_TURNS  # noqa: E402
from chronicler.validation_ablation import (  # noqa: E402
    COHORT_ABLATION_MIN_EFFECT,
    NEEDS_ABLATION_MIN_EFFECT,
    NEEDS_ABLATION_PAIRINGS,
    ablation_ratio,
    judge,
)

W = ABLATION_WINDOW_TURNS
TAU = 5.0  # turns for the shared draws to decay to 1/e

# Cohort exposure per fork: q = share of forks with a cohort, f = mean share
# of the fork's agents in it (drawn uniformly in 0.5 f .. 1.5 f), h = base
# hazard per turn, sigma = spread of the arms' world shocks at full
# divergence (rebellions come in regional waves: larger).
EXPOSURE = {
    "template": {
        "agents": 170,
        "safety": (0.07, 0.15, 0.054, 0.5),
        "material": (0.45, 0.22, 0.056, 0.5),
        "social": (0.88, 0.02, 0.058, 0.5),
        "spiritual": (0.73, 0.18, 0.057, 0.5),
        "autonomy": (0.25, 0.05, 0.135, 1.0),
        "purpose": (1.00, 0.18, 0.061, 0.5),
        "members": (1.00, 0.85, 0.045, 0.5),
    },
    "procedural": {
        "agents": 550,
        "safety": (0.28, 0.02, 0.06, 0.5),
        "material": (0.72, 0.05, 0.08, 0.5),
        "social": (1.00, 0.09, 0.074, 0.5),
        "spiritual": (1.00, 0.37, 0.075, 0.5),
        "autonomy": (0.61, 0.08, 0.127, 1.0),
        "purpose": (1.00, 0.12, 0.045, 0.5),
        "members": (1.00, 0.85, 0.045, 0.5),
    },
    # Measured on the full gates of docs/integration/ablation-oracles.md
    # (section 3; main 7c44ed8 with the arms): per pairing, q from the seeds
    # with a cohort over their forks (independent forks), the mean cohort of a
    # fork that has one over its agents, and the ablated arm's events per
    # agent-turn (docs/integration/community-anchoring.md, section 6).
    "template_gate": {
        "agents": 185,
        "safety": (0.030, 0.104, 0.045, 0.5),
        "material": (0.527, 0.184, 0.051, 0.5),
        "social": (1.00, 0.021, 0.057, 0.5),
        "spiritual": (0.650, 0.225, 0.049, 0.5),
        "autonomy": (0.155, 0.239, 0.087, 1.0),
        "purpose": (1.00, 0.175, 0.047, 0.5),
        "members": (1.00, 0.862, 0.054, 0.5),
    },
    "procedural_gate": {
        "agents": 542,
        "safety": (0.146, 0.0152, 0.050, 0.5),
        "material": (0.400, 0.0166, 0.065, 0.5),
        "social": (1.00, 0.0765, 0.060, 0.5),
        "spiritual": (1.00, 0.415, 0.057, 0.5),
        "autonomy": (0.510, 0.123, 0.076, 1.0),
        "purpose": (1.00, 0.129, 0.035, 0.5),
        "members": (1.00, 0.845, 0.063, 0.5),
    },
}
SCALES = {
    # name: (world, seeds, forks per seed)
    "template_full": ("template", 200, 4),
    "procedural_full": ("procedural", 100, 2),
    "template_subset": ("template", 20, 1),
    "procedural_subset": ("procedural", 20, 1),
    # Gate exposure (measured): the method 7 designs and the fork spacings
    # weighed for method 8 (forks every 100, 50 or 20 turns from turn 100).
    "template_gate_every100": ("template_gate", 200, 4),
    "procedural_gate_every100": ("procedural_gate", 100, 2),
    "procedural_gate_every50": ("procedural_gate", 100, 4),
    "procedural_gate_every20": ("procedural_gate", 100, 9),
    "procedural_gate_200_seeds": ("procedural_gate", 200, 2),
}
# name: (needs effect, cohort effect, age confound): the plain arm's rate over
# the ablated arm's minus 1, for every needs pairing / for members' migration.
WORLDS = {
    "null": (0.0, 0.0, False),
    "null_age_confound": (0.0, 0.0, True),
    "reversed": (-0.20, 0.20, False),
    "below_minimum": (0.05, -0.05, False),
    "at_minimum": (NEEDS_ABLATION_MIN_EFFECT, -COHORT_ABLATION_MIN_EFFECT, False),
    "effect_0.15": (0.15, -0.20, False),
    "effect_0.20": (0.20, -0.25, False),
    "effect_0.30": (0.30, -0.30, False),
}
REQUIRED = [need for need, _t, _e, required in NEEDS_ABLATION_PAIRINGS if required]
PAIRINGS = [need for need, *_ in NEEDS_ABLATION_PAIRINGS]


def _fork_counts(rng, n, h, effect, sigma, seed_mult, age_confound):
    """(plain, ablated) events of a cohort of ``n`` over the window."""
    if n == 0:
        return 0, 0
    frailty = rng.gamma(1.0, 1.0, n)
    if age_confound:
        # Cohort members are old and the old move less: lower hazards, both arms.
        frailty *= rng.uniform(0.3, 0.8, n)
    base = (h * seed_mult * frailty)[:, None]
    rho = np.exp(-np.arange(W) / TAU)
    spread = sigma * np.sqrt(1.0 - rho)
    shock_plain = np.exp(rng.normal(0.0, 1.0, W) * spread)[None, :]
    shock_ablated = np.exp(rng.normal(0.0, 1.0, W) * spread)[None, :]
    u_plain = rng.random((n, W))
    shared = rng.random((n, W)) < rho[None, :]
    u_ablated = np.where(shared, u_plain, rng.random((n, W)))
    hp = np.minimum(base * (1.0 + effect) * shock_plain, 1.0)
    ha = np.minimum(base * shock_ablated, 1.0)
    return int((u_plain < hp).sum()), int((u_ablated < ha).sum())


def draw_batch(rng, scale: str, world: str) -> dict[str, list[tuple[int, int, int]]]:
    """Per cohort definition, the per-seed (cohort, plain, ablated) tallies of one batch."""
    kind, seeds, forks = SCALES[scale]
    params = EXPOSURE[kind]
    needs_effect, cohort_effect, age_confound = WORLDS[world]
    tallies = {name: [] for name in PAIRINGS + ["members"]}
    for _seed in range(seeds):
        seed_mult = rng.lognormal(0.0, 0.4)
        per = {name: [0, 0, 0] for name in tallies}
        for _fork in range(forks):
            agents = max(10, int(round(params["agents"] * rng.lognormal(0.0, 0.3))))
            fork_mult = seed_mult * rng.lognormal(0.0, 0.3)
            for name in tallies:
                q, f, h, sigma = params[name]
                if rng.random() >= q:
                    continue
                n = int(rng.binomial(agents, min(1.0, rng.uniform(0.5 * f, 1.5 * f))))
                effect = cohort_effect if name == "members" else needs_effect
                p, a = _fork_counts(rng, n, h, effect, sigma, fork_mult, age_confound)
                per[name][0] += n
                per[name][1] += p
                per[name][2] += a
        for name, tally in per.items():
            tallies[name].append(tuple(tally))
    return tallies


def score(tallies) -> dict:
    out = {}
    for need in PAIRINGS:
        stats = ablation_ratio(tallies[need])
        status, _failed = judge(stats, "increase", NEEDS_ABLATION_MIN_EFFECT)
        out[need] = (status, stats)
    out["needs_component"] = ("PASS" if all(out[n][0] == "PASS" for n in REQUIRED) else "FAIL", None)
    stats = ablation_ratio(tallies["members"])
    status, _failed = judge(stats, "decrease", COHORT_ABLATION_MIN_EFFECT)
    out["cohort"] = (status, stats)
    return out


def run(replicates: int, scales: list[str], worlds: list[str], seed: int = 20261027, out: Path | None = None) -> dict:
    results: dict = {}
    for scale in scales:
        for world in worlds:
            rng = np.random.default_rng([seed, list(SCALES).index(scale), list(WORLDS).index(world)])
            needs_effect, cohort_effect, _age = WORLDS[world]
            acc: dict = {}
            start = time.monotonic()
            for _rep in range(replicates):
                scored = score(draw_batch(rng, scale, world))
                for name, (status, stats) in scored.items():
                    entry = acc.setdefault(name, {"pass": 0, "bound_clears": 0, "covered": 0, "measured": 0,
                                                  "rr": [], "se": []})
                    entry["pass"] += status == "PASS"
                    if stats is None or stats.get("rate_ratio") is None or stats.get("interval") is None:
                        continue
                    true_rr = 1.0 + (cohort_effect if name == "cohort" else needs_effect)
                    entry["measured"] += 1
                    entry["rr"].append(stats["rate_ratio"])
                    entry["se"].append(stats["standard_error"])
                    if name == "cohort":
                        entry["bound_clears"] += stats["upper_bound"] < 1.0
                    else:
                        entry["bound_clears"] += stats["lower_bound"] > 1.0
                    lo, hi = stats["interval"]
                    entry["covered"] += lo <= true_rr <= hi
            summary = {}
            for name, entry in acc.items():
                measured = entry["measured"]
                summary[name] = {
                    "pass_rate": round(entry["pass"] / replicates, 4),
                    "bound_clears_no_effect": round(entry["bound_clears"] / measured, 4) if measured else None,
                    "interval_coverage": round(entry["covered"] / measured, 4) if measured else None,
                    "measured_batches": measured,
                    "mean_rate_ratio": round(float(np.mean(entry["rr"])), 4) if entry["rr"] else None,
                    "sd_rate_ratio": round(float(np.std(entry["rr"])), 4) if entry["rr"] else None,
                    "mean_se": round(float(np.mean(entry["se"])), 4) if entry["se"] else None,
                }
            results.setdefault(scale, {})[world] = {
                "needs_effect": needs_effect, "cohort_effect": cohort_effect,
                "replicates": replicates, "seconds": round(time.monotonic() - start, 1), "by": summary,
            }
            comp = summary["needs_component"]["pass_rate"]
            coh = summary["cohort"]["pass_rate"]
            print(f"{scale:18s} {world:18s} needs component PASS {comp:.3f}  cohort PASS {coh:.3f}", flush=True)
            if out is not None:
                out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return results


def check_pipeline(rng_seed: int = 7, batches: int = 3) -> None:
    """Rebuild sidecars and arm structures for a few batches and check the
    oracle components give the tallies and verdicts ``score`` gives."""
    from chronicler.validation_ablation import cohort_ablation_result, needs_ablation_component
    from chronicler.validation_io import EVENT_NAME_TO_CODE

    rng = np.random.default_rng(rng_seed)
    thresholds = {need: threshold for need, threshold, *_ in NEEDS_ABLATION_PAIRINGS}
    events_of = {need: event for need, _t, event, _r in NEEDS_ABLATION_PAIRINGS}
    for batch in range(batches):
        seed_runs, needs_arm, kin_arm = [], {"window": W, "forks": {}}, {"window": W, "forks": {}}
        expect = {name: [] for name in PAIRINGS + ["members"]}
        next_id = 1
        for seed in range(6):
            run = {"seed": seed, "events": [], "needs_columns": {k: [] for k in
                   ("turn", "agent_id", *thresholds)}, "relationship_columns": None, "memory_columns": None}
            per = {name: [0, 0, 0] for name in expect}
            for fork in (100, 200):
                ids = list(range(next_id, next_id + 30))
                next_id += 30
                cohort = {need: set(rng.choice(ids, size=int(rng.integers(0, 8)), replace=False).tolist())
                          for need in PAIRINGS}
                for agent in ids:
                    run["needs_columns"]["turn"].append(fork)
                    run["needs_columns"]["agent_id"].append(agent)
                    for need, threshold in thresholds.items():
                        run["needs_columns"][need].append(threshold - 0.1 if agent in cohort[need] else threshold + 0.2)
                ablated_turns: dict = {}
                for need in PAIRINGS:
                    code = EVENT_NAME_TO_CODE[events_of[need]]
                    for agent in sorted(cohort[need]):
                        for arm in ("plain", "ablated"):
                            for turn in sorted(rng.choice(np.arange(fork + 1, fork + W + 1),
                                                          size=int(rng.integers(0, 3)), replace=False).tolist()):
                                if arm == "plain":
                                    run["events"].append({"turn": turn, "agent_id": agent, "event_type": code})
                                else:
                                    ablated_turns.setdefault((agent, code), []).append(turn)
                needs_arm["forks"].setdefault(seed, {})[fork] = ablated_turns
                kin_arm["forks"].setdefault(seed, {})[fork] = ablated_turns
            # Expected tallies straight from the events (an agent may be in several cohorts).
            for fork in (100, 200):
                rows = [i for i, t in enumerate(run["needs_columns"]["turn"]) if t == fork]
                for need in PAIRINGS:
                    code = EVENT_NAME_TO_CODE[events_of[need]]
                    members = [run["needs_columns"]["agent_id"][i] for i in rows
                               if run["needs_columns"][need][i] < thresholds[need]]
                    p = sum(1 for e in run["events"] if e["agent_id"] in members and e["event_type"] == code
                            and fork < e["turn"] <= fork + W)
                    a = sum(len(needs_arm["forks"][seed][fork].get((m, code), ())) for m in members)
                    per[need][0] += len(members)
                    per[need][1] += p
                    per[need][2] += a
            for name in PAIRINGS:
                expect[name].append(tuple(per[name]))
            seed_runs.append(run)
        component = needs_ablation_component(seed_runs, needs_arm)
        scored = score({**expect, "members": [(0, 0, 0)]})
        for need in PAIRINGS:
            got = component["by_pairing"][need]
            want = scored[need][1]
            for key in ("cohort", "plain_events", "ablated_events", "rate_ratio", "lower_bound", "upper_bound"):
                assert got[key] == want[key], (need, key, got[key], want[key])
            assert got["status"] == scored[need][0]
        cohort = cohort_ablation_result(seed_runs, kin_arm)
        assert cohort["status"] in ("PASS", "FAIL")
    print(f"pipeline check: {batches} batches, component tallies equal the per-seed scoring")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--replicates", type=int, default=200)
    parser.add_argument("--scales", default=",".join(SCALES))
    parser.add_argument("--worlds", default=",".join(WORLDS))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check-pipeline", action="store_true")
    args = parser.parse_args(argv)
    if args.check_pipeline:
        check_pipeline()
    results = run(args.replicates, args.scales.split(","), args.worlds.split(","), out=args.out)
    if args.out:
        args.out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
