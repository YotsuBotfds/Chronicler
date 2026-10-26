"""Whole-turn CPU profile split by phase.

Runs the real CLI pipeline (``execute_run``, ``--simulate-only``) in this
process and wraps the turn's phase functions with process-CPU timers
(``time.process_time``: every thread, so native rayon work is included).
Each wrapped call records inclusive and exclusive CPU under its caller, so
the report is a call tree whose exclusive times add up to the turn.

Wrapped: ``run_turn_result`` and the functions it calls (found from its
source, two levels down), the snapshot-building helpers of
``execute_run``'s loop, the ``AgentBridge`` methods and every method of the
native ``AgentSimulator`` (as ``native.<name>``). CPU spent in the loop
itself (``TurnSnapshot`` arguments, memory streams) is ``main.loop``.

``--target N`` multiplies region capacities and starting populations so the
pool starts near N agents (as ``scripts/agent_scale_benchmark.py``); 0
leaves the world as generated. Warm-up turns are excluded.

Example::

    RAYON_NUM_THREADS=1 python scripts/turn_phase_profile.py --target 43700 \\
        --warmup 20 --turns 8 --out prof.json

``--source-root`` runs another checkout's ``src`` (and ``--native-root`` a
saved ``chronicler_agents`` package) by re-executing with ``PYTHONPATH``.
The wrappers do not change arguments, results or call order, so the run's
outputs are those of an unprofiled run.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import contextlib
import functools
import importlib
import inspect
import io
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import textwrap
import time
import types

_cpu = time.process_time

# Small helpers called many times per turn: timing them costs more than
# they do and blurs their callers.
SKIP = frozenset({
    "clamp", "get_civ", "civ_index", "get_override", "get_multiplier", "len",
    "isinstance", "getattr", "setattr", "hasattr", "sorted", "min", "max",
    "sum", "any", "all", "int", "float", "str", "list", "dict", "set",
    "tuple", "range", "enumerate", "zip", "round", "abs", "next", "iter",
    "Event", "NamedEvent", "history_index", "_require_phase_acc_for_hybrid",
    "get_severity_multiplier", "region_map", "_contact_ledger_on",
    "_epidemiology_on", "_maritime_on", "_nomads_on", "_cities_on",
    "_agent_movements_on", "_guilds_on", "_diplomacy_on", "_techniques_on",
    "_gp_agendas_on", "normalize_shock", "sync_civ_population",
})


class Profiler:
    def __init__(self) -> None:
        self.stack: list[list] = []
        self.enabled = False
        # (parent, label) -> [calls, inclusive, exclusive]
        self.rows: dict[tuple[str, str], list] = defaultdict(lambda: [0, 0.0, 0.0])
        self.wrapped: set[int] = set()

    def wrap(self, label: str, fn):
        if getattr(fn, "_phase_profiled", False):
            return fn
        prof = self

        @functools.wraps(fn)
        def timed(*args, **kwargs):
            if not prof.enabled:
                return fn(*args, **kwargs)
            frame = [label, _cpu(), 0.0]
            parent = prof.stack[-1][0] if prof.stack else "turn"
            prof.stack.append(frame)
            try:
                return fn(*args, **kwargs)
            finally:
                elapsed = _cpu() - frame[1]
                prof.stack.pop()
                row = prof.rows[(parent, label)]
                row[0] += 1
                row[1] += elapsed
                row[2] += elapsed - frame[2]
                if prof.stack:
                    prof.stack[-1][2] += elapsed

        timed._phase_profiled = True
        return timed

    def gc_callback(self, phase: str, info: dict) -> None:
        """Book cyclic-GC pauses as ``gc.gen<N>`` under the running phase."""
        if not self.enabled:
            return
        if phase == "start":
            self._gc_start = _cpu()
            return
        start = getattr(self, "_gc_start", None)
        if start is None:
            return
        self._gc_start = None
        elapsed = _cpu() - start
        parent = self.stack[-1][0] if self.stack else "turn"
        row = self.rows[(parent, f"gc.gen{info.get('generation')}")]
        row[0] += 1
        row[1] += elapsed
        row[2] += elapsed
        if self.stack:
            self.stack[-1][2] += elapsed


PROF = Profiler()


def _is_ours(obj) -> bool:
    mod = getattr(obj, "__module__", "") or ""
    return mod.startswith("chronicler") and not mod.startswith("chronicler_agents")


def _patch_attr(owner, name: str, label: str) -> None:
    try:
        fn = getattr(owner, name)
    except AttributeError:
        return
    if isinstance(fn, type) or not callable(fn):
        return
    setattr(owner, name, PROF.wrap(label, fn))


def _callees(fn) -> list[tuple[object, str, str]]:
    """``(owner, attribute, label)`` for the chronicler functions ``fn`` calls."""
    fn = inspect.unwrap(fn)
    try:
        src = textwrap.dedent(inspect.getsource(fn))
    except (OSError, TypeError):
        return []
    tree = ast.parse(src)
    glb = fn.__globals__
    local_from: dict[str, tuple[str, str]] = {}
    local_mod: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                local_from[alias.asname or alias.name] = (node.module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_mod[alias.asname or alias.name] = alias.name
    out = []
    seen = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        target = None
        if isinstance(f, ast.Name):
            name = f.id
            if name in SKIP:
                continue
            if name in local_from:
                modname, attr = local_from[name]
                try:
                    mod = importlib.import_module(modname)
                except Exception:
                    continue
                obj = getattr(mod, attr, None)
                if isinstance(obj, types.FunctionType) and _is_ours(obj):
                    target = (mod, attr, f"{modname.removeprefix('chronicler.')}.{attr}")
            else:
                obj = glb.get(name)
                if isinstance(obj, types.FunctionType) and _is_ours(obj):
                    mod = sys.modules[fn.__module__]
                    target = (mod, name, f"{obj.__module__.removeprefix('chronicler.')}.{obj.__name__}")
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            base = f.value.id
            mod = None
            if base in local_mod:
                mod = sys.modules.get(local_mod[base])
            elif base in local_from:
                try:
                    cand = importlib.import_module(f"{local_from[base][0]}.{local_from[base][1]}")
                    mod = cand
                except Exception:
                    mod = None
            elif isinstance(glb.get(base), types.ModuleType):
                mod = glb[base]
            if mod is not None and (mod.__name__ or "").startswith("chronicler."):
                obj = getattr(mod, f.attr, None)
                if isinstance(obj, types.FunctionType) and _is_ours(obj) and f.attr not in SKIP:
                    target = (mod, f.attr, f"{mod.__name__.removeprefix('chronicler.')}.{f.attr}")
        if target and (id(target[0]), target[1]) not in seen:
            seen.add((id(target[0]), target[1]))
            out.append(target)
    return out


def _instrument_tree(owner, name: str, label: str, depth: int) -> None:
    fn = getattr(owner, name, None)
    if fn is None or getattr(fn, "_phase_profiled", False):
        return
    children = _callees(fn) if depth > 0 else []
    _patch_attr(owner, name, label)
    for c_owner, c_name, c_label in children:
        _instrument_tree(c_owner, c_name, c_label, depth - 1)


class _TimedNative:
    """Proxy timing every method of the native simulator."""

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)

    def __getattr__(self, name):
        value = getattr(self._inner, name)
        if callable(value) and not name.startswith("__"):
            return PROF.wrap(f"native.{name}", value)
        return value

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)


def instrument(depth: int) -> None:
    import chronicler.main as cm
    import chronicler.simulation as sim
    import chronicler.agent_bridge as ab
    from chronicler.accumulator import StatAccumulator

    # The turn and its phases (callees found from the source).
    _instrument_tree(cm, "run_turn_result", "run_turn", depth)
    for name in ("apply_keep", "apply", "to_shock_signals", "to_demand_signals"):
        _patch_attr(StatAccumulator, name, f"acc.{name}")

    # Snapshot building and the rest of the main loop.
    for name in list(vars(cm)):
        if name.endswith("_snapshot_fields") or name in (
            "compute_accuracy", "_get_perceived_stat_with_accuracy", "border_pairs",
            "_governance_snapshot", "_pandemic_region_names", "_urban_counts_by_civ",
            "_save_memory_streams", "_write_state_checkpoint",
        ):
            _patch_attr(cm, name, f"main.{name.lstrip('_')}")
    for cls_name in ("TurnSnapshot", "CivSnapshot", "ActionEngine"):
        cls = getattr(cm, cls_name)
        setattr(cm, cls_name, PROF.wrap(f"main.{cls_name}()", cls))
    from chronicler import historiography, languages
    _instrument_tree(historiography, "observe_turn", "historiography.observe_turn", 1)
    _instrument_tree(languages, "observe_turn", "languages.observe_turn", 1)

    # Bridge.
    for name in ("sync_regions", "tick_agents", "_process_tick_results",
                 "_refresh_snapshot_metrics", "_write_back", "_process_promotions",
                 "_convert_events", "_process_deaths", "_detect_character_events",
                 "_aggregate_events", "_write_sidecar_snapshot", "_write_economy_sidecar",
                 "take_post_tick_snapshot", "read_social_edges"):
        _patch_attr(ab.AgentBridge, name, f"bridge.{name.lstrip('_')}")
    for name in ("build_region_batch", "build_settlement_batch", "build_signals",
                 "_send_movement_table", "_city_route_graph", "_get_agent_memory_records"):
        _patch_attr(ab, name, f"bridge.{name.lstrip('_')}")
    from chronicler import economy
    _patch_attr(economy, "build_merchant_route_graph", "economy.build_merchant_route_graph")

    original_init = ab.AgentBridge.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._sim = _TimedNative(self._sim)

    ab.AgentBridge.__init__ = init


def _child(opts: argparse.Namespace) -> dict:
    os.environ.setdefault("CHRONICLER_QUIET", "1")
    import chronicler.main as cm
    from chronicler.utils import sync_civ_population

    if opts.target:
        original_generate = cm.generate_world

        def scaled_generate(*args, **kwargs):
            world = original_generate(*args, **kwargs)
            mult = opts.target / max(1, sum(r.population for r in world.regions))
            for region in world.regions:
                region.carrying_capacity = max(1, round(region.carrying_capacity * mult))
                region.population = round(region.population * mult)
            for civ in world.civilizations:
                sync_civ_population(civ, world)
            return world

        cm.generate_world = scaled_generate

    if not opts.no_instrument:
        instrument(opts.depth)
        import gc
        gc.callbacks.append(PROF.gc_callback)

    out_dir = Path(tempfile.mkdtemp(prefix="turn-prof-", dir=opts.run_root))
    argv = [
        "--seed", str(opts.seed), "--turns", str(opts.warmup + opts.turns),
        "--agents", opts.agents, "--simulate-only",
        "--output", str(out_dir / "chronicle.md"), "--state", str(out_dir / "state.json"),
    ]
    argv += ["--regions", str(opts.regions), "--civs", str(opts.civs),
             "--reflection-interval", "10"]
    if opts.worldgen:
        argv += ["--worldgen", opts.worldgen]
    argv += list(opts.cli_arg)
    args = cm._build_parser().parse_args(argv)
    args.tuning_overrides = {}

    marks: list[tuple[float, float]] = []
    alive: list[int] = []

    def on_turn(*_):
        marks.append((time.perf_counter(), _cpu()))
        if len(marks) == opts.warmup:
            PROF.rows.clear()
            PROF.enabled = True

    import chronicler.agent_bridge as ab
    bridges = []
    init = ab.AgentBridge.__init__

    def keep(self, *a, **k):
        init(self, *a, **k)
        bridges.append(self)

    ab.AgentBridge.__init__ = keep

    def on_turn_alive(*a):
        if bridges:
            try:
                alive.append(int(getattr(bridges[0]._sim, "last_tick_alive")))
            except Exception:
                pass
        on_turn(*a)

    if opts.warmup == 0:
        PROF.enabled = True
    start = (time.perf_counter(), _cpu())
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            cm.execute_run(args, on_turn=on_turn_alive)
    finally:
        PROF.enabled = False
        if opts.keep_run:
            print(f"run kept in {out_dir}", file=sys.stderr)
        else:
            shutil.rmtree(out_dir, ignore_errors=True)
    end = (time.perf_counter(), _cpu())

    all_marks = [start] + marks
    turn_cpu = [b[1] - a[1] for a, b in zip(all_marks, all_marks[1:])]
    turn_wall = [b[0] - a[0] for a, b in zip(all_marks, all_marks[1:])]
    measured_cpu = turn_cpu[opts.warmup:]
    measured_wall = turn_wall[opts.warmup:]
    # The last measured turn ends at its on_turn; anything after (final save,
    # bundle) is outside the window and not in the rows either.
    window = sum(measured_cpu)
    rows = [
        {"parent": p, "label": l, "calls": v[0], "incl": v[1], "excl": v[2]}
        for (p, l), v in PROF.rows.items()
    ]
    accounted = sum(r["excl"] for r in rows)
    rows.append({"parent": "turn", "label": "main.loop", "calls": len(measured_cpu),
                 "incl": window - accounted, "excl": window - accounted})
    return {
        "argv": argv,
        "target": opts.target,
        "warmup": opts.warmup,
        "turns": opts.turns,
        "rayon_threads": os.environ.get("RAYON_NUM_THREADS", "default"),
        "alive_measured": alive[opts.warmup:],
        "turn_cpu": measured_cpu,
        "turn_wall": measured_wall,
        "window_cpu": window,
        "window_wall": sum(measured_wall),
        "run_cpu": end[1] - start[1],
        "run_wall": end[0] - start[0],
        "rows": rows,
    }


def report(data: dict, top: int = 40) -> str:
    n = max(1, data["turns"])
    window = data["window_cpu"]
    excl: dict[str, float] = defaultdict(float)
    calls: dict[str, int] = defaultdict(int)
    for r in data["rows"]:
        excl[r["label"]] += r["excl"]
        calls[r["label"]] += r["calls"]
    lines = [
        f"turns {data['turns']} (after {data['warmup']} warm-up), alive "
        f"{statistics.median(data['alive_measured']) if data['alive_measured'] else 'n/a'}, "
        f"rayon {data['rayon_threads']}",
        f"turn CPU median {statistics.median(data['turn_cpu']) * 1e3:.1f} ms, "
        f"mean {window / n * 1e3:.1f} ms; wall mean {data['window_wall'] / n * 1e3:.1f} ms",
        f"{'exclusive CPU':<48} {'ms/turn':>9} {'share':>7} {'calls/turn':>11}",
    ]
    for label, value in sorted(excl.items(), key=lambda kv: -kv[1])[:top]:
        lines.append(f"{label:<48} {value / n * 1e3:9.2f} {100 * value / window:6.1f}% "
                     f"{calls[label] / n:11.1f}")
    return "\n".join(lines)


def _parse(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--target", type=int, default=0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--regions", type=int, default=8, help="CLI default 8")
    p.add_argument("--civs", type=int, default=4, help="CLI default 4")
    p.add_argument("--worldgen", default=None, choices=["auto", "template", "procedural"])
    p.add_argument("--agents", default="hybrid",
                   choices=["off", "demographics-only", "shadow", "hybrid"])
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--turns", type=int, default=8)
    p.add_argument("--depth", type=int, default=2, help="levels of callees below run_turn_result")
    p.add_argument("--no-instrument", action="store_true", help="time whole turns only")
    p.add_argument("--cli-arg", action="append", default=[],
                   help="extra CLI argument (repeatable, e.g. --cli-arg=--validation-sidecar)")
    p.add_argument("--run-root", type=Path, default=Path(tempfile.gettempdir()))
    p.add_argument("--keep-run", action="store_true")
    p.add_argument("--source-root", type=Path, default=None)
    p.add_argument("--native-root", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--report", type=Path, default=None, help="print the report of a saved JSON")
    p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(argv=None) -> int:
    opts = _parse(argv)
    if opts.report:
        print(report(json.loads(opts.report.read_text()), opts.top))
        return 0
    if (opts.source_root or opts.native_root) and not opts.child:
        env = dict(os.environ)
        paths = [str(p.resolve()) for p in (opts.native_root,) if p]
        if opts.source_root:
            paths.append(str((opts.source_root / "src").resolve()))
        env["PYTHONPATH"] = os.pathsep.join(paths + [env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
        cmd = [sys.executable, str(Path(__file__).resolve()), "--child",
               *[a for a in (argv if argv is not None else sys.argv[1:])]]
        return subprocess.call(cmd, env=env)
    opts.run_root.mkdir(parents=True, exist_ok=True)
    data = _child(opts)
    if opts.out:
        opts.out.parent.mkdir(parents=True, exist_ok=True)
        opts.out.write_text(json.dumps(data, indent=1) + "\n")
    print(report(data, opts.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
