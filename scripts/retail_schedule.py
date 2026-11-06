"""Extract a household retail pilot opening schedule from a run's bundle.

The output is the JSON ``--household-retail-boundary schedule
--household-retail-schedule PATH`` reads: ``{"<region index>": [[open, close],
..., [open, null]]}``, canonical (compact, ascending region), so its SHA-256
equals the digest the run records. It replays one arm's enrollment in another
(A2R: the wage at a fixed enrollment, ``docs/integration/household-retail.md``).

Exact from the last retail record's ``intervals`` (rules version 2 since S1):
a region is enrolled on exactly the source's turns, subject to the replaying
world's controller filter. A bundle without them (rules 1, or rules 2 before
S1) gives the intervals its completed-turn frames imply: approximate (a closure
with nothing held leaves no frame row); a warning says so and ``--strict``
refuses it.

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
                        help="refuse a bundle without recorded intervals (its schedule is approximate)")
    args = parser.parse_args(argv)
    from chronicler.bundle_codec import load_bundle
    from chronicler.household_retail import extract_schedule, write_schedule
    try:
        found = extract_schedule(load_bundle(args.bundle))
    except (OSError, ValueError, KeyError) as exc:
        print(f"Error: {args.bundle}: {exc}", file=sys.stderr)
        return 1
    if not found["exact"]:
        print(f"{'Error' if args.strict else 'Warning'}: {args.bundle} records no pilot intervals: the "
              f"schedule is read from its frames and is approximate", file=sys.stderr)
        if args.strict:
            return 1
    digest = write_schedule(args.output, found["schedule"])
    print(json.dumps({"output": str(args.output), "sha256": digest, "regions": len(found["schedule"]),
                      "source": found["source"], "exact": found["exact"], "closures": found["closures"],
                      "regions_closed": found["regions_closed"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
