#!/usr/bin/env python3
"""Per-run technique and era numbers for one or more run batches.

``python scripts/techniques_report.py LABEL=BATCH_DIR [LABEL=BATCH_DIR ...] [--json OUT]``

Each batch directory holds ``seed_*/`` run directories (``state.json`` and
``chronicle_bundle.json``), as written by ``chronicler.main --seed-range`` or
the validation gate. Works for techniques-off batches too (technique columns
are then zero). Prints a markdown table of per-run means:

* techniques known per living civ at turns 50, 100, 150 and the last turn
  (``history[n].techniques.known``);
* inventions, and techniques gained by channel (merchants, migrants,
  soldiers, pilgrims, shared borders, land changing hands) and lost (decay,
  land) from ``state.techniques.counts``;
* tech advances and regressions (``tech_advancement`` / ``tech_regression``
  events, whichever system produced them);
* the era distribution of living civs at turn 100 and the last turn;
* extinct worlds (no living population);
* effects on other systems: final population, trade actions, wars
  declared, builds, expansions, great persons and artifacts, and, when those
  systems are on, epidemic deaths, quarantines, state loans and defaults, and
  treaties.

See docs/integration/techniques.md.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from chronicler.techniques_state import CHANNELS, CONQUEST  # noqa: E402

GAIN_CHANNELS = tuple(c for c in CHANNELS if c not in ("invention", "seeded")) + (CONQUEST,)
ERAS = ("tribal", "bronze", "iron", "classical", "medieval", "renaissance", "industrial", "information")
CHECKPOINTS = (50, 100, 150)
EFFECTS_ROWS = (
    ("population", "Final population"), ("trade_actions", "Trade actions"),
    ("wars_declared", "Wars declared"),
    ("builds", "Builds started"), ("expansions", "Expansions"),
    ("great_persons", "Great persons born"), ("artifacts", "Artifacts created"),
    ("epidemic_deaths", "Epidemic deaths"), ("quarantines", "Quarantines"),
    ("loans_issued", "State borrowing (treasury)"), ("defaults", "State defaults"),
    ("treaties", "Treaties signed"),
)


def _known_mean(snap: dict) -> float:
    known = (snap.get("techniques") or {}).get("known") or {}
    return sum(known.values()) / len(known) if known else 0.0


def _eras(snap: dict) -> Counter:
    return Counter(cs["tech_era"] for cs in snap.get("civ_stats", {}).values()
                   if cs.get("regions") and cs.get("alive", True))


def run_numbers(run_dir: Path) -> dict:
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    events = Counter(e["event_type"] for e in state["events_timeline"])
    counts = (state.get("techniques") or {}).get("counts", {})
    history: list[dict] = []
    bundle_path = run_dir / "chronicle_bundle.json"
    if bundle_path.exists():
        history = json.loads(bundle_path.read_text(encoding="utf-8")).get("history", [])
    by_turn = {snap["turn"]: snap for snap in history}
    last = history[-1] if history else {}
    known = {t: _known_mean(by_turn[t]) for t in CHECKPOINTS if t in by_turn}
    population = sum(r.get("population", 0) for r in state["regions"])
    epi = state.get("epidemics") or {}
    fin = (state.get("finance") or {}).get("totals", {})
    dip = state.get("diplomacy") or {}
    effects = {
        "population": population,
        "trade_actions": events.get("trade", 0),
        "wars_declared": events.get("war_declared", 0),
        "builds": events.get("build_started", 0),
        "expansions": events.get("expand", 0),
        "great_persons": events.get("great_person_born", 0),
        "artifacts": events.get("artifact_created", 0),
        "epidemic_deaths": epi.get("deaths_total", 0),
        "quarantines": events.get("quarantine", 0),
        "loans_issued": fin.get("issued_domestic", 0) + fin.get("issued_foreign", 0),
        "defaults": events.get("state_default", 0),
        "treaties": len(dip.get("treaties", [])),
    }
    return {
        "seed": run_dir.name,
        "known": known,
        "known_end": _known_mean(last) if last else 0.0,
        "invented": counts.get("invented", 0),
        "gained": {c: counts.get(f"gained:{c}", 0) for c in GAIN_CHANNELS},
        "lost_decay": counts.get("lost:decay", 0),
        "lost_land": counts.get("lost:land", 0),
        "advances": events.get("tech_advancement", 0),
        "regressions": events.get("tech_regression", 0),
        "eras_100": dict(_eras(by_turn[100])) if 100 in by_turn else {},
        "eras_end": dict(_eras(last)) if last else {},
        "extinct": population <= 0,
        "effects": effects,
    }


def batch_numbers(batch_dir: Path) -> list[dict]:
    return [run_numbers(d) for d in sorted(batch_dir.glob("seed_*")) if (d / "state.json").exists()]


def summarize(runs: list[dict]) -> dict:
    n = max(1, len(runs))
    out: dict = {"runs": len(runs)}
    for t in CHECKPOINTS:
        vals = [r["known"][t] for r in runs if t in r["known"]]
        out[f"known_t{t}"] = sum(vals) / len(vals) if vals else 0.0
    out["known_t_end"] = sum(r["known_end"] for r in runs) / n
    out["invented"] = sum(r["invented"] for r in runs) / n
    for c in GAIN_CHANNELS:
        out[f"gained_{c}"] = sum(r["gained"][c] for r in runs) / n
    out["lost_decay"] = sum(r["lost_decay"] for r in runs) / n
    out["lost_land"] = sum(r["lost_land"] for r in runs) / n
    out["advances"] = sum(r["advances"] for r in runs) / n
    out["regressions"] = sum(r["regressions"] for r in runs) / n
    for key in ("eras_100", "eras_end"):
        total: Counter = Counter()
        for r in runs:
            total.update(r[key])
        out[key] = {e: total[e] for e in ERAS if total[e]}
    out["extinct"] = sum(1 for r in runs if r["extinct"])
    for key, _ in EFFECTS_ROWS:
        out[f"fx_{key}"] = sum(r["effects"][key] for r in runs) / n
    return out


def _era_text(dist: dict) -> str:
    return ", ".join(f"{e} {n}" for e, n in dist.items()) or "-"


def markdown(labels: list[str], summaries: list[dict]) -> str:
    rows = [("Runs", "runs", "{:d}")]
    rows += [(f"Techniques known per civ, t{t}", f"known_t{t}", "{:.1f}") for t in CHECKPOINTS]
    rows += [("Techniques known per civ, last turn", "known_t_end", "{:.1f}"),
             ("Inventions", "invented", "{:.1f}")]
    rows += [(f"Gained via {c}", f"gained_{c}", "{:.1f}") for c in GAIN_CHANNELS]
    rows += [("Lost (practice decayed)", "lost_decay", "{:.1f}"), ("Lost (land lost)", "lost_land", "{:.1f}"),
             ("Tech advances", "advances", "{:.1f}"), ("Tech regressions", "regressions", "{:.1f}")]
    lines = ["| Per run | " + " | ".join(labels) + " |", "| --- |" + " --- |" * len(labels)]
    for title, key, fmt in rows:
        lines.append(f"| {title} | " + " | ".join(fmt.format(s[key]) for s in summaries) + " |")
    lines.append("| Eras of living civs, t100 (all runs) | "
                 + " | ".join(_era_text(s["eras_100"]) for s in summaries) + " |")
    lines.append("| Eras of living civs, last turn (all runs) | "
                 + " | ".join(_era_text(s["eras_end"]) for s in summaries) + " |")
    lines.append("| Extinct worlds | " + " | ".join(str(s["extinct"]) for s in summaries) + " |")
    for key, title in EFFECTS_ROWS:
        lines.append(f"| {title} | " + " | ".join(f"{s[f'fx_{key}']:.1f}" for s in summaries) + " |")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    json_out = None
    if "--json" in argv:
        i = argv.index("--json")
        json_out = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print(__doc__)
        return 2
    labels, summaries, detail = [], [], {}
    for spec in argv:
        label, _, path = spec.partition("=")
        runs = batch_numbers(Path(path))
        labels.append(label)
        summaries.append(summarize(runs))
        detail[label] = {"summary": summaries[-1], "runs": runs}
    print(markdown(labels, summaries))
    if json_out is not None:
        json_out.write_text(json.dumps(detail, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
