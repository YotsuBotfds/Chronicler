#!/usr/bin/env python3
"""Dated retail coverage observations in one closed development pilot case.

Does not infer political ownership from final world_state or granary custody.
Only the frozen bundle codec is imported from Chronicler.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--checkout", type=Path, required=True)
parser.add_argument("--directory", type=Path, required=True)
parser.add_argument("--case", required=True)
parser.add_argument("--receipt", type=Path, required=True)
args = parser.parse_args()
if args.receipt.exists(): parser.error("receipt exists; preserve it")
resource.setrlimit(resource.RLIMIT_CPU, (20, 22))
start, before = time.perf_counter(), resource.getrusage(resource.RUSAGE_SELF)
sys.path.insert(0, str(args.checkout / "src"))
from chronicler.bundle_codec import load_bundle
import chronicler.bundle_codec as codec
assert Path(codec.__file__).resolve() == (args.checkout / "src/chronicler/bundle_codec.py").resolve()
arm, world = args.case.split("-")
tag, seed = world[0], int(world[1:])
rows = [json.loads(s) for s in (args.directory / "metrics.jsonl").read_text().splitlines() if s]
metric = [r for r in rows if (r["arm"], r["stratum"], r["seed"]) == (arm, tag, seed)]
assert len(metric) == 1 and metric[0]["rc"] == 0
path = args.directory / "runs" / args.case / "chronicle_bundle.json"
bundle = load_bundle(path)
assert bundle["metadata"]["seed"] == seed and len(bundle["history"]) == 120
counts, missing = Counter(), []
for snap in bundle["history"]:
    turn = snap["turn"] - 1
    retail = snap["livelihoods"]["household_retail"]
    food = snap["food_accounting"]
    assert retail["source_turn"] == food["source_turn"] == turn and retail["boundary"] == "all"
    retail_rows = {r["region"]: r for r in retail["regions"]}
    for row in food["regions"]:
        rid = row["region_id"]
        if row["native_count"] <= 0 or retail_rows.get(rid, {}).get("provisioning") is not None:
            continue
        record = retail_rows.get(rid)
        intervals = retail.get("intervals", {}).get(str(rid))
        open_interval = any(begin <= turn and (end is None or turn < end) for begin, end in intervals or [])
        closed_now = [r for r in retail["log"] if r["turn"] == turn and r.get("region") == rid and r["kind"] == "pilot_closed"]
        event = {"turn": turn, "region": rid, "phase2_native_count": row["native_count"],
                 "retail_frame_row": "absent" if record is None else "present_without_provisioning",
                 "retail_phase2_record": record is not None and record.get("phase2") is not None,
                 "dated_intervals": intervals, "interval_open_at_turn": open_interval,
                 "dated_pilot_closed_events": closed_now,
                 "public_granary_owner_id": row["public"]["owner_id"] if row.get("public") else None}
        counts[event["retail_frame_row"]] += 1
        counts["interval_open" if open_interval else "no_open_interval"] += 1
        counts["phase2_record" if event["retail_phase2_record"] else "no_phase2_record"] += 1
        counts["closure_same_turn" if closed_now else "no_closure_event_same_turn"] += 1
        missing.append(event)
assert len(missing) == metric[0]["m"]["retail_access_unknown_region_turns"]
assert metric[0]["m"]["retail_access_deficit"] is None if missing else metric[0]["m"]["retail_access_deficit"] is not None
modules = sorted(k for k in sys.modules if k == "chronicler" or k.startswith("chronicler."))
assert modules == ["chronicler", "chronicler.bundle_codec"]
assert not any(k.startswith("chronicler_agents") for k in sys.modules)
after = resource.getrusage(resource.RUSAGE_SELF)
receipt = {"status": "PASS", "case": args.case, "producer_identity": metric[0]["identity"],
           "bundle_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "counts": dict(counts),
           "missing_populated_region_turns": len(missing), "dated_observations": missing,
           "decoder_source": codec.__file__, "native_imported": False, "final_political_ownership_consulted": False,
           "interpretation": "all is the eligibility recipe for qualifying controlled regions; realized enrollment/coverage is dated and can differ. Granary owner is custody, not an inferred political controller. An open interval is a saved observation, not a complete within-turn controller history.",
           "simulation_runs": 0, "cpu_user_seconds": after.ru_utime - before.ru_utime,
           "cpu_system_seconds": after.ru_stime - before.ru_stime, "wall_seconds": time.perf_counter() - start,
           "max_single_process_rss_kib": after.ru_maxrss}
args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps({k: receipt[k] for k in ("status", "case", "missing_populated_region_turns", "counts", "cpu_user_seconds", "cpu_system_seconds")}))
