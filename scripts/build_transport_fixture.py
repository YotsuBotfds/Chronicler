#!/usr/bin/env python3
"""Build the transport fixture: a small bundle holding every optional system.

    python scripts/build_transport_fixture.py [OUT]

Writes ``viewer/src/__fixtures__/transport_bundle.json`` (bundle version 6)
by default. Both test suites load it: the Python live adapters
(``tests/test_historical_parity.py``) and the viewer's static, Batch Lab,
streaming and reconnect paths (``viewer/src/lib/__tests__/transport.test.ts``).

The source is a real 10-turn ``--agents off`` run (seed 42, 4 civs, 8
regions) with the default systems and ``--scholarship`` (off by default),
which writes every snapshot system of
``chronicler/transport_contract.json`` except the agent-mode ``food`` and
``migration``, ``grain_reserves`` and expansion experiment fields, plus the
``historiography``, ``languages`` and ``pruned_civ_stats`` fields. Agent-only fields are added as
stand-ins of the exported shape (``mutual_aid.snapshot_summary`` and
``[from region, to region, agents]`` rows): ``sufficiency`` 1.0 for each
controlled region and ``None`` elsewhere, no aid, and one row moving 5 agents
from the first controlled region to the next, plus explicitly empty granary,
injury/care, harvest-report and gathering summaries. These are transport shapes;
they do not qualify the mechanisms or establish natural-world observations.
``generated_at`` is fixed so
the file is reproducible. The committed file is built without the native
extension (the Python ecology path; ``PYTHONHASHSEED=0``): with it the same
run records different events.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "viewer" / "src" / "__fixtures__" / "transport_bundle.json"


def _stand_ins(bundle: dict) -> None:
    names = [r["name"] for r in bundle["world_state"]["regions"]]
    for snap in bundle["history"]:
        controlled = [i for i, name in enumerate(names) if snap["region_control"].get(name)]
        snap["food"] = {"sufficiency": [1.0 if i in controlled else None for i in range(len(names))],
                        "aid": []}
        snap["migration"] = [[controlled[0], controlled[1], 5]] if len(controlled) > 1 else []
        # Transport shape only: the source run has no agent economy or granaries.
        snap["grain_reserves"] = {"source_turn": snap["turn"] - 1, "granaries": [], "flows": [], "counters": {}}
        snap["health_care"] = {"source_turn": snap["turn"] - 1, "units": "worker-turns", "regions": [],
                                **dict.fromkeys(("episodes", "new_injuries", "recoveries", "impaired_work",
                                                 "care_work", "care_recipients", "recovery_progress",
                                                 "cared_recovery_progress"), 0)}
        snap["harvest_forecasts"] = {"source_turn": snap["turn"] - 1, "reports": [], "outcomes": [],
                                     "preparedness": [], "counters": {}, "calibration": []}
        snap["ritual_gatherings"] = {"source_turn": snap["turn"] - 1, "schedules": [],
                                    "outcomes": [], "counters": {}}


def build(out: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from chronicler.bundle import write_bundle
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    from chronicler.transport import BUNDLE_CARRIERS, BUNDLE_SYSTEMS, SNAPSHOT_SYSTEMS

    with tempfile.TemporaryDirectory() as tmp:
        args = _build_parser().parse_args([
            "--seed", "42", "--turns", "10", "--civs", "4", "--regions", "8", "--agents", "off",
            "--simulate-only", "--scholarship", "--output", str(Path(tmp) / "chronicle.md"),
            "--state", str(Path(tmp) / "state.json"),
        ])
        execute_run(args)
        bundle = load_bundle(Path(tmp) / "chronicle_bundle.json")
    _stand_ins(bundle)
    bundle["metadata"]["generated_at"] = "2026-10-26T00:00:00+00:00"
    missing = [k for k in SNAPSHOT_SYSTEMS if any(k not in s for s in bundle["history"])]
    missing += [k for k in BUNDLE_SYSTEMS + BUNDLE_CARRIERS if k not in bundle]
    if missing:
        raise SystemExit(f"the run did not write {missing}")
    out.parent.mkdir(parents=True, exist_ok=True)
    write_bundle(bundle, out)
    print(f"{out} ({out.stat().st_size} bytes, {len(bundle['history'])} snapshots)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", nargs="?", type=Path, default=DEFAULT_OUT)
    build(parser.parse_args().out)


if __name__ == "__main__":
    main()
