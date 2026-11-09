"""L7 relocation costs: development funnel on template seeds.

    python scripts/archive/relocation_costs_funnel.py run OUT_DIR [--seeds 1,2,3] [--turns 200] [--jobs 2]
    python scripts/archive/relocation_costs_funnel.py report OUT_DIR/funnel.jsonl

Run with the native interpreter whose extension matches the source under
test. Arms per world: ``off``, ``paid``, ``assisted``, ``liquidity_only``
(the control) and ``assisted_food`` (assisted with ``--food-allocation``, for
the arrivals' rations). Development seeds only; raw output is deleted after
extraction. Worlds are the units.
"""
import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PY = sys.executable
REPO = str(Path(__file__).resolve().parents[2])
BASE = ["--civs", "4", "--regions", "8", "--agents", "hybrid", "--simulate-only"]
ARMS = {
    "off": [],
    "paid": ["--relocation-costs"],
    "assisted": ["--relocation-costs", "--relocation-mode", "assisted"],
    "liquidity_only": ["--relocation-costs", "--relocation-mode", "liquidity_only"],
    "assisted_food": ["--relocation-costs", "--relocation-mode", "assisted", "--food-allocation"],
}


def extract(bundle_path: Path) -> dict:
    sys.path.insert(0, f"{REPO}/src")
    from chronicler.bundle_codec import load_bundle
    b = load_bundle(bundle_path)
    hist = b["history"]
    last = hist[-1]
    out = {"turns": len(hist),
           "population": sum(v["population"] for v in last["civ_stats"].values()),
           "treasury": sum(v["treasury"] for v in last["civ_stats"].values())}
    gate: dict[str, int] = {}
    worse = relief = 0
    worse_example = relief_example = None
    ration = {"arrivals": 0, "arrivals_sum": 0.0, "residents": 0, "residents_sum": 0.0}
    record = None
    for snap in hist:
        rc = (snap.get("livelihoods") or {}).get("relocation_costs")
        if not rc:
            continue
        record = rc
        for k, v in (rc["gate"] or {}).items():
            gate[k] = gate.get(k, 0) + v
        for row in rc["regions"] or []:
            if row["arrivals"] and row["pressure_after"] is not None and row["pressure_after"] > row["pressure_before"] > 0 and row["pressure_after"] > 1:
                worse += 1
                worse_example = worse_example or {"turn": rc["source_turn"], **row}
            if row["departures"] and row["pressure_before"] is not None and row["pressure_before"] > 1 and row["pressure_after"] < row["pressure_before"]:
                relief += 1
                relief_example = relief_example or {"turn": rc["source_turn"], **row}
        for s in rc["services"] or []:
            if s["arrivals_rationed"]:
                ration["arrivals"] += s["arrivals_rationed"]
                ration["arrivals_sum"] += s["arrivals_mean_ration"] * s["arrivals_rationed"]
            if s["residents_rationed"]:
                ration["residents"] += s["residents_rationed"]
                ration["residents_sum"] += s["residents_mean_ration"] * s["residents_rationed"]
    if record is not None:
        out.update(counters=record["counters"], gate=gate, congestion_worsened_region_turns=worse,
                   origin_relieved_region_turns=relief, congestion_example=worse_example,
                   relief_example=relief_example)
        if ration["arrivals"]:
            out["arrivals_mean_ration"] = round(ration["arrivals_sum"] / ration["arrivals"], 4)
            out["residents_mean_ration"] = round(ration["residents_sum"] / max(1, ration["residents"]), 4)
            out["rationed_arrival_observations"] = ration["arrivals"]
    return out


def run_one(out_dir: Path, seed: int, arm: str, turns: int) -> dict:
    d = out_dir / f"t{seed}_{arm}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    cmd = [PY, "-m", "chronicler.main", "--seed", str(seed), "--turns", str(turns), *BASE, *ARMS[arm],
           "--output", str(d / "chronicle.md"), "--state", str(d / "state.json")]
    env = {"PYTHONHASHSEED": "0", "PATH": "/usr/bin:/bin", "PYTHONPATH": f"{REPO}/src"}
    proc = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{seed} {arm} failed:\n{proc.stderr[-3000:]}")
    row = extract(d / "chronicle_bundle.json")
    shutil.rmtree(d)
    return {"seed": seed, "arm": arm, **row}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("out")
    run.add_argument("--seeds", default="1,2,3")
    run.add_argument("--turns", type=int, default=200)
    run.add_argument("--jobs", type=int, default=2)
    rep = sub.add_parser("report")
    rep.add_argument("path")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        seeds = [int(s) for s in args.seeds.split(",")]
        if any(s >= 100 for s in seeds):
            raise SystemExit("development seeds only (held cohorts are not inspected)")
        jobs = [(seed, arm) for seed in seeds for arm in ARMS]
        with ThreadPoolExecutor(max_workers=min(args.jobs, 2)) as pool:
            rows = list(pool.map(lambda job: run_one(out, job[0], job[1], args.turns), jobs))
        with open(out / "funnel.jsonl", "w") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
        args.path = str(out / "funnel.jsonl")
    for line in open(args.path):
        print(line.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
