#!/usr/bin/env python3
"""Per-system activity of gate batches, for comparing worlds side by side.

``world_systems_report.py LABEL=DIR [LABEL=DIR ...] [--json OUT]``

Each DIR is a run directory (holding ``chronicle_bundle.json``) or a batch
directory (``seed_*`` subdirectories). Every run is read from its bundle
alone (the final ``world_state`` and the history), one run at a time, so
``state.json`` and the memory streams may be deleted from a batch first.

Per run it records population (start, final, minimum, extinct), civs (start,
records, alive), famine (food sufficiency below 0.6 in observed region-turns,
and episodes of three turns or more, the report label's rule), the event
counts of the timeline and the cumulative counters of every system state that
keeps them (cities, guilds, movements, maritime, nomads, agendas, finance,
diplomacy, techniques, epidemic deaths). The table gives, per label, the mean
per world and (in brackets) the share of worlds where the value is above 0;
``--per-civ-century`` shows counts per starting civ per 100 turns instead,
pooled over the label's worlds, so worlds of different sizes and lengths
compare. ``LABEL=FILE.json`` reads the runs a previous ``--json`` saved.

See docs/integration/procedural-gates.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FAMINE_SUFFICIENCY = 0.6
FAMINE_MIN_TURNS = 3

# Rows of the comparison table: (row label, metric key).
TABLE_ROWS: tuple[tuple[str, str], ...] = (
    ("extinct worlds", "extinct"),
    ("population, start", "pop_start"),
    ("population, final", "pop_final"),
    ("population, minimum / start", "pop_min_ratio"),
    ("civs at start", "civs_start"),
    ("civ records at end", "civ_records"),
    ("civs alive at end", "civs_alive"),
    ("famine region-turns (share of observed)", "famine_share"),
    ("famine episodes per world", "famine_episodes"),
    ("famine episode mean length (turns)", "famine_episode_mean"),
    ("famine episodes of 20+ turns (share)", "famine_long_share"),
    ("wars declared", "ev:war_declared"),
    ("secessions", "ev:secession"),
    ("rebellions (civ events)", "ev:rebellion"),
    ("mass migrations", "ev:mass_migration"),
    ("cities founded", "cities:founded"),
    ("cities alive at end", "cities_alive"),
    ("free cities", "cities:free_cities"),
    ("city commerce (cumulative)", "cities:commerce"),
    ("guilds founded", "guilds:founded"),
    ("guild privileges", "guilds:privileges"),
    ("burgher factions formed", "guilds:burghers_formed"),
    ("movement news foundings", "guilds:news_foundings"),
    ("movements founded", "movements:founded"),
    ("reforms enacted", "movements:enacted"),
    ("movement risings", "movements:risings"),
    ("movement secessions", "movements:secessions"),
    ("sea trade (cargo units)", "maritime:sea_trade"),
    ("fleets commissioned", "maritime:fleets_commissioned"),
    ("naval battles", "maritime:naval_battles"),
    ("overseas campaigns", "maritime:overseas_campaigns"),
    ("colonies", "maritime:colonies"),
    ("nomad raids", "nomads:raids"),
    ("hordes formed", "nomads:hordes_formed"),
    ("nomad conquests", "nomads:nomad_conquests"),
    ("agendas declared", "agendas:declared"),
    ("agendas fulfilled", "agendas:fulfilled"),
    ("epidemics (events)", "ev:epidemic"),
    ("epidemic deaths", "epidemic_deaths"),
    ("loan principal issued (domestic + foreign)", "finance:issued"),
    ("loan principal written off", "finance:written_off"),
    ("treaties signed", "diplomacy:signed"),
    ("techniques invented", "techniques:invented"),
)

_COUNTER_SYSTEMS = (
    ("cities", "counters"),
    ("guilds", "counters"),
    ("agent_movements", "counters"),
    ("maritime", "counters"),
    ("nomads", "counters"),
    ("gp_agendas", "counts"),
    ("finance", "totals"),
    ("diplomacy", "counts"),
    ("techniques", "counts"),
)
_SYSTEM_PREFIX = {"agent_movements": "movements", "gp_agendas": "agendas"}


def _bundles(path: Path) -> list[Path]:
    if (path / "chronicle_bundle.json").exists():
        return [path / "chronicle_bundle.json"]
    return sorted(path.glob("seed_*/chronicle_bundle.json"))


def _famine(history: list[dict]) -> dict:
    runs: dict[int, int] = {}
    observed = famine = 0
    episodes: list[int] = []
    for snapshot in history:
        food = snapshot.get("food")
        sufficiency = food.get("sufficiency") if isinstance(food, dict) else None
        if not isinstance(sufficiency, list):
            continue
        for region, value in enumerate(sufficiency):
            if value is None:
                if runs.get(region, 0) >= FAMINE_MIN_TURNS:
                    episodes.append(runs[region])
                runs[region] = 0
                continue
            observed += 1
            if value < FAMINE_SUFFICIENCY:
                famine += 1
                runs[region] = runs.get(region, 0) + 1
            else:
                if runs.get(region, 0) >= FAMINE_MIN_TURNS:
                    episodes.append(runs[region])
                runs[region] = 0
    episodes.extend(length for length in runs.values() if length >= FAMINE_MIN_TURNS)
    return {
        "famine_share": famine / observed if observed else 0.0,
        "famine_episodes": len(episodes),
        "famine_episode_mean": sum(episodes) / len(episodes) if episodes else 0.0,
        "famine_long_share": sum(1 for e in episodes if e >= 20) / len(episodes) if episodes else 0.0,
    }


def run_metrics(bundle_path: Path) -> dict:
    from chronicler.bundle_codec import load_bundle
    from chronicler.snapshot_pruning import restore_bundle

    bundle = restore_bundle(load_bundle(bundle_path))
    world = bundle.get("world_state") or {}
    history = bundle.get("history") or []
    pops = [sum(c.get("population", 0) for c in s.get("civ_stats", {}).values()) for s in history]
    first = history[0].get("civ_stats", {}) if history else {}
    row: dict = {
        "run": str(bundle_path.parent),
        "seed": bundle.get("metadata", {}).get("seed"),
        "generator": (world.get("geography") or {}).get("generator", "template"),
        "regions": len(world.get("regions", [])),
        "turns": bundle.get("metadata", {}).get("total_turns"),
        "pop_start": pops[0] if pops else 0,
        "pop_final": pops[-1] if pops else 0,
        "pop_min_ratio": (min(pops) / pops[0]) if pops and pops[0] else 0.0,
        "extinct": int(bool(pops) and pops[-1] == 0),
        "civs_start": len(first),
        "civ_records": len(world.get("civilizations", [])),
        "civs_alive": sum(1 for c in world.get("civilizations", []) if c.get("regions")),
    }
    row.update(_famine(history))
    events = Counter(e.get("event_type") for e in bundle.get("events_timeline", []) or [])
    row.update({f"ev:{kind}": count for kind, count in events.items()})
    for system, field in _COUNTER_SYSTEMS:
        state = world.get(system)
        counters = state.get(field) if isinstance(state, dict) else None
        if not isinstance(counters, dict):
            continue
        prefix = _SYSTEM_PREFIX.get(system, system)
        row[f"{prefix}:on"] = 1
        for key, value in counters.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                row[f"{prefix}:{key}"] = value
    finance = world.get("finance")
    if isinstance(finance, dict):
        totals = finance.get("totals") or {}
        row["finance:issued"] = totals.get("issued_domestic", 0) + totals.get("issued_foreign", 0)
    diplomacy = world.get("diplomacy")
    if isinstance(diplomacy, dict):
        counts = diplomacy.get("counts") or {}
        row["diplomacy:signed"] = sum(v for k, v in counts.items() if k.startswith("signed:"))
    cities = world.get("cities")
    if isinstance(cities, dict):
        row["cities_alive"] = len(cities.get("cities") or [])
    epidemics = world.get("epidemics")
    if isinstance(epidemics, dict):
        row["epidemic_deaths"] = epidemics.get("deaths_total", 0)
    return row


_NOT_COUNTS = frozenset({"extinct", "pop_start", "pop_final", "pop_min_ratio", "civs_start", "civ_records",
                         "civs_alive", "famine_share", "famine_episode_mean", "famine_long_share", "regions", "turns"})


def summarize(rows: list[dict]) -> dict:
    keys = sorted({k for r in rows for k, v in r.items() if isinstance(v, (int, float)) and k != "seed"})
    civ_centuries = sum(float(r.get("civs_start") or 0) * float(r.get("turns") or 0) / 100.0 for r in rows)
    out: dict = {"worlds": len(rows), "civ_centuries": civ_centuries}
    for key in keys:
        values = [float(r.get(key, 0) or 0) for r in rows]
        out[key] = {"mean": sum(values) / len(values), "any": sum(1 for v in values if v > 0) / len(values),
                    "rate": sum(values) / civ_centuries if civ_centuries else 0.0}
    return out


def _cell(summary: dict, key: str, per_civ_century: bool = False) -> str:
    item = summary.get(key)
    if item is None:
        return "-"
    mean = item["rate"] if per_civ_century and key not in _NOT_COUNTS else item["mean"]
    text = f"{mean:.3f}" if abs(mean) < 10 else f"{mean:,.0f}" if abs(mean) >= 1000 else f"{mean:.1f}"
    return f"{text} ({100 * item['any']:.0f}%)"


def markdown(labels: list[str], summaries: list[dict], per_civ_century: bool = False) -> str:
    lines = ["| Measure | " + " | ".join(labels) + " |", "| --- |" + " ---: |" * len(labels)]
    lines.append("| worlds | " + " | ".join(str(s["worlds"]) for s in summaries) + " |")
    for title, key in TABLE_ROWS:
        if per_civ_century and key == "famine_episodes":
            title = "famine episodes"
        lines.append(f"| {title} | " + " | ".join(_cell(s, key, per_civ_century) for s in summaries) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batches", nargs="+", help="LABEL=DIR")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--per-civ-century", action="store_true",
                        help="counts per starting civ per 100 turns (pooled) instead of per world")
    args = parser.parse_args(argv)
    labels: list[str] = []
    summaries: list[dict] = []
    all_rows: dict[str, list[dict]] = {}
    for item in args.batches:
        label, _, path = item.partition("=")
        if not path:
            label, path = Path(item).name, item
        if path.endswith(".json") and Path(path).is_file():
            saved = json.loads(Path(path).read_text(encoding="utf-8"))["runs"]
            rows = saved[label] if label in saved else next(iter(saved.values()))
        else:
            rows = [run_metrics(p) for p in _bundles(Path(path))]
        if not rows:
            print(f"{label}: no bundles under {path}", file=sys.stderr)
            return 1
        labels.append(label)
        summaries.append(summarize(rows))
        all_rows[label] = rows
    sys.stdout.write(markdown(labels, summaries, args.per_civ_century))
    if args.json is not None:
        args.json.write_text(json.dumps({"summaries": dict(zip(labels, summaries)), "runs": all_rows},
                                        indent=1, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
