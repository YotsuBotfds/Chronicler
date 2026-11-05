"""Livelihoods sprint screens: run the preregistered arms and summarize them.

    python scripts/livelihoods_screens.py run OUT_DIR [--seeds template|procedural|all] [--jobs 3] [--arms a,b]
    python scripts/livelihoods_screens.py report OUT_DIR/metrics.jsonl

Run with the native interpreter whose extension matches the source under test
(the arms are hybrid). Arms, cohorts and outcomes are preregistered in
docs/superpowers/progress/livelihoods-sprint1-screens.md; worlds are the units.
Each run's raw output is deleted after extraction, except the first seed of
each stratum (kept as an example world). Metrics go to OUT_DIR/metrics.jsonl.
"""
import argparse, json, os, shutil, subprocess, sys, time
from statistics import mean
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PY = sys.executable
REPO = str(Path(__file__).resolve().parents[1])
BASE = ["--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves", "--public-grain-shipments"]
ARMS = {
    "off": [],
    "L1_operate": ["--workshops"],
    "L1_cost_only": ["--workshops", "--workshop-mode", "cost_only"],
    "L2_floor_means": ["--food-allocation"],
    "L2_targeted": ["--food-allocation", "--food-allocation-regime", "targeted_relief"],
    "L3_timber": ["--timber-stock"],
    "L3_ablation": ["--timber-stock", "TUNING_NO_CAP"],
    "L4_convoys": ["--grain-convoys"],
    "I1_work_food": ["--workshops", "--food-allocation"],
    "I2_timber_work": ["--workshops", "--timber-stock"],
    "I3_convoy_relief": ["--grain-convoys", "--food-allocation", "--food-allocation-regime", "targeted_relief"],
    "ALL": ["--workshops", "--food-allocation", "--timber-stock", "--grain-convoys"],
}
STRATA = {"template": [("t", s, []) for s in range(101, 107)],
          "procedural": [("p", s, ["--worldgen", "procedural", "--regions", "32", "--civs", "10"]) for s in range(201, 207)]}


def metrics(bundle_path: Path) -> dict:
    sys.path.insert(0, f"{REPO}/src")
    from chronicler.bundle_codec import load_bundle
    b = load_bundle(bundle_path)
    hist = b["history"]
    last = hist[-1]
    m = {"turns": len(hist),
         "population": sum(v["population"] for v in last["civ_stats"].values()),
         "treasury": sum(v["treasury"] for v in last["civ_stats"].values()),
         "alive_civs": sum(1 for v in last["civ_stats"].values() if v.get("population", 0) > 0)}
    regions = b["world_state"]["regions"]
    m["crafts_stock_end"] = sum(r.get("stockpile", {}).get("goods", {}).get("crafts", 0.0) for r in regions)
    m["timber_goods_end"] = sum(r.get("stockpile", {}).get("goods", {}).get("timber", 0.0) for r in regions)
    w = {"site_turns": 0, "operating": 0, "building": 0, "idle": 0, "alloc": 0.0, "real": 0.0, "out": 0.0, "paid": 0}
    f = {"scarce": 0, "short": 0.0, "sp": 0.0, "pp": 0, "sr": 0.0, "pr": 0, "sc": 0.0, "pc": 0, "relief_t": 0.0, "unalloc": 0.0}
    t = {"extraction": 0.0, "regrowth": 0.0, "cleared": 0.0, "overdraft": 0.0, "capped": 0, "stock_end": None, "cap_end": None}
    for s in hist:
        liv = s.get("livelihoods") or {}
        ws = liv.get("workshops")
        for r in (ws or {}).get("receipts") or []:
            w["site_turns"] += 1; w["alloc"] += r["allocated"]; w["real"] += r["realized"]
            w["out"] += r["region_craft_output"] or 0.0; w["paid"] += sum((r.get("paid") or {}).values())
            if r.get("craft_ceiling"): w["operating"] += 1
            if (r.get("paid") or {}).get("construction"): w["building"] += 1
            if r.get("asset") == "idle": w["idle"] += 1
        fa = liv.get("food_allocation")
        for r in (fa or {}).get("regions") or []:
            f["scarce"] += 1; f["short"] += r["shortfall"]; f["sp"] += r["shortfall_poorer_half"]; f["pp"] += r["people_poorer_half"]
            f["sr"] += r["shortfall_richer_half"]; f["pr"] += r["people_richer_half"]; f["sc"] += r["shortfall_children"]
            f["pc"] += r["children"]; f["relief_t"] += r["relief_to_targeted"]; f["unalloc"] += r["unallocated"]
        ts = liv.get("timber_stock")
        if ts and ts.get("totals"):
            tt = ts["totals"]
            for k in ("extraction", "regrowth", "cleared", "overdraft"): t[k] += tt[k]
            t["capped"] += tt["capped_slots"]; t["stock_end"] = tt["stock"]; t["cap_end"] = tt["capacity"]
    if any(s.get("livelihoods", {}).get("workshops") for s in hist): m["workshops"] = w
    if any(s.get("livelihoods", {}).get("food_allocation") for s in hist): m["food"] = f
    if any(s.get("livelihoods", {}).get("timber_stock") for s in hist): m["timber"] = t
    gc = (last.get("livelihoods") or {}).get("grain_convoys")
    if gc: m["convoys"] = gc["counters"]
    return m


def run(out: Path, arm: str, stratum: str, seed: int, extra: list[str], keep: bool) -> dict:
    d = (out / "runs" / f"{arm}-{stratum}{seed}").resolve()
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    flags = list(ARMS[arm])
    if "TUNING_NO_CAP" in flags:
        flags.remove("TUNING_NO_CAP")
        (d / "tuning.yaml").write_text("livelihoods:\n  timber:\n    enforce_cap: 0\n")
        flags += ["--tuning", str(d / "tuning.yaml")]
    cmd = [PY, "-m", "chronicler.main", "--seed", str(seed), *BASE, *extra, *flags,
           "--output", str(d / "chronicle.md"), "--state", str(d / "state.json")]
    env = dict(os.environ, PYTHONHASHSEED="0", RAYON_NUM_THREADS="1", CHRONICLER_QUIET="1")
    t0 = time.time()
    p = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True)
    row = {"arm": arm, "stratum": stratum, "seed": seed, "rc": p.returncode, "wall_s": round(time.time() - t0, 1)}
    if p.returncode != 0:
        row["error"] = p.stderr[-2000:]
    else:
        row.update(metrics(d / "chronicle_bundle.json"))
    if not keep:
        shutil.rmtree(d)
    return row


def run_main(argv):
    ap = argparse.ArgumentParser(prog="livelihoods_screens.py run")
    ap.add_argument("out"); ap.add_argument("--seeds", default="all"); ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--arms", default=",".join(ARMS))
    a = ap.parse_args(argv)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    strata = list(STRATA) if a.seeds == "all" else [a.seeds]
    jobs = []
    for name in strata:
        for i, (tag, seed, extra) in enumerate(STRATA[name]):
            for arm in a.arms.split(","):
                jobs.append((arm, tag, seed, extra, i == 0))
    t0 = time.time()
    with open(out / "metrics.jsonl", "a") as fh, ThreadPoolExecutor(a.jobs) as ex:
        for row in ex.map(lambda j: run(out, *j), jobs):
            fh.write(json.dumps(row) + "\n"); fh.flush()
            print(row["arm"], row["stratum"], row["seed"], row["rc"], row["wall_s"], flush=True)
    print("total wall", round(time.time() - t0, 1))


def report_main(argv):
    rows = [json.loads(l) for l in open(argv[0])]

    by = {(r["arm"], r["stratum"], r["seed"]): r for r in rows}
    arms = list(dict.fromkeys(r["arm"] for r in rows))
    strata = {"t": "template 8x4 (seeds 101-106)", "p": "procedural 32x10 (seeds 201-206)"}
    fails = [r for r in rows if r["rc"] != 0]
    out = []
    out.append(f"Runs: {len(rows)}; failed: {len(fails)}; wall seconds total {sum(r['wall_s'] for r in rows):.0f}")
    for f in fails:
        out.append(f"- FAILED {f['arm']} {f['stratum']}{f['seed']}: {f.get('error','')[-300:]}")


    def rng(vals):
        return f"{mean(vals):+.1f} [{min(vals):+.0f}, {max(vals):+.0f}]" if vals else "n/a"


    out.append("\n### Paired differences vs off (mean [min, max] over worlds)\n")
    out.append("| Arm | Stratum | Worlds | Population | Treasury |")
    out.append("| --- | --- | --- | --- | --- |")
    for arm in arms:
        if arm == "off":
            continue
        for s in strata:
            seeds = sorted({r["seed"] for r in rows if r["stratum"] == s})
            dp, dt = [], []
            for seed in seeds:
                a, o = by.get((arm, s, seed)), by.get(("off", s, seed))
                if a and o and a["rc"] == 0 and o["rc"] == 0:
                    dp.append(a["population"] - o["population"]); dt.append(a["treasury"] - o["treasury"])
            out.append(f"| {arm} | {s} | {len(dp)} | {rng(dp)} | {rng(dt)} |")

    out.append("\n### Activation funnels and primary outcomes (sum or mean per world)\n")
    for s in strata:
        out.append(f"\n**{strata[s]}**\n")
        for arm in arms:
            rs = [r for r in rows if r["arm"] == arm and r["stratum"] == s and r["rc"] == 0]
            if not rs:
                continue
            parts = []
            if any("workshops" in r for r in rs):
                w = [r["workshops"] for r in rs]
                act = sum(1 for x in w if x["operating"] > 0)
                parts.append(f"workshops: worlds operating {act}/{len(w)}, site-turns {mean(x['site_turns'] for x in w):.0f}, "
                             f"operating {mean(x['operating'] for x in w):.0f}, building {mean(x['building'] for x in w):.0f}, "
                             f"idle {mean(x['idle'] for x in w):.0f}, work alloc/real {mean(x['alloc'] for x in w):.1f}/{mean(x['real'] for x in w):.1f}, "
                             f"site-region craft out {mean(x['out'] for x in w):.1f}, paid {mean(x['paid'] for x in w):.0f}")
            if any("food" in r for r in rs):
                f = [r["food"] for r in rs]
                sp = sum(x["sp"] for x in f) / max(1, sum(x["pp"] for x in f))
                sr = sum(x["sr"] for x in f) / max(1, sum(x["pr"] for x in f))
                sc = sum(x["sc"] for x in f) / max(1, sum(x["pc"] for x in f))
                poorer_worse = sum(1 for x in f if x["pp"] and x["pr"] and x["sp"] / x["pp"] > x["sr"] / x["pr"])
                parts.append(f"food: scarce region-turns/world {mean(x['scarce'] for x in f):.0f}, mean shortfall poorer {sp:.3f} vs richer {sr:.3f} "
                             f"(poorer worse in {poorer_worse}/{len(f)} worlds), children {sc:.3f}, relief to targeted/world {mean(x['relief_t'] for x in f):.2f}, "
                             f"unallocated/world {mean(x['unalloc'] for x in f):.1f}")
            if any("timber" in r for r in rs):
                t = [r["timber"] for r in rs]
                parts.append(f"timber: extraction/world {mean(x['extraction'] for x in t):.1f}, regrowth {mean(x['regrowth'] for x in t):.1f}, "
                             f"cleared {mean(x['cleared'] for x in t):.1f}, overdraft {mean(x['overdraft'] for x in t):.3f}, "
                             f"capped slot-turns {mean(x['capped'] for x in t):.1f} (worlds binding {sum(1 for x in t if x['capped'])}/{len(t)})")
            if any("convoys" in r for r in rs):
                c = [r["convoys"] for r in rs]
                keys = ("eligible", "no_budget", "unaffordable", "dispatched", "arrived", "delivered", "captured", "lost", "returned", "stranded", "escorted", "escort_wasted")
                parts.append("convoys (sum over worlds): " + ", ".join(f"{k} {sum(x.get(k, 0) for x in c):.0f}" for k in keys))
            if parts:
                out.append(f"- {arm}: " + "; ".join(parts))
    print("\n".join(out))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("run", "report") or argv[1:2] in (["-h"], ["--help"]) and argv[0] == "report":
        print(__doc__)
        return 0 if argv[1:2] in (["-h"], ["--help"]) or not argv else 2
    if argv[0] == "run":
        run_main(argv[1:])
    else:
        report_main(argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
