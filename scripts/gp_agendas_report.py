#!/usr/bin/env python3
"""Per-run great-person agenda numbers, for flag-on and flag-off runs alike.

``gp_agendas_report.py report LABEL=DIR [LABEL=DIR ...] [--json OUT]``
    DIR is one run directory (``state.json`` and ``chronicle_bundle.json``)
    or a batch of ``seed_*`` runs. Per run: agendas declared, fulfilled and
    failed by role (zero with the switch off), coups (by great persons, and
    all coups including the leader-mortality hazard's), wars declared,
    battles, the mean number of active trade routes per turn, artifacts
    created, and conversions when the run was measured (below). Prints a
    per-label mean table; ``--json`` writes every row.

``gp_agendas_report.py measure OUT_DIR -- ARGS...``
    Runs ``chronicler.main ARGS`` in this process (one seed, no
    ``--parallel``), counting agents whose belief changed from one turn's
    Phase 10 snapshot to the next (the snapshot that
    ``religion.compute_majority_belief`` reads), and writes
    ``OUT_DIR/conversions.json``. The counter only observes; outputs are
    unchanged. Select the source with ``PYTHONPATH`` (base or branch).

See docs/integration/great-person-agendas.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROLES = ("general", "merchant", "prophet", "scientist")


def _runs(path: Path) -> list[Path]:
    if (path / "state.json").exists():
        return [path]
    return sorted(p for p in path.glob("seed_*") if (p / "state.json").exists())


def run_metrics(run: Path) -> dict:
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    agendas = state.get("gp_agendas")
    counts = (agendas or {}).get("counts", {})
    events = state.get("events_timeline", [])
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
    row: dict = {"run": run.name, "on": agendas is not None}
    for role in ROLES:
        row[f"declared_{role}"] = counts.get(f"declared:{role}", 0)
    for key in ("declared", "fulfilled", "failed", "coup_attempts", "coups", "coups_failed",
                "campaign_victories", "war_agitation", "trade_missions", "trading_houses",
                "crown_loans", "preaching", "shrines"):
        row[key] = counts.get(key, 0)
    row["bonds"] = sum(v for k, v in counts.items() if k.startswith("bond:"))
    row["all_coups"] = sum(1 for ne in state.get("named_events", []) if ne.get("event_type") == "coup")
    row["wars_declared"] = by_type.get("war_declared", 0)
    row["war_events"] = by_type.get("war", 0)
    row["artifacts"] = len(state.get("artifacts", []))
    bundle_path = run / "chronicle_bundle.json"
    if bundle_path.exists():
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        history = bundle.get("history", [])
        routes = [len(h.get("trade_routes", [])) for h in history]
        row["trade_routes_mean"] = round(sum(routes) / len(routes), 3) if routes else 0.0
    conv = run / "conversions.json"
    if conv.exists():
        row["conversions"] = json.loads(conv.read_text(encoding="utf-8"))["conversions"]
    return row


_TABLE = ("declared_general", "declared_merchant", "declared_prophet", "declared_scientist",
          "fulfilled", "failed", "coups", "coups_failed", "all_coups", "wars_declared", "war_events",
          "trade_routes_mean", "conversions", "artifacts", "bonds")


def report(argv: list[str]) -> int:
    out_json = None
    if "--json" in argv:
        i = argv.index("--json")
        out_json = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    rows: dict[str, list[dict]] = {}
    for item in argv:
        label, _, directory = item.partition("=")
        rows[label] = [run_metrics(r) for r in _runs(Path(directory))]
    print("label".ljust(14) + "runs " + " ".join(k[:10].rjust(10) for k in _TABLE))
    for label, items in rows.items():
        cells = []
        for k in _TABLE:
            vals = [r[k] for r in items if k in r]
            cells.append(f"{sum(vals) / len(vals):10.2f}" if vals else "         -")
        print(label.ljust(14) + f"{len(items):4d} " + " ".join(cells))
    if out_json is not None:
        out_json.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    return 0


def measure(argv: list[str]) -> int:
    out_dir = Path(argv[0])
    if len(argv) < 2 or argv[1] != "--":
        print(__doc__)
        return 2
    import chronicler.religion as religion
    from chronicler.columnar import batch_arrays

    real = religion.compute_majority_belief
    seen: dict[int, int] = {}
    total = {"conversions": 0, "turns": 0}

    def counting(snapshot, *args, **kwargs):
        arrays = batch_arrays(snapshot, ("id", "belief")) if snapshot is not None else None
        if arrays is not None:
            ids, beliefs = (a.tolist() for a in arrays)
            changed = sum(1 for i, b in zip(ids, beliefs) if i in seen and seen[i] != b)
            total["conversions"] += changed
            total["turns"] += 1
            seen.clear()
            seen.update(zip(ids, beliefs))
        return real(snapshot, *args, **kwargs)

    religion.compute_majority_belief = counting
    from chronicler.main import main as chronicler_main
    sys.argv = ["chronicler.main", *argv[2:]]
    try:
        chronicler_main()
    finally:
        religion.compute_majority_belief = real
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "conversions.json").write_text(json.dumps(total, sort_keys=True), encoding="utf-8")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("report", "measure"):
        print(__doc__)
        return 2
    return report(argv[1:]) if argv[0] == "report" else measure(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
