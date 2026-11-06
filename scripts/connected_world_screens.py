"""Connected-world program screens (CW1-CW6): run, report and check them.

    python scripts/connected_world_screens.py run OUT_DIR --screen CW1 --cohort pilot|held|reserve|dev [...]
    python scripts/connected_world_screens.py report OUT_DIR/metrics.jsonl --screen CW1
    python scripts/connected_world_screens.py check --screen CW1|all [--metrics ... --cohort ...]
    python scripts/connected_world_screens.py mark-run OUT_DIR --screen CW1
    python scripts/connected_world_screens.py registry

The generic runner, the seed rules, the fixed harm panel, activation, the compute
ceiling and the identities are in ``scripts/screen_runner.py``; the seed numbers
are reserved in ``scripts/seed_registry.json``; the page is
docs/integration/connected-world-screens.md.

CW1-CW6 are **stubs**: only their cohorts are declared. Each slice fills in its
screen's base, arms, packages, outcomes (2-3 primary), activation rule and
extractor, writes its preregistration and sets ``ready=True``. Until then every
run of the screen is refused (``check`` reports it NOT READY, exit code 2).

``DEV`` is a development-only smoke screen (no pilot or held cohort): it runs the
runner end to end on registered development worlds, e.g.

    python scripts/connected_world_screens.py run OUT --screen DEV --cohort dev --worlds t1 --turns 10 --jobs 1
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screen_runner as SR  # noqa: E402  (the generic runner)

MODULE = Path(__file__).resolve()
PROGRESS = SR.REPO / "docs" / "superpowers" / "progress"

#: Shared by every screen (never held): template 5, procedural 19.
PILOT = {"template": (5,), "procedural": (19,)}
#: Placeholder base until a slice declares its own (every program arm is hybrid).
BASE = ("--turns", "200", "--agents", "hybrid", "--simulate-only")

#: Screen -> (title, the slice that fills it in, template held, procedural held).
_STUBS = {
    "CW1": ("S1 accounting and wages (A1-A2)", "S1", range(731, 737), range(831, 837)),
    "CW2": ("S2 workshop economics and owned-stock lifecycle (A3, A5)", "S2", range(741, 747), range(841, 847)),
    "CW3": ("S3 watershed and infrastructure (B1-B3)", "S3", range(751, 757), range(851, 857)),
    "CW4": ("S3 quarantine and public health (C1)", "S3", range(761, 767), range(861, 867)),
    "CW5": ("S4 trade, forest-water, care, attribution, requisition", "S4", range(771, 777), range(871, 877)),
    "CW6": ("S5 adaptive decisions, cross-border organisation, war; the integrated evaluation", "S5",
            range(781, 787), range(881, 887)),
}


def _stub(name: str, title: str, slice_: str, template, procedural) -> SR.Screen:
    return SR.Screen(
        name=name, title=title, preregistration=PROGRESS / f"connected-world-screens-{name.lower()}.md",
        base=BASE, arms={}, root=None, pilot=PILOT,
        held={"template": tuple(template), "procedural": tuple(procedural)},
        ready=False, not_ready=f"a stub: slice {slice_} declares its arms, outcomes, activation and extractor",
        module=MODULE)


SCREENS: dict[str, SR.Screen] = {name: _stub(name, *spec) for name, spec in _STUBS.items()}


# --- DEV: the development smoke screen ---------------------------------------------

def _timber_activation(bundle: dict, flags) -> tuple[bool | None, str]:
    """The timber stock acted when any observed turn cut timber."""
    observed = [r for s in bundle.get("history") or []
                if isinstance(r := SR._get(s, ("livelihoods", "timber_stock")), dict) and r.get("observed")]
    if not observed:
        return None, "no observed timber account"
    cut = sum(SR._num((r.get("totals") or {}).get("extraction")) and r["totals"]["extraction"] > 0 for r in observed)
    return (cut > 0), f"{cut} of {len(observed)} observed turns cut timber"


SCREENS["DEV"] = SR.Screen(
    name="DEV", title="Development smoke screen (development worlds only; never evidence)",
    preregistration=None,
    base=("--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves", "--public-grain-shipments"),
    arms={"W": ((), None), "TS": (("--timber-stock",), "W")}, root="W", pilot={}, held={},
    packages=(SR.Package("--timber-stock", ("livelihoods", "timber_stock")),),
    outcomes=(
        SR.Outcome("dev_population", "Population at the end (TS - W)", "TS", "W",
                   lambda r: SR.harm_value(r, "population"), primary=True),
        SR.Outcome("dev_stand", "Timber stand share of capacity at the end (TS)", "TS", None,
                   lambda r: SR.harm_value(r, "forest_stand"), primary=True),
        SR.Outcome("dev_food", "Food shortfall after relief (TS - W)", "TS", "W",
                   lambda r: SR.harm_value(r, "food_shortfall")),
    ),
    activation=_timber_activation, ready=True, module=MODULE)


def main(argv=None) -> int:
    return SR.main(argv, SCREENS, prog="connected_world_screens.py")


if __name__ == "__main__":
    raise SystemExit(main())
