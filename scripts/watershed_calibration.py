"""Development-world calibration report of the watershed account (B1, record only).

Reads saved bundles of runs with ``--watershed`` and compares, region by
region, the water index the account would derive with the index the
simulation used: means, mean absolute gap, correlation over time and the
climate-phase cycle, for headwater regions (nothing drains into them) and
regions with upstream inflow; plus the account's totals, floods and
droughts. Development worlds only: it refuses a bundle whose seed is not a
procedural development seed (docs/superpowers/roadmaps/connected-world-program.md,
section 7). The constants are declared and uncalibrated; this report
describes them, it does not tune them.

    python scripts/watershed_calibration.py BUNDLE [BUNDLE ...] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

DEVELOPMENT_PROCEDURAL = (7, 11, 13, 17, 21, 31, 302, 303)
PHASES = ("temperate", "warming", "drought", "cooling")


def _mean(values):
    values = [v for v in values if v is not None]
    return math.fsum(values) / len(values) if values else None


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = math.fsum(xs) / n, math.fsum(ys) / n
    sx = math.sqrt(math.fsum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(math.fsum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _round(value, digits=3):
    return None if value is None else round(value, digits)


def summarize(bundle: dict) -> dict:
    """One bundle's report (pure: reads the decoded bundle only)."""
    seed = bundle["metadata"].get("seed")
    if seed not in DEVELOPMENT_PROCEDURAL or bundle["world_state"].get("geography") is None:
        raise SystemExit(f"refused: seed {seed!r} is not a procedural development world {DEVELOPMENT_PROCEDURAL}")
    records = [s["livelihoods"]["watershed"] for s in bundle["history"]
               if (s.get("livelihoods") or {}).get("watershed") and s["livelihoods"]["watershed"]["observed"]]
    if not records:
        raise SystemExit("refused: the bundle records no settled watershed account")
    down = records[-1]["graph"]["down"]
    n = len(down)
    has_upstream = [any(d == r for d in down) for r in range(n)]
    groups = {"headwater": [r for r in range(n) if not has_upstream[r]],
              "with_upstream": [r for r in range(n) if has_upstream[r]]}
    report = {"seed": seed, "regions": n, "turns": len(records), "first_turn": records[0]["source_turn"],
              "last_turn": records[-1]["source_turn"], "groups": {}}
    for name, members in groups.items():
        observed = [[rec["regions"]["index_observed"][r] for rec in records] for r in members]
        derived = [[rec["regions"]["index_derived"][r] for rec in records] for r in members]
        if not members:
            report["groups"][name] = {"regions": 0}
            continue
        gaps = [abs(d - o) for os, ds in zip(observed, derived) for o, d in zip(os, ds)]
        corrs = [_corr(os, ds) for os, ds in zip(observed, derived)]
        by_phase = {}
        for phase in PHASES:
            turns = [k for k, rec in enumerate(records) if rec["phase"] == phase]
            by_phase[phase] = {
                "observed": _round(_mean([observed[i][k] for i in range(len(members)) for k in turns])),
                "derived": _round(_mean([derived[i][k] for i in range(len(members)) for k in turns])),
            }
        amplitude = {kind: _round(max(v[kind] for v in by_phase.values() if v[kind] is not None)
                                  - min(v[kind] for v in by_phase.values() if v[kind] is not None))
                     for kind in ("observed", "derived")}
        report["groups"][name] = {
            "regions": len(members),
            "mean_observed": _round(_mean([v for s in observed for v in s])),
            "mean_derived": _round(_mean([v for s in derived for v in s])),
            "mean_abs_gap": _round(_mean(gaps)),
            "median_corr": _round(sorted(c for c in corrs if c is not None)[len([c for c in corrs if c is not None]) // 2])
            if any(c is not None for c in corrs) else None,
            "by_phase": by_phase,
            "phase_amplitude": amplitude,
        }
    last = records[-1]
    report["cumulative"] = {k: _round(v, 3) for k, v in last["cumulative"].items() if k != "closure_residual"}
    report["max_abs_closure_residual"] = max(abs(rec["totals"]["closure_residual"]) for rec in records)
    report["counters"] = last["counters"]
    report["floods"] = sum(len(rec["floods"]) for rec in records)
    report["flooded_regions"] = len({f["region"] for rec in records for f in rec["floods"]})
    return report


def markdown(reports: list[dict]) -> str:
    lines = ["| World | Group | Regions | Mean used | Mean derived | Mean abs gap | Median corr | Cycle amplitude used / derived |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for rep in reports:
        for name, g in rep["groups"].items():
            if not g.get("regions"):
                continue
            lines.append(f"| procedural {rep['seed']} | {name} | {g['regions']} | {g['mean_observed']} | {g['mean_derived']} | "
                         f"{g['mean_abs_gap']} | {g['median_corr']} | {g['phase_amplitude']['observed']} / "
                         f"{g['phase_amplitude']['derived']} |")
    lines += ["", "| World | Turns | Floods (regions) | Droughts declared | Drought region-turns | Precipitation | Evaporation | "
              "Irrigation | To sea | To sinks | Storage open → now | Max abs residual |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for rep in reports:
        c, k = rep["cumulative"], rep["counters"]
        lines.append(f"| procedural {rep['seed']} | {rep['turns']} | {rep['floods']} ({rep['flooded_regions']}) | "
                     f"{k['droughts_declared']} | {k['drought_region_turns']} | {c['precipitation']} | {c['evaporation']} | "
                     f"{c['withdrawal']} | {c['to_sea']} | {c['to_sink']} | {c['opening_storage']} → {c['storage']} | "
                     f"{rep['max_abs_closure_residual']:.1e} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("bundles", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, help="also write the reports as JSON here")
    args = parser.parse_args(argv)
    from chronicler.bundle_codec import load_bundle
    reports = [summarize(load_bundle(path)) for path in args.bundles]
    if args.json:
        args.json.write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    print("Development worlds only; declared, uncalibrated constants (record only).\n")
    print(markdown(reports))
    return 0


if __name__ == "__main__":
    sys.exit(main())
