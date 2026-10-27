#!/usr/bin/env python3
"""Public granaries: what they do to hunger, prices, treasuries and trade.

``grain_reserves_probe.py run RUN_DIR [--set NAME=VALUE ...] -- <chronicler.main arguments>``
    Runs one simulation in this process (an agent mode) and observes every
    turn, reading only: per region the goods economy's food demand, its food
    sufficiency before the granaries open (as the economy computed it) and
    after (what the agents, labels and merchants read), its food price
    (demand over post-trade supply), the merchants' food departures and
    arrivals (the native delivery diagnostics, diffed per turn); per civ the
    treasury. Writes ``RUN_DIR/probe_turns.jsonl``; the CLI writes its usual
    files (give ``--output RUN_DIR/chronicle.md``). The same run with the
    switch on and off is the paired comparison. ``--set`` overrides a
    parameter of :mod:`chronicler.grain_reserves` for an experiment.

``grain_reserves_probe.py summarize RUN_DIR [RUN_DIR ...] --json OUT``
    Per run: famine and dearth reports; populated owned region-turns fed,
    in dearth (sufficiency 0.6-1), severe (below 0.6) and in famine (three
    turns or more below 0.6) and the mean shortfall; deaths and births per
    1,000 agent-turns overall and in short region-turns (``agent_events.arrow``);
    the food price's mean and volatility (per region the standard deviation
    of the log price over its populated turns, averaged); fiscal events per
    starting civ per 100 turns, mean treasury, civ-turns below 20; merchant
    food departures; final population; granary grain and target over time
    (observed each turn) and the final counters (``world_state.grain_reserves``).

``grain_reserves_probe.py compare OFF.json ON.json``
    Paired by seed: the mean of each measure in both arms and the mean
    difference with its standard error, as a Markdown table.

See docs/integration/grain-reserves.md.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

FISCAL_EVENTS = ("fiscal_crisis", "fiscal_strain", "loan_taken", "state_default", "debasement")
FOOD_EVENTS = ("famine", "dearth", "mutual_aid", "aid_convoy", "granary_opened", "granary_exhausted",
               "grain_bought")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def _run(run_dir: Path, main_args: list[str]) -> None:
    import chronicler.economy as econ
    import chronicler.simulation as sim
    from chronicler.columnar import pylist
    from chronicler.economy import FIXED_GOODS, FOOD_GOODS

    run_dir.mkdir(parents=True, exist_ok=True)
    food_slots = {i for i, g in enumerate(FIXED_GOODS) if g in FOOD_GOODS}
    state = {"bridge": None, "diag": {}, "pending": None}
    out = open(run_dir / "probe_turns.jsonl", "w")

    def flush_pending():
        rec = state["pending"]
        if rec is None:
            return
        result, names = rec["_result"], rec.pop("_names")
        del rec["_result"]
        for row, name in zip(rec["regions"], names):
            row["s_post"] = round(float(result.food_sufficiency.get(name, 0.0)), 5)
        out.write(json.dumps(rec, separators=(",", ":")) + "\n")
        state["pending"] = None

    orig_turn = sim.run_turn_result

    def run_turn_result(world, action_selector, narrator, seed=0, agent_bridge=None, *a, **k):
        state["bridge"] = agent_bridge
        return orig_turn(world, action_selector, narrator, seed, agent_bridge, *a, **k)

    sim.run_turn_result = run_turn_result
    orig_rec = econ.reconstruct_economy_result

    def diagnostics(simulator):
        batch = simulator.get_delivery_diagnostics()
        totals: dict[int, list[float]] = {}
        if batch.num_rows == 0:
            return totals
        cols = [pylist(batch.column(c)) for c in ("region_id", "good_slot", "total_departures",
                                                  "total_arrivals")]
        for rid, slot, dep, arr in zip(*cols):
            if slot in food_slots:
                t = totals.setdefault(rid, [0.0, 0.0])
                t[0] += dep
                t[1] += arr
        return totals

    def reconstruct(*args, **kwargs):
        flush_pending()
        world = args[5] if len(args) > 5 else kwargs["world"]
        result = orig_rec(*args, **kwargs)
        bridge = state["bridge"]
        diag = diagnostics(bridge._sim) if bridge is not None and world.agent_mode == "hybrid" else {}
        prev = state["diag"]
        state["diag"] = diag
        rows = []
        for i, region in enumerate(world.regions):
            demand = result.market_demand.get(region.name, (0.0,))[0]
            supply = result.market_supply.get(region.name, (0.0,))[0]
            d_now, d_prev = diag.get(i, [0.0, 0.0]), prev.get(i, [0.0, 0.0])
            rows.append({
                "c": region.controller, "D": round(float(demand), 5),
                "s": round(float(result.food_sufficiency.get(region.name, 0.0)), 5),
                "p": round(float(demand) / max(float(supply), 0.1), 5) if demand > 0 else 0.0,
                "dep": round(d_now[0] - d_prev[0], 5), "arr": round(d_now[1] - d_prev[1], 5),
            })
        reserves = getattr(world, "grain_reserves", None)
        state["pending"] = {
            "turn": world.turn,
            "treasury": {c.name: c.treasury for c in world.civilizations if c.regions},
            # Granaries as the previous turn left them (before this turn's release).
            "granary": ([round(sum(g.grain for g in reserves.granaries), 4),
                         round(sum(g.target for g in reserves.granaries), 4)]
                        if reserves is not None else None),
            "regions": rows, "_result": result, "_names": [r.name for r in world.regions],
        }
        return result

    econ.reconstruct_economy_result = reconstruct
    from chronicler.main import main as cli_main
    sys.argv = ["chronicler"] + main_args
    try:
        cli_main()
    finally:
        flush_pending()
        out.close()


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------

def _deaths_births(path: Path) -> tuple[dict, dict]:
    deaths: Counter = Counter()
    births: Counter = Counter()
    if not path.exists():
        return deaths, births
    import pyarrow.ipc as ipc
    with ipc.open_file(str(path)) as f:
        table = f.read_all()
    types = table.column("event_type").to_pylist()
    turns = table.column("turn").to_pylist()
    regions = table.column("region").to_pylist()
    for t, turn, region in zip(types, turns, regions):
        if t == "death":
            deaths[(turn, region)] += 1
        elif t == "birth":
            births[(turn, region)] += 1
    return deaths, births


def summarize_run(run_dir: Path) -> dict:
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(run_dir / "chronicle_bundle.json")
    meta = bundle.get("metadata", {})
    seed = int(meta.get("seed", -1))
    total = int(meta.get("total_turns", 0))
    history = bundle.get("history", [])
    start_civs = len(history[0]["civ_stats"]) if history else 0
    civ_centuries = max(1e-9, start_civs * total / 100.0)
    out: dict[str, float] = {"seed": seed}
    events = Counter(e["event_type"] for e in bundle.get("events_timeline", []))
    for k in FOOD_EVENTS:
        out[f"ev_{k}"] = events.get(k, 0)
    for k in FISCAL_EVENTS:
        out[f"fiscal_{k}_per_civ_century"] = events.get(k, 0) / civ_centuries

    deaths, births = _deaths_births(run_dir / "agent_events.arrow")
    turns = [json.loads(line) for line in open(run_dir / "probe_turns.jsonl")]
    cls = Counter()
    short_depth = 0.0
    agent_turns = Counter()
    dead = Counter()
    born = Counter()
    run_below = defaultdict(int)
    logp: dict[int, list[float]] = defaultdict(list)
    price_sum = price_n = 0.0
    dep = arr = 0.0
    treas = []
    for rec in turns:
        t = rec["turn"]
        treas.extend(rec["treasury"].values())
        for rid, row in enumerate(rec["regions"]):
            dep += row["dep"]
            arr += row["arr"]
            if row["c"] is None or row["D"] <= 0:
                run_below[rid] = 0
                continue
            s = row["s_post"]
            agents = row["D"] / 0.5
            if s >= 1.0 - 1e-6:
                k = "fed"
                run_below[rid] = 0
            elif s >= 0.6:
                k = "dearth"
                run_below[rid] = 0
            else:
                run_below[rid] += 1
                k = "famine" if run_below[rid] >= 3 else "severe"
            cls[k] += 1
            short_depth += max(0.0, 1.0 - s)
            agent_turns[k] += agents
            dead[k] += deaths.get((t, rid), 0)
            born[k] += births.get((t, rid), 0)
            if row["p"] > 0:
                price_sum += row["p"]
                price_n += 1
                logp[rid].append(math.log(row["p"]))
    rt = sum(cls.values())
    for k in ("fed", "dearth", "severe", "famine"):
        out[f"share_{k}"] = cls[k] / rt if rt else 0.0
    out["share_short"] = (cls["dearth"] + cls["severe"] + cls["famine"]) / rt if rt else 0.0
    out["mean_shortfall"] = short_depth / rt if rt else 0.0
    at = sum(agent_turns.values())
    out["deaths_per_1000"] = 1000 * sum(dead.values()) / at if at else 0.0
    out["births_per_1000"] = 1000 * sum(born.values()) / at if at else 0.0
    short_at = agent_turns["dearth"] + agent_turns["severe"] + agent_turns["famine"]
    out["agent_turns_short_share"] = short_at / at if at else 0.0
    out["agent_turns_famine_share"] = agent_turns["famine"] / at if at else 0.0
    out["deaths_in_short"] = dead["dearth"] + dead["severe"] + dead["famine"]
    out["deaths_in_famine"] = dead["famine"]
    out["deaths_total"] = sum(deaths.values())
    out["births_total"] = sum(births.values())
    out["deaths_per_1000_short"] = 1000 * out["deaths_in_short"] / short_at if short_at else 0.0
    out["price_mean"] = price_sum / price_n if price_n else 0.0
    vols = []
    for series in logp.values():
        if len(series) >= 12:
            m = sum(series) / len(series)
            vols.append(math.sqrt(sum((x - m) ** 2 for x in series) / len(series)))
    out["price_log_sd"] = sum(vols) / len(vols) if vols else 0.0
    out["food_departures"] = dep
    out["food_arrivals"] = arr
    out["treasury_mean"] = sum(treas) / len(treas) if treas else 0.0
    out["treasury_below_20_share"] = sum(1 for x in treas if x < 20) / len(treas) if treas else 0.0
    final = history[-1]["civ_stats"] if history else {}
    out["final_population"] = sum(cs.get("population", 0) for cs in final.values()
                                  if cs.get("alive", True) and cs.get("regions"))
    pops = [sum(cs.get("population", 0) for cs in h["civ_stats"].values() if cs.get("regions"))
            for h in history]
    out["mean_population"] = sum(pops) / len(pops) if pops else 0.0
    levels = [rec["granary"] for rec in turns if rec.get("granary") is not None]
    final_state = (bundle.get("world_state") or {}).get("grain_reserves")
    if levels and final_state:
        held = [g for g, _ in levels]
        target = [t for _, t in levels]
        out["granary_grain_mean"] = sum(held) / len(held)
        out["granary_target_mean"] = sum(target) / len(target)
        out["granary_fill_mean"] = (sum(held) / sum(target)) if sum(target) > 0 else 0.0
        for third in range(3):
            lo, hi = third * len(held) // 3, (third + 1) * len(held) // 3
            out[f"granary_grain_t{third}"] = sum(held[lo:hi]) / max(1, hi - lo)
        counters = final_state.get("counters", {})
        for k, v in counters.items():
            out[f"granary_{k}"] = v
        demand = sum(row["D"] for rec in turns for row in rec["regions"] if row["c"] is not None)
        out["granary_released_share_of_demand"] = counters.get("released", 0.0) / demand if demand else 0.0
        out["granary_spoiled_per_released"] = (counters.get("spoiled", 0.0) / counters["released"]
                                               if counters.get("released") else 0.0)
    return out


def _summarize(args: list[str]) -> None:
    out_path = None
    if "--json" in args:
        i = args.index("--json")
        out_path = Path(args[i + 1])
        args = args[:i] + args[i + 2:]
    rows = [summarize_run(Path(a)) for a in args]
    text = json.dumps(rows, indent=1, sort_keys=True)
    if out_path:
        out_path.write_text(text)
    else:
        print(text)


def _compare(off_path: str, on_path: str) -> None:
    off = {r["seed"]: r for r in json.loads(Path(off_path).read_text())}
    on = {r["seed"]: r for r in json.loads(Path(on_path).read_text())}
    seeds = sorted(set(off) & set(on))
    keys = [k for k in on[seeds[0]] if k != "seed"]
    print(f"| measure ({len(seeds)} paired worlds) | off | on | difference (SE) |")
    print("| --- | ---: | ---: | ---: |")
    for k in keys:
        a = [off[s].get(k, 0.0) for s in seeds]
        b = [on[s].get(k, 0.0) for s in seeds]
        d = [y - x for x, y in zip(a, b)]
        n = len(d)
        md = sum(d) / n
        se = math.sqrt(sum((x - md) ** 2 for x in d) / (n - 1) / n) if n > 1 else 0.0
        print(f"| {k} | {sum(a) / n:.4g} | {sum(b) / n:.4g} | {md:+.4g} ({se:.2g}) |")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "run":
        if "--" not in sys.argv[3:]:
            raise SystemExit("usage: grain_reserves_probe.py run RUN_DIR [--set NAME=VALUE ...] -- "
                             "<chronicler.main arguments>")
        cut = sys.argv.index("--", 3)
        opts = sys.argv[3:cut]
        if opts:
            # Experiments: --set NAME=VALUE overrides a chronicler.grain_reserves parameter.
            import chronicler.grain_reserves as GR
            for i in range(0, len(opts), 2):
                if opts[i] != "--set":
                    raise SystemExit(f"unknown option {opts[i]}")
                name, value = opts[i + 1].split("=", 1)
                if not hasattr(GR, name):
                    raise SystemExit(f"no parameter {name}")
                setattr(GR, name, type(getattr(GR, name))(value))
        _run(Path(sys.argv[2]), sys.argv[cut + 1:])
    elif cmd == "summarize":
        _summarize(sys.argv[2:])
    elif cmd == "compare":
        _compare(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
