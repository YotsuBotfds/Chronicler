"""Extract a household retail pilot opening schedule from a run's bundle.

The output is the JSON ``--household-retail-boundary schedule
--household-retail-schedule PATH`` reads: ``{"<region index>": <first opening
turn>}``, canonical (compact, ascending region), so its SHA-256 equals the
digest the run records. It replays one arm's enrollment in another (A2R: the
wage at a fixed enrollment, ``docs/integration/household-retail.md``).

The schedule comes from the last retail record's ``opened_turn`` (rules
version 2) or, in a version-1 bundle, from the first completed-turn frame of
each region; when both exist they must agree. A region that closed (no
controller) may reopen at another turn in the replay, because the schedule
reopens a region as soon as it has a controller again: such closures are
listed, and ``--strict`` refuses them.

Usage: python scripts/retail_schedule.py BUNDLE --output SCHEDULE.json [--strict]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path, help="chronicle_bundle.json of a household retail run")
    parser.add_argument("--output", type=Path, required=True, help="where to write the schedule JSON")
    parser.add_argument("--strict", action="store_true",
                        help="refuse a bundle whose log shows a pilot closure (the replay may differ)")
    args = parser.parse_args(argv)
    from chronicler.bundle_codec import load_bundle
    from chronicler.household_retail import extract_schedule, write_schedule
    try:
        found = extract_schedule(load_bundle(args.bundle))
    except (OSError, ValueError, KeyError) as exc:
        print(f"Error: {args.bundle}: {exc}", file=sys.stderr)
        return 1
    if args.strict and (found["closures"] or found["regions_closed"]):
        print(f"Error: {args.bundle}: pilot regions closed {found['closures'] or found['regions_closed']}; "
              "a replay may reopen them at other turns", file=sys.stderr)
        return 1
    digest = write_schedule(args.output, found["schedule"])
    print(json.dumps({"output": str(args.output), "sha256": digest, "regions": len(found["schedule"]),
                      "source": found["source"], "closures": found["closures"],
                      "regions_closed": found["regions_closed"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
