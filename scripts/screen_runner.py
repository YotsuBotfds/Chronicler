"""Generic held-screen runner: run, report, check and resume a declared ``Screen``.

A program script declares its screens and hands them to :func:`main`
(``scripts/connected_world_screens.py`` does this for CW1-CW6):

    python scripts/<program>_screens.py run OUT_DIR --screen S --cohort pilot|held|reserve|dev [--jobs 3]
        [--arms a,b] [--seeds all|template|procedural] [--pilot PILOT_DIR/metrics.jsonl] [--reason TEXT]
        [--worlds t1,p7] [--turns N] [--keep-first] [--resume]
    python scripts/<program>_screens.py report OUT_DIR/metrics.jsonl --screen S
    python scripts/<program>_screens.py check --screen S|all [--metrics OUT_DIR/metrics.jsonl --cohort C]
    python scripts/<program>_screens.py mark-run OUT_DIR --screen S
    python scripts/<program>_screens.py registry

The skeleton (run/report/check, ``--resume``, the run environment and the source
identity) is lifted from ``scripts/productive_recovery_screens.py`` (run, report,
check: lines 1841-2166) and ``scripts/livelihoods_screens.py`` (``_run_env``,
``source_identity``), which stay frozen as evidence of their preregistrations.
Nothing here imports them, and nothing here is tied to ``LIVELIHOODS_SWITCHES``:
a package is any switch with a dated snapshot record, optionally a ``COUNTERS``
declaration.

What the runner enforces for every screen:

* **Seeds** (``check_seeds``) are read against ``scripts/seed_registry.json``.
  A held cohort must equal its own registry reservation and appear in no other
  entry, no restricted gate range (template 42-241, procedural 42-141), not in
  1000-1999, no development world, and must not have been run or listed twice.
  A pilot seed must be registered as the program's shared timing pilot and may
  share its number only with other timing pilots (never a held or reserve
  cohort, a gate, the holdout range or a development world).
* **Preregistration**: 2-3 primary outcomes per screen; a held run also needs
  the preregistration's ``Status:`` line to read FROZEN, a machine-read
  ``Compute ceiling: X core-hours`` line and a ``Primary outcomes: a, b`` line
  naming exactly the screen's primaries.
* **Compute ceiling**: a held run needs ``--pilot`` (the pilot's metrics and its
  ``source.txt``: same extension, runner, screen module, registry and dirty
  count, and a source revision that differs at most outside the code); it
  refuses when the pilot projection times 1.5 exceeds the ceiling, and starts a
  run only while the seconds used, the expected seconds of the runs in flight
  and the run's own expected seconds fit under the ceiling (expected: the larger
  of the pilot mean for the arm and stratum and the finished runs' mean for the
  stratum). The runs not started are reported as not run; exit code 4.
* **Evidence runs** (``held``, or ``reserve`` with ``--reason`` for a named screen
  whose held run must be repeated) are recorded at their start in
  ``OUT_DIR/held-run.json`` and the clone's ledger (``output/held-runs/``); a new
  run of the same cohort is refused while one is recorded (resume it instead).
  ``mark-run`` then records the run in the registry (status ``run`` with a
  ``held_run`` record), which refuses the cohort in every clone.
* **Harm panel** (``HARM_PANEL``): the same harms are extracted for every run and
  shown beside every comparison. A harm whose system is off reads "not
  recorded", one without a bundle field reads "requires slice extractor";
  neither reads as zero.
* **Activation** is recorded per run and reported per world before any effect;
  a world where the arm did not act is shown as "not activated", never as zero,
  and is left out of the effect summaries.
* **Identity**: ``source.txt`` records the source revision and dirty count, the
  imported ``chronicler``, the native extension's SHA-256, the interpreter, the
  SHA-256 of this runner, of the screen module (extractors live there), of the
  registry and, for evidence runs, of the preregistration; every row carries the
  identity digest and the schema versions it read. ``--resume`` refuses any
  change.
* **Uncertainty**, descriptive only: per stratum mean, min/max, sign counts and
  an exact enumeration of the paired sign flips of the mean over the worlds (for
  an outcome with a control; the harm panel is shown beside every arm against
  its control).

A missing or malformed outcome (or harm) makes the run a visible failure
(rc 3, the reasons named); nothing missing reads as zero.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Mapping, Sequence

REPO = Path(__file__).resolve().parents[1]
RUNNER = Path(__file__).resolve()
REGISTRY = REPO / "scripts" / "seed_registry.json"
PY = sys.executable
STRATA = ("template", "procedural")
TAGS = {"template": "t", "procedural": "p"}
STRATUM_OF = {tag: stratum for stratum, tag in TAGS.items()}
PROCEDURAL = ("--worldgen", "procedural", "--regions", "32", "--civs", "10")
#: Restricted qualification gate ranges (inclusive) and the out-of-gate holdout range.
GATE_RANGES = {"template": ((42, 241),), "procedural": ((42, 141),)}
HOLDOUT_RANGE = (1000, 1999)
PRIMARIES = (2, 3)
CEILING_MARGIN = 1.5
REGISTRY_STATUSES = ("run", "never_run", "reserved", "restricted_gate", "development")
REGISTRY_COHORTS = ("held", "pilot", "reserve")
ENTRY_KEYS = ("id", "source", "use", "stratum", "world", "seeds", "turns", "status")
OPTIONAL_ENTRY_KEYS = ("program", "cohort", "screen", "held_run")
HELD_RUN_KEYS = ("out", "identity", "started", "rows", "complete", "recorded")
#: Cohorts that are evidence: a frozen preregistration, the compute ceiling, the ledger.
EVIDENCE_COHORTS = ("held", "reserve")
#: Every evidence run's start, per clone (``output/`` is ignored by git); ``mark-run``
#: records the run in the registry, which every clone reads.
LEDGER = REPO / "output" / "held-runs" / "ledger.jsonl"
#: Exit codes: a simulation failed (1), an outcome is missing or malformed (3), the
#: compute ceiling stopped the run (4).
RC_FAILED, RC_MISSING, RC_CEILING = 1, 3, 4
SIGN_FLIP_MAX_WORLDS = 16


# --- Declarations ------------------------------------------------------------------

@dataclass(frozen=True)
class Package:
    """A switch a screen enables and checks: its flag, the snapshot record it writes
    (keys from the snapshot, e.g. ``("livelihoods", "household_retail")``), the
    lifetime counters read from the record's ``counters`` (declared by
    ``counters_module.COUNTERS``) and its mode option and default mode."""
    flag: str
    path: tuple[str, ...]
    counters_module: str | None = None
    counters: tuple[str, ...] = ()
    mode_flag: str | None = None
    default_mode: str | None = None

    @property
    def name(self) -> str:
        return self.path[-1]


@dataclass(frozen=True)
class Outcome:
    """One preregistered outcome: ``read(row)`` for the arm minus ``read(row)`` for the
    control on the same world (or the arm alone when ``control`` is None)."""
    id: str
    label: str
    arm: str
    control: str | None
    read: Callable[[dict], float | None]
    primary: bool = False


@dataclass(frozen=True)
class Screen:
    """A preregistered screen. ``ready=False`` marks a stub whose arms, outcomes and
    extractor a later slice fills in; every run of it is refused."""
    name: str
    title: str
    preregistration: Path | None
    base: tuple[str, ...]
    arms: Mapping[str, tuple[tuple[str, ...], str | None]]
    root: str | None
    pilot: Mapping[str, tuple[int, ...]]
    held: Mapping[str, tuple[int, ...]]
    packages: tuple[Package, ...] = ()
    outcomes: tuple[Outcome, ...] = ()
    #: (bundle, arm flags) -> (activated: True/False/None for unknown, evidence text)
    activation: Callable[[dict, Sequence[str]], tuple[bool | None, str]] | None = None
    #: (bundle, arm flags) -> (screen measures, problems)
    extract: Callable[[dict, Sequence[str]], tuple[dict, list[str]]] | None = None
    ready: bool = False
    not_ready: str = ""
    procedural: tuple[str, ...] = PROCEDURAL
    requires_native: bool = True
    module: Path | None = None

    def cohort(self, cohort: str) -> Mapping[str, tuple[int, ...]]:
        return {"pilot": self.pilot, "held": self.held}[cohort]

    def primaries(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.primary]


@dataclass
class Runtime:
    """What touches the machine, replaceable in tests (the offline guard forbids
    child processes): one simulation, the source identity, the clock, the evidence-run
    ledger and the paths that differ between two source revisions."""
    simulate: Callable[[list[str]], Any] = None  # type: ignore[assignment]
    identity: Callable[[Screen], list[str]] = None  # type: ignore[assignment]
    clock: Callable[[], float] = time.time
    ledger: Path = LEDGER
    changed_paths: Callable[[str, str], list[str] | None] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.simulate is None:
            self.simulate = simulate
        if self.identity is None:
            self.identity = source_identity
        if self.changed_paths is None:
            self.changed_paths = changed_paths


def changed_paths(old: str, new: str) -> list[str] | None:
    """Paths that differ between two revisions (None when git cannot tell)."""
    p = subprocess.run(["git", "-C", str(REPO), "diff", "--name-only", old, new], capture_output=True, text=True)
    return p.stdout.split() if p.returncode == 0 else None


# --- Seed registry -----------------------------------------------------------------

def load_registry(path: Path = REGISTRY) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def expand(seeds) -> set[int]:
    """The seed numbers of an entry: ints and inclusive ``[low, high]`` ranges."""
    out: set[int] = set()
    for item in seeds:
        if isinstance(item, list):
            out.update(range(item[0], item[1] + 1))
        else:
            out.add(item)
    return out


def _seed_items_ok(seeds) -> bool:
    if not isinstance(seeds, list) or not seeds:
        return False
    for item in seeds:
        if isinstance(item, list):
            if len(item) != 2 or not all(type(x) is int and x >= 0 for x in item) or item[0] > item[1]:
                return False
        elif type(item) is not int or item < 0:
            return False
    return True


def _in_ranges(seed: int, ranges) -> bool:
    return any(lo <= seed <= hi for lo, hi in ranges)


def restricted(stratum: str) -> tuple[tuple[int, int], ...]:
    """The gate range of a stratum and the holdout range."""
    return (*GATE_RANGES[stratum], HOLDOUT_RANGE)


def validate_registry(reg: Mapping) -> list[str]:
    """Problems with the registry's shape or its reservations (empty when sound)."""
    problems = []
    if reg.get("schema_version") != 1:
        problems.append(f"schema_version {reg.get('schema_version')!r}, expected 1")
    entries = reg.get("entries")
    if not isinstance(entries, list) or not entries:
        return problems + ["entries missing"]
    ranges = reg.get("restricted_ranges") or {}
    expected = {"template": [list(r) for r in GATE_RANGES["template"]],
                "procedural": [list(r) for r in GATE_RANGES["procedural"]], "both": [list(HOLDOUT_RANGE)]}
    if ranges != expected:
        problems.append(f"restricted_ranges {ranges!r} differ from the runner's {expected!r}")
    seen_ids: set[str] = set()
    good = []
    for i, e in enumerate(entries):
        where = f"entry {i} ({e.get('id') if isinstance(e, dict) else '?'})"
        if not isinstance(e, dict):
            problems.append(f"{where}: not an object")
            continue
        missing = [k for k in ENTRY_KEYS if k not in e]
        extra = [k for k in e if k not in ENTRY_KEYS + OPTIONAL_ENTRY_KEYS]
        if missing or extra:
            problems.append(f"{where}: missing {missing}, unknown {extra}")
            continue
        if not isinstance(e["id"], str) or e["id"] in seen_ids:
            problems.append(f"{where}: id missing or repeated")
        seen_ids.add(e["id"])
        if e["stratum"] not in STRATA:
            problems.append(f"{where}: stratum {e['stratum']!r}")
        if e["status"] not in REGISTRY_STATUSES:
            problems.append(f"{where}: status {e['status']!r}")
        if not _seed_items_ok(e["seeds"]):
            problems.append(f"{where}: seeds must be non-negative ints or [low, high] ranges")
        if not isinstance(e["turns"], list) or not all(type(t) is int and t > 0 for t in e["turns"]):
            problems.append(f"{where}: turns must be a list of positive ints")
        if not all(isinstance(e[k], str) and e[k] for k in ("source", "use", "world")):
            problems.append(f"{where}: source, use and world must be text")
        cohort = e.get("cohort")
        if cohort is not None and cohort not in REGISTRY_COHORTS:
            problems.append(f"{where}: cohort {cohort!r}")
        if e["status"] == "reserved":
            if not e.get("program") or cohort is None:
                problems.append(f"{where}: a reservation names its program and cohort")
            if cohort == "held" and not e.get("screen"):
                problems.append(f"{where}: a held reservation names its screen")
        if "held_run" in e:
            run = e["held_run"]
            if e["status"] != "run" or not isinstance(run, dict) or not set(HELD_RUN_KEYS) <= set(run) \
                    or not set(run) <= set(HELD_RUN_KEYS) | {"reason"}:
                problems.append(f"{where}: held_run is a {list(HELD_RUN_KEYS)} record on a run entry")
        if e["stratum"] in STRATA and _seed_items_ok(e["seeds"]):
            good.append(e)
    for stratum in STRATA:
        gates = {tuple(x) for e in good if e["stratum"] == stratum and e["status"] == "restricted_gate"
                 for x in e["seeds"] if isinstance(x, list)}
        for lo_hi in GATE_RANGES[stratum]:
            if lo_hi not in gates:
                problems.append(f"{stratum}: no restricted_gate entry for the gate range {list(lo_hi)}")
    for e in good:
        if e["status"] != "reserved":
            continue
        mine = expand(e["seeds"])
        bad = sorted(s for s in mine if _in_ranges(s, restricted(e["stratum"])))
        if bad:
            problems.append(f"{e['id']}: reserved seeds {bad[:6]} are in a restricted range")
        for other in good:
            if other is e or other["stratum"] != e["stratum"]:
                continue
            shared = mine & expand(other["seeds"])
            if not shared:
                continue
            if e.get("cohort") == "pilot" and other.get("cohort") == "pilot":
                continue
            if e.get("cohort") == "pilot" and other.get("cohort") is None and other["status"] != "development":
                continue      # a shared timing pilot may have been seen by an exploratory run
            problems.append(f"{e['id']}: reserved seeds {sorted(shared)[:6]} are also in {other['id']}")
    return problems


def seed_sets(reg: Mapping, stratum: str) -> dict[str, set[int]]:
    """The registry's derived sets for one stratum: every seed used, those never to be
    run again (cohorts run or withdrawn), development worlds, restricted seeds and
    reserved seeds."""
    out = {"used": set(), "never_run_again": set(), "development": set(), "restricted": set(), "reserved": set()}
    for e in reg["entries"]:
        if e["stratum"] != stratum:
            continue
        seeds = expand(e["seeds"])
        out["used"] |= seeds
        if e["status"] in ("run", "never_run"):
            out["never_run_again"] |= seeds
        elif e["status"] == "development":
            out["development"] |= seeds
        elif e["status"] == "restricted_gate":
            out["restricted"] |= seeds
        elif e["status"] == "reserved":
            out["reserved"] |= seeds
    return out


def check_seeds(screen: Screen, reg: Mapping) -> tuple[list[str], list[str]]:
    """(problems, notes) for the screen's pilot and held cohorts against the registry."""
    problems, notes = validate_registry(reg), []
    if problems:
        return problems, notes          # a malformed registry is refused, never half-read
    for stratum in STRATA:
        entries = [e for e in reg["entries"] if e["stratum"] == stratum]
        development = set().union(*(expand(e["seeds"]) for e in entries if e["status"] == "development"))
        held_list = list(screen.held.get(stratum, ()))
        pilot_list = list(screen.pilot.get(stratum, ()))
        held, pilot = set(held_list), set(pilot_list)
        for label, seeds in (("held", held_list), ("pilot", pilot_list)):
            twice = sorted({s for s in seeds if seeds.count(s) > 1})
            if twice:
                problems.append(f"{screen.name} {stratum} {label}: seeds {twice} listed more than once")
            gated = sorted(s for s in set(seeds) if _in_ranges(s, GATE_RANGES[stratum]))
            if gated:
                problems.append(f"{screen.name} {stratum} {label}: seeds {gated} are in the restricted gate range")
            held_out = sorted(s for s in set(seeds) if _in_ranges(s, (HOLDOUT_RANGE,)))
            if held_out:
                problems.append(f"{screen.name} {stratum} {label}: seeds {held_out} are in 1000-1999")
            dev = sorted(set(seeds) & development)
            if dev:
                problems.append(f"{screen.name} {stratum} {label}: seeds {dev} are development worlds")
        if pilot & held:
            problems.append(f"{screen.name} {stratum}: pilot and held overlap {sorted(pilot & held)}")
        own = [e for e in entries if e.get("screen") == screen.name and e.get("cohort") == "held"]
        reserved = set().union(*(expand(e["seeds"]) for e in own))
        if held and held != reserved:
            problems.append(f"{screen.name} {stratum} held {sorted(held)} differs from its registry reservation "
                            f"{sorted(reserved)}")
        for e in own:
            if e["status"] == "run":
                problems.append(f"{screen.name} {stratum}: held seeds of {e['id']} were already run (reused)")
            elif e["status"] != "reserved":
                problems.append(f"{screen.name} {stratum}: {e['id']} is {e['status']}, not reserved")
        for e in entries:
            if e in own:
                continue
            shared = held & expand(e["seeds"])
            if shared:
                problems.append(f"{screen.name} {stratum} held seeds {sorted(shared)} are in another cohort "
                                f"or use: {e['id']} ({e['status']})")
        for seed in sorted(pilot):
            hits = [e for e in entries if seed in expand(e["seeds"])]
            shared_pilot = [e for e in hits if e.get("cohort") == "pilot" and e["status"] == "reserved"
                            and e.get("screen") in (None, screen.name)]
            if not shared_pilot:
                problems.append(f"{screen.name} {stratum} pilot seed {seed} is not registered as the shared pilot")
            for e in hits:
                if e.get("cohort") in ("held", "reserve"):
                    problems.append(f"{screen.name} {stratum} pilot seed {seed} is in a {e['cohort']} cohort: {e['id']}")
                elif e.get("cohort") is None and e["status"] not in ("development", "restricted_gate"):
                    notes.append(f"{stratum} pilot seed {seed} was also used by {e['id']} ({e['use']}); "
                                 "a timing pilot is never held")
    return problems, notes


def compress(seeds: set[int]) -> str:
    """``1-3, 5, 7-9``."""
    out, run = [], []
    for s in sorted(seeds):
        if run and s == run[-1] + 1:
            run.append(s)
            continue
        if run:
            out.append(str(run[0]) if len(run) == 1 else f"{run[0]}-{run[-1]}")
        run = [s]
    if run:
        out.append(str(run[0]) if len(run) == 1 else f"{run[0]}-{run[-1]}")
    return ", ".join(out)


# --- Preregistration ---------------------------------------------------------------

_STATUS = re.compile(r"^Status:(.*)$", re.M)
_CEILING = re.compile(r"^Compute ceiling:\s*([0-9]+(?:\.[0-9]+)?)\s*core-hours\b", re.M)
_PRIMARIES = re.compile(r"^Primary outcomes:\s*(.+)$", re.M)


def preregistration_text(screen: Screen) -> str | None:
    if screen.preregistration is None:
        return None
    try:
        return Path(screen.preregistration).read_text(encoding="utf-8")
    except OSError:
        return None


def preregistration_frozen(text: str | None) -> bool:
    """Whether a ``Status:`` line reads FROZEN (and not DRAFT): the lead's freeze."""
    return bool(text) and any("FROZEN" in m and "DRAFT" not in m for m in _STATUS.findall(text))


def compute_ceiling(text: str | None) -> float | None:
    """The machine-read ``Compute ceiling: X core-hours`` of a preregistration."""
    found = _CEILING.findall(text or "")
    return float(found[0]) if len(found) == 1 else None


def declared_primaries(text: str | None) -> list[str] | None:
    found = _PRIMARIES.findall(text or "")
    if len(found) != 1:
        return None
    return [p.strip().strip("`") for p in found[0].split(",") if p.strip()]


def check_preregistration(screen: Screen, *, held: bool) -> list[str]:
    """Outcome declarations (2-3 primaries, known arms, declared comparisons) and, for
    a held run, the frozen preregistration with its ceiling and primaries."""
    problems = []
    primaries = screen.primaries()
    lo, hi = PRIMARIES
    if not lo <= len(primaries) <= hi:
        problems.append(f"{screen.name}: {len(primaries)} primary outcomes, a screen declares {lo}-{hi}")
    ids = [o.id for o in screen.outcomes]
    if len(ids) != len(set(ids)):
        problems.append(f"{screen.name}: outcome ids repeat")
    for o in screen.outcomes:
        if o.arm not in screen.arms:
            problems.append(f"outcome {o.id}: unknown arm {o.arm}")
            continue
        if o.control is not None:
            chain, a = [], screen.arms[o.arm][1]
            while a is not None and a in screen.arms and a not in chain:
                chain.append(a)
                a = screen.arms[a][1]
            if o.control not in chain:
                problems.append(f"outcome {o.id}: {o.control} is not a control of {o.arm} (its controls: {chain})")
    if held:
        text = preregistration_text(screen)
        where = screen.preregistration.relative_to(REPO) if screen.preregistration and \
            Path(screen.preregistration).is_relative_to(REPO) else screen.preregistration
        if text is None:
            problems.append(f"{screen.name}: preregistration {where} missing")
        else:
            if not preregistration_frozen(text):
                problems.append(f"{screen.name}: {where} is not marked FROZEN")
            if compute_ceiling(text) is None:
                problems.append(f"{screen.name}: {where} has no single 'Compute ceiling: X core-hours' line")
            declared = declared_primaries(text)
            if declared is None or sorted(declared) != sorted(o.id for o in primaries):
                problems.append(f"{screen.name}: {where} 'Primary outcomes:' line {declared} differs from the "
                                f"screen's primaries {[o.id for o in primaries]}")
    return problems


# --- Screen checks -----------------------------------------------------------------

def _src() -> None:
    if str(REPO / "src") not in sys.path:
        sys.path.insert(0, str(REPO / "src"))


def check_screen(screen: Screen) -> list[str]:
    """A ready screen's arms (a tree rooted at its root, every command line parsing
    and accepted by the feature catalog), packages (counters declared by their
    module) and outcome declarations."""
    if not screen.ready:
        return [f"{screen.name} is not ready: {screen.not_ready or 'no arms or outcomes yet'}"]
    problems = []
    if not screen.arms or screen.root not in screen.arms:
        problems.append(f"{screen.name}: root arm {screen.root!r} is not an arm")
    roots = [arm for arm, (_f, control) in screen.arms.items() if control is None]
    if roots != [screen.root]:
        problems.append(f"{screen.name}: root arms {roots}, expected [{screen.root!r}]")
    for arm, (_flags, control) in screen.arms.items():
        seen, a = set(), arm
        while a is not None and a in screen.arms and a not in seen:
            seen.add(a)
            a = screen.arms[a][1]
        if a is not None:
            problems.append(f"arm {arm}: its controls do not lead to the root ({control!r})")
    if screen.activation is None:
        problems.append(f"{screen.name}: no activation rule (activation is reported before any effect)")
    problems += check_preregistration(screen, held=False)
    problems += check_packages_declared(screen)
    problems += check_arm_flags(screen)
    return problems


def check_packages_declared(screen: Screen) -> list[str]:
    from importlib import import_module
    _src()
    problems = []
    for p in screen.packages:
        if p.counters and not p.counters_module:
            problems.append(f"{p.flag}: counters read without a declaring module")
            continue
        if p.counters_module:
            try:
                declared = set(getattr(import_module(p.counters_module), "COUNTERS"))
            except (ImportError, AttributeError) as error:
                problems.append(f"{p.flag}: {p.counters_module}.COUNTERS unavailable ({error})")
                continue
            problems += [f"{p.name}.{c} is not a declared counter" for c in p.counters if c not in declared]
    return problems


def arm_command(screen: Screen, arm: str, stratum: str, seed: int, turns: int | None = None) -> list[str]:
    base = list(screen.base)
    if turns is not None:
        if "--turns" not in base:
            raise SystemExit(f"{screen.name}: the base names no --turns to override")
        base[base.index("--turns") + 1] = str(turns)
    extra = list(screen.procedural) if stratum == "procedural" else []
    return ["--seed", str(seed), *base, *extra, *screen.arms[arm][0]]


def check_arm_flags(screen: Screen) -> list[str]:
    """Every arm's command line parses with the real parser and the feature catalog
    accepts the switches it turns on (prerequisites, agent mode, choices)."""
    _src()
    from chronicler import feature_catalog as fc
    from chronicler.main import _build_parser
    parser = _build_parser()
    problems = []
    for arm in screen.arms:
        for stratum in STRATA:
            argv = arm_command(screen, arm, stratum, 1)
            try:
                args = parser.parse_args(argv)
            except SystemExit:
                problems.append(f"arm {arm} ({stratum}): the command line does not parse: {' '.join(argv)}")
                continue
            refusal = fc.validate_features({}, fc.live_surface(args))
            if refusal:
                problems.append(f"arm {arm} ({stratum}): {refusal}")
    return problems


def expected_packages(screen: Screen, flags: Sequence[str]) -> dict[str, str | None]:
    """{package name: mode} of the declared packages the base plus ``flags`` enable."""
    flags = [*screen.base, *flags]
    out = {}
    for p in screen.packages:
        if p.flag in flags:
            out[p.name] = (flags[flags.index(p.mode_flag) + 1] if p.mode_flag and p.mode_flag in flags
                           else p.default_mode)
    return out


# --- Extraction --------------------------------------------------------------------

def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _get(d, path):
    for key in path:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
    return d


def schema_versions(bundle: dict) -> dict:
    """Every schema version the extractor read: the bundle's, the livelihoods
    container's, each package record's and each dated snapshot record's."""
    out: dict[str, Any] = {"bundle": (bundle.get("metadata") or {}).get("bundle_version")}
    livelihoods, packages, records = set(), {}, {}
    for snap in bundle.get("history") or []:
        if not isinstance(snap, dict):
            continue
        for key, value in snap.items():
            if not isinstance(value, dict):
                continue
            if key == "livelihoods":
                livelihoods.add(value.get("schema_version"))
                for name, rec in value.items():
                    if isinstance(rec, dict) and "schema_version" in rec:
                        packages.setdefault(name, set()).add(rec["schema_version"])
            elif "schema_version" in value:
                records.setdefault(key, set()).add(value["schema_version"])
    key = lambda v: (str(type(v)), str(v))  # noqa: E731
    out["livelihoods"] = sorted(livelihoods, key=key)
    out["packages"] = {k: sorted(v, key=key) for k, v in sorted(packages.items())}
    out["records"] = {k: sorted(v, key=key) for k, v in sorted(records.items())}
    return out


def package_problems(screen: Screen, bundle: dict, flags: Sequence[str]) -> tuple[dict, list[str]]:
    """({package: {counter: value}}, problems): every enabled package's record is dated
    and in its mode, its counters are declared and numeric; a package the arm does not
    enable records nothing."""
    from importlib import import_module
    hist = bundle.get("history") or []
    expected = expected_packages(screen, flags)
    out, problems = {}, []
    for p in screen.packages:
        carrying = [s for s in hist if _get(s, p.path) is not None]
        if p.name not in expected:
            if carrying:
                problems.append(f"{p.name}: recorded at turns {[s.get('turn') for s in carrying[:5]]} "
                                "in an arm without it")
            continue
        if not carrying:
            problems.append(f"{p.name}: enabled but never recorded")
            continue
        mode = expected[p.name]
        declared = None
        if p.counters:
            _src()
            declared = set(getattr(import_module(p.counters_module), "COUNTERS"))
        # Every snapshot's record is checked, not only the last one's.
        not_object, misdated, modes, no_counters = [], [], {}, []
        undeclared, non_numeric = set(), set()
        for snap in carrying:
            rec, turn = _get(snap, p.path), snap.get("turn")
            if not isinstance(rec, dict):
                not_object.append(turn)
                continue
            if "source_turn" in rec and rec["source_turn"] != snap.get("turn", 0) - 1:
                misdated.append(turn)
            if mode is not None and rec.get("mode") != mode:
                modes.setdefault(repr(rec.get("mode")), []).append(turn)
            if declared is not None:
                counters = rec.get("counters")
                if not isinstance(counters, dict):
                    no_counters.append(turn)
                    continue
                undeclared |= set(counters) - declared
                non_numeric |= {k for k, v in counters.items() if not _num(v)}
        if not_object:
            problems.append(f"{p.name}: records that are not objects at turns {not_object[:5]}")
        if misdated:
            problems.append(f"{p.name}: misdated records at turns {misdated[:5]}")
        for got, turns in modes.items():
            problems.append(f"{p.name}: mode {got}, expected {mode!r} at turns {turns[:5]}")
        if no_counters:
            problems.append(f"{p.name}: counters missing at turns {no_counters[:5]}")
        if undeclared:
            problems.append(f"{p.name}: undeclared counters {sorted(undeclared)[:5]}")
        if non_numeric:
            problems.append(f"{p.name}: non-numeric counters {sorted(non_numeric)[:5]}")
        rec = _get(hist[-1], p.path)
        if not isinstance(rec, dict):
            problems.append(f"{p.name}: no record in the last snapshot")
            continue
        if declared is not None and isinstance(rec.get("counters"), dict):
            # A declared counter absent from the record was never incremented: every
            # record starts empty when its switch is enabled (the sprint-3 rule).
            out[p.name] = {k: rec["counters"].get(k, 0) for k in p.counters}
    return out, problems


# --- The fixed harm panel ----------------------------------------------------------

#: Harm states: a value, the recording system off in this run, a present but
#: unreadable record (the run fails), or no bundle field yet.
RECORDED, NOT_RECORDED, MALFORMED, REQUIRES_EXTRACTOR = "recorded", "not_recorded", "malformed", "requires_slice_extractor"


def _harm(state: str, value: float | None = None, note: str = "") -> dict:
    return {"state": state, "value": value, "note": note}


def _civs(snap) -> list[dict]:
    return [c for c in ((snap or {}).get("civ_stats") or {}).values() if isinstance(c, dict)]


def harm_population(bundle: dict) -> dict:
    hist = bundle.get("history") or []
    civs = _civs(hist[-1]) if hist else []
    if not civs or not all(_num(c.get("population")) for c in civs):
        return _harm(MALFORMED, note="civ_stats population missing in the last snapshot")
    return _harm(RECORDED, sum(c["population"] for c in civs))


def harm_treasury(bundle: dict) -> dict:
    hist = bundle.get("history") or []
    civs = _civs(hist[-1]) if hist else []
    if not civs or not all(_num(c.get("treasury")) for c in civs):
        return _harm(MALFORMED, note="civ_stats treasury missing in the last snapshot")
    return _harm(RECORDED, sum(c["treasury"] for c in civs))


def harm_food_shortfall(bundle: dict) -> dict:
    """Unmet food demand after public relief over the run: per region and turn,
    demand x max(0, 1 - min(1, sufficiency after relief)) (the productive-recovery rule)."""
    hist = bundle.get("history") or []
    n = len((bundle.get("world_state") or {}).get("regions") or [])
    if not any(s.get("food_accounting") is not None for s in hist):
        return _harm(NOT_RECORDED, note="food accounting is not recorded in this run")
    total, bad, unobserved = 0.0, [], []
    for snap in hist:
        fa = snap.get("food_accounting") or {}
        rows = fa.get("regions")
        if fa.get("source_turn") != snap.get("turn", 0) - 1 or not isinstance(rows, list) or len(rows) != n \
                or not all(isinstance(row, dict) for row in rows):
            bad.append(snap.get("turn"))
            continue
        natives = [row.get("native") is not None for row in rows]
        if rows and not any(natives):
            unobserved.append(snap.get("turn"))     # no native economy tick: no ledger this turn
            continue
        for i, row in enumerate(rows):
            d, s = (row.get("native") or {}).get("demand"), row.get("sufficiency_after_relief")
            if row.get("region_id") != i or not _num(d) or not _num(s):
                bad.append(snap.get("turn"))
                break
            total += d * max(0.0, 1.0 - min(1.0, s))
    if bad:
        return _harm(MALFORMED, note=f"food accounting missing or incomplete at turns {bad[:5]}")
    if unobserved:
        return _harm(NOT_RECORDED, note=(
            "no native food ledger in this run (no agent economy)" if len(unobserved) == len(hist) else
            f"no native food ledger at turns {unobserved[:5]}: the run total is unknown, not zero"))
    return _harm(RECORDED, total)


def _priced_out(bundle: dict, column: str) -> dict:
    """Priced-out person- or child-turns: the household retail frames' provisioning
    rows summed over the run (persons checked against the lifetime counter)."""
    hist = bundle.get("history") or []
    records = [(s, _get(s, ("livelihoods", "household_retail"))) for s in hist]
    if not any(r is not None for _s, r in records):
        return _harm(NOT_RECORDED, note="household retail is off in this run (no priced-out frames)")
    total, persons, bad = 0.0, 0.0, []
    for snap, rec in records:
        if rec is None:
            continue
        if not isinstance(rec, dict) or rec.get("source_turn") != snap.get("turn", 0) - 1:
            bad.append(snap.get("turn"))
            continue
        frames = rec.get("regions")
        if frames is None:
            continue                    # an unobserved turn: unknown, and the counter has none
        if not isinstance(frames, list):
            bad.append(snap.get("turn"))
            continue
        for f in frames:
            prov = f.get("provisioning") if isinstance(f, dict) else None
            if prov is None:
                continue
            if not isinstance(prov, dict) or not _num(prov.get(column)) or not _num(prov.get("priced_out_persons")):
                bad.append(snap.get("turn"))
                break
            total += prov[column]
            persons += prov["priced_out_persons"]
    if bad:
        return _harm(MALFORMED, note=f"household retail frames malformed at turns {bad[:5]}")
    counter = _get(records[-1][1], ("counters", "priced_out_persons")) if records[-1][1] is not None else None
    if counter is not None and (not _num(counter) or abs(counter - persons) > 1e-6 * max(1.0, abs(counter))):
        return _harm(MALFORMED, note=f"frames sum priced-out persons to {persons}, the counter has {counter}")
    return _harm(RECORDED, total)


def harm_priced_out_persons(bundle: dict) -> dict:
    return _priced_out(bundle, "priced_out_persons")


def harm_priced_out_children(bundle: dict) -> dict:
    return _priced_out(bundle, "priced_out_children")


def harm_epidemic_deaths(bundle: dict) -> dict:
    """Deaths the epidemic system attributes to disease: its ``deaths_total`` in the
    last snapshot that carries an epidemics summary."""
    hist = bundle.get("history") or []
    carrying = [s["epidemics"] for s in hist if isinstance(s.get("epidemics"), dict)]
    if not carrying:
        return _harm(NOT_RECORDED, note="epidemiology is off in this run")
    total = carrying[-1].get("deaths_total")
    if not _num(total):
        return _harm(MALFORMED, note="epidemics.deaths_total missing")
    return _harm(RECORDED, total)


def harm_out_migration(bundle: dict) -> dict:
    """Agents who moved between regions over the run (``migration`` rows
    [from region, to region, agents], recorded with an agent pool)."""
    hist = bundle.get("history") or []
    if not any(s.get("migration") is not None for s in hist):
        return _harm(NOT_RECORDED, note="agent migrations are not recorded in this run (no agent pool)")
    total, bad = 0, []
    for snap in hist:
        rows = snap.get("migration")
        if rows is None:
            continue
        if not isinstance(rows, list) or not all(isinstance(r, list) and len(r) == 3 and all(_num(x) for x in r)
                                                 for r in rows):
            bad.append(snap.get("turn"))
            continue
        total += sum(r[2] for r in rows if r[0] != r[1])
    if bad:
        return _harm(MALFORMED, note=f"migration rows malformed at turns {bad[:5]}")
    return _harm(RECORDED, total)


def harm_wealth_gini(bundle: dict) -> dict:
    """Mean wealth Gini of the living civilizations at the end. The Gini comes from the
    agent pool; without one (no snapshot records agent migrations) civ_stats holds a
    placeholder 0, which is not a recorded value."""
    hist = bundle.get("history") or []
    if not any(s.get("migration") is not None for s in hist):
        return _harm(NOT_RECORDED, note="no agent pool in this run: the wealth Gini is not computed")
    civs = [c for c in (_civs(hist[-1]) if hist else []) if (c.get("population") or 0) > 0]
    if not civs:
        return _harm(NOT_RECORDED, note="no living civilization in the last snapshot")
    if not all(_num(c.get("gini")) for c in civs):
        return _harm(MALFORMED, note="civ_stats gini missing in the last snapshot")
    return _harm(RECORDED, mean(c["gini"] for c in civs))


def harm_forest_stand(bundle: dict) -> dict:
    """Standing timber as a share of its capacity at the end: the last snapshot's L3
    timber stock totals (a stock, not forest cover)."""
    hist = bundle.get("history") or []
    recs = [_get(s, ("livelihoods", "timber_stock")) for s in hist]
    if not any(r is not None for r in recs):
        return _harm(NOT_RECORDED, note="the timber stock is off in this run (no stand record)")
    rec = recs[-1]
    if rec is None:
        return _harm(NOT_RECORDED, note="no timber stock record in the last snapshot: unknown, not zero")
    if not isinstance(rec, dict):
        return _harm(MALFORMED, note="the last timber stock record is not an object")
    if not rec.get("observed"):
        return _harm(NOT_RECORDED, note="the last timber account was not observed: unknown, not zero")
    totals = rec.get("totals")
    if not isinstance(totals, dict) or not _num(totals.get("stock")) or not _num(totals.get("capacity")):
        return _harm(MALFORMED, note="timber stock totals missing stock or capacity")
    if totals["capacity"] <= 0:
        return _harm(NOT_RECORDED, note="no timber capacity at the end (no slot)")
    return _harm(RECORDED, totals["stock"] / totals["capacity"])


@dataclass(frozen=True)
class HarmMetric:
    key: str
    label: str
    source: str
    extractor: Callable[[dict], dict] | None
    #: Who must supply the extractor when there is none yet.
    owner: str = ""


#: The fixed harm panel shared by every screen, in display order (data; a screen
#: cannot drop or reorder it). ``extractor=None``: no bundle field records it yet.
HARM_PANEL: tuple[HarmMetric, ...] = (
    HarmMetric("population", "Population at the end (sum over civilizations)",
               "history[-1].civ_stats[*].population", harm_population),
    HarmMetric("treasury", "Treasury at the end (sum over civilizations)",
               "history[-1].civ_stats[*].treasury", harm_treasury),
    HarmMetric("food_shortfall", "Food shortfall after relief over the run (food)",
               "history[*].food_accounting.regions[*]: native.demand, sufficiency_after_relief", harm_food_shortfall),
    HarmMetric("priced_out_persons", "Priced-out person-turns",
               "history[*].livelihoods.household_retail.regions[*].provisioning.priced_out_persons",
               harm_priced_out_persons),
    HarmMetric("priced_out_children", "Priced-out child-turns",
               "history[*].livelihoods.household_retail.regions[*].provisioning.priced_out_children",
               harm_priced_out_children),
    HarmMetric("deaths_famine", "Deaths by famine (the famine authority)",
               "no bundle field: aggregate famine tolls and native starvation deaths are not recorded by cause",
               None, owner="the slice that records deaths by authority (A1-A2 accounting or E)"),
    HarmMetric("deaths_epidemic", "Deaths by epidemic (the epidemic authority)",
               "history[*].epidemics.deaths_total (last)", harm_epidemic_deaths),
    HarmMetric("deaths_war", "Deaths by war (the casualty authority)",
               "no bundle field: war casualties are not recorded per turn outside the campaign layer",
               None, owner="slice D3 (war's human consequences)"),
    HarmMetric("out_migration", "Agents migrating between regions over the run",
               "history[*].migration rows [from, to, agents]", harm_out_migration),
    HarmMetric("wealth_gini", "Mean wealth Gini of living civilizations at the end",
               "history[-1].civ_stats[*].gini", harm_wealth_gini),
    HarmMetric("forest_stand", "Timber stand share of capacity at the end",
               "history[-1].livelihoods.timber_stock.totals: stock / capacity", harm_forest_stand),
)


def harm_panel(bundle: dict) -> tuple[dict, list[str]]:
    """Every harm of the panel for one run, and the problems (malformed harms)."""
    out, problems = {}, []
    for h in HARM_PANEL:
        if h.extractor is None:
            out[h.key] = _harm(REQUIRES_EXTRACTOR, note=f"requires slice extractor: {h.owner}")
            continue
        value = h.extractor(bundle)
        out[h.key] = value
        if value["state"] == MALFORMED:
            problems.append(f"harm {h.key}: {value['note']}")
    return out, problems


def harm_value(row: dict, key: str) -> float | None:
    h = (row.get("harm") or {}).get(key) or {}
    return h.get("value") if h.get("state") == RECORDED else None


# --- Running -----------------------------------------------------------------------

def _run_env() -> dict:
    """Every run imports this checkout's ``src`` (never an installed copy)."""
    return dict(os.environ, PYTHONHASHSEED="0", RAYON_NUM_THREADS="1", CHRONICLER_QUIET="1",
                PYTHONPATH=str(REPO / "src"))


def simulate(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO, env=_run_env(), capture_output=True, text=True)


_WHICH = ("import hashlib, chronicler\n"
          "print(chronicler.__file__)\n"
          "try:\n"
          "    import chronicler_agents.chronicler_agents as m\n"
          "    print(m.__file__, hashlib.sha256(open(m.__file__, 'rb').read()).hexdigest())\n"
          "except Exception as error:\n"
          "    print('none', type(error).__name__)\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_identity(screen: Screen) -> list[str]:
    """The identity lines of a run directory (``source.txt``); refuses when the runs
    would not import this checkout's ``src`` or need an extension that is absent."""
    p = subprocess.run([PY, "-c", _WHICH], cwd=REPO, env=_run_env(), capture_output=True, text=True)
    lines = p.stdout.split("\n")
    if p.returncode != 0 or not lines[0].startswith(f"{REPO}/src/"):
        raise SystemExit(f"runs would not import {REPO}/src: {p.stdout} {p.stderr[-500:]}")
    if screen.requires_native and lines[1].startswith("none"):
        raise SystemExit(f"{screen.name} needs the native extension; this interpreter has none ({lines[1]})")
    git = ["git", "-C", str(REPO)]
    rev = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run([*git, "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True).stdout.splitlines()
    return identity_lines(rev, len(dirty), lines[0], lines[1], screen)


def _shown(path: Path) -> str:
    path = Path(path).resolve()
    return str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)


def identity_lines(rev: str, dirty: int, chronicler: str, native: str, screen: Screen) -> list[str]:
    module = screen.module or RUNNER
    return [f"source {rev}", f"dirty {dirty} tracked files", f"chronicler {chronicler}", f"native {native}",
            f"interpreter {PY}", f"runner {sha256_file(RUNNER)} {_shown(RUNNER)}",
            f"screens {sha256_file(module)} {_shown(module)}",
            f"registry {sha256_file(REGISTRY)} {_shown(REGISTRY)}"]


def identity_digest(lines: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def jobs_for(screen: Screen, cohort: str, seeds: str, arms: Sequence[str],
             worlds: Sequence[tuple[str, int]] = (),
             cohort_map: Mapping[str, Sequence[int]] | None = None) -> list[tuple[str, str, int, bool]]:
    """(arm, stratum tag, seed, first world of its stratum) per run; procedural first."""
    out = []
    if cohort == "dev":
        firsts = set()
        for tag, seed in sorted(worlds, key=lambda w: w[0] != "p"):
            for arm in arms:
                out.append((arm, tag, seed, tag not in firsts))
            firsts.add(tag)
        return out
    cohort_map = screen.cohort(cohort) if cohort_map is None else cohort_map
    strata = ["procedural", "template"] if seeds == "all" else [seeds]
    for stratum in strata:
        for i, seed in enumerate(cohort_map.get(stratum, ())):
            for arm in arms:
                out.append((arm, TAGS[stratum], seed, i == 0))
    return out


def run_one(screen: Screen, rt: Runtime, out: Path, cohort: str, arm: str, tag: str, seed: int, keep: bool,
            identity: str, turns: int | None = None) -> dict:
    d = (out / "runs" / f"{arm}-{tag}{seed}").resolve()
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    flags = list(screen.arms[arm][0])
    cmd = [PY, "-m", "chronicler.main", *arm_command(screen, arm, STRATUM_OF[tag], seed, turns),
           "--output", str(d / "chronicle.md"), "--state", str(d / "state.json")]
    t0 = rt.clock()
    p = rt.simulate(cmd)
    row = {"screen": screen.name, "cohort": cohort, "arm": arm, "stratum": tag, "seed": seed, "rc": p.returncode,
           "wall_s": round(rt.clock() - t0, 1), "identity": identity}
    if p.returncode != 0:
        row["error"] = (p.stderr or "")[-2000:]
    else:
        t1 = rt.clock()
        try:
            row.update(extract_row(screen, arm, d / "chronicle_bundle.json", flags))
        except Exception as error:  # an unreadable bundle is a missing outcome, never zero
            row["rc"], row["error"] = RC_MISSING, f"missing or malformed outcomes: {type(error).__name__}: {error}"
        row["extract_s"] = round(rt.clock() - t1, 1)
    # A failed run's output is kept for diagnosis; a passing one only when asked.
    if not keep and row["rc"] == 0:
        shutil.rmtree(d)
    return row


def extract_row(screen: Screen, arm: str, bundle_path: Path, flags: Sequence[str]) -> dict:
    """Schema versions, the harm panel, package counters, activation and the screen's
    own measures of one run; rc 3 with the reasons when anything is missing."""
    _src()
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(bundle_path)
    return extract_bundle(screen, arm, bundle, flags)


def extract_bundle(screen: Screen, arm: str, bundle: dict, flags: Sequence[str]) -> dict:
    if not bundle.get("history"):
        return {"rc": RC_MISSING, "error": "missing or malformed outcomes: the bundle has no history"}
    row: dict[str, Any] = {"schemas": schema_versions(bundle)}
    row["harm"], problems = harm_panel(bundle)
    row["pk"], pp = package_problems(screen, bundle, flags)
    problems += pp
    if arm == screen.root:
        row["activation"] = {"activated": None, "evidence": "root arm"}
    elif screen.activation is None:
        row["activation"] = {"activated": None, "evidence": "no activation rule"}
    else:
        activated, evidence = screen.activation(bundle, flags)
        row["activation"] = {"activated": activated, "evidence": evidence}
    if screen.extract is not None:
        row["m"], mp = screen.extract(bundle, flags)
        problems += mp
    if problems:
        row["rc"], row["error"] = RC_MISSING, "missing or malformed outcomes: " + "; ".join(problems)
    return row


def exit_code(rows, stopped: bool = False) -> int:
    if any(r["rc"] == RC_MISSING for r in rows):
        return RC_MISSING
    if any(r["rc"] != 0 for r in rows):
        return RC_FAILED
    return RC_CEILING if stopped else 0


def run_seconds(r) -> float:
    """A run's simulation and extraction seconds (extraction ran in the runner process)."""
    return r.get("wall_s", 0.0) + r.get("extract_s", 0.0)


def read_rows(path, screen: Screen) -> list[dict]:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    foreign = [r for r in rows if r.get("screen") != screen.name]
    if foreign:
        raise SystemExit(f"{path} holds rows of another screen than {screen.name}: "
                         f"{sorted({str(r.get('screen')) for r in foreign})}")
    return rows


def pilot_means(rows) -> dict[tuple[str, str], float]:
    """Mean seconds of the passing pilot runs per (arm, stratum tag)."""
    out: dict[tuple[str, str], list[float]] = {}
    for r in rows:
        if r["rc"] == 0:
            out.setdefault((r["arm"], r["stratum"]), []).append(run_seconds(r))
    return {k: mean(v) for k, v in out.items()}


def projected_core_hours(rows, screen: Screen, cohort_map: Mapping[str, Sequence[int]]) -> float | None:
    """Pilot run time (simulation and extraction) per arm and stratum times the worlds of
    the cohort per stratum, in core-hours (None if a pilot arm or stratum is missing)."""
    means = pilot_means(rows)
    total = 0.0
    for arm in screen.arms:
        for stratum, tag in TAGS.items():
            worlds = cohort_map.get(stratum, ())
            if not worlds:
                continue
            if (arm, tag) not in means:
                return None
            total += means[(arm, tag)] * len(worlds)
    return total / 3600


def projected_held_core_hours(rows, screen: Screen) -> float | None:
    return projected_core_hours(rows, screen, screen.held)


def _field(lines: Sequence[str], key: str) -> str | None:
    for line in lines:
        if line.startswith(key + " "):
            return line[len(key) + 1:]
    return None


def identity_of(source_text: str) -> list[str]:
    """The identity lines a run directory's ``source.txt`` starts with."""
    lines = []
    for line in source_text.splitlines():
        if line.startswith(("run: ", "resumed: ")):
            break
        lines.append(line)
    return lines


#: Paths whose change between the pilot's and the held run's source revision makes the
#: pilot timing another program's.
CODE_PATHS = ("src/", "chronicler-agents/", "scripts/", "pyproject.toml", "uv.lock")


def load_pilot(path, screen: Screen, identity: Sequence[str], rt: Runtime) -> tuple[list[dict], list[str]]:
    """The pilot rows a projection may use, and the reasons to refuse them: rows of
    another identity than their ``source.txt``, or a pilot of another extension,
    runner, screen module, registry, dirty count, or a source revision that differs
    in code."""
    path = Path(path)
    rows = [r for r in read_rows(path, screen) if r.get("cohort") == "pilot"]
    source = path.parent / "source.txt"
    if not source.exists():
        return rows, [f"pilot refused: {source} is missing (its identity cannot be checked)"]
    pilot = identity_of(source.read_text(encoding="utf-8"))
    problems = []
    digests = sorted({str(r.get("identity")) for r in rows})
    if digests != [identity_digest(pilot)]:
        problems.append(f"pilot refused: its rows carry identity {digests}, not the identity of {source}")
    for key in ("native", "runner", "screens", "registry", "dirty"):
        if _field(pilot, key) != _field(identity, key):
            problems.append(f"pilot refused: {key} {_field(pilot, key)!r} differs from this run's "
                            f"{_field(identity, key)!r}")
    old, new = _field(pilot, "source"), _field(identity, "source")
    if old != new:
        changed = rt.changed_paths(old or "", new or "")
        if changed is None:
            problems.append(f"pilot refused: cannot compare source {old} with {new}")
        else:
            code = [p for p in changed if p.startswith(CODE_PATHS)]
            if code:
                problems.append(f"pilot refused: source {old} differs from {new} in code: {code[:6]}")
    return rows, problems


def preregistration_line(screen: Screen) -> str:
    return f"preregistration {sha256_file(screen.preregistration)} {_shown(screen.preregistration)}"


# --- The evidence-run ledger -----------------------------------------------------------

def ledger_entries(path: Path) -> list[dict]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def ledger_conflicts(path: Path, screen: Screen, cohort: str) -> list[str]:
    """A recorded start of the same evidence cohort: the screen's held cohort, or the
    program's reserve (whichever screen used it). A new run of it is refused."""
    out = []
    for e in ledger_entries(path):
        same = (e.get("cohort") == "reserve") if cohort == "reserve" else \
            (e.get("cohort") == "held" and e.get("screen") == screen.name)
        if same:
            out.append(f"a {e.get('cohort')} run of {e.get('screen')} was started at {e.get('started')} into "
                       f"{e.get('out')} (identity {str(e.get('identity'))[:12]}): resume it there with --resume, "
                       f"or record it with mark-run; a new run of that cohort is refused")
    return out


def cohort_seeds(screen: Screen, cohort: str, reg: Mapping | None = None) -> dict[str, tuple[int, ...]]:
    """The seeds of a cohort per stratum: the screen's pilot or held cohort, or the
    program's reserve (registry entries of cohort ``reserve`` free or used by the screen)."""
    if cohort in ("pilot", "held"):
        return {s: tuple(v) for s, v in screen.cohort(cohort).items() if v}
    if cohort != "reserve":
        return {}
    reg = load_registry() if reg is None else reg
    out: dict[str, set[int]] = {}
    for e in reg["entries"]:
        if e.get("cohort") == "reserve" and e.get("screen") in (None, screen.name):
            out.setdefault(e["stratum"], set()).update(expand(e["seeds"]))
    return {s: tuple(sorted(v)) for s, v in out.items()}


def check_reserve(screen: Screen, reg: Mapping) -> list[str]:
    """The reserve is free (every entry reserved, assigned to no other screen)."""
    entries = [e for e in reg["entries"] if e.get("cohort") == "reserve"]
    if not entries:
        return ["the registry has no reserve cohort"]
    problems = []
    for e in entries:
        if e.get("screen") not in (None, screen.name):
            problems.append(f"the reserve {e['id']} is assigned to {e['screen']}")
        if e["status"] != "reserved":
            problems.append(f"the reserve {e['id']} was already used ({e['status']}"
                            f"{', by ' + e['screen'] if e.get('screen') else ''})")
    return problems


_RUN_HEADER = re.compile(r"^run: screen (\S+); cohort (\w+);")


def recorded_run(text: str) -> tuple[str, str] | None:
    for line in text.splitlines():
        m = _RUN_HEADER.match(line)
        if m:
            return m.group(1), m.group(2)
    return None


def _dev_worlds(spec: str | None, reg: Mapping) -> list[tuple[str, int]]:
    if not spec:
        raise SystemExit("--cohort dev needs --worlds (development worlds such as t1,p7)")
    worlds = []
    for item in spec.split(","):
        m = re.fullmatch(r"([tp])(\d+)", item.strip())
        if not m:
            raise SystemExit(f"--worlds: {item!r} is not t<seed> or p<seed>")
        tag, seed = m.group(1), int(m.group(2))
        if seed not in seed_sets(reg, STRATUM_OF[tag])["development"]:
            raise SystemExit(f"--worlds: {item} is not a registered development world")
        worlds.append((tag, seed))
    return worlds


def _screen_arg(screens: Mapping[str, Screen], name: str) -> Screen:
    if name not in screens:
        raise SystemExit(f"unknown screen {name!r}; screens: {', '.join(screens)}")
    return screens[name]


def run_main(argv, screens: Mapping[str, Screen], rt: Runtime | None = None, prog: str = "screens") -> int:
    rt = rt or Runtime()
    ap = argparse.ArgumentParser(prog=f"{prog} run")
    ap.add_argument("out")
    ap.add_argument("--screen", required=True)
    ap.add_argument("--cohort", choices=("pilot", "held", "reserve", "dev"), required=True)
    ap.add_argument("--reason", default=None, help="reserve: why the screen needs the reserve cohort (recorded)")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--arms", default=None)
    ap.add_argument("--seeds", choices=("all", "template", "procedural"), default="all")
    ap.add_argument("--pilot", default=None, help="held or reserve: the pilot's metrics.jsonl (the compute projection)")
    ap.add_argument("--worlds", default=None, help="dev: development worlds, e.g. t1,p7")
    ap.add_argument("--turns", type=int, default=None, help="dev only: override the base's --turns")
    ap.add_argument("--keep-first", action="store_true", help="keep the first world of each stratum")
    ap.add_argument("--resume", action="store_true", help="continue an interrupted run in OUT_DIR on the same source")
    a = ap.parse_args(argv)
    screen = _screen_arg(screens, a.screen)
    if not screen.ready:
        raise SystemExit(f"run refused: {screen.name} is not ready ({screen.not_ready or 'a stub'})")
    reg = load_registry()
    evidence = a.cohort in EVIDENCE_COHORTS
    seeds_by = cohort_seeds(screen, a.cohort, reg)
    if a.cohort != "dev" and not any(seeds_by.values()):
        raise SystemExit(f"run refused: {screen.name} has no {a.cohort} cohort")
    if a.turns is not None and a.cohort != "dev":
        raise SystemExit("--turns is for development runs only; pilot and held runs use the screen's turns")
    reason = (a.reason or "").strip()
    if (a.cohort == "reserve") != bool(reason):
        raise SystemExit("--reason is required with --cohort reserve, and only there")
    problems, notes = check_seeds(screen, reg)
    if a.cohort == "reserve":
        problems += check_reserve(screen, reg)
    problems += check_screen(screen)
    if evidence:
        problems += check_preregistration(screen, held=True)
        if not a.resume:
            problems += ledger_conflicts(rt.ledger, screen, a.cohort)
    if problems:
        raise SystemExit("run refused: " + "; ".join(problems))
    worlds = _dev_worlds(a.worlds, reg) if a.cohort == "dev" else []
    identity = rt.identity(screen)
    if evidence:
        identity = [*identity, preregistration_line(screen)]
    digest = identity_digest(identity)
    ceiling, means, pilot_note = None, {}, ""
    if evidence:
        ceiling = compute_ceiling(preregistration_text(screen))
        if not a.pilot:
            raise SystemExit(f"{a.cohort} run refused: --pilot PILOT_DIR/metrics.jsonl gives the compute projection")
        pilot_rows, pilot_problems = load_pilot(a.pilot, screen, identity, rt)
        if pilot_problems:
            raise SystemExit(f"{a.cohort} run refused: " + "; ".join(pilot_problems))
        hours = projected_core_hours(pilot_rows, screen, seeds_by)
        if hours is None:
            raise SystemExit(f"{a.cohort} run refused: {a.pilot} lacks a passing pilot run of some arm and stratum")
        if hours * CEILING_MARGIN > ceiling:
            raise SystemExit(f"{a.cohort} run refused: the pilot projects {hours:.3f} core-hours; x{CEILING_MARGIN} = "
                             f"{hours * CEILING_MARGIN:.3f} exceeds the ceiling of {ceiling} core-hours")
        means = pilot_means(pilot_rows)
        pilot_note = (f"pilot {a.pilot} sha256 {sha256_file(Path(a.pilot))}; projected {hours:.3f} core-hours; "
                      f"ceiling {ceiling} core-hours; expected seconds per run: max of the pilot mean per arm and "
                      f"stratum ({', '.join(f'{arm} {tag} {s:.1f}' for (arm, tag), s in sorted(means.items()))}) "
                      f"and the finished runs' mean per stratum\n")
    chosen = a.arms.split(",") if a.arms else list(screen.arms)
    unknown = [arm for arm in chosen if arm not in screen.arms]
    if unknown:
        raise SystemExit(f"unknown arms: {unknown}")
    if a.jobs < 1:
        raise SystemExit("--jobs must be at least 1")
    out = Path(a.out)
    metrics, source = out / "metrics.jsonl", out / "source.txt"
    done: set = set()
    prior_rows: list[dict] = []
    if metrics.exists() and not a.resume:
        raise SystemExit(f"{metrics} exists: pass --resume to continue it, or choose a new OUT_DIR")
    if a.resume:
        if not metrics.exists() or not source.exists():
            raise SystemExit(f"nothing to resume in {out}")
        recorded = source.read_text(encoding="utf-8")
        started = recorded_run(recorded)
        if started != (screen.name, a.cohort):
            raise SystemExit(f"resume refused: {out} was started as {started}, not ({screen.name!r}, {a.cohort!r})")
        if identity_of(recorded) != identity:
            raise SystemExit("resume refused: the source, dirty count, chronicler path, extension, interpreter, "
                             "runner, screen module, registry or preregistration changed:\n" + "\n".join(identity))
        if evidence and not any(e.get("out") == str(out.resolve()) and e.get("identity") == digest
                                for e in ledger_entries(rt.ledger)):
            raise SystemExit(f"resume refused: the ledger {rt.ledger} records no {a.cohort} run in {out}")
        for r in read_rows(metrics, screen):
            if r.get("cohort") != a.cohort or r.get("identity") != digest:
                raise SystemExit(f"{metrics} holds a row of cohort {r.get('cohort')} or another identity")
            prior_rows.append(r)
            done.add((r["arm"], r["stratum"], r["seed"]))
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    with open(source, "a" if a.resume else "w", encoding="utf-8") as fh:
        if not a.resume:
            fh.write("\n".join(identity) + "\n")
        fh.write(f"{'resumed' if a.resume else 'run'}: screen {screen.name}; cohort {a.cohort}; seeds {a.seeds}; "
                 f"arms {','.join(chosen)}; jobs {a.jobs}; worlds {a.worlds or '-'}; turns {a.turns or '-'}; "
                 f"rows already written {len(done)}\n{f'reason: {reason}' + chr(10) if reason else ''}{pilot_note}"
                 f"started {stamp}\n")
    if evidence and not a.resume:
        entry = {"screen": screen.name, "cohort": a.cohort, "out": str(out.resolve()), "identity": digest,
                 "preregistration": _field(identity, "preregistration"), "started": stamp,
                 "seeds": {s: list(v) for s, v in seeds_by.items()}, "reason": reason or None}
        (out / "held-run.json").write_text(json.dumps(entry, indent=1) + "\n", encoding="utf-8")
        Path(rt.ledger).parent.mkdir(parents=True, exist_ok=True)
        with open(rt.ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    print("\n".join(identity), flush=True)
    for note in notes:
        print("note:", note, flush=True)
    pending = [j for j in jobs_for(screen, a.cohort, a.seeds, chosen, worlds, seeds_by) if (j[0], j[1], j[2]) not in done]
    rows: list[dict] = []
    used = sum(run_seconds(r) for r in prior_rows)
    t0 = rt.clock()

    def expected(arm: str, tag: str) -> float:
        # Never below the pilot; once runs of the stratum finished, never below their mean.
        finished = [run_seconds(r) for r in (*prior_rows, *rows) if r["stratum"] == tag]
        return max(means.get((arm, tag), 0.0), mean(finished) if finished else 0.0)

    refused_at = None
    with open(metrics, "a", encoding="utf-8") as fh, ThreadPoolExecutor(a.jobs) as ex:
        running: dict = {}
        while True:
            while pending and len(running) < a.jobs:
                arm, tag, seed, first = pending[0]
                if ceiling is not None:
                    in_flight = sum(expected(r_arm, r_tag) for r_arm, r_tag in running.values())
                    cost = expected(arm, tag)
                    if used + in_flight + cost > ceiling * 3600:
                        refused_at = (used, in_flight, cost)
                        break
                pending.pop(0)
                future = ex.submit(run_one, screen, rt, out, a.cohort, arm, tag, seed, a.keep_first and first,
                                   digest, a.turns)
                running[future] = (arm, tag)
            if not running:
                break
            finished, _ = wait(set(running), return_when=FIRST_COMPLETED)
            for future in finished:
                # Each row is written as soon as its run finishes, so a killed run
                # loses only the runs in flight (``--resume`` runs those).
                running.pop(future)
                row = future.result()
                rows.append(row)
                used += run_seconds(row)
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                note = f" FAILED: {row.get('error', '')[-300:]}" if row["rc"] else ""
                print(row["arm"], f"{row['stratum']}{row['seed']}", row["rc"], row["wall_s"], note, flush=True)
    stopped = bool(pending)
    wall = round(rt.clock() - t0, 1)
    with open(source, "a", encoding="utf-8") as fh:
        if stopped:
            u, f, c = refused_at
            fh.write(f"stopped at the compute ceiling ({ceiling} core-hours): {u / 3600:.3f} used, "
                     f"{f / 3600:.3f} expected in flight, the next run expected {c:.1f} s; {len(pending)} runs not "
                     f"started: " + ", ".join(f"{arm} {tag}{seed}" for arm, tag, seed, _f in pending) + "\n")
        fh.write(f"finished {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}: {len(rows)} runs, "
                 f"{sum(r['rc'] != 0 for r in rows)} failed, {sum(run_seconds(r) for r in rows):.0f} s of "
                 f"simulation and extraction ({used / 3600:.3f} core-hours in all), {wall} s wall\n")
    if stopped:
        print(f"STOPPED at the compute ceiling: {len(pending)} runs not started (reported as not run)")
    for r in rows:
        if r["rc"]:
            print(f"FAILED run {r['arm']} {r['stratum']}{r['seed']} (rc {r['rc']}): {r.get('error', '')[-500:]}")
    if evidence:
        print(f"Record this {a.cohort} run in the registry (commit it with the results): "
              f"python scripts/{prog} mark-run {out} --screen {screen.name}")
    return exit_code(rows, stopped)


# --- mark-run: record an evidence run in the registry ----------------------------------

def dump_registry(reg: Mapping) -> str:
    """The registry file's text: one header field and one entry per line."""
    lines = ["{"]
    for key, value in reg.items():
        if key != "entries":
            lines.append(f" {json.dumps(key)}: {json.dumps(value)},")
    lines.append(' "entries": [')
    entries = reg["entries"]
    lines += ["  " + json.dumps(e) + ("," if i < len(entries) - 1 else "") for i, e in enumerate(entries)]
    lines += [" ]", "}"]
    return "\n".join(lines) + "\n"


def mark_run(reg: dict, screen: Screen, rows: list[dict], ledger: Mapping) -> list[str]:
    """Set the run cohort's registry entries to ``run`` with a ``held_run`` record; the
    names of the entries changed. Refuses an entry that is not ``reserved``."""
    cohort = ledger["cohort"]
    if cohort == "held":
        entries = [e for e in reg["entries"] if e.get("screen") == screen.name and e.get("cohort") == "held"]
    else:
        entries = [e for e in reg["entries"] if e.get("cohort") == "reserve" and e.get("screen") in (None, screen.name)]
    if not entries:
        raise SystemExit(f"mark-run refused: no {cohort} registry entry for {screen.name}")
    bad = [f"{e['id']} is {e['status']}" for e in entries if e["status"] != "reserved"]
    if bad:
        raise SystemExit("mark-run refused: " + "; ".join(bad))
    seeds = {s: tuple(v) for s, v in ledger["seeds"].items()}
    complete = check_metrics(rows, cohort, screen, seeds=seeds) == []
    record = {"out": ledger["out"], "identity": ledger["identity"], "started": ledger["started"],
              "rows": len(rows), "complete": complete,
              "recorded": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    if ledger.get("reason"):
        record["reason"] = ledger["reason"]
    for e in entries:
        e["status"] = "run"
        e["screen"] = screen.name
        e["held_run"] = dict(record)
    return [e["id"] for e in entries]


def mark_run_main(argv, screens: Mapping[str, Screen], prog: str = "screens") -> int:
    ap = argparse.ArgumentParser(prog=f"{prog} mark-run")
    ap.add_argument("out", help="the held or reserve run's OUT_DIR")
    ap.add_argument("--screen", required=True)
    ap.add_argument("--registry", default=str(REGISTRY))
    a = ap.parse_args(argv)
    screen = _screen_arg(screens, a.screen)
    out = Path(a.out)
    try:
        ledger = json.loads((out / "held-run.json").read_text(encoding="utf-8"))
    except OSError:
        raise SystemExit(f"mark-run refused: {out / 'held-run.json'} is missing") from None
    if ledger.get("screen") != screen.name or ledger.get("cohort") not in EVIDENCE_COHORTS:
        raise SystemExit(f"mark-run refused: {out} holds a {ledger.get('cohort')} run of {ledger.get('screen')}")
    metrics = out / "metrics.jsonl"
    rows = read_rows(metrics, screen) if metrics.exists() else []
    if any(r.get("identity") != ledger["identity"] or r.get("cohort") != ledger["cohort"] for r in rows):
        raise SystemExit(f"mark-run refused: {metrics} holds rows of another identity or cohort")
    path = Path(a.registry)
    reg = load_registry(path)
    problems = validate_registry(reg)
    if problems:
        raise SystemExit("mark-run refused: the registry is invalid: " + "; ".join(problems))
    changed = mark_run(reg, screen, rows, ledger)
    problems = validate_registry(reg)
    if problems:
        raise SystemExit("mark-run refused: the result would be invalid: " + "; ".join(problems))
    path.write_text(dump_registry(reg), encoding="utf-8")
    print(f"marked {', '.join(changed)} as run ({len(rows)} rows); commit {path.name} with the results")
    return 0


# --- Uncertainty (descriptive) -----------------------------------------------------

def describe(values: Sequence[float]) -> dict | None:
    """Mean, min, max and sign counts of per-world values."""
    if not values:
        return None
    return {"n": len(values), "mean": mean(values), "min": min(values), "max": max(values),
            "positive": sum(v > 0 for v in values), "negative": sum(v < 0 for v in values),
            "zero": sum(v == 0 for v in values)}


def sign_flip(diffs: Sequence[float]) -> dict | None:
    """The exact paired sign-flip enumeration of the mean difference over the worlds:
    every assignment of signs to the per-world differences (2^n, equally weighted),
    summarized by how many are at least as far from zero as the observed mean and
    their range. Descriptive only, not a significance test."""
    n = len(diffs)
    if n == 0 or n > SIGN_FLIP_MAX_WORLDS:
        return None
    observed = mean(diffs)
    means = sorted(math.fsum(s * d for s, d in zip(signs, diffs)) / n
                   for signs in itertools.product((1, -1), repeat=n))
    tol = 1e-12 * max(1.0, abs(observed))
    return {"n": n, "assignments": 2 ** n, "observed": observed, "min": means[0], "max": means[-1],
            "at_least_as_extreme": sum(abs(m) >= abs(observed) - tol for m in means)}


# --- Report ------------------------------------------------------------------------

def _activation_cell(row) -> str:
    if row is None:
        return "not run"
    if row["rc"] != 0:
        return "failed"
    act = (row.get("activation") or {}).get("activated")
    return {True: "activated", False: "not activated", None: "unknown"}[act]


def _strata_seen(rows, cohort_map: Mapping[str, Sequence[int]]) -> dict[str, list[int]]:
    out = {}
    for stratum, tag in TAGS.items():
        seeds = set(cohort_map.get(stratum, ())) | {r["seed"] for r in rows if r["stratum"] == tag}
        if seeds:
            out[tag] = sorted(seeds)
    return out


def paired_values(rows, screen: Screen, arm: str, control: str | None, read, tag: str,
                  seeds: Sequence[int], need_activation: bool = True,
                  why: Callable[[dict], str] = lambda row: "unknown") -> tuple[list[str], list[float]]:
    """Per-world cells and the values of the activated worlds (arm minus control);
    ``why(row)`` names a value that is missing (default "unknown")."""
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    cells, values = [], []
    for seed in seeds:
        a, c = by.get((arm, tag, seed)), (by.get((control, tag, seed)) if control else None)
        if a is None or (control and c is None):
            cells.append(f"{seed}: not run")
            continue
        if a["rc"] != 0 or (control and c["rc"] != 0):
            cells.append(f"{seed}: failed")
            continue
        act = (a.get("activation") or {}).get("activated")
        if need_activation and arm != screen.root and act is not True:
            cells.append(f"{seed}: {'not activated' if act is False else 'activation unknown'}")
            continue
        va, vc = read(a), (read(c) if control else 0.0)
        if va is None or vc is None:
            cells.append(f"{seed}: {why(a if va is None else c)}")
            continue
        values.append(va - vc)
        cells.append(f"{seed}: {va - vc:+.4g}")
    return cells, values


def _summary_cells(values, paired: bool = True) -> tuple[str, str, str]:
    d = describe(values)
    if d is None:
        return "n/a", "0 / 0 / 0", "n/a"
    flip = sign_flip(values) if paired else None
    flip_text = ("n/a (no control)" if not paired else "n/a" if flip is None else
                 f"{flip['at_least_as_extreme']}/{flip['assignments']} as extreme; means "
                 f"[{flip['min']:+.4g}, {flip['max']:+.4g}]")
    return (f"{d['mean']:+.4g} [{d['min']:+.4g}, {d['max']:+.4g}]",
            f"{d['positive']} / {d['negative']} / {d['zero']}", flip_text)


def _harm_reader(key):
    return lambda row: harm_value(row, key)


def _harm_why(key):
    return lambda row: ((row.get("harm") or {}).get(key) or {}).get("state", "absent").replace("_", " ")


def _harm_state(rows, key) -> str:
    states = sorted({((r.get("harm") or {}).get(key) or {}).get("state", "absent") for r in rows if r["rc"] == 0})
    notes = sorted({((r.get("harm") or {}).get(key) or {}).get("note", "") for r in rows if r["rc"] == 0} - {""})
    return ", ".join(states) + (f" ({'; '.join(notes)})" if notes else "")


def harm_pairs(screen: Screen) -> list[tuple[str, str]]:
    """Every non-root arm against its declared control, then any other comparison an
    outcome declares: the harm panel is shown beside each."""
    pairs = [(arm, control) for arm, (_flags, control) in screen.arms.items() if control is not None]
    for o in screen.outcomes:
        if o.control is not None and (o.arm, o.control) not in pairs:
            pairs.append((o.arm, o.control))
    return pairs


def report_lines(rows, screen: Screen, cohort_map: Mapping[str, Sequence[int]] | None = None) -> list[str]:
    cohorts = sorted({r.get("cohort") for r in rows})
    cohort = cohorts[0] if len(cohorts) == 1 else "mixed"
    if cohort_map is None:
        cohort_map = cohort_seeds(screen, cohort) if cohort in ("pilot", "held") else {}
    strata = _strata_seen(rows, cohort_map)
    fails = [r for r in rows if r["rc"] != 0]
    seconds = sum(run_seconds(r) for r in rows)
    out = [f"# {screen.name}: {screen.title}", "",
           f"Cohort {cohort}. Runs: {len(rows)}; failed: {len(fails)} (missing outcomes: "
           f"{sum(r['rc'] == RC_MISSING for r in rows)}); simulation and extraction seconds {seconds:.0f} "
           f"({seconds / 3600:.3f} core-hours)"]
    for f in fails:
        out.append(f"- FAILED {f['arm']} {f['stratum']}{f['seed']} (rc {f['rc']}): {f.get('error', '')[-300:]}")
    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    for arm in screen.arms:
        for tag, seeds in strata.items():
            for seed in seeds:
                if (arm, tag, seed) not in by:
                    out.append(f"- INCOMPLETE {arm} {tag}{seed}: not run")
    identities = sorted({r.get("identity") for r in rows})
    out.append(f"\nIdentity digests: {', '.join(str(i) for i in identities)} (source.txt holds the lines)")
    schemas = sorted({json.dumps(r.get("schemas"), sort_keys=True) for r in rows if r.get("schemas")})
    out.append(f"Schema versions read: {'; '.join(schemas) or 'none'}")

    out.append("\n## Activation per world (before any effect)\n")
    out.append("| Arm | Stratum | Per world | Activated |")
    out.append("| --- | --- | --- | --- |")
    for arm in screen.arms:
        if arm == screen.root:
            continue
        for tag, seeds in strata.items():
            cells = [f"{seed}: {_activation_cell(by.get((arm, tag, seed)))}" for seed in seeds]
            n = sum(_activation_cell(by.get((arm, tag, seed))) == "activated" for seed in seeds)
            out.append(f"| {arm} | {tag} | {'; '.join(cells)} | {n} of {len(seeds)} |")

    for title, outcomes in (("Primary outcomes", [o for o in screen.outcomes if o.primary]),
                            ("Secondary outcomes", [o for o in screen.outcomes if not o.primary])):
        if not outcomes:
            continue
        out.append(f"\n## {title} (arm minus control on each world; non-activated worlds excluded)\n")
        out.append("| Outcome | Stratum | Per world (seed: value) | Mean [min, max] | >0 / <0 / =0 | Sign-flip |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        for o in outcomes:
            for tag, seeds in strata.items():
                cells, values = paired_values(rows, screen, o.arm, o.control, o.read, tag, seeds)
                summary, signs, flip = _summary_cells(values, paired=o.control is not None)
                out.append(f"| {o.id}: {o.label} | {tag} | {'; '.join(cells)} | {summary} | {signs} | {flip} |")

    out.append("\n## Harm panel beside every comparison (each arm minus its control; non-activated worlds "
               "excluded)\n")
    out.append("| Comparison | Harm | Stratum | Per world | Mean [min, max] | >0 / <0 / =0 | Sign-flip | States |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for arm, control in harm_pairs(screen):
        for h in HARM_PANEL:
            for tag, seeds in strata.items():
                cohort_rows = [r for r in rows if r["stratum"] == tag and r["arm"] in (arm, control)]
                if h.extractor is None:
                    out.append(f"| {arm} - {control} | {h.label} | {tag} | requires slice extractor | n/a | n/a | n/a "
                               f"| {h.owner} |")
                    continue
                cells, values = paired_values(rows, screen, arm, control, _harm_reader(h.key), tag, seeds,
                                              why=_harm_why(h.key))
                summary, signs, flip = _summary_cells(values)
                out.append(f"| {arm} - {control} | {h.label} | {tag} | {'; '.join(cells)} | {summary} | {signs} | "
                           f"{flip} | {_harm_state(cohort_rows, h.key)} |")

    out.append("\n## Run time per arm (simulation and extraction seconds per run: mean [min, max])\n")
    out.append("| Arm | " + " | ".join(strata) + " |")
    out.append("| --- | " + " | ".join("---" for _ in strata) + " |")
    for arm in screen.arms:
        cells = []
        for tag in strata:
            d = describe([run_seconds(r) for r in rows if r["arm"] == arm and r["stratum"] == tag])
            cells.append("n/a" if d is None else f"{d['mean']:.1f} [{d['min']:.1f}, {d['max']:.1f}]")
        out.append(f"| {arm} | " + " | ".join(cells) + " |")
    out.append("\nDescriptive only: the sign-flip column counts the 2^n sign assignments whose mean is at least as "
               "far from zero as the observed mean, with the range of those means; it is not a significance test.")
    return out


def report_main(argv, screens: Mapping[str, Screen], prog: str = "screens") -> int:
    ap = argparse.ArgumentParser(prog=f"{prog} report")
    ap.add_argument("metrics")
    ap.add_argument("--screen", required=True)
    a = ap.parse_args(argv)
    screen = _screen_arg(screens, a.screen)
    rows = read_rows(a.metrics, screen)
    cohorts = {r.get("cohort") for r in rows}
    cohort_map = cohort_seeds(screen, next(iter(cohorts))) if len(cohorts) == 1 else {}
    lines = report_lines(rows, screen, cohort_map)
    if rows and cohorts == {"pilot"}:
        hours = projected_held_core_hours(rows, screen)
        lines.insert(3, "Projected held run time from this pilot: " + (
            f"{hours:.3f} core-hours (x{CEILING_MARGIN} = {hours * CEILING_MARGIN:.3f}) for "
            f"{len(screen.arms) * sum(map(len, screen.held.values()))} runs" if hours is not None
            else "unknown (an arm or stratum is missing)"))
    print("\n".join(lines))
    return 0


# --- Check -------------------------------------------------------------------------

def check_metrics(rows, cohort: str, screen: Screen, worlds: Sequence[tuple[str, int]] = (),
                  seeds: Mapping[str, Sequence[int]] | None = None) -> list[str]:
    """Every arm and world of the cohort has exactly one row of the screen, none failed,
    and every row carries the same identity."""
    problems = [f"{r['arm']} {r['stratum']}{r['seed']}: row of screen {r.get('screen')}"
                for r in rows if r.get("screen") != screen.name]
    seen: dict = {}
    for r in rows:
        key = (r["arm"], r["stratum"], r["seed"])
        seen[key] = seen.get(key, 0) + 1
        if r.get("cohort") != cohort:
            problems.append(f"{r['arm']} {r['stratum']}{r['seed']}: row of cohort {r.get('cohort')}")
        if r["rc"] != 0:
            problems.append(f"{r['arm']} {r['stratum']}{r['seed']}: rc {r['rc']}: {r.get('error', '')[-300:]}")
    if len({r.get("identity") for r in rows}) > 1:
        problems.append("rows carry more than one identity digest")
    if cohort == "dev":
        expected = [(tag, seed) for tag, seed in worlds]
    else:
        seeds = cohort_seeds(screen, cohort) if seeds is None else seeds
        expected = [(TAGS[s], seed) for s in STRATA for seed in seeds.get(s, ())]
    for tag, seed in expected:
        for arm in screen.arms:
            n = seen.get((arm, tag, seed), 0)
            if n != 1:
                problems.append(f"{arm} {tag}{seed}: {n} rows")
    extra = sorted(k for k in seen if k[0] not in screen.arms or (k[1], k[2]) not in set(expected))
    problems += [f"{a} {s}{seed}: not in the cohort" for a, s, seed in extra]
    return problems


def check_main(argv, screens: Mapping[str, Screen], prog: str = "screens") -> int:
    ap = argparse.ArgumentParser(prog=f"{prog} check")
    ap.add_argument("--screen", required=True, help="a screen, a comma-separated list or 'all'")
    ap.add_argument("--metrics", default=None)
    ap.add_argument("--cohort", choices=("pilot", "held", "reserve", "dev"), default=None)
    ap.add_argument("--worlds", default=None, help="dev metrics: the development worlds run")
    a = ap.parse_args(argv)
    names = list(screens) if a.screen == "all" else a.screen.split(",")
    reg = load_registry()
    rc = 0
    for name in names:
        screen = _screen_arg(screens, name)
        problems, notes = check_seeds(screen, reg)
        for note in notes:
            print(f"{screen.name} note: {note}")
        if problems:
            for p in problems:
                print(f"{screen.name} FAILED seeds: {p}")
            rc = max(rc, 1)
            continue
        print(f"{screen.name}: seeds OK (pilot {dict(screen.pilot)}, held "
              f"{ {s: compress(set(v)) for s, v in screen.held.items()} })")
        if not screen.ready:
            print(f"{screen.name}: NOT READY ({screen.not_ready}); every run is refused")
            rc = max(rc, 2)
            continue
        problems = check_screen(screen)
        for p in problems:
            print(f"{screen.name} FAILED: {p}")
        if problems:
            rc = max(rc, 1)
            continue
        print(f"{screen.name}: extractor, packages, {len(screen.arms)} arms and {len(screen.outcomes)} outcomes "
              f"({len(screen.primaries())} primary): OK")
    if a.metrics:
        if a.cohort is None or len(names) != 1:
            raise SystemExit("--metrics needs --cohort and one --screen")
        screen = _screen_arg(screens, names[0])
        rows = read_rows(a.metrics, screen)
        worlds = _dev_worlds(a.worlds, reg) if a.cohort == "dev" else []
        problems = check_metrics(rows, a.cohort, screen, worlds, cohort_seeds(screen, a.cohort, reg))
        for p in problems:
            print("FAILED", p)
        if any(r["rc"] == RC_MISSING for r in rows):
            return RC_MISSING
        if problems:
            return max(rc, 1)
        print(f"{len(rows)} runs: complete, every outcome extracted")
    return rc


def registry_main(argv, screens: Mapping[str, Screen], prog: str = "screens") -> int:
    ap = argparse.ArgumentParser(prog=f"{prog} registry")
    ap.add_argument("--registry", default=str(REGISTRY))
    a = ap.parse_args(argv)
    reg = load_registry(Path(a.registry))
    problems = validate_registry(reg)
    for p in problems:
        print("FAILED", p)
    print(f"{len(reg.get('entries') or [])} entries")
    if problems:
        return 1
    for stratum in STRATA:
        sets = seed_sets(reg, stratum)
        print(f"{stratum}: used {compress(sets['used'])}")
        print(f"{stratum}: never run again {compress(sets['never_run_again'])}")
        print(f"{stratum}: development {compress(sets['development'])}; reserved {compress(sets['reserved'])}")
    for e in reg["entries"]:
        if e["status"] == "reserved":
            print(f"reserved {e['id']}: {e['stratum']} {compress(expand(e['seeds']))} ({e['use']})")
    for u in reg.get("unresolved") or []:
        print(f"unresolved: {u['source']}: {u['note']}")
    return 0


def main(argv=None, screens: Mapping[str, Screen] | None = None, prog: str = "screens",
         rt: Runtime | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    screens = screens or {}
    commands = {"run": lambda args: run_main(args, screens, rt, prog),
                "report": lambda args: report_main(args, screens, prog),
                "check": lambda args: check_main(args, screens, prog),
                "registry": lambda args: registry_main(args, screens, prog),
                "mark-run": lambda args: mark_run_main(args, screens, prog)}
    if not argv or argv[0] not in commands:
        print(__doc__)
        return 0 if not argv else 2
    return commands[argv[0]](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
