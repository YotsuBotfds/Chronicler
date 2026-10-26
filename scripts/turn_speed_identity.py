#!/usr/bin/env python3
"""Byte-identity runs for performance work.

``run OUT_DIR [--case NAME ...] [--source-root SRC] [--native-root DIR] [--cli-arg ARG ...]``
    Run the case matrix below as CLI subprocesses (``PYTHONHASHSEED=0``,
    ``RAYON_NUM_THREADS=1``), one at a time, each into ``OUT_DIR/<case>``.
    ``--source-root`` puts another checkout's ``src`` first on
    ``PYTHONPATH`` and ``--native-root`` a saved ``chronicler_agents``
    package, which is how a base tree is run. ``--cli-arg`` adds a CLI
    argument to every case (a feature switch such as ``--no-scholarship``).

``compare BASE_DIR NEW_DIR``
    Every file of every case byte for byte (``chronicle_bundle.json``
    decoded, without ``metadata.generated_at``), as
    ``scripts/cities_identity.py compare``; each bundle's raw bytes are
    also compared with only the ``generated_at`` value blanked.

Scaled cases multiply region capacities and starting populations before
the first turn, as ``scripts/agent_scale_benchmark.py`` does.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]

# name -> (CLI arguments, starting-agent target or 0)
CASES: dict[str, tuple[list[str], int]] = {
    "off_s42": (["--seed", "42", "--turns", "300", "--agents", "off"], 0),
    "off_s7": (["--seed", "7", "--turns", "300", "--agents", "off"], 0),
    "hybrid_s42": (["--seed", "42", "--turns", "200", "--agents", "hybrid",
                    "--validation-sidecar"], 0),
    "hybrid_s7": (["--seed", "7", "--turns", "200", "--agents", "hybrid",
                   "--validation-sidecar"], 0),
    "hybrid_s1234": (["--seed", "1234", "--turns", "200", "--agents", "hybrid"], 0),
    "proc48_hybrid_s42": (["--seed", "42", "--turns", "150", "--regions", "48", "--civs", "10",
                           "--agents", "hybrid", "--validation-sidecar"], 0),
    "proc48_off_s7": (["--seed", "7", "--turns", "200", "--regions", "48", "--civs", "10",
                       "--agents", "off"], 0),
    "scaled22k_s42": (["--seed", "42", "--turns", "30", "--regions", "12", "--civs", "4",
                       "--agents", "hybrid", "--validation-sidecar"], 18800),
    "scaled52k_s7": (["--seed", "7", "--turns", "20", "--regions", "12", "--civs", "4",
                      "--agents", "hybrid"], 43700),
}

_SCALED_RUNNER = r"""
import sys
import chronicler.main as cm
from chronicler.utils import sync_civ_population
target = int(sys.argv[1])
original = cm.generate_world
def scaled(*a, **k):
    world = original(*a, **k)
    mult = target / max(1, sum(r.population for r in world.regions))
    for region in world.regions:
        region.carrying_capacity = max(1, round(region.carrying_capacity * mult))
        region.population = round(region.population * mult)
    for civ in world.civilizations:
        sync_civ_population(civ, world)
    return world
cm.generate_world = scaled
sys.argv = ["chronicler"] + sys.argv[2:]
cm.main()
"""


def _env(source_root: Path | None, native_root: Path | None) -> dict:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["RAYON_NUM_THREADS"] = "1"
    env["CHRONICLER_QUIET"] = "1"
    paths = []
    if native_root:
        paths.append(str(native_root.resolve()))
    if source_root:
        paths.append(str((source_root / "src").resolve()))
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths)
    else:
        env.pop("PYTHONPATH", None)
    return env


_WHICH = (
    "import hashlib, chronicler, chronicler_agents.chronicler_agents as m\n"
    "print('chronicler', chronicler.__file__)\n"
    "print('native', m.__file__, hashlib.sha256(open(m.__file__, 'rb').read()).hexdigest())\n"
)


def run(out: Path, cases: list[str], source_root: Path | None, native_root: Path | None,
        extra: list[str] | None = None) -> int:
    env = _env(source_root, native_root)
    # Record which source tree and native build the runs used.
    which = subprocess.run([sys.executable, "-c", _WHICH], env=env, cwd=str(out),
                           capture_output=True, text=True)
    (out / "which.txt").write_text(which.stdout + which.stderr)
    print(which.stdout.strip(), flush=True)
    status = 0
    for name in cases:
        cli, target = CASES[name]
        case_dir = out / name
        case_dir.mkdir(parents=True, exist_ok=True)
        cli = cli + list(extra or []) + ["--simulate-only", "--output", str(case_dir / "chronicle.md"),
                     "--state", str(case_dir / "state.json")]
        if target:
            cmd = [sys.executable, "-c", _SCALED_RUNNER, str(target), *cli]
        else:
            cmd = [sys.executable, "-m", "chronicler.main", *cli]
        t0 = time.monotonic()
        with open(out / f"{name}.log", "w") as log:
            proc = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                  cwd=str(out))
        print(f"{name}: exit {proc.returncode} in {time.monotonic() - t0:.0f} s", flush=True)
        status |= proc.returncode != 0
    return int(status)


_GENERATED_AT = re.compile(rb'"generated_at": ?"[^"]*"')


def _raw_bundle_problems(base: Path, new: Path) -> list[str]:
    """Raw bytes of every bundle, with only the wall-clock stamp blanked."""
    problems = []
    for a in sorted(base.rglob("chronicle_bundle.json")):
        b = new / a.relative_to(base)
        if not b.exists():
            continue
        if _GENERATED_AT.sub(b"", a.read_bytes()) != _GENERATED_AT.sub(b"", b.read_bytes()):
            problems.append(f"raw bytes differ: {a.relative_to(base)}")
    return problems


def compare(base: Path, new: Path) -> int:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from cities_identity import compare as compare_dirs

    total_checked = 0
    total_problems = 0
    cases = sorted(p.name for p in base.iterdir() if p.is_dir())
    for name in cases:
        checked, problems = compare_dirs(base / name, new / name)
        problems += _raw_bundle_problems(base / name, new / name)
        total_checked += checked
        total_problems += len(problems)
        print(f"{name}: {checked} files, {len(problems)} differences")
        for line in problems:
            print(f"  {line}")
    print(f"{len(cases)} cases, {total_checked} files compared, {total_problems} differences")
    return 0 if total_checked and not total_problems else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("out", type=Path)
    r.add_argument("--case", action="append", choices=sorted(CASES))
    r.add_argument("--source-root", type=Path)
    r.add_argument("--native-root", type=Path)
    r.add_argument("--cli-arg", action="append", default=[],
                   help="extra CLI argument for every case (repeatable)")
    c = sub.add_parser("compare")
    c.add_argument("base", type=Path)
    c.add_argument("new", type=Path)
    a = p.parse_args(argv)
    if a.cmd == "run":
        a.out.mkdir(parents=True, exist_ok=True)
        return run(a.out.resolve(), a.case or list(CASES), a.source_root, a.native_root, a.cli_arg)
    return compare(a.base, a.new)


if __name__ == "__main__":
    sys.exit(main())
