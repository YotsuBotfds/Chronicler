"""Agent-scale benchmark: Rust tick time and full-turn time versus agent count.

Runs the real CLI pipeline (``execute_run``, ``--simulate-only``) on a generated
world whose region carrying capacities and starting populations are multiplied
by a benchmark-only factor, so the Rust pool starts near a target agent count.
Default worlds are untouched: the factor is applied by wrapping
``chronicler.main.generate_world`` inside the child process only.

Each target runs in its own child process. Per turn the child records

* ``rust_tick``: wall and process CPU time inside ``AgentSimulator.tick``
  (the native agent tick, including its rayon threads),
* ``turn``: wall and process CPU time between consecutive ``on_turn``
  callbacks (the whole turn: Python phases, ecology/economy/politics native
  calls, the agent tick, bridge post-processing and history capture),
* the alive agent count after the tick.

Warm-up turns are dropped and medians are reported. Process CPU time counts
every thread, so on a shared machine it is the steadier number; wall time is
what a user waits for.

Example::

    python scripts/agent_scale_benchmark.py --targets 1000,5000,20000 \
        --warmup 3 --turns 8 --out /tmp/scale.json

``--agent-scale-mode`` is forwarded to the CLI when the source tree supports
it; ``--source-root`` and ``--native-root`` select another checkout or a
saved native extension (both are prepended to ``PYTHONPATH`` for the child),
which is how base and new trees are compared.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time


REPO_ROOT = Path(__file__).resolve().parents[1]


def _median(values):
    return statistics.median(values) if values else None


def _child(opts: argparse.Namespace) -> dict:
    import resource

    os.environ.setdefault("CHRONICLER_QUIET", "1")
    import chronicler.main as cm
    import chronicler.agent_bridge as ab
    from chronicler.utils import sync_civ_population

    original_generate = cm.generate_world
    scale_info: dict = {}

    def scaled_generate(*args, **kwargs):
        world = original_generate(*args, **kwargs)
        base_pop = sum(r.population for r in world.regions)
        mult = opts.target / max(1, base_pop) if opts.target else opts.capacity_mult
        for region in world.regions:
            region.carrying_capacity = max(1, round(region.carrying_capacity * mult))
            region.population = round(region.population * mult)
            if region.carrying_capacity > 60000 or region.population > 60000:
                raise SystemExit("region exceeds u16 bridge range; use more regions")
        for civ in world.civilizations:
            sync_civ_population(civ, world)
        scale_info.update(
            base_population=base_pop,
            multiplier=mult,
            start_population=sum(r.population for r in world.regions),
            max_region_population=max(r.population for r in world.regions),
            populated_regions=sum(1 for r in world.regions if r.population > 0),
        )
        return world

    cm.generate_world = scaled_generate

    def cpu() -> float:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        return ru.ru_utime + ru.ru_stime

    tick_log: list[tuple[float, float, int]] = []

    class TimedSim:
        """Delegating proxy that times ``tick`` on the native simulator."""

        def __init__(self, inner):
            object.__setattr__(self, "_inner", inner)

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __setattr__(self, name, value):
            setattr(self._inner, name, value)

        def tick(self, *args, **kwargs):
            w0, c0 = time.perf_counter(), cpu()
            result = self._inner.tick(*args, **kwargs)
            tick_log.append((time.perf_counter() - w0, cpu() - c0,
                             int(self._inner.last_tick_alive)))
            return result

    original_init = ab.AgentBridge.__init__

    def timed_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._sim = TimedSim(self._sim)

    ab.AgentBridge.__init__ = timed_init

    out_dir = Path(tempfile.mkdtemp(prefix="agent-scale-", dir=opts.run_root))
    argv = [
        "--seed", str(opts.seed), "--turns", str(opts.warmup + opts.turns),
        "--civs", str(opts.civs), "--regions", str(opts.regions),
        "--agents", opts.agents, "--simulate-only",
        "--output", str(out_dir / "chronicle.md"), "--state", str(out_dir / "state.json"),
        "--state-every", str(10 ** 6),
    ]
    if opts.worldgen:
        argv += ["--worldgen", opts.worldgen]
    if opts.agent_scale_mode:
        argv += ["--agent-scale-mode", opts.agent_scale_mode]
    args = cm._build_parser().parse_args(argv)

    turn_marks: list[tuple[float, float]] = []

    def on_turn(*_):
        turn_marks.append((time.perf_counter(), cpu()))

    start = (time.perf_counter(), cpu())
    try:
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            cm.execute_run(args, on_turn=on_turn)
    finally:
        if not opts.keep_runs:
            shutil.rmtree(out_dir, ignore_errors=True)
    total = (time.perf_counter() - start[0], cpu() - start[1])

    marks = [start] + turn_marks
    turn_wall = [b[0] - a[0] for a, b in zip(marks, marks[1:])]
    turn_cpu = [b[1] - a[1] for a, b in zip(marks, marks[1:])]
    w = opts.warmup
    measured_ticks = tick_log[w:]
    alive = [t[2] for t in measured_ticks]
    return {
        "target": opts.target,
        "agents_mode": opts.agents,
        "agent_scale_mode": opts.agent_scale_mode or "default",
        "seed": opts.seed,
        "regions": opts.regions,
        "civs": opts.civs,
        "worldgen": opts.worldgen or "auto",
        "warmup": w,
        "turns": opts.turns,
        **scale_info,
        "alive_median": _median(alive),
        "alive_min": min(alive) if alive else None,
        "alive_max": max(alive) if alive else None,
        "rust_tick_wall_ms": _median([t[0] * 1e3 for t in measured_ticks]),
        "rust_tick_cpu_ms": _median([t[1] * 1e3 for t in measured_ticks]),
        "turn_wall_ms": _median([t * 1e3 for t in turn_wall[w:]]),
        "turn_cpu_ms": _median([t * 1e3 for t in turn_cpu[w:]]),
        "total_wall_s": total[0],
        "total_cpu_s": total[1],
        "per_turn": [
            {"turn": i, "alive": tick_log[i][2] if i < len(tick_log) else None,
             "rust_wall_ms": tick_log[i][0] * 1e3 if i < len(tick_log) else None,
             "rust_cpu_ms": tick_log[i][1] * 1e3 if i < len(tick_log) else None,
             "turn_wall_ms": turn_wall[i] * 1e3, "turn_cpu_ms": turn_cpu[i] * 1e3}
            for i in range(len(turn_wall))
        ],
        "rayon_threads": os.environ.get("RAYON_NUM_THREADS", "default"),
    }


def _parse(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--targets", default="1000,5000,20000,50000,100000",
                   help="comma-separated starting agent counts")
    p.add_argument("--target", type=int, default=0, help=argparse.SUPPRESS)
    p.add_argument("--capacity-mult", type=float, default=1.0,
                   help="fixed multiplier when no target is given")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--regions", type=int, default=12)
    p.add_argument("--civs", type=int, default=4)
    p.add_argument("--worldgen", default=None, choices=["auto", "template", "procedural"],
                   help="forwarded to the CLI (worlds above 12 regions are procedural)")
    p.add_argument("--agents", default="hybrid",
                   choices=["demographics-only", "shadow", "hybrid"])
    p.add_argument("--agent-scale-mode", default=None, choices=["exact", "fast"])
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--turns", type=int, default=8)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--jobs", type=int, default=1, help="concurrent child processes")
    p.add_argument("--timeout", type=float, default=3600.0, help="per child, seconds")
    p.add_argument("--source-root", type=Path, default=None,
                   help="checkout whose src/ is used by the child")
    p.add_argument("--native-root", type=Path, default=None,
                   help="directory containing a chronicler_agents package to use")
    p.add_argument("--run-root", type=Path, default=Path(tempfile.gettempdir()))
    p.add_argument("--keep-runs", action="store_true")
    p.add_argument("--out", type=Path, default=None, help="write results JSON here")
    p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _child_cmd(opts: argparse.Namespace, target: int) -> list[str]:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--child",
           "--target", str(target), "--seed", str(opts.seed),
           "--regions", str(opts.regions), "--civs", str(opts.civs),
           "--agents", opts.agents, "--warmup", str(opts.warmup),
           "--turns", str(opts.turns), "--run-root", str(opts.run_root),
           "--capacity-mult", str(opts.capacity_mult)]
    if opts.worldgen:
        cmd += ["--worldgen", opts.worldgen]
    if opts.agent_scale_mode:
        cmd += ["--agent-scale-mode", opts.agent_scale_mode]
    if opts.keep_runs:
        cmd.append("--keep-runs")
    return cmd


def _child_env(opts: argparse.Namespace) -> dict:
    env = dict(os.environ)
    paths = []
    if opts.native_root:
        paths.append(str(opts.native_root.resolve()))
    if opts.source_root:
        paths.append(str((opts.source_root / "src").resolve()))
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths + [env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    return env


def main(argv=None) -> int:
    opts = _parse(argv)
    if opts.child:
        print(json.dumps(_child(opts)))
        return 0
    opts.run_root.mkdir(parents=True, exist_ok=True)
    targets = [int(t) for t in opts.targets.split(",") if t.strip()]
    jobs = [(t, r) for t in targets for r in range(opts.repeats)]
    env = _child_env(opts)
    results = []
    running: list[tuple[int, int, subprocess.Popen, float]] = []
    pending = list(jobs)
    while pending or running:
        while pending and len(running) < max(1, opts.jobs):
            t, r = pending.pop(0)
            proc = subprocess.Popen(_child_cmd(opts, t), env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            running.append((t, r, proc, time.monotonic()))
        for item in list(running):
            t, r, proc, started = item
            if proc.poll() is None:
                if time.monotonic() - started > opts.timeout:
                    proc.kill()
                    proc.wait()
                    results.append({"target": t, "repeat": r, "error": "timeout"})
                    running.remove(item)
                continue
            out, err = proc.communicate()
            running.remove(item)
            if proc.returncode != 0:
                results.append({"target": t, "repeat": r, "error": err[-2000:]})
                print(f"target {t} repeat {r}: FAILED\n{err[-2000:]}", file=sys.stderr)
                continue
            row = json.loads(out.strip().splitlines()[-1])
            row["repeat"] = r
            results.append(row)
            print(f"target {t:>7} r{r}: alive~{row['alive_median']}, "
                  f"rust tick {row['rust_tick_wall_ms']:.1f} ms wall / "
                  f"{row['rust_tick_cpu_ms']:.1f} ms cpu, "
                  f"turn {row['turn_wall_ms']:.1f} ms wall / {row['turn_cpu_ms']:.1f} ms cpu",
                  flush=True)
        time.sleep(0.2)
    if opts.out:
        opts.out.parent.mkdir(parents=True, exist_ok=True)
        opts.out.write_text(json.dumps({
            "argv": sys.argv[1:],
            "source_root": str(opts.source_root or REPO_ROOT),
            "native_root": str(opts.native_root) if opts.native_root else None,
            "results": sorted(results, key=lambda r: (r["target"], r.get("repeat", 0))),
        }, indent=2) + "\n")
    return 0 if all("error" not in r for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
