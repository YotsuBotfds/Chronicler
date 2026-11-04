#!/usr/bin/env python3
"""Disease statistics for a run or a batch, with or without epidemiology.

``census [--] <chronicler.main args>``
    Run ``chronicler.main`` in this process and count the people every
    disease path removed: the hazard plague toll (``simulation``), the M18
    pandemic toll (``emergence``; in hybrid mode it is a direct region
    mutation that the agent write-back overwrites, so it is reported
    separately as nominal) and, with epidemiology on, the epidemic deaths.
    Writes ``disease_census.json`` next to ``--output``.

``summarize BATCH_OR_RUN_DIR``
    Per-run and mean statistics from ``state.json``, ``chronicle_bundle.json``
    and ``disease_census.json`` (when present): disease events, deaths,
    epidemics, peak prevalence, regions affected, quarantines, virgin-soil
    arrivals and the population trajectory. Prints JSON.

``chains RUN_DIR [N]``
    The N outbreaks of a run with the most recorded consequences, each with
    the causal chain that led to it and the events that cite it.

See docs/integration/epidemiology.md.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def census(argv: list[str]) -> int:
    import chronicler.emergence as emergence
    import chronicler.simulation as simulation
    from chronicler import main as cli

    counted = {"plague_toll": 0, "pandemic_toll_nominal": 0}

    def wrap(module, label):
        original = module.distribute_pop_loss

        def counting(regions, loss):
            drains = original(regions, loss)
            counted[label] += sum(drains)
            return drains
        module.distribute_pop_loss = counting

    wrap(simulation, "plague_toll")
    wrap(emergence, "pandemic_toll_nominal")
    captured = {}
    original_execute = cli.execute_run

    def execute(args, *a, **kw):
        result = original_execute(args, *a, **kw)
        captured["output"] = Path(args.output)
        return result

    cli.execute_run = execute
    if argv and argv[0] == "--":
        argv = argv[1:]
    sys.argv = ["chronicler.main", *argv]
    cli.main()
    out = captured["output"].parent / "disease_census.json"
    out.write_text(json.dumps(counted, indent=2, sort_keys=True), encoding="utf-8")
    return 0


def _runs(root: Path) -> list[Path]:
    if (root / "state.json").exists():
        return [root]
    return sorted(p.parent for p in root.glob("*/state.json"))


def _run_stats(run: Path) -> dict:
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    timeline = state.get("events_timeline", [])
    kinds = Counter(e["event_type"] for e in timeline)
    seed = state.get("seed")
    stats: dict = {
        "seed": seed,
        "turns": state.get("turn"),
        "hazard_or_civ_plague": kinds["plague"],
        "pandemic": kinds["pandemic"],
        "pandemic_spread": kinds["pandemic_spread"],
        "pandemic_leader_death": kinds["pandemic_leader_death"],
        "epidemics": kinds["epidemic"],
        "epidemic_arrivals": kinds["epidemic_arrival"],
        "virgin_soil_arrivals": sum(1 for e in timeline if e["event_type"] == "epidemic_arrival"
                                    and "never known it" in e.get("description", "")),
        "quarantines": kinds["quarantine"],
        "strains": kinds["pathogen_mutation"],
        "leader_deaths_by_disease": sum(1 for e in timeline if e["event_type"] == "leader_death"
                                        and " dies of " in e.get("description", "")),
        "epidemics_by_pathogen": dict(sorted(Counter(
            e.get("shock_category") for e in timeline if e["event_type"] == "epidemic").items())),
    }
    regions = {e.get("region") for e in timeline if e["event_type"] == "epidemic"}
    stats["regions_affected"] = len(regions)
    bundle_path = run / "chronicle_bundle.json"
    if bundle_path.exists():
        from chronicler.snapshot_pruning import restore_bundle
        # Version-5 histories leave dead civs out; restore every civ row.
        bundle = restore_bundle(json.loads(bundle_path.read_text(encoding="utf-8")))
        history = bundle.get("history", [])
        pops = [sum(c.get("population", 0) for c in snap.get("civ_stats", {}).values()) for snap in history]
        stats["population"] = {"first": pops[0] if pops else None, "min": min(pops) if pops else None,
                               "final": pops[-1] if pops else None}
        series = [snap["epidemics"] for snap in history if snap.get("epidemics") is not None]
        if series:
            from chronicler.epidemiology import extract_epidemic_metrics
            metrics = extract_epidemic_metrics([bundle])["by_seed"][0]
            stats["epidemic_deaths"] = metrics["deaths"]
            stats["epidemic_deaths_by_pathogen"] = metrics["deaths_by_pathogen"]
            stats["peak_prevalence"] = metrics["peak_prevalence"]
            stats["quarantine_turns"] = metrics["quarantine_turns"]
        else:
            stats["pandemic_regions_ever"] = len({r for snap in history for r in snap.get("pandemic_regions", [])})
    census_path = run / "disease_census.json"
    if census_path.exists():
        census_data = json.loads(census_path.read_text(encoding="utf-8"))
        stats.update(census_data)
    deaths = stats.get("epidemic_deaths", 0) + stats.get("plague_toll", 0)
    stats["disease_deaths_applied"] = deaths
    return stats


def summarize(root: Path) -> dict:
    runs = [_run_stats(r) for r in _runs(root)]
    numeric = sorted({k for r in runs for k, v in r.items() if isinstance(v, (int, float)) and k != "seed"})
    means = {k: round(sum(r.get(k, 0) or 0 for r in runs) / len(runs), 3) for k in numeric} if runs else {}
    pop = [r["population"] for r in runs if "population" in r]
    if pop:
        means["population_final"] = round(sum(p["final"] for p in pop) / len(pop), 1)
        means["population_min_any_run"] = min(p["min"] for p in pop)
        means["extinct_worlds"] = sum(1 for p in pop if p["final"] == 0)
    return {"runs": len(runs), "mean": means, "by_seed": runs}


def chains(run: Path, n: int = 3) -> list[dict]:
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    timeline = state.get("events_timeline", [])
    by_id = {e.get("event_id"): e for e in timeline if e.get("event_id")}
    effects: dict[str, list[dict]] = {}
    for e in timeline:
        for c in e.get("causes", []):
            effects.setdefault(c, []).append(e)
    onsets = [e for e in timeline if e["event_type"] == "epidemic"]

    def root_chain(ev: dict) -> list[dict]:
        chain, seen = [ev], {ev.get("event_id")}
        while chain[0].get("causes"):
            nxt = by_id.get(chain[0]["causes"][0])
            if nxt is None or nxt.get("event_id") in seen:
                break
            seen.add(nxt.get("event_id"))
            chain.insert(0, nxt)
        return chain

    def descendants(ev: dict, depth: int = 3) -> list[dict]:
        out, frontier = [], [ev]
        for _ in range(depth):
            nxt = []
            for f in frontier:
                for child in effects.get(f.get("event_id"), []):
                    if child not in out:
                        out.append(child)
                        nxt.append(child)
            frontier = nxt
        return out

    scored = sorted(onsets, key=lambda e: (-len(descendants(e)), -len(root_chain(e)), e["turn"]))
    stories = []
    for ev in scored[:n]:
        stories.append({
            "onset": f"[t{ev['turn']}] {ev['description']}",
            "because": [f"[t{c['turn']}] {c['event_type']}: {c['description']}" for c in root_chain(ev)[:-1]],
            "led_to": [f"[t{c['turn']}] {c['event_type']}: {c['description']}" for c in descendants(ev)],
        })
    return stories


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "census":
        return census(argv[1:])
    if argv[0] == "summarize" and len(argv) == 2:
        print(json.dumps(summarize(Path(argv[1])), indent=2, sort_keys=True))
        return 0
    if argv[0] == "chains" and len(argv) in (2, 3):
        print(json.dumps(chains(Path(argv[1]), int(argv[2]) if len(argv) == 3 else 3), indent=2))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
