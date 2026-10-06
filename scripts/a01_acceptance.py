"""A01 capture/compare harness for existing Python regression fixtures or saved inputs.

Run this same driver in separate processes against reviewed baseline and candidate.
Native continuation and native-state reconstruction are deliberately unsupported.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
import gc
import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from unittest.mock import patch
import weakref

BASELINE = "2ab3b4814abb665c7b3d5c255152cf5767bbf25a"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def first_difference(left, right, path="root"):
    if type(left) is not type(right):
        return path
    if isinstance(left, dict):
        # Preserve insertion order because it can affect later reductions.
        if list(left) != list(right):
            return path + ".keys/order"
        for key in left:
            found = first_difference(left[key], right[key], f"{path}.{key}")
            if found:
                return found
    elif isinstance(left, list):
        if len(left) != len(right):
            return path + ".length"
        for index, (a, b) in enumerate(zip(left, right)):
            found = first_difference(a, b, f"{path}[{index}]")
            if found:
                return found
    elif isinstance(left, float) and left.hex() != right.hex():
        return path
    elif left != right:
        return path
    return None


def _jsonl_difference(left, right):
    # Do not load whole RNG traces into memory; stop at the first difference.
    from itertools import zip_longest
    with left.open() as a, right.open() as b:
        for index, (x, y) in enumerate(zip_longest(a, b)):
            if x != y:
                if x is None or y is None:
                    return {"record": index, "path": "trace.length"}
                return {"record": index, "path": first_difference(json.loads(x), json.loads(y)) or "encoding/bytes"}
    return None


def compare(before_dir, after_dir, *, expected_candidate_head=None):
    before = json.loads((before_dir / "report.json").read_text())
    after = json.loads((after_dir / "report.json").read_text())
    problems = []
    if before["identity"]["head"] != BASELINE or before["identity"].get("dirty"):
        problems.append({"path": "baseline.head", "reason": "requires reviewed 2ab3b48 baseline"})
    if after["identity"].get("dirty"):
        problems.append({"path": "candidate.dirty", "reason": "requires a clean committed candidate"})
    if expected_candidate_head is not None and after["identity"]["head"] != expected_candidate_head:
        problems.append({"path": "candidate.head", "reason": "candidate differs from the requested commit"})
    for arm, report in (("baseline", before), ("candidate", after)):
        for key, committed in (("source_sha256", "committed_source_sha256"),
                               ("native_source_sha256", "committed_native_source_sha256")):
            if report["identity"][key] != report["identity"][committed]:
                problems.append({"path": arm + "." + key, "reason": arm + " bytes differ from its Git tree"})
    for key in ("input", "environment", "driver_sha256", "runtime"):
        found = first_difference(before[key], after[key], key)
        if found:
            problems.append({"path": found})
    found = first_difference(before["identity"]["native_source_sha256"],
                             after["identity"]["native_source_sha256"], "native_source_sha256")
    if found:
        problems.append({"path": found})
    for directory, report in ((before_dir, before), (after_dir, after)):
        actual = {str(p.relative_to(directory / "artifacts")):
                  {"bytes": p.stat().st_size, "sha256": digest(p.read_bytes())}
                  for p in sorted((directory / "artifacts").rglob("*")) if p.is_file()}
        if actual != report["artifacts"]:
            problems.append({"path": "capture.artifacts", "directory": str(directory),
                             "reason": "captured files differ from recorded manifest"})
    for name in ("turns.jsonl", "narrator.jsonl", "rng.jsonl"):
        found = _jsonl_difference(before_dir / name, after_dir / name)
        if found:
            problems.append({"artifact": name, **found})
    for name in sorted(before["artifacts"].keys() | after["artifacts"].keys()):
        a, b = before["artifacts"].get(name), after["artifacts"].get(name)
        if a != b:
            item = {"artifact": name, "path": "bytes/sha256"}
            if a is not None and b is not None and name.endswith(".json"):
                left = json.loads((before_dir / "artifacts" / name).read_text())
                right = json.loads((after_dir / "artifacts" / name).read_text())
                item["path"] = first_difference(left, right) or "encoding/bytes"
            problems.append(item)
    a, b = before.get("checkpoint"), after.get("checkpoint")
    if a is not None or b is not None:
        if a is None or b is None or a["status"] != "PASS" or b["status"] != "PASS":
            problems.append({"path": "checkpoint.status", "reason": "both within-source split arms must PASS"})
        elif a["turn_digests"] != b["turn_digests"]:
            problems.append({"path": first_difference(a["turn_digests"], b["turn_digests"], "checkpoint.turn_digests")})
    # Doubles can establish runner parity only, never integrated acceptance.
    return {"exact_comparison_passed": not problems,
            "integrated_python_off_acceptance": not problems and not before["test_doubles"] and not after["test_doubles"],
            "integrated_acceptance": False,
            "integration_scope": "Full A01 acceptance requires native phase-10/dataflow evidence; this harness covers Python off only",
            "native_acceptance": "BLOCKED: no exact native build/admitted in-process input in this harness",
            "first_divergence": problems[0] if problems else None, "differences": problems,
            "baseline_identity": before["identity"], "candidate_identity": after["identity"],
            "baseline_metrics": before["metrics"], "candidate_metrics": after["metrics"]}


class DecodeTrace:
    """Read-only C-call observer; never wraps Arrow batches or native producers.

    Records real native get_snapshot calls and Arrow to_pylist calls. Resolve
    columns by buffer identity against batches already present in caller frames.
    Ambiguous/unavailable identity is explicit, never guessed. Buffer addresses
    and object IDs are local diagnostics, not cross-process equivalence fields.
    """
    def __init__(self, source):
        self.source = source
        self.calls = []
        self.batches = {}
        self.next_batch = 0

    def _batch_token(self, batch):
        old = self.batches.get(id(batch))
        if old is None or old[0]() is not batch:
            old = (weakref.ref(batch), self.next_batch)
            self.next_batch += 1
            self.batches[id(batch)] = old
        return old[1]

    @staticmethod
    def _buffers(array):
        return (str(array.type), len(array), array.offset,
                tuple(None if b is None else (b.address, b.size) for b in array.buffers()))

    def observe(self, frame, event, value):
        if event != "c_call":
            return
        name = getattr(value, "__name__", "")
        if name not in ("to_pylist", "get_snapshot"):
            return
        if "chronicler" not in frame.f_code.co_filename:
            return
        record = {"operation": name, "caller": frame.f_code.co_name,
                  "file": Path(frame.f_code.co_filename).name, "line": frame.f_lineno,
                  "source_turn": None, "stage": "unresolved", "batch": None}
        cursor = frame
        batches = []
        seen = set()
        import pyarrow as pa
        while cursor is not None:
            world = cursor.f_locals.get("world")
            if record["source_turn"] is None and world is not None and hasattr(world, "turn"):
                record["source_turn"] = world.turn
            for local in cursor.f_locals.values():
                stamp = getattr(local, "stamp", None) if type(local).__name__ == "AgentRows" else None
                if stamp is not None:
                    record.update(source_turn=stamp.source_turn, stage=stamp.stage)
                    local = local.batch
                if isinstance(local, pa.RecordBatch) and id(local) not in seen:
                    batches.append(local)
                    seen.add(id(local))
            cursor = cursor.f_back
        if name == "to_pylist":
            array = getattr(value, "__self__", None)
            if isinstance(array, pa.Array):
                record["elements"] = len(array)
                signature = self._buffers(array)
                matches = []
                for batch in batches:
                    for index, column in enumerate(batch.column_names):
                        if self._buffers(batch.column(index)) == signature:
                            matches.append((batch, column))
                if len(matches) == 1:
                    batch, column = matches[0]
                    record.update(batch=self._batch_token(batch), column=column,
                                  rows=batch.num_rows, schema=str(batch.schema))
                else:
                    record["identity_status"] = "ambiguous" if matches else "unavailable"
        self.calls.append(record)

    @contextmanager
    def active(self):
        if sys.getprofile() is not None:
            raise RuntimeError("dataflow observer requires no existing Python profiler")
        sys.setprofile(self.observe)
        try:
            yield
        finally:
            sys.setprofile(None)


def capture(args):
    source = args.source_root.resolve()
    sys.path[:0] = [str(source / "src"), str(source)]
    if args.test_doubles:
        # The plugin fails if real upstream slices have arrived.
        sys.path.insert(0, str(Path(__file__).parent))
        import a01_test_doubles  # noqa: F401
    from chronicler import main as runner
    from chronicler import checkpoint_replay as replay
    from chronicler.models import WorldState
    from chronicler.world_gen import generate_world
    from scripts.benchmark_headless import FixedDateTime, rng_trace
    from chronicler.narrative import NarrativeEngine

    if args.fixture:
        fixture = source / "tests/fixtures/performance/corrected_423a67c.json"
        spec = json.loads(fixture.read_text())["workloads"][args.fixture]["spec"]
        initial = generate_world(seed=spec["seed"], num_civs=spec["civs"], num_regions=spec["regions"])
        turns = spec["turns"]
        input_id = {"kind": "existing regression fixture", "name": args.fixture,
                    "fixture_sha256": digest(fixture.read_bytes()), "spec": spec}
    else:
        payload = args.state.read_bytes()
        initial = WorldState.model_validate_json(payload)
        turns = args.turns
        if turns is None or turns < 1:
            raise ValueError("--state requires positive --turns")
        input_id = {"kind": "existing saved input", "sha256": digest(payload),
                    "bytes": len(payload), "turns": turns}
    input_id["initial_state_sha256"] = digest(initial.model_dump_json().encode())
    replay._require_supported(initial, replay.RUNTIME)
    if runner._create_ecology_runtime(initial) is not None or runner._create_politics_runtime(initial) is not None:
        raise ValueError("native off-mode runtime is installed; this Python-only lane is unavailable")
    if args.split is not None and not 0 <= args.split < turns:
        raise ValueError("require 0 <= split < turns")
    args.report_dir.mkdir(parents=True, exist_ok=False)
    environment = {"python": sys.version, "platform": platform.platform(),
                   "packages": dict(sorted((d.metadata["Name"], d.version) for d in distributions()
                                           if d.metadata["Name"].lower() != "chronicler"))}
    source_hashes = {str(p.relative_to(source)): digest(p.read_bytes())
                     for p in sorted((source / "src/chronicler").rglob("*.py"))}
    native_hashes = {str(p.relative_to(source)): digest(p.read_bytes())
                     for p in sorted((source / "chronicler-agents").rglob("*"))
                     if p.is_file() and "target" not in p.parts and (p.suffix == ".rs" or p.name in ("Cargo.toml", "Cargo.lock"))}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True)

    def committed_hashes(paths):
        result = {}
        # Hash Git object bytes independently of working-tree status flags.
        entries = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=source, text=True)
        tracked = set(entries.splitlines())
        for name in sorted(set(paths) | {name for name in tracked if
                (name.startswith("src/chronicler/") and name.endswith(".py")) or
                (name.startswith("chronicler-agents/") and
                 (name.endswith(".rs") or Path(name).name in ("Cargo.toml", "Cargo.lock")))}):
            relevant = name.startswith("src/chronicler/") if paths is source_hashes else name.startswith("chronicler-agents/")
            if relevant and name in tracked:
                result[name] = digest(subprocess.check_output(["git", "show", "HEAD:" + name], cwd=source))
        return result

    committed_source = committed_hashes(source_hashes)
    committed_native = committed_hashes(native_hashes)
    metrics = {"callback_live_views": [], "snapshot_span_seconds": []}
    trace = DecodeTrace(source)

    def live_views():
        # Does not keep object references after return; class name supports doubles.
        return sum(type(o).__name__ == "AgentRows" for o in gc.get_objects())

    def run(folder, turn_log=None, narrator_log=None, measured=False):
        namespace = argparse.Namespace(
            seed=initial.seed, turns=initial.turn + turns,
            civs=len(initial.civilizations), regions=len(initial.regions),
            output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
            resume=None, reflection_interval=10, llm_actions=False,
            scenario=None, simulate_only=False, agents="off",
        )
        span = []
        seam = "run_turn_result" if hasattr(runner, "run_turn_result") else "run_turn"
        original = getattr(runner, seam)

        def tick(*a, **kw):
            result = original(*a, **kw)
            if measured:
                span.append(time.perf_counter())
            return result

        def narrate(_engine, world, events):
            data = {"source_turn": world.turn, "world": world.model_dump(mode="json"),
                    "events": [e.model_dump(mode="json") for e in events]}
            if narrator_log is not None:
                narrator_log.write(encoded(data) + "\n")
            return encoded({"turn": world.turn, "events": data["events"]})

        world = initial.model_copy(deep=True)

        def callback(snapshot, text, events, named):
            if measured:
                metrics["snapshot_span_seconds"].append(time.perf_counter() - span.pop())
            if turn_log is not None:
                turn_log.write(encoded({"snapshot": snapshot.model_dump(mode="json"), "text": text,
                                       "events": [e.model_dump(mode="json") for e in events],
                                       "named_events": [e.model_dump(mode="json") for e in named],
                                       "world": world.model_dump(mode="json")}) + "\n")
                metrics["callback_live_views"].append(live_views())
        with open(os.devnull, "w") as sink, redirect_stdout(sink), \
                patch("chronicler.bundle.datetime", FixedDateTime), \
                patch.object(NarrativeEngine, "narrator", narrate), patch.object(runner, seam, tick):
            runner.execute_run(namespace, world=world, on_turn=callback)

    # Warmed, untraced timing with identical inputs, including artifact I/O.
    with tempfile.TemporaryDirectory(prefix="a01-timing-") as temporary:
        temporary = Path(temporary)
        run(temporary / "warm")
        timings = []
        for index in range(args.repetitions):
            gc.collect()
            start = time.perf_counter()
            run(temporary / str(index), measured=True)
            timings.append(time.perf_counter() - start)
        gc.collect()
        tracemalloc.start()
        run(temporary / "allocation")
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    metrics.update(whole_run_seconds=timings, median_seconds=statistics.median(timings),
                   allocated_current_bytes=current, peak_tracemalloc_bytes=peak,
                   rss_peak_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                   end_live_views=live_views())
    with (args.report_dir / "turns.jsonl").open("w") as turns_log, \
            (args.report_dir / "narrator.jsonl").open("w") as narrator_log, \
            rng_trace(args.report_dir / "rng.jsonl") as rng, trace.active():
        run(args.report_dir / "artifacts", turns_log, narrator_log)
    (args.report_dir / "dataflow.json").write_text(json.dumps(trace.calls, indent=2) + "\n")
    metrics.update(column_decode_calls=sum(c["operation"] == "to_pylist" for c in trace.calls),
                   decoded_elements=sum(c.get("elements", 0) for c in trace.calls),
                   native_snapshot_calls=sum(c["operation"] == "get_snapshot" for c in trace.calls),
                   dataflow_scope="Python off-mode: no phase-10 native rows; native metrics unavailable")
    artifacts = {str(p.relative_to(args.report_dir / "artifacts")):
                 {"bytes": p.stat().st_size, "sha256": digest(p.read_bytes())}
                 for p in sorted((args.report_dir / "artifacts").rglob("*")) if p.is_file()}
    checkpoint = None
    if args.split is not None:
        checkpoint = replay.validate_replay(initial, turns=turns, split=args.split,
                                           checkpoint_path=args.report_dir / "checkpoint.json")
    report = {"schema": 1, "identity": {"head": head, "dirty": dirty,
              "source_sha256": source_hashes, "native_source_sha256": native_hashes,
              "committed_source_sha256": committed_source, "committed_native_source_sha256": committed_native,
              "runtime_identity": replay._runtime_identity()}, "input": input_id,
              "environment": environment, "driver_sha256": digest(Path(__file__).read_bytes()),
              "runtime": "Python off; native ecology/politics absent; deterministic narrator",
              "test_doubles": args.test_doubles,
              "test_double_sha256": digest((Path(__file__).parent / "a01_test_doubles.py").read_bytes()) if args.test_doubles else None,
              "metrics": metrics, "rng": rng,
              "artifacts": artifacts, "checkpoint": checkpoint,
              "native_coverage": "BLOCKED: native binary and admitted in-process inputs unavailable"}
    (args.report_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return {"report": str(args.report_dir / "report.json"), "test_doubles": args.test_doubles}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("capture")
    run.add_argument("--source-root", type=Path, required=True)
    inputs = run.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--state", type=Path)
    inputs.add_argument("--fixture", choices=("single", "standard", "wide"))
    run.add_argument("--turns", type=int)
    run.add_argument("--split", type=int)
    run.add_argument("--report-dir", type=Path, required=True)
    run.add_argument("--repetitions", type=int, default=3, choices=range(1, 6))
    run.add_argument("--test-doubles", action="store_true")
    diff = commands.add_parser("compare")
    diff.add_argument("--baseline", type=Path, required=True)
    diff.add_argument("--candidate", type=Path, required=True)
    diff.add_argument("--expected-candidate-head", help="Pin comparison to an exact reviewed candidate commit")
    args = parser.parse_args()
    try:
        result = capture(args) if args.command == "capture" else compare(
            args.baseline, args.candidate, expected_candidate_head=args.expected_candidate_head)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"A01 evidence error: {exc}\n")
    print(json.dumps(result, indent=2))
    return 0 if args.command == "capture" or result["exact_comparison_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
