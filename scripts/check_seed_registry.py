#!/usr/bin/env python3
"""Check validation seeds against ``scripts/seed_registry.json``.

Two read-only checks:

* **Gate range** (``check``): the seeds of a ``full`` validation profile must be
  exactly the range of a ``restricted_gate`` entry of their stratum that is also
  the stratum's ``restricted_ranges`` gate range (template 42-241, entry
  ``gate200-t``; procedural 42-141, entry ``gate-proc-p``). The seeds of any other
  profile must equal the range of some ``restricted_gate`` entry of the stratum
  (for example the 20-seed subset, ``gate200-subset-t``). ``m53b_run_validation.py``
  refuses a ``full`` run with a problem and prints a ``subset`` run's problems as
  warnings.
* **Restricted reuse** (``reuse_offenders``): every entry with status ``run`` whose
  seeds intersect a restricted range of its stratum (or the ``both`` holdout
  range) must say "development" in its ``use``. Entries that do not are reported
  as warnings; the existing ones are recorded history and are listed as an
  explicit allowlist in ``tests/test_seed_registry_check.py``, so a new one fails
  that test.

Usage::

    .venv/bin/python scripts/check_seed_registry.py
    .venv/bin/python scripts/check_seed_registry.py --profile full --seed-start 42 --seeds 200

It reads the registry only, never runs a simulation and exits 1 only when a
``full`` profile's seeds fail the gate-range check.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent / "seed_registry.json"
STRATA = ("template", "procedural")
HOLDOUT_KEY = "both"
GATE_STATUS = "restricted_gate"
DEVELOPMENT_WORD = "development"


def load_registry(path: Path = REGISTRY) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def expand(items: Iterable) -> set[int]:
    """Seed numbers of a registry ``seeds`` list: ints and inclusive ``[low, high]`` ranges."""
    out: set[int] = set()
    for item in items:
        if isinstance(item, list):
            out.update(range(item[0], item[1] + 1))
        else:
            out.add(item)
    return out


def _range_text(seeds: set[int]) -> str:
    if not seeds:
        return "no seeds"
    low, high = min(seeds), max(seeds)
    if seeds == set(range(low, high + 1)):
        return f"{low}-{high}"
    return f"{len(seeds)} seeds between {low} and {high}, not contiguous"


def check(profile: str, seeds: Iterable[int], stratum: str, registry: Mapping | None = None) -> list[str]:
    """Problems with a validation profile's seeds against the registry's gate entries
    (empty when they match). ``seeds`` are the profile's seed numbers; ``stratum`` is
    ``template`` or ``procedural`` (the ``--worldgen`` of the run)."""
    reg = load_registry() if registry is None else registry
    if stratum not in STRATA:
        return [f"stratum {stratum!r} is not one of {STRATA}"]
    wanted = set(seeds)
    gates = [e for e in reg.get("entries") or []
             if e.get("stratum") == stratum and e.get("status") == GATE_STATUS]
    if profile == "full":
        gate_ranges = [list(r) for r in (reg.get("restricted_ranges") or {}).get(stratum) or []]
        allowed = [e for e in gates if e.get("seeds") in ([r] for r in gate_ranges)]
        if not allowed:
            return [f"{stratum}: no restricted_gate entry has the gate range {gate_ranges}"]
    else:
        allowed = gates
    for entry in allowed:
        if expand(entry["seeds"]) == wanted:
            return []
    names = ", ".join(f"{e['id']} ({_range_text(expand(e['seeds']))})" for e in allowed) or "none"
    return [f"profile {profile} {stratum} seeds {_range_text(wanted)} match no restricted_gate "
            f"entry of the registry (allowed: {names})"]


def _restricted_ranges(reg: Mapping, stratum: str) -> list[tuple[int, int]]:
    ranges = reg.get("restricted_ranges") or {}
    return [tuple(r) for r in (ranges.get(stratum) or []) + (ranges.get(HOLDOUT_KEY) or [])]


def reuse_offenders(registry: Mapping | None = None) -> list[dict]:
    """``run`` entries whose seeds intersect a restricted range of their stratum (or
    the holdout range) and whose ``use`` does not say "development": one record per
    entry, ``{"id", "stratum", "restricted_seeds"}`` with the count of restricted
    seeds it used, in registry order."""
    reg = load_registry() if registry is None else registry
    out = []
    for entry in reg.get("entries") or []:
        if entry.get("status") != "run" or DEVELOPMENT_WORD in str(entry.get("use", "")):
            continue
        ranges = _restricted_ranges(reg, entry.get("stratum"))
        hit = [s for s in expand(entry.get("seeds") or []) if any(lo <= s <= hi for lo, hi in ranges)]
        if hit:
            out.append({"id": entry["id"], "stratum": entry["stratum"], "restricted_seeds": len(hit)})
    return out


def reuse_warnings(registry: Mapping | None = None) -> list[str]:
    return [f"warning: registry entry {o['id']} ({o['stratum']}) ran {o['restricted_seeds']} restricted "
            f"seed(s) and its use does not say {DEVELOPMENT_WORD!r}"
            for o in reuse_offenders(registry)]


def profile_seeds(seed_start: int, count: int) -> range:
    """The seeds ``m53b_run_validation.py`` runs: ``--seed-start`` and ``--seeds``."""
    return range(seed_start, seed_start + count)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--profile", help="validation profile to check (full refuses a mismatch)")
    parser.add_argument("--seed-start", type=int, default=42)
    parser.add_argument("--seeds", type=int, help="seed count (default: 200 template, 100 procedural)")
    parser.add_argument("--worldgen", choices=STRATA, default="template")
    args = parser.parse_args(argv)
    reg = load_registry(args.registry)
    for line in reuse_warnings(reg):
        print(line)
    if args.profile is None:
        return 0
    count = args.seeds if args.seeds is not None else (100 if args.worldgen == "procedural" else 200)
    problems = check(args.profile, profile_seeds(args.seed_start, count), args.worldgen, reg)
    for line in problems:
        print(("error: " if args.profile == "full" else "warning: ") + line)
    if not problems:
        print(f"profile {args.profile} {args.worldgen} seeds {args.seed_start}-{args.seed_start + count - 1}: "
              "match a restricted_gate entry")
    return 1 if problems and args.profile == "full" else 0


if __name__ == "__main__":
    sys.exit(main())
