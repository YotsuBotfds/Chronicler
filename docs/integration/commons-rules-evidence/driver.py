"""L8 commons rules: development-cohort evidence driver (template seeds 1-3).

    python docs/integration/commons-rules-evidence/driver.py run OUT [--jobs 2]

Run with the native interpreter whose extension matches the source under test.
Six arms x three seeds, 200 turns, hybrid; each run's raw output is deleted
after its metrics are extracted to OUT/metrics.jsonl (one row per arm and
seed). docs/integration/commons-rules.md section 10 reports them.
"""
import json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PY = sys.executable
REPO = str(Path(__file__).resolve().parents[3])
BASE = ["--turns", "200", "--agents", "hybrid", "--simulate-only"]
ARMS = {
    "timber": ["--timber-stock"],
    "enforced": ["--timber-stock", "--commons-rules"],
    "cost_only": ["--timber-stock", "--commons-rules", "--commons-rule-mode", "cost_only"],
    "ws_timber": ["--workshops", "--timber-stock"],
    "ws_enforced": ["--workshops", "--timber-stock", "--commons-rules"],
    "ws_cost_only": ["--workshops", "--timber-stock", "--commons-rules", "--commons-rule-mode", "cost_only"],
}
SEEDS = (1, 2, 3)


def metrics(path: Path) -> dict:
    sys.path.insert(0, f"{REPO}/src")
    from chronicler.bundle_codec import load_bundle
    b = load_bundle(path)
    hist = b["history"]
    last = hist[-1]
    names = [r["name"] for r in b["world_state"]["regions"]]
    m = {"turns": len(hist),
         "population": sum(v["population"] for v in last["civ_stats"].values()),
         "treasury": sum(v["treasury"] for v in last["civ_stats"].values())}
    # Timber accounts per slot over the whole run.
    slots = {}
    for snap in hist:
        ts = (snap.get("livelihoods") or {}).get("timber_stock")
        for r in (ts or {}).get("regions") or []:
            key = f'{r["region_id"]}:{r["slot"]}'
            s = slots.setdefault(key, {"extraction": 0.0, "regrowth": 0.0, "cleared": 0.0, "capped": 0,
                                       "stock_sum": 0.0, "capacity_sum": 0.0, "turns": 0})
            s["extraction"] += r["extraction"]; s["regrowth"] += r["regrowth"]; s["cleared"] += r["cleared"]
            s["capped"] += bool(r["capped"]); s["stock_sum"] += r["stock"]; s["capacity_sum"] += r["capacity"]
            s["turns"] += 1; s["stock_end"] = r["stock"]; s["capacity_end"] = r["capacity"]
    m["timber"] = slots
    # Region outcomes over the whole run for regions with a timber slot.
    regions = {int(k.split(":")[0]) for k in slots}
    crafts = {names[r]: 0.0 for r in regions}
    for snap in hist:
        for city in (snap.get("cities") or {}).get("cities", []):
            if city["region"] in crafts:
                crafts[city["region"]] += city.get("crafts", 0.0)
    m["city_crafts"] = crafts
    pops = {names[r]: [snap["regional_population"]["counts"][r] for snap in hist if snap.get("regional_population")]
            for r in regions}
    m["region_pop_mean"] = {k: (sum(v) / len(v) if v else None) for k, v in pops.items()}
    # Commons rules.
    cr_last = None
    rec = {"receipts": 0, "rule_turns_by_slot": {}, "craft_output": 0.0, "fim": [], "food": [], "raw_imports": 0.0,
           "extraction": 0.0, "excess": 0.0, "binding": 0, "grievance": 0.0, "first_rule_turn": None,
           "decisions": [], "coverage": [], "neighbour_slots": 0, "neighbour_open_extraction": 0.0}
    for snap in hist:
        cr = (snap.get("livelihoods") or {}).get("commons_rules")
        if cr is None:
            continue
        cr_last = cr
        rec["decisions"] += cr.get("decisions") or []
        for r in cr.get("receipts") or []:
            rec["receipts"] += 1
            key = f'{r["region_id"]}:{r["slot"]}'
            rec["rule_turns_by_slot"][key] = rec["rule_turns_by_slot"].get(key, 0) + 1
            if rec["first_rule_turn"] is None:
                rec["first_rule_turn"] = cr["source_turn"]
            rec["craft_output"] += r["craft_output"] or 0.0
            if r["farmer_income_modifier"] is not None: rec["fim"].append(r["farmer_income_modifier"])
            if r["food_sufficiency"] is not None: rec["food"].append(r["food_sufficiency"])
            rec["raw_imports"] += r["raw_imports"] or 0.0
            rec["extraction"] += r["extraction"]; rec["excess"] += r["excess"]
            rec["binding"] += bool(r["binding"]); rec["grievance"] += r["grievance_added"]
            rec["coverage"].append(r["coverage"])
            rec["neighbour_slots"] += r["neighbour_slots"]; rec["neighbour_open_extraction"] += r["neighbour_open_extraction"]
    if cr_last is not None:
        rec["fim"] = sum(rec["fim"]) / len(rec["fim"]) if rec["fim"] else None
        rec["food"] = sum(rec["food"]) / len(rec["food"]) if rec["food"] else None
        rec["coverage"] = sum(rec["coverage"]) / len(rec["coverage"]) if rec["coverage"] else None
        m["commons"] = {"counters": cr_last["counters"], "rules_end": cr_last["rules"], **rec}
    ws = None
    w = {"out": 0.0, "paid": 0, "real": 0.0}
    for snap in hist:
        ws = (snap.get("livelihoods") or {}).get("workshops")
        for r in (ws or {}).get("receipts") or []:
            w["out"] += r.get("region_craft_output") or 0.0; w["real"] += r.get("realized") or 0.0
            w["paid"] += sum((r.get("paid") or {}).values())
    if any((s.get("livelihoods") or {}).get("workshops") for s in hist):
        m["workshops"] = w
    return m


def run(out: Path, arm: str, seed: int) -> dict:
    d = (out / "runs" / f"{arm}-t{seed}").resolve()
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    cmd = [PY, "-m", "chronicler.main", "--seed", str(seed), *BASE, *ARMS[arm],
           "--output", str(d / "chronicle.md"), "--state", str(d / "state.json")]
    env = dict(os.environ, PYTHONHASHSEED="0", RAYON_NUM_THREADS="1", CHRONICLER_QUIET="1",
               PYTHONPATH=f"{REPO}/src")
    t0 = time.time()
    p = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True)
    row = {"arm": arm, "seed": seed, "rc": p.returncode, "wall_s": round(time.time() - t0, 1)}
    if p.returncode != 0:
        row["error"] = p.stderr[-3000:]
    else:
        row.update(metrics(d / "chronicle_bundle.json"))
    shutil.rmtree(d)
    return row


def main(argv):
    if argv[0] == "run":
        out = Path(argv[1]); out.mkdir(parents=True, exist_ok=True)
        jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 2
        tasks = [(arm, seed) for arm in ARMS for seed in SEEDS]
        t0 = time.time()
        with ThreadPoolExecutor(jobs) as ex:
            rows = list(ex.map(lambda t: run(out, *t), tasks))
        with open(out / "metrics.jsonl", "w") as f:
            for row in rows:
                f.write(json.dumps(row, sort_keys=True) + "\n")
        print(f"{len(rows)} runs, {sum(r['rc'] != 0 for r in rows)} failed, {time.time() - t0:.0f}s wall")


if __name__ == "__main__":
    main(sys.argv[1:])
