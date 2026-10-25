#!/usr/bin/env python3
"""Print the cities of a run: counters, and each city's history as the
simulation recorded it, with its in-world name when the languages layer ran.

    python scripts/cities_report.py RUN_DIR [--city SETTLEMENT_ID]

RUN_DIR holds ``state.json`` (and its sidecars) and ``chronicle_bundle.json``
from a ``--cities`` run. See docs/integration/cities.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chronicler.cities import city_history
from chronicler.cities_state import CHARTER_NAMES, RANK_NAMES
from chronicler.models import WorldState


def _in_world(index, sid: int, turn: int) -> str:
    if index is None:
        return ""
    view = index.views("settlement", sid, turn)
    if view is None or view["name"] == view["canonical"]:
        return ""
    gloss = f", '{view['gloss']}'" if view.get("gloss") else ""
    return f" ({view['name']} in {index.lang_name(view['lang'])}{gloss})"


def report(run_dir: Path, only: int | None = None) -> str:
    world = WorldState.load(run_dir / "state.json")
    if world.cities is None:
        return f"{run_dir}: cities off\n"
    index = None
    bundle_path = run_dir / "chronicle_bundle.json"
    if bundle_path.exists():
        from chronicler.languages import NameIndex
        index = NameIndex.from_bundle(json.loads(bundle_path.read_text(encoding="utf-8")))
    civs = world.civilizations
    state = world.cities
    out = [f"{run_dir} (turn {world.turn})",
           "counters: " + ", ".join(f"{k} {round(v, 1):g}" for k, v in state.counters.items() if v)]
    for city in sorted(state.cities + state.fallen, key=lambda c: (c.founded_turn, c.settlement_id)):
        if only is not None and city.settlement_id != only:
            continue
        founder = civs[city.founder].name if 0 <= city.founder < len(civs) else "no one"
        lord = civs[city.lord].name if 0 <= city.lord < len(civs) else "no one"
        fate = (f"fell at turn {city.fallen_turn} ({city.fall_cause})" if city.fallen_turn is not None
                else f"standing: {RANK_NAMES[city.rank]} of {round(city.size)}, lord {lord}")
        out.append("")
        out.append(f"{city.name}{_in_world(index, city.settlement_id, world.turn)}, "
                   f"{world.regions[city.region].name}; founded turn {city.founded_turn} under {founder}; "
                   f"peak {RANK_NAMES[city.peak_rank]} ({city.peak_residents} people), "
                   f"purse peak {city.peak_wealth:.0f}; charter {CHARTER_NAMES[city.charter]}; {fate}")
        out.extend("  " + line for line in city_history(world, city.settlement_id))
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--city", type=int, default=None, help="only this settlement id")
    args = parser.parse_args(argv)
    sys.stdout.write(report(args.run_dir, args.city))
    return 0


if __name__ == "__main__":
    sys.exit(main())
