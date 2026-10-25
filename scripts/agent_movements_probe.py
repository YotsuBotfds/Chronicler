#!/usr/bin/env python3
"""Movement distributions over a set of worlds (``--agent-movements``).

``agent_movements_probe.py OUT_DIR --seeds 42-51 [--turns 500] [--parallel 2]
[-- extra chronicler.main flags]``

Runs each seed (hybrid, ``--simulate-only``, ``--agent-movements``, the gate's
default world) in a child process that records the native grievance census
every ``--every`` turns, then prints and writes ``probe.json``:

* the census: the share of a region's adults aggrieved per creed (region
  samples with at least 5 adults), mean and quantiles, and how many samples
  reach the founding share;
* per world: movements founded, significant ones (a demand made and a peak
  of at least ``--significant`` members), by creed; demands, grants,
  refusals, crackdowns, risings, secessions, schisms; lasting reforms
  enacted, repealed by reason, restored; leaders; how the movements ended;
* the conditions cited by the foundings (famine, epidemic, occupation,
  conquest, persecution, a repealed reform).

Child mode (``--child OUT SEED EVERY -- ARGS``) is internal. Outputs stay in
OUT_DIR; delete them after reading the report.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CREEDS = ("commons", "liberty", "sect")
CAUSES = ("famine", "pandemic", "occupation", "conquest", "persecution", "reform_repealed")


def _child(out: Path, every: int, argv: list[str]) -> int:
    import chronicler.agent_movements as M
    from chronicler import main as entry

    samples: list[list] = []
    original = M._grievance_census

    def recording(agent_bridge, nreg):
        census = original(agent_bridge, nreg)
        world_turn = recording.turn
        if census is not None and world_turn is not None and world_turn % every == 0:
            adults, aggrieved = census
            for r in range(nreg):
                if adults[r]:
                    samples.append([world_turn, r, adults[r], *aggrieved[r]])
        return census

    recording.turn = None
    original_tick = M.tick_agent_movements

    def tick(world, *a, **kw):
        recording.turn = world.turn
        return original_tick(world, *a, **kw)

    M._grievance_census = recording
    M.tick_agent_movements = tick
    sys.argv = ["chronicler.main", *argv]
    try:
        entry.main()
    finally:
        (out / "census.json").write_text(json.dumps(samples))
    return 0


def _quantiles(values: list[float]) -> dict:
    if not values:
        return {}
    v = sorted(values)
    pick = lambda q: round(v[min(len(v) - 1, int(q * len(v)))], 4)  # noqa: E731
    return {"n": len(v), "mean": round(sum(v) / len(v), 4), "p50": pick(0.5), "p90": pick(0.9),
            "p99": pick(0.99), "max": round(v[-1], 4)}


def _load_state(run: Path):
    from chronicler.models import WorldState
    return WorldState.load(run / "state.json")


def _summarize_world(run: Path, significant: int) -> dict:
    from chronicler.agent_movements_state import END_NAMES, REPEAL_NAMES
    world = _load_state(run)
    state = world.agent_movements
    by_id = {e.event_id: e for e in world.events_timeline if e.event_id}
    out = {"seed": world.seed, "movements": len(state.movements), "significant": 0,
           "by_creed": {c: 0 for c in CREEDS}, "significant_by_creed": {c: 0 for c in CREEDS},
           "ends": {}, "counters": {k: v for k, v in state.counters.items() if v},
           "repeals": {}, "reforms_in_force": 0, "founding_causes": {c: 0 for c in CAUSES},
           "foundings_with_cause": 0, "peaks": []}
    for m in state.movements:
        creed = CREEDS[m.creed]
        out["by_creed"][creed] += 1
        out["peaks"].append(m.peak_members)
        if m.demands >= 1 and m.peak_members >= significant:
            out["significant"] += 1
            out["significant_by_creed"][creed] += 1
        if m.end:
            out["ends"][END_NAMES[m.end]] = out["ends"].get(END_NAMES[m.end], 0) + 1
        founded = next((eid for _t, kind, eid in m.history if kind == "founded"), "")
        ev = by_id.get(founded)
        seen = set()
        for cause in (ev.causes if ev is not None else []):
            src = by_id.get(cause)
            kind = src.event_type if src is not None else ""
            for c in CAUSES:
                if kind.startswith(c) or (c == "famine" and kind in ("famine", "dearth")):
                    seen.add(c)
        for c in seen:
            out["founding_causes"][c] += 1
        out["foundings_with_cause"] += bool(seen)
    for r in getattr(state, "reforms", []):
        if r.repeal:
            name = REPEAL_NAMES[r.repeal]
            out["repeals"][name] = out["repeals"].get(name, 0) + 1
        else:
            out["reforms_in_force"] += 1
    return out


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--child":
        out, _seed, every = Path(argv[1]), argv[2], int(argv[3])
        rest = argv[argv.index("--") + 1:] if "--" in argv else []
        return _child(out, every, rest)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--seeds", default="42-51")
    parser.add_argument("--turns", type=int, default=500)
    parser.add_argument("--parallel", type=int, default=2)
    parser.add_argument("--every", type=int, default=10)
    parser.add_argument("--significant", type=int, default=10)
    parser.add_argument("--summarize-only", action="store_true")
    args, extra = parser.parse_known_args(argv)
    if extra and extra[0] == "--":
        extra = extra[1:]
    lo, _, hi = args.seeds.partition("-")
    seeds = list(range(int(lo), int(hi or lo) + 1))
    args.out.mkdir(parents=True, exist_ok=True)

    def run(seed: int) -> int:
        run_dir = args.out / f"seed_{seed}"
        run_dir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, __file__, "--child", str(run_dir), str(seed), str(args.every), "--",
               "--seed", str(seed), "--turns", str(args.turns), "--agents", "hybrid",
               "--simulate-only", "--agent-movements", "--output", str(run_dir / "chronicle.md"),
               "--state", str(run_dir / "state.json"), *extra]
        env = dict(os.environ, PYTHONHASHSEED="0")
        with open(run_dir / "log.txt", "w") as log:
            return subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env).returncode

    if not args.summarize_only:
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            codes = list(pool.map(run, seeds))
        if any(codes):
            print("failed seeds:", [s for s, c in zip(seeds, codes) if c])
    shares = {c: [] for c in CREEDS}
    reach = {c: 0 for c in CREEDS}
    worlds = []
    for seed in seeds:
        run_dir = args.out / f"seed_{seed}"
        census = json.loads((run_dir / "census.json").read_text()) if (run_dir / "census.json").exists() else []
        for _turn, _r, adults, *agg in census:
            if adults < 5:
                continue
            for c, a in zip(CREEDS, agg):
                shares[c].append(a / adults)
                reach[c] += a / adults >= 0.20 and a >= 5
        if (run_dir / "state.json").exists():
            worlds.append(_summarize_world(run_dir, args.significant))
    n = max(1, len(worlds))
    totals: dict = {}
    for w in worlds:
        for key in ("movements", "significant", "reforms_in_force", "foundings_with_cause"):
            totals[key] = totals.get(key, 0) + w[key]
        for group in ("by_creed", "significant_by_creed", "ends", "counters", "repeals", "founding_causes"):
            for k, v in w[group].items():
                totals.setdefault(group, {})[k] = round(totals.setdefault(group, {}).get(k, 0) + v, 3)
    report = {
        "seeds": seeds, "turns": args.turns, "extra": extra, "worlds": len(worlds),
        "census": {c: {**_quantiles(shares[c]), "at_founding_share": reach[c]} for c in CREEDS},
        "per_world": {k: round(v / n, 2) for k, v in totals.items() if not isinstance(v, dict)},
        "per_world_groups": {g: {k: round(v / n, 2) for k, v in d.items()}
                             for g, d in totals.items() if isinstance(d, dict)},
        "significant_per_world": [w["significant"] for w in worlds],
        "movements_per_world": [w["movements"] for w in worlds],
        "worlds_detail": worlds,
    }
    (args.out / "probe.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "worlds_detail"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
