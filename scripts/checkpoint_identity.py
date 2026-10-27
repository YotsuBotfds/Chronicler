#!/usr/bin/env python3
"""Resume identity for exact checkpoints (``--checkpoint-every``, ``--resume``).

``run OUT_DIR --case NAME [--case ...] [--ks K,K,...] [--jobs 2] [--cli-arg ARG ...]``
    For each case: one straight run of N turns without checkpoints
    (``plain``), one with a checkpoint at every turn of K (``straight``),
    and for every k in K a run resumed from the turn-k checkpoint
    (``resume_k``). Then compares, byte for byte (``chronicle_bundle.json``
    decoded without ``metadata.generated_at``, as ``scripts/cities_identity.py``):

    * ``plain`` with ``straight``: writing checkpoints changes nothing;
    * every ``resume_k`` with ``straight``: every file the resumed run
      writes. Per-turn validation JSON files of turns up to k are written
      only by the run that played those turns and are not expected in
      ``resume_k``.

    ``resume_k`` directories and checkpoints are deleted after a passing
    comparison (``--keep`` keeps them). Default K: every turn 1..N-1 for
    the short cases, a spread for the long ones (``cases`` lists them).
    Runs use ``PYTHONHASHSEED=0`` and ``RAYON_NUM_THREADS=1`` (resumes:
    ``--resume-hash-seed``), one CLI subprocess each, at most ``--jobs``
    at a time. Writes ``OUT_DIR/<case>/report.json`` and prints a line per k.

``cases``
    Lists the case matrix.
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# name -> (CLI arguments, turns, starting-agent target or 0, resume turns)
# Resume turns None: every turn 1..N-1 (short runs); "spread": SPREAD below.
CASES: dict[str, tuple[list[str], int, int, str | None]] = {
    "off_s42": (["--seed", "42", "--agents", "off"], 60, 0, None),
    "off_s7_scholarship": (["--seed", "7", "--agents", "off", "--scholarship"], 60, 0, None),
    "off_s42_minimal": (["--seed", "42", "--agents", "off", "--no-campaigns", "--no-governance",
                         "--no-contact-ledger", "--no-finance", "--no-diplomacy", "--no-techniques",
                         "--no-maritime", "--no-gp-agendas", "--no-nomads", "--no-cities",
                         "--no-agent-movements", "--no-guilds", "--no-historiography",
                         "--no-languages", "--no-fisheries"], 40, 0, None),
    "hybrid_s42": (["--seed", "42", "--agents", "hybrid", "--validation-sidecar"], 60, 0, None),
    "hybrid_s7_scholarship": (["--seed", "7", "--agents", "hybrid", "--scholarship",
                               "--validation-sidecar", "--relationship-stats"], 60, 0, None),
    "hybrid_s1234_fast": (["--seed", "1234", "--agents", "hybrid", "--agent-scale-mode", "fast"],
                          40, 0, None),
    "demographics_s42": (["--seed", "42", "--agents", "demographics-only"], 40, 0, None),
    "shadow_s42": (["--seed", "42", "--agents", "shadow"], 40, 0, None),
    "proc32_hybrid_s11": (["--seed", "11", "--regions", "32", "--civs", "8", "--worldgen",
                           "procedural", "--agents", "hybrid", "--validation-sidecar"], 40, 0, None),
    "proc48_hybrid_s42_scholarship": (["--seed", "42", "--regions", "48", "--civs", "10",
                                       "--agents", "hybrid", "--scholarship"], 40, 0, None),
    # The long runs of scripts/turn_speed_identity.py.
    "off_s42_long": (["--seed", "42", "--agents", "off"], 300, 0, "spread"),
    "hybrid_s42_long": (["--seed", "42", "--agents", "hybrid", "--validation-sidecar"], 200, 0,
                        "spread"),
    "hybrid_s7_long_scholarship": (["--seed", "7", "--agents", "hybrid", "--validation-sidecar",
                                    "--scholarship"], 200, 0, "spread"),
    "proc48_off_s7_long": (["--seed", "7", "--regions", "48", "--civs", "10", "--agents", "off"],
                           200, 0, "spread"),
    "proc48_hybrid_s42_long": (["--seed", "42", "--regions", "48", "--civs", "10", "--agents",
                                "hybrid", "--validation-sidecar"], 150, 0, "spread"),
    "scaled22k_s42": (["--seed", "42", "--regions", "12", "--civs", "4", "--agents", "hybrid",
                       "--validation-sidecar"], 30, 18800, "spread"),
    "scaled52k_s7": (["--seed", "7", "--regions", "12", "--civs", "4", "--agents", "hybrid"], 20,
                     43700, "spread"),
    # Four sects take the native slots of vanished faiths (turns 37, 100, 134,
    # 168): resumes on both sides of each change of the permanent faith table
    # (docs/integration/permanent-faiths.md).
    "proc32_hybrid_s42_recycling": (["--seed", "42", "--regions", "32", "--civs", "10", "--worldgen",
                                     "procedural", "--agents", "hybrid", "--validation-sidecar"], 200, 0,
                                    "spread"),
}

# Resume turns of a long run: early turns, a Fibonacci spread, the first
# economy sidecar turns (100 on) and the last turn.
SPREAD = (1, 2, 3, 5, 8, 13, 21, 34, 35, 40, 46, 55, 89, 99, 100, 101, 110, 144, 233)


def _default_ks(turns: int, kind: str | None) -> list[int]:
    if kind is None:
        return list(range(1, turns))
    return sorted({k for k in SPREAD if k < turns} | {turns // 2, turns - 1})


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

_PER_TURN = re.compile(r"_turn_(\d+)\.json$")


def _env(hash_seed: str = "0") -> dict:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    env["RAYON_NUM_THREADS"] = "1"
    env["CHRONICLER_QUIET"] = "1"
    return env


def _run(cmd: list[str], log: Path, env: dict) -> tuple[int, float]:
    t0 = time.monotonic()
    with open(log, "w") as fh:
        proc = subprocess.run(cmd, env=env, stdout=fh, stderr=subprocess.STDOUT, cwd=str(log.parent))
    return proc.returncode, time.monotonic() - t0


def _cmd(target: int, cli: list[str]) -> list[str]:
    if target:
        return [sys.executable, "-c", _SCALED_RUNNER, str(target), *cli]
    return [sys.executable, "-m", "chronicler.main", *cli]


def _outputs(directory: Path) -> list[str]:
    return ["--simulate-only", "--output", str(directory / "chronicle.md"),
            "--state", str(directory / "state.json")]


def _compare_resume(straight: Path, resumed: Path, k: int) -> tuple[int, list[str]]:
    from cities_identity import compare as compare_dirs
    checked, problems = compare_dirs(straight, resumed)
    kept = []
    for line in problems:
        if line.startswith("only in base: "):
            rel = line[len("only in base: "):]
            if rel.startswith("ckpt/"):
                continue
            m = _PER_TURN.search(rel)
            if m and int(m.group(1)) <= k:
                continue
        kept.append(line)
    return checked, kept


def run_case(out: Path, name: str, ks: list[int] | None, jobs: int, extra: list[str],
             keep: bool, resume_hash_seed: str) -> dict:
    cli, turns, target, kind = CASES[name]
    cli = [*cli, "--turns", str(turns), *extra]
    case = out / name
    if case.exists():
        shutil.rmtree(case)
    case.mkdir(parents=True)
    ks = sorted(set(ks if ks is not None else _default_ks(turns, kind)))
    ks = [k for k in ks if 0 < k < turns]
    report: dict = {"case": name, "cli": cli, "turns": turns, "target_agents": target, "ks": ks,
                    "results": {}}
    plain, straight = case / "plain", case / "straight"
    plain.mkdir()
    straight.mkdir()
    ckpt = straight / "ckpt"
    ckpt_args = ["--checkpoint-every", "1", "--checkpoint", str(ckpt / "turn_{turn:04d}.ckpt")]
    # Checkpoints not in K are deleted as soon as they appear (each is
    # complete when visible: written to a temporary file and renamed).
    sizes: dict[int, int] = {}
    stop = threading.Event()

    def prune() -> None:
        while True:
            done = stop.is_set()
            for path in sorted(ckpt.glob("turn_*.ckpt")):
                turn = int(path.stem.split("_")[1])
                if turn not in sizes:
                    sizes[turn] = path.stat().st_size
                if turn not in ks:
                    path.unlink()
            if done:
                return
            stop.wait(0.2)

    pruner = threading.Thread(target=prune, daemon=True)
    pruner.start()
    with ThreadPoolExecutor(max_workers=min(jobs, 2)) as pool:
        f_plain = pool.submit(_run, _cmd(target, [*cli, *_outputs(plain)]), case / "plain.log", _env())
        f_straight = pool.submit(_run, _cmd(target, [*cli, *_outputs(straight), *ckpt_args]),
                                 case / "straight.log", _env())
        (rc_p, s_p), (rc_s, s_s) = f_plain.result(), f_straight.result()
    stop.set()
    pruner.join()
    report["plain"] = {"exit": rc_p, "seconds": round(s_p, 2)}
    report["straight"] = {"exit": rc_s, "seconds": round(s_s, 2)}
    if rc_p or rc_s:
        report["error"] = "straight run failed"
        return report
    report["checkpoint_bytes"] = dict(sorted(sizes.items()))
    from cities_identity import compare as compare_dirs
    checked, problems = compare_dirs(plain, straight)
    problems = [p for p in problems if not p.startswith("only in new: ckpt/")]
    report["checkpointing_changes_nothing"] = {"files": checked, "differences": problems}
    print(f"{name}: plain vs straight with checkpoints: {checked} files, {len(problems)} differences",
          flush=True)

    def resume(k: int) -> tuple[int, dict]:
        rdir = case / f"resume_{k:04d}"
        rdir.mkdir()
        rc, secs = _run(_cmd(0, ["--resume", str(ckpt / f"turn_{k:04d}.ckpt"), *_outputs(rdir)]),
                        case / f"resume_{k:04d}.log", _env(resume_hash_seed))
        result = {"exit": rc, "seconds": round(secs, 2)}
        if rc == 0:
            n, diffs = _compare_resume(straight, rdir, k)
            result.update(files=n, differences=diffs)
            if not diffs and not keep:
                shutil.rmtree(rdir)
                (case / f"resume_{k:04d}.log").unlink()
        return k, result

    with ThreadPoolExecutor(max_workers=min(jobs, 2)) as pool:
        for k, result in pool.map(resume, ks):
            report["results"][str(k)] = result
            status = ("FAIL exit %d" % result["exit"] if result["exit"]
                      else f"{result['files']} files, {len(result['differences'])} differences")
            print(f"{name}: resume at {k}: {status}", flush=True)
            for line in result.get("differences", [])[:10]:
                print(f"    {line}", flush=True)
    passed = (not problems and all(r["exit"] == 0 and not r["differences"]
                                   for r in report["results"].values()))
    report["pass"] = passed
    if passed and not keep:
        shutil.rmtree(ckpt)
        shutil.rmtree(plain)
    (case / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{name}: {'PASS' if passed else 'FAIL'} ({len(ks)} resume points)", flush=True)
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("out", type=Path)
    r.add_argument("--case", action="append", choices=sorted(CASES), required=True)
    r.add_argument("--ks", type=str, default=None, help="comma-separated resume turns (default: all)")
    r.add_argument("--jobs", type=int, default=1, choices=(1, 2))
    r.add_argument("--keep", action="store_true")
    r.add_argument("--resume-hash-seed", default="0")
    r.add_argument("--cli-arg", action="append", default=[])
    sub.add_parser("cases")
    a = p.parse_args(argv)
    if a.cmd == "cases":
        for name, (cli, turns, target, kind) in CASES.items():
            print(f"{name}: {turns} turns{f', {target} agents' if target else ''}, resume at "
                  f"{_default_ks(turns, kind)}: {' '.join(cli)}")
        return 0
    a.out.mkdir(parents=True, exist_ok=True)
    ks = [int(x) for x in a.ks.split(",")] if a.ks else None
    status = 0
    for name in a.case:
        report = run_case(a.out.resolve(), name, ks, a.jobs, a.cli_arg, a.keep, a.resume_hash_seed)
        status |= not report.get("pass", False)
    return status


if __name__ == "__main__":
    sys.exit(main())
