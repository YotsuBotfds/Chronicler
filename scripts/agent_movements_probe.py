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


#: Threshold grid of the needs sample (``--grid``): satisfaction, and the
#: creed need (material, autonomy, spiritual).
GRID_SAT = (0.40, 0.45, 0.50)
GRID_NEED = ((0.35, 0.40, 0.45, 0.50, 0.55), (0.40, 0.45, 0.50, 0.55, 0.60), (0.35, 0.40, 0.45))
FLAGS = ("famine", "foreign", "persecuted", "minority")


def _region_flags(world, ri: int) -> tuple[bool, ...]:
    """Bad conditions of a region: an open famine episode; occupied or
    conquered within 20 turns; persecution; a faith other than the ruler's."""
    from chronicler import provenance as prov
    region = world.regions[ri]
    name = region.name
    civ = world.civ_map.get(region.controller) if region.controller else None
    famine = prov.open_episode(world, "famine", name) is not None
    foreign = (region.occupied_by is not None
               or prov.recall(world, prov.key("conquest", name), within=20) is not None)
    persecuted = bool(getattr(region, "persecution_intensity", 0.0))
    minority = (civ is not None and region.majority_belief not in (None, 255)
                and region.majority_belief != getattr(civ, "civ_majority_faith", 255))
    return famine, foreign, persecuted, minority


def _needs_sample(world, agent_bridge, phase10, grid: dict) -> None:
    """Per region with 5+ adults: whether the aggrieved share of each creed
    reaches the founding share under each grid threshold, by condition."""
    import numpy as np
    sim = getattr(agent_bridge, "_sim", None)
    rows = getattr(phase10, "agents", None) if phase10 is not None else None
    if sim is None or rows is None or not hasattr(sim, "get_all_needs"):
        return
    import pyarrow as pa
    needs = pa.record_batch(sim.get_all_needs())
    arrays = rows.arrays("id", "age")
    if arrays is None:
        return
    ids, ages = (np.asarray(a, dtype=np.int64) for a in arrays)
    age_of = dict(zip(ids.tolist(), ages.tolist()))
    nid = np.asarray(needs.column("agent_id").to_numpy(), dtype=np.int64)
    adult = np.array([age_of.get(int(i), 0) >= 16 for i in nid], dtype=bool)
    region = np.asarray(needs.column("region").to_numpy(), dtype=np.int64)[adult]
    sat = np.asarray(needs.column("satisfaction").to_numpy())[adult]
    creed_needs = [np.asarray(needs.column(c).to_numpy())[adult] for c in ("material", "autonomy", "spiritual")]
    nreg = len(world.regions)
    adults = np.bincount(region, minlength=nreg)
    flags = [_region_flags(world, r) for r in range(nreg)]
    for c, values in enumerate(creed_needs):
        for s in GRID_SAT:
            for n in GRID_NEED[c]:
                mask = (sat < s) & (values < n)
                agg = np.bincount(region[mask], minlength=nreg)
                for r in range(nreg):
                    if adults[r] < 5:
                        continue
                    hit = int(bool(agg[r] >= 5 and agg[r] / adults[r] >= 0.20))
                    key = f"{CREEDS[c]}|{s}|{n}"
                    cell = grid.setdefault(key, {"all": [0, 0], **{f: [0, 0] for f in FLAGS}, "good": [0, 0]})
                    cell["all"][0] += hit
                    cell["all"][1] += 1
                    bad = False
                    for f, on in zip(FLAGS, flags[r]):
                        if on:
                            bad = True
                            cell[f][0] += hit
                            cell[f][1] += 1
                    if not bad:
                        cell["good"][0] += hit
                        cell["good"][1] += 1


def _child(out: Path, every: int, argv: list[str], grid_on: bool = False) -> int:
    import chronicler.agent_movements as M
    from chronicler import main as entry

    samples: list[list] = []
    grid: dict = {}
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

    foundings: list[list] = []
    base: dict[str, list[int]] = {"regions": [0], **{f: [0] for f in FLAGS}, "good": [0]}

    def tick(world, *a, **kw):
        recording.turn = world.turn
        state = world.agent_movements
        before = len(state.movements) if state is not None else 0
        if world.turn % every == 0:
            if grid_on:
                _needs_sample(world, kw.get("agent_bridge"), kw.get("phase10"), grid)
            for r in range(len(world.regions)):
                if world.regions[r].controller is None:
                    continue
                flags = _region_flags(world, r)
                base["regions"][0] += 1
                for f, on in zip(FLAGS, flags):
                    base[f][0] += on
                base["good"][0] += not any(flags)
        events = original_tick(world, *a, **kw)
        state = world.agent_movements
        for m in (state.movements[before:] if state is not None else []):
            foundings.append([world.turn, m.home_region, m.creed, *_region_flags(world, m.home_region)])
        return events

    M._grievance_census = recording
    M.tick_agent_movements = tick
    sys.argv = ["chronicler.main", *argv]
    try:
        entry.main()
    finally:
        (out / "census.json").write_text(json.dumps(samples))
        (out / "conditions.json").write_text(json.dumps({"base": base, "foundings": foundings, "grid": grid}))
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
        return _child(out, every, rest, grid_on="--grid" in argv[:argv.index("--")] if "--" in argv else False)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--seeds", default="42-51")
    parser.add_argument("--turns", type=int, default=500)
    parser.add_argument("--parallel", type=int, default=2)
    parser.add_argument("--every", type=int, default=10)
    parser.add_argument("--significant", type=int, default=10)
    parser.add_argument("--summarize-only", action="store_true")
    parser.add_argument("--grid", action="store_true",
                        help="sample the needs and score the grievance threshold grid")
    args, extra = parser.parse_known_args(argv)
    if extra and extra[0] == "--":
        extra = extra[1:]
    lo, _, hi = args.seeds.partition("-")
    seeds = list(range(int(lo), int(hi or lo) + 1))
    args.out.mkdir(parents=True, exist_ok=True)

    def run(seed: int) -> int:
        run_dir = args.out / f"seed_{seed}"
        run_dir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, __file__, "--child", str(run_dir), str(seed), str(args.every),
               *(["--grid"] if args.grid else []), "--",
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
    base_total: dict[str, int] = {}
    founding_flags = {c: {f: 0 for f in (*FLAGS, "good", "all")} for c in CREEDS}
    grid_total: dict = {}
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
        cond_path = run_dir / "conditions.json"
        if cond_path.exists():
            cond = json.loads(cond_path.read_text())
            for k, v in cond["base"].items():
                base_total[k] = base_total.get(k, 0) + v[0]
            for _turn, _region, creed, *flags in cond["foundings"]:
                cell = founding_flags[CREEDS[creed]]
                cell["all"] += 1
                for f, on in zip(FLAGS, flags):
                    cell[f] += bool(on)
                cell["good"] += not any(flags)
            for key, cell in cond["grid"].items():
                tot = grid_total.setdefault(key, {})
                for f, (hit, n) in cell.items():
                    h0, n0 = tot.get(f, (0, 0))
                    tot[f] = (h0 + hit, n0 + n)
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
        "conditions": {
            "region_share": {k: round(v / max(1, base_total.get("regions", 0)), 4)
                             for k, v in base_total.items() if k != "regions"},
            "founding_share": {c: {f: round(v / max(1, cell["all"]), 3) for f, v in cell.items() if f != "all"}
                               | {"n": cell["all"]} for c, cell in founding_flags.items()},
        },
        "grid": {key: {f: round(h / n, 4) if n else None for f, (h, n) in cell.items()}
                 for key, cell in sorted(grid_total.items())},
        "significant_per_world": [w["significant"] for w in worlds],
        "movements_per_world": [w["movements"] for w in worlds],
        "worlds_detail": worlds,
    }
    (args.out / "probe.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "worlds_detail"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
