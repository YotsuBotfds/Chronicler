#!/usr/bin/env python3
"""One closed raw case: decode/Arrow admission and cost, not a cohort effect."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import resource
import subprocess
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--checkout", type=Path, required=True)
parser.add_argument("--directory", type=Path, required=True)
parser.add_argument("--case", default="AD-p4201")
parser.add_argument("--expected-source", required=True)
parser.add_argument("--receipt", type=Path, required=True)
args = parser.parse_args()
if args.receipt.exists():
    parser.error("receipt exists; preserve it and choose a new path")
resource.setrlimit(resource.RLIMIT_CPU, (20, 22))
start = time.perf_counter()
before = resource.getrusage(resource.RUSAGE_SELF)
receipt = {"kind": "closed-case decode/Arrow admission only", "case": args.case,
           "simulation_runs": 0, "partial_cohort_effect_claim": False, "cpu_limit_seconds": 20}
try:
    source = subprocess.check_output(["git", "-C", str(args.checkout), "rev-parse", "HEAD"], text=True).strip()
    assert source == args.expected_source
    assert not subprocess.check_output(["git", "-C", str(args.checkout), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    sys.path.insert(0, str(args.checkout / "src"))
    assert not any(name.startswith("chronicler_agents") for name in sys.modules)
    from chronicler.bundle_codec import load_bundle
    import chronicler.bundle_codec as codec
    import pyarrow as pa
    import pyarrow.ipc as ipc
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    assert Path(codec.__file__).resolve() == (args.checkout / "src/chronicler/bundle_codec.py").resolve()
    arm, world = args.case.split("-")
    tag, seed = world[0], int(world[1:])
    rows = [json.loads(line) for line in (args.directory / "metrics.jsonl").read_text().splitlines() if line]
    matching = [r for r in rows if (r.get("arm"), r.get("stratum"), r.get("seed")) == (arm, tag, seed)]
    assert len(matching) == 1 and matching[0]["rc"] == 0
    metrics = matching[0]["m"]
    path = args.directory / "runs" / args.case / "chronicle_bundle.json"
    bundle = load_bundle(path)
    history = bundle["history"]
    assert [s["turn"] for s in history] == list(range(1, 121))
    assert bundle["metadata"]["seed"] == bundle["world_state"]["seed"] == seed
    assert bundle["metadata"]["total_turns"] == 120
    regions = len(bundle["world_state"]["regions"])
    assert regions == {"p": 32, "t": 8}[tag]
    shortfalls, epidemic, population = [], [], []
    for turn, snap in enumerate(history):
        food = snap["food_accounting"]
        assert food["source_turn"] == turn and len(food["regions"]) == regions
        for row in food["regions"]:
            demand, suff = row["native"]["demand"], row["sufficiency_after_relief"]
            assert type(demand) in (int, float) and math.isfinite(demand) and demand >= 0
            assert type(suff) in (int, float) and math.isfinite(suff) and suff >= 0
            shortfalls.append(demand * max(0, 1 - min(1, suff)))
        epidemic.append(snap["epidemics"]["deaths"])
        population.append(sum(snap["regional_population"]["counts"]))
    calculated = {"food_shortfall": math.fsum(shortfalls), "epidemic_deaths": sum(epidemic),
                  "person_turns": sum(population)}
    assert calculated["epidemic_deaths"] == history[-1]["epidemics"]["deaths_total"]
    for key, value in calculated.items():
        assert math.isclose(value, metrics[key], rel_tol=1e-11, abs_tol=1e-7), (key, value, metrics[key])
    arrow_path = path.with_name("agent_events.arrow")
    table = ipc.open_file(arrow_path).read_all()
    required = {"turn", "agent_id", "event_type", "region", "target_region", "migration_driver"}
    assert required <= set(table.column_names)
    columns = {name: table[name].to_pylist() for name in required}
    assert all(type(t) is int and 0 <= t < 120 for t in columns["turn"])
    assert all(type(i) is int and 0 <= i < 2**32 for i in columns["agent_id"])
    counts = Counter(columns["event_type"])
    unknown = sum(k == "migration" and d == 255 for k, d in zip(columns["event_type"], columns["migration_driver"]))
    side = metrics["event_sidecar"]
    digest = hashlib.sha256(arrow_path.read_bytes()).hexdigest()
    assert counts["migration"] == metrics["all_migrations"] == side["migration"]
    assert counts["death"] == metrics["deaths"] == side["deaths"]
    assert unknown == metrics["unknown_migration_drivers"] == side["unknown"]
    assert arrow_path.stat().st_size == side["bytes"] and digest == side["sha256"]
    assert not any(name.startswith("chronicler_agents") for name in sys.modules)
    imported = sorted(name for name in sys.modules if name == "chronicler" or name.startswith("chronicler."))
    assert imported == ["chronicler", "chronicler.bundle_codec"], imported
    receipt.update(status="PASS", source=source, codec=codec.__file__, pyarrow=pa.__version__,
                   source_identity=matching[0]["identity"], bundle_bytes=path.stat().st_size,
                   bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   snapshots=len(history), raw_primary_observations=calculated,
                   arrow_events=table.num_rows, event_kinds=dict(counts), arrow_sha256=digest,
                   imported_chronicler_modules=imported, native_module_imported=False,
                   frame_contract_checks="not yet performed; admission only")
except Exception as error:
    receipt.update(status="FAIL", error=f"{type(error).__name__}: {error}")
after = resource.getrusage(resource.RUSAGE_SELF)
receipt.update(wall_seconds=time.perf_counter() - start,
               cpu_user_seconds=after.ru_utime - before.ru_utime,
               cpu_system_seconds=after.ru_stime - before.ru_stime,
               max_single_process_rss_kib=after.ru_maxrss)
args.receipt.parent.mkdir(parents=True, exist_ok=True)
args.receipt.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
print(json.dumps(receipt))
raise SystemExit(0 if receipt["status"] == "PASS" else 1)
