"""Capture and replay the watershed account on development worlds (calibration).

In ``record_only`` the account changes nothing, so the index the simulation
uses, and everything the account reads, is the same whatever its constants.
``capture`` runs procedural development worlds once with ``--watershed`` and
saves, per turn, the account's inputs (``watershed.region_inputs``) and the
index observed after each tick; ``replay`` runs ``watershed.account_step`` on
those inputs under other constants and reports the calibration metrics:

* drift: the change of the world's total storage between the same climate
  phases one cycle apart after the first cycle (turns 150-199 against
  75-124), relative; the observed index's drift over the same windows is
  reported beside it;
* spin-up: the first cycle (turns 0-74, from the world-generation index) is
  left out of every other metric;
* level: the mean of (derived - observed) index over every region-turn, for
  headwater regions and regions with upstream inflow;
* amplitude: the derived index's climate-phase amplitude over the observed
  index's (phase means of the world's regions);
* correlation: the median per-region correlation of the two series;
* droughts: the share of region-turns in a drought (storage below the
  drought fraction for the drought length), against the same rule applied
  to the observed index's fill;
* floods: flood region-turns per world.

Development worlds only (``DEVELOPMENT_PROCEDURAL``); it refuses any other
seed. Nothing here changes the simulation.

    python scripts/watershed_replay.py capture OUT [--seeds 7,11,...] [--turns 200] [--agents hybrid]
    python scripts/watershed_replay.py replay OUT [--params JSON] [--b1]
    python scripts/watershed_replay.py search OUT [--sweeps 3]

``search`` is a deterministic coordinate descent of ``score`` over the
declared ranges in ``SEARCH``, starting from the constants in force.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

DEVELOPMENT_PROCEDURAL = (7, 11, 13, 17, 21, 31, 302, 303)
PHASES = ("temperate", "warming", "drought", "cooling")
CYCLE = 75


def _check_seeds(seeds):
    bad = [s for s in seeds if s not in DEVELOPMENT_PROCEDURAL]
    if bad:
        raise SystemExit(f"refused: {bad} are not procedural development worlds {DEVELOPMENT_PROCEDURAL}")


def capture(out: Path, seeds: list[int], turns: int, agents: str, regions: int = 32, civs: int = 10) -> None:
    from chronicler import watershed as ws
    from chronicler.main import _build_parser, execute_run
    _check_seeds(seeds)
    out.mkdir(parents=True, exist_ok=True)
    for seed in seeds:
        rec: dict = {"seed": seed, "regions": regions, "civs": civs, "agents": agents, "turns": []}
        originals = (ws.region_inputs, ws.after_ecology, ws.open_account)

        def region_inputs(world, state, _orig=originals[0]):
            turn, key, trend, inputs = _orig(world, state)
            rec["turns"].append({"turn": turn, "phase": key, "trend": trend, "inputs": [list(i) for i in inputs]})
            return turn, key, trend, inputs

        def after_ecology(world, acc, _orig=originals[1]):
            events = _orig(world, acc)
            rec["turns"][-1]["observed"] = [float(r.ecology.water) for r in world.regions]
            return events

        def open_account(world, graph, mode="record_only", _orig=originals[2]):
            state = _orig(world, graph, mode)
            rec.update(graph=graph.model_dump(), opening_storage=list(state.storage),
                       opening_index=list(state.last_index))
            return state

        ws.region_inputs, ws.after_ecology, ws.open_account = region_inputs, after_ecology, open_account
        try:
            folder = out / f"p{seed}"
            args = _build_parser().parse_args([
                "--seed", str(seed), "--turns", str(turns), "--regions", str(regions), "--civs", str(civs),
                "--worldgen", "procedural", "--agents", agents, "--simulate-only", "--watershed",
                "--output", str(folder / "chronicle.md"), "--state", str(folder / "state.json")])
            execute_run(args)
        finally:
            ws.region_inputs, ws.after_ecology, ws.open_account = originals
        from chronicler.bundle_codec import load_bundle
        events = load_bundle(folder / "chronicle_bundle.json")["events_timeline"]
        rec["river_floods"] = sum(1 for e in events if e.get("event_type") == "flood"
                                  and "river floods" in e.get("description", ""))
        rec["coastal_floods"] = sum(1 for e in events if e.get("event_type") == "flood"
                                    and "Flooding devastates" in e.get("description", ""))
        (out / f"capture_p{seed}.json").write_text(json.dumps(rec), encoding="utf-8")
        print(f"captured procedural {seed}: {len(rec['turns'])} turns", flush=True)


def _corr(xs, ys):
    n = len(xs)
    mx, my = math.fsum(xs) / n, math.fsum(ys) / n
    sx = math.sqrt(math.fsum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(math.fsum((y - my) ** 2 for y in ys))
    return None if sx == 0 or sy == 0 else math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _spell_share(fractions: list[list[float]], threshold: float, length: int) -> float:
    """Share of region-turns inside a run of at least ``length`` turns below ``threshold``."""
    inside = total = 0
    for series in fractions:
        run = 0
        flags = []
        for f in series:
            run = run + 1 if f < threshold else 0
            flags.append(run)
        # a turn is in a drought once its run reaches the length (as the account declares it)
        inside += sum(1 for r in flags if r >= length)
        total += len(series)
    return inside / total if total else 0.0


def replay_world(rec: dict, params) -> dict:
    from chronicler import watershed as ws
    from chronicler.watershed_state import WatershedGraph
    graph = WatershedGraph(**rec["graph"])
    n = len(graph.down)
    storage, last = list(rec["opening_storage"]), list(rec["opening_index"])
    derived = [[] for _ in range(n)]
    observed = [[] for _ in range(n)]
    fill_d = [[] for _ in range(n)]
    fill_o = [[] for _ in range(n)]
    phases, totals, floods = [], [], 0
    flow = {"precipitation": 0.0, "evaporation": 0.0, "withdrawal": 0.0, "to_sea": 0.0, "to_sink": 0.0}
    for t in rec["turns"]:
        inputs = [ws.RegionInput(*row) for row in t["inputs"]]
        plan = ws.account_step(graph, storage, last, t["turn"], t["phase"], t["trend"], inputs, params)
        c = plan.columns
        storage, last = list(c["storage"]), list(t["observed"])
        phases.append(t["phase"])
        totals.append(math.fsum(storage))
        floods += sum(1 for v in c["flood_excess"] if v > 0.0)
        for k in ("precipitation", "evaporation", "withdrawal"):
            flow[k] += math.fsum(c[k])
        flow["to_sea"] += math.fsum(plan.routed["to_sea"])
        flow["to_sink"] += math.fsum(plan.routed["to_sink"])
        for r in range(n):
            derived[r].append(c["index_derived"][r])
            observed[r].append(t["observed"][r])
            fill_d[r].append(c["storage"][r] / c["capacity"][r])
            span = max(inputs[r].cap - params.index_floor, 1e-9)
            fill_o[r].append((t["observed"][r] - params.index_floor) / span)
    upstream = [any(d == r for d in graph.down) for r in range(n)]
    out = {"seed": rec["seed"], "turns": len(rec["turns"])}
    early, late = totals[CYCLE:CYCLE + 50], totals[2 * CYCLE:2 * CYCLE + 50]
    mean = lambda xs: math.fsum(xs) / len(xs)
    out["drift"] = (mean(late) - mean(early)) / mean(early) if len(late) == 50 else None
    obs_tot = [math.fsum(observed[r][k] for r in range(n)) for k in range(len(phases))]
    out["drift_observed"] = ((mean(obs_tot[2 * CYCLE:2 * CYCLE + 50]) - mean(obs_tot[CYCLE:CYCLE + 50]))
                             / mean(obs_tot[CYCLE:CYCLE + 50])) if len(late) == 50 else None
    # Leave the first cycle (spin-up from the world-generation index) out of the rest.
    derived = [series[CYCLE:] for series in derived]
    observed = [series[CYCLE:] for series in observed]
    fill_d = [series[CYCLE:] for series in fill_d]
    fill_o = [series[CYCLE:] for series in fill_o]
    phases = phases[CYCLE:]
    out["storage_open_to_end"] = [round(math.fsum(rec["opening_storage"]), 3), round(totals[-1], 3)]
    for name, members in (("all", range(n)), ("headwater", [r for r in range(n) if not upstream[r]]),
                          ("upstream", [r for r in range(n) if upstream[r]])):
        members = list(members)
        if not members:
            continue
        gaps = [derived[r][k] - observed[r][k] for r in members for k in range(len(phases))]
        out[f"level_{name}"] = math.fsum(gaps) / len(gaps)
        out[f"mean_observed_{name}"] = math.fsum(v for r in members for v in observed[r]) / len(gaps)
    by_phase = {}
    for ph in PHASES:
        ks = [k for k, p in enumerate(phases) if p == ph]
        by_phase[ph] = (math.fsum(derived[r][k] for r in range(n) for k in ks) / (n * len(ks)),
                        math.fsum(observed[r][k] for r in range(n) for k in ks) / (n * len(ks)))
    amp_d = max(v[0] for v in by_phase.values()) - min(v[0] for v in by_phase.values())
    amp_o = max(v[1] for v in by_phase.values()) - min(v[1] for v in by_phase.values())
    out["amplitude_ratio"] = amp_d / amp_o if amp_o else None
    out["phase_means"] = {ph: [round(a, 3), round(b, 3)] for ph, (a, b) in by_phase.items()}
    corrs = sorted(c for c in (_corr(derived[r], observed[r]) for r in range(n)) if c is not None)
    out["median_corr"] = corrs[len(corrs) // 2] if corrs else None
    out["drought_share"] = _spell_share(fill_d, params.drought_fraction, params.drought_turns)
    out["drought_share_observed"] = _spell_share(fill_o, params.drought_fraction, params.drought_turns)
    out["flood_region_turns"] = floods
    out["river_floods_old"] = rec.get("river_floods")
    out["flows"] = {k: round(v, 2) for k, v in flow.items()}
    return out


def replay(folder: Path, params) -> dict:
    worlds = [replay_world(json.loads(p.read_text(encoding="utf-8")), params)
              for p in sorted(folder.glob("capture_p*.json"))]
    _check_seeds([w["seed"] for w in worlds])
    pooled = {}
    for key in ("drift", "drift_observed", "level_all", "level_headwater", "level_upstream", "amplitude_ratio",
                "median_corr", "drought_share", "drought_share_observed"):
        values = [w[key] for w in worlds if w.get(key) is not None]
        pooled[key] = math.fsum(values) / len(values) if values else None
    pooled["max_abs_drift"] = max(abs(w["drift"]) for w in worlds)
    pooled["flood_region_turns_per_world"] = math.fsum(w["flood_region_turns"] for w in worlds) / len(worlds)
    pooled["river_floods_old_per_world"] = math.fsum(w["river_floods_old"] or 0 for w in worlds) / len(worlds)
    return {"pooled": pooled, "worlds": worlds}


def score(pooled: dict) -> float:
    """Lower is better: stationarity first, then level, amplitude and droughts."""
    return (4.0 * abs(pooled["drift"]) + 2.0 * pooled["max_abs_drift"] + 4.0 * abs(pooled["level_all"])
            + 1.0 * abs(pooled["level_headwater"]) + 1.0 * abs(pooled["level_upstream"])
            + 1.0 * abs(pooled["amplitude_ratio"] - 1.0)
            + 2.0 * abs(pooled["drought_share"] - pooled["drought_share_observed"]))


#: Searched constants and their candidate values (scalars, or phase-table entries as "table.key").
SEARCH: dict[str, tuple[float, ...]] = {
    "baseflow": (0.005, 0.01, 0.015, 0.02, 0.03, 0.05),
    "precipitation_base": (0.06, 0.08, 0.1, 0.12, 0.14, 0.17, 0.2),
    "evaporation_base": (0.02, 0.03, 0.04, 0.05, 0.06, 0.08),
    "phase_precipitation.warming": (0.4, 0.6, 0.8, 1.0),
    "phase_precipitation.drought": (-0.6, -0.3, 0.0, 0.3, 0.6),
    "phase_precipitation.cooling": (-0.6, -0.3, 0.0, 0.3, 0.6),
    "phase_evaporation.warming": (1.0, 1.3, 1.6, 2.0),
    "phase_evaporation.drought": (1.0, 1.5, 2.0, 2.5, 3.0),
    "phase_evaporation.cooling": (0.5, 0.7, 1.0, 1.5, 2.0),
    "shock_precipitation": (0.5, 1.0, 1.5, 2.0),
    "transpiration": (0.0, 0.3, 0.6),
    "forest_retention": (0.25, 0.5, 1.0),
}


def _with(params, name: str, value: float):
    from dataclasses import replace
    if "." in name:
        table, key = name.split(".")
        return replace(params, **{table: {**getattr(params, table), key: value}})
    return replace(params, **{name: value})


#: Continuous ranges of the local search (``refine``).
RANGES: dict[str, tuple[float, float]] = {
    "baseflow": (0.002, 0.08), "precipitation_base": (0.04, 0.3), "evaporation_base": (0.005, 0.12),
    "phase_precipitation.warming": (-1.0, 1.2), "phase_precipitation.drought": (-1.5, 1.0),
    "phase_precipitation.cooling": (-1.5, 1.0),
    # Physically ordered: warming evaporates at least as much as temperate, cooling no more than
    # drought; forests keep a capacity and transpiration effect (the forest linkage needs them).
    "phase_evaporation.warming": (1.0, 2.0), "phase_evaporation.drought": (1.0, 4.0),
    "phase_evaporation.cooling": (0.5, 1.5),
    "shock_precipitation": (0.0, 3.0), "transpiration": (0.1, 1.0), "forest_retention": (0.25, 1.0),
}


def _get(params, name: str) -> float:
    if "." in name:
        table, key = name.split(".")
        return getattr(params, table)[key]
    return getattr(params, name)


def refine(folder: Path, params, iterations: int = 400, seed: int = 0):
    """Deterministic random local search: perturb one constant at a time
    within ``RANGES`` (shrinking steps), keep a change that lowers ``score``."""
    import random
    rng = random.Random(seed)            # the calibration tool's own stream; the simulation never sees it
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("capture_p*.json"))]
    _check_seeds([r["seed"] for r in records])

    def evaluate(candidate):
        worlds = [replay_world(r, candidate) for r in records]
        pooled = {}
        for key in ("drift", "level_all", "level_headwater", "level_upstream", "amplitude_ratio",
                    "drought_share", "drought_share_observed"):
            values = [w[key] for w in worlds if w.get(key) is not None]
            pooled[key] = math.fsum(values) / len(values)
        pooled["max_abs_drift"] = max(abs(w["drift"]) for w in worlds)
        return score(pooled), pooled

    best, (best_score, best_pooled) = params, evaluate(params)
    names = list(RANGES)
    for it in range(iterations):
        name = names[rng.randrange(len(names))]
        lo, hi = RANGES[name]
        step = (hi - lo) * 0.25 * (1.0 - it / iterations) + (hi - lo) * 0.01
        value = min(hi, max(lo, _get(best, name) + rng.uniform(-step, step)))
        candidate = _with(best, name, round(value, 4))
        got, pooled = evaluate(candidate)
        if got < best_score - 1e-9:
            best, best_score, best_pooled = candidate, got, pooled
        if (it + 1) % 50 == 0:
            print(f"iteration {it + 1}: score {best_score:.4f} {json.dumps({k: round(v, 3) for k, v in best_pooled.items()})}",
                  flush=True)
    return best, best_score, best_pooled


def search(folder: Path, params, sweeps: int = 3):
    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("capture_p*.json"))]
    _check_seeds([r["seed"] for r in records])

    def evaluate(candidate):
        worlds = [replay_world(r, candidate) for r in records]
        pooled = {}
        for key in ("drift", "level_all", "level_headwater", "level_upstream", "amplitude_ratio",
                    "drought_share", "drought_share_observed"):
            values = [w[key] for w in worlds if w.get(key) is not None]
            pooled[key] = math.fsum(values) / len(values)
        pooled["max_abs_drift"] = max(abs(w["drift"]) for w in worlds)
        return score(pooled), pooled

    best, (best_score, best_pooled) = params, evaluate(params)
    for sweep in range(sweeps):
        improved = False
        for name, values in SEARCH.items():
            for value in values:
                candidate = _with(best, name, value)
                got, pooled = evaluate(candidate)
                if got < best_score - 1e-9:
                    best, best_score, best_pooled, improved = candidate, got, pooled, True
        print(f"sweep {sweep + 1}: score {best_score:.4f} {json.dumps({k: round(v, 3) for k, v in best_pooled.items()})}",
              flush=True)
        if not improved:
            break
    return best, best_score, best_pooled


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("out", type=Path)
    cap.add_argument("--seeds", default=",".join(map(str, DEVELOPMENT_PROCEDURAL)))
    cap.add_argument("--turns", type=int, default=200)
    cap.add_argument("--agents", default="hybrid")
    rep = sub.add_parser("replay")
    rep.add_argument("out", type=Path)
    rep.add_argument("--params", help="JSON object of Parameters fields to override")
    rep.add_argument("--b1", action="store_true", help="the B1 constants instead of those in force")
    sea = sub.add_parser("search")
    sea.add_argument("out", type=Path)
    sea.add_argument("--sweeps", type=int, default=3)
    sea.add_argument("--params", help="JSON object of Parameters fields to start from")
    sea.add_argument("--refine", type=int, default=0, help="then this many local-search iterations")
    args = parser.parse_args(argv)
    if args.cmd == "capture":
        capture(args.out, [int(s) for s in args.seeds.split(",")], args.turns, args.agents)
        return 0
    from dataclasses import replace
    from chronicler import watershed as ws
    params = ws.B1_PARAMETERS if getattr(args, "b1", False) else ws.PARAMETERS
    if args.params:
        params = replace(params, **json.loads(args.params))
    if args.cmd == "search":
        best, best_score, pooled = search(args.out, params, args.sweeps) if args.sweeps else (params, None, None)
        if args.refine:
            best, best_score, pooled = refine(args.out, best, args.refine)
        print(json.dumps({"score": best_score, "pooled": pooled, "params": best.as_dict()}, indent=1))
        return 0
    result = replay(args.out, params)
    result["params"] = params.as_dict()
    result["score"] = score(result["pooled"])
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
