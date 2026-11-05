"""L9 local budgets: development evidence driver (template seeds 1-3, procedural seed 7).

    python docs/integration/local-budgets-evidence/driver.py run OUT [--jobs 2] [--groups base,providers,procedural,constructed]

Run with the native interpreter whose extension matches the source under test
(every arm is hybrid). Each run's raw output is deleted after its metrics are
extracted to OUT/metrics.jsonl (one row per arm and seed); the raw bundles are
reproducible from the fixed seeds. docs/integration/local-budgets.md reports
the rows. Groups:

* ``base``: the part-1 arms on template seeds 1-3, 200 turns, with
  ``--grain-reserves --grain-storage --workshops --food-allocation``: L9 off,
  bargained, fixed shares, targeted relief, and a 0.03 envelope share.
* ``providers``: every switch the registered providers need (academy services,
  workshop payroll, timber stock, commons rules) on template seeds 1-3: L9
  off, bargained and fixed shares.
* ``procedural``: the providers' switch set plus ``--grain-convoys``, on
  procedural seed 7 (32 regions x 10 civilizations): bargained and fixed shares.
* ``constructed``: paired CONSTRUCTED cases on template seed 3. Each is the
  real simulation except one named intervention (a budget and two voices'
  influence set for one civilization at one decision and restored right
  after, or a treasury seized before Phase 2). The natural twin runs too, and
  the row records the first snapshot where the two differ.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PY = sys.executable
REPO = Path(__file__).resolve().parents[3]
TEMPLATE = ["--civs", "4", "--regions", "8", "--reflection-interval", "10"]
PROCEDURAL = ["--worldgen", "procedural", "--regions", "32", "--civs", "10", "--reflection-interval", "10"]
HYBRID = ["--agents", "hybrid", "--simulate-only"]
BASE = ["--grain-reserves", "--grain-storage", "--workshops", "--food-allocation"]
PROVIDERS = ["--grain-reserves", "--public-grain-shipments", "--scholarship", "--techniques", "--academy-services",
             "--workshops", "--workshop-payroll", "--timber-stock", "--commons-rules", "--food-allocation"]
SHARE03 = {"livelihoods.budgets.envelope_share": 0.03}

GROUPS = {
    "base": [(arm, seed, TEMPLATE + BASE + flags, tuning, 200)
             for seed in (1, 2, 3)
             for arm, flags, tuning in (
                 ("off", [], None),
                 ("bargained", ["--local-budgets"], None),
                 ("fixed_shares", ["--local-budgets", "--local-budget-mode", "fixed_shares"], None),
                 ("targeted", ["--local-budgets", "--food-allocation-regime", "targeted_relief"], None),
                 ("share03", ["--local-budgets"], SHARE03))],
    "providers": [(arm, seed, TEMPLATE + PROVIDERS + flags, None, 200)
                  for seed in (1, 2, 3)
                  for arm, flags in (("prov_off", []), ("prov_bargained", ["--local-budgets"]),
                                     ("prov_fixed_shares", ["--local-budgets", "--local-budget-mode", "fixed_shares"]))],
    "procedural": [(arm, 7, PROCEDURAL + PROVIDERS + ["--grain-convoys", "--grain-storage"] + flags, None, 200)
                   for arm, flags in (("proc_bargained", ["--local-budgets"]),
                                      ("proc_fixed_shares", ["--local-budgets", "--local-budget-mode", "fixed_shares"]))],
}
#: Constructed cases: (name, natural arm flags, tuning, turns, intervention).
CONSTRUCTED = [
    ("relief_first_91", BASE + ["--local-budgets"], SHARE03, 110, {"budget": [91, 0, 3, 0.6, 0.1]}),
    ("production_first_91", BASE + ["--local-budgets"], SHARE03, 110, {"budget": [91, 0, 3, 0.1, 0.6]}),
    ("budget_loss_91", BASE + ["--local-budgets"], None, 100, {"seize": [91, 0]}),
]


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------

def _command(seed, flags, out: Path, tuning, turns):
    cmd = [PY, "-m", "chronicler.main", "--seed", str(seed), "--turns", str(turns), *HYBRID, *flags,
           "--output", str(out / "chronicle.md"), "--state", str(out / "state.json")]
    if tuning:
        lines = []
        for key, value in tuning.items():
            parts = key.split(".")
            lines.append("\n".join("  " * i + p + ":" for i, p in enumerate(parts[:-1]))
                         + "\n" + "  " * (len(parts) - 1) + f"{parts[-1]}: {value}")
        (out / "tuning.yaml").write_text("\n".join(lines) + "\n")
        cmd += ["--tuning", str(out / "tuning.yaml")]
    return cmd


def _env():
    return dict(os.environ, PYTHONHASHSEED="0", RAYON_NUM_THREADS="1", CHRONICLER_QUIET="1",
                PYTHONPATH=str(REPO / "src"))


def _load(path):
    sys.path.insert(0, str(REPO / "src"))
    from chronicler.bundle_codec import load_bundle
    return load_bundle(path)


def spending(hist) -> dict:
    """Governed spending observed in the services' own receipts."""
    out = {"workshop": 0, "crew_work": 0.0, "storage": 0, "storage_work": 0.0, "relief": 0, "relief_grain": 0.0,
           "wardens": 0, "warden_coverage_turns": 0, "teaching": 0, "teaching_crafts": 0.0,
           "poorer_half_shortfall": 0.0}
    for snap in hist:
        liv = snap.get("livelihoods") or {}
        for r in (liv.get("workshops") or {}).get("receipts") or []:
            out["workshop"] += sum((r.get("paid") or {}).values())
            out["crew_work"] += r.get("allocated") or 0.0
        res = snap.get("grain_reserves") or {}
        for r in (res.get("storage") or {}).get("receipts") or []:
            if r["turn"] == res.get("source_turn"):
                out["storage"] += r["treasury_paid"]
                out["storage_work"] += r["delivered"]
        for f in res.get("flows") or []:
            if f["kind"] in ("bought", "dispatched"):
                out["relief"] += f["cost"] or 0
                out["relief_grain"] += f["amount"]
        for r in (liv.get("commons_rules") or {}).get("receipts") or []:
            out["wardens"] += r["paid"]
            out["warden_coverage_turns"] += r["coverage"] > 0
        for r in (liv.get("workshop_payroll") or {}).get("receipts") or []:
            out["teaching"] += r["sales"] // 1000
            out["teaching_crafts"] += r["sold"] / 1000
        for r in (liv.get("food_allocation") or {}).get("regions") or []:
            out["poorer_half_shortfall"] += r["shortfall_poorer_half"]
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in out.items()}


def budgets(hist) -> dict | None:
    if not any((s.get("livelihoods") or {}).get("local_budgets") for s in hist):
        return None
    props, awards, outcomes, settled, refused = {}, {}, {}, {}, {}
    raised = eased = 0
    for snap in hist:
        x = snap["livelihoods"]["local_budgets"]
        for d in x["decisions"] or []:
            outcomes[d["outcome"]] = outcomes.get(d["outcome"], 0) + 1
            for p in d["proposals"]:
                props[p["service"]] = props.get(p["service"], 0) + 1
            for a in d["awards"]:
                s = d["proposals"][a["pid"]]["service"]
                awards[s] = awards.get(s, 0) + 1
            for pid, why in d["refused"]:
                key = f'{d["proposals"][pid]["service"]}:{why}'
                refused[key] = refused.get(key, 0) + 1
        for c in x["settled"] or []:
            key = f'{c["service"]}:{c["outcome"]}:{c["reason"]}'
            settled[key] = settled.get(key, 0) + 1
        for r in x["responses"] or []:
            raised += r["applied"] > 0
            eased += r["applied"] < 0
    last = hist[-1]["livelihoods"]["local_budgets"]
    return {"counters": last["counters"], "proposals": props, "awards": awards, "outcomes": outcomes,
            "settled": settled, "refused": refused, "responses_raised": raised, "responses_eased": eased}


def run_one(out_root: Path, arm, seed, flags, tuning, turns) -> dict:
    d = out_root / "runs" / f"{arm}-s{seed}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    t0 = time.time()
    p = subprocess.run(_command(seed, flags, d, tuning, turns), cwd=REPO, env=_env(), capture_output=True, text=True)
    row = {"arm": arm, "seed": seed, "turns": turns, "flags": flags, "tuning": tuning, "rc": p.returncode,
           "wall_s": round(time.time() - t0, 1)}
    if p.returncode:
        row["error"] = p.stderr[-2000:]
    else:
        hist = _load(d / "chronicle_bundle.json")["history"]
        last = hist[-1]
        row.update(population=sum(v["population"] for v in last["civ_stats"].values()),
                   treasury=sum(v["treasury"] for v in last["civ_stats"].values()),
                   spending=spending(hist), budgets=budgets(hist))
    shutil.rmtree(d)
    return row


# ---------------------------------------------------------------------------
# Constructed cases
# ---------------------------------------------------------------------------

def _constructed_child(out: Path, spec: dict) -> None:
    """In a child process: install the named intervention, then run the CLI."""
    sys.path.insert(0, str(REPO / "src"))
    from chronicler import finance, grain_storage, local_budgets as LB
    from chronicler.models import FactionType
    from chronicler.main import _build_parser, execute_run
    if "budget" in spec:
        turn, civ, coins, commons, patricians = spec["budget"]
        real_decide = LB._decide

        def decide(world, state, obs, providers, acc):
            if world.turn != turn:
                return real_decide(world, state, obs, providers, acc)
            c = world.civilizations[civ]
            saved = dict(c.factions.influence)
            c.factions.influence[FactionType.CULTURAL], c.factions.influence[FactionType.MERCHANT] = commons, patricians
            params = LB._parameters(world)
            reserved = (sum(int(p.obligations(world, civ, obs)) for p in providers)
                        + sum(x.amount for x in state.open if x.civ == civ))
            need = int(params["floor"]) + reserved + int(-(-coins // params["envelope_share"]))
            real_projections = finance._projections

            def projections(w, a):
                values = list(real_projections(w, a))
                values[civ] = need
                return values
            finance._projections = projections
            try:
                return real_decide(world, state, obs, providers, acc)
            finally:
                finance._projections = real_projections
                c.factions.influence.clear()
                c.factions.influence.update(saved)
        LB._decide = decide
    if "seize" in spec:
        turn, civ = spec["seize"]
        real_prepare = grain_storage.prepare_storage_work

        def prepare(world, *a, **k):
            if world.turn == turn:
                world.civilizations[civ].treasury = 0
            return real_prepare(world, *a, **k)
        grain_storage.prepare_storage_work = prepare
    args = _build_parser().parse_args(spec["argv"])
    if getattr(args, "tuning", None):
        from chronicler.tuning import load_tuning
        args.tuning_overrides = load_tuning(Path(args.tuning))      # as main() does
    else:
        args.tuning_overrides = {}
    execute_run(args)


def _at(hist, turn):
    return next(s for s in hist if s["livelihoods"]["local_budgets"]["source_turn"] == turn)


def _decision(hist, turn, civ):
    d = next(x for x in _at(hist, turn)["livelihoods"]["local_budgets"]["decisions"] if x["civ"] == civ)
    svc = lambda pid: d["proposals"][pid]["service"]
    return {"budget": d["budget"], "projected": d["projected"], "influence": d["influence"], "burdens": d["burdens"],
            "outcome": d["outcome"], "own": {k: [[svc(p), a] for p, a in v] for k, v in d["candidates"].items()},
            "awards": [[svc(a["pid"]), a["amount"], a["sponsor"]] for a in d["awards"]],
            "refused": [[svc(p), why] for p, why in d["refused"]],
            "proposals": [[p["service"], p["cost"], p["recipients"]] for p in d["proposals"]]}


def _settled(hist, turn, civ):
    return [[c["service"], c["recipients"], c["amount"], c["spent"], round(c["delivered"], 3), c["outcome"],
             c["reason"], c["response"], c["venue"]]
            for c in _at(hist, turn)["livelihoods"]["local_budgets"]["settled"] or [] if c["civ"] == civ]


def _story(hist, spec) -> dict:
    turn, civ = (spec.get("budget") or spec.get("seize"))[:2]
    decided = turn if "budget" in spec else turn - 1
    out = {"decision": _decision(hist, decided, civ), "settled_next": _settled(hist, decided + 1, civ)}
    s = _at(hist, decided + 1)
    out["responses_next"] = [r for r in s["livelihoods"]["local_budgets"]["responses"] or [] if r["civ"] == civ]
    out["workshop_sites_next"] = [[x["site"], x["region"], x["asset"], x["arrears"], round(x["condition"], 2)]
                                  for x in s["livelihoods"]["workshops"]["sites"]]
    relief = next((p for d in _at(hist, decided)["livelihoods"]["local_budgets"]["decisions"]
                   for p in d["proposals"] if p["service"] == "relief" and p["civ"] == civ), None)
    if relief is not None:
        recips = relief["recipients"]
        rows = []
        for t in range(decided + 1, min(decided + 9, hist[-1]["livelihoods"]["local_budgets"]["source_turn"] + 1)):
            snap = _at(hist, t)
            g = snap["grain_reserves"]["granaries"]
            rows.append({"turn": t, "granary": {str(r): round(g[r]["grain"], 2) for r in recips},
                         "released": [[f["region"], round(f["amount"], 2)] for f in snap["grain_reserves"]["flows"]
                                      if f["kind"] == "released" and f["region"] in recips],
                         "short_poorer_n_richer_n": {str(r["region"]): [round(r["shortfall_poorer_half"], 2),
                                                                        r["people_poorer_half"],
                                                                        round(r["shortfall_richer_half"], 2),
                                                                        r["people_richer_half"]]
                                                     for r in snap["livelihoods"]["food_allocation"]["regions"] or []
                                                     if r["region"] in recips}})
        out["relief_recipients"] = recips
        out["after"] = rows
    return out


def run_constructed(out_root: Path, name, flags, tuning, turns, spec) -> dict:
    row = {"arm": f"constructed:{name}", "seed": 3, "turns": turns, "flags": flags, "tuning": tuning,
           "intervention": spec}
    hists = {}
    t0 = time.time()
    for twin in ("natural", "constructed"):
        d = out_root / "runs" / f"{name}-{twin}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        cmd = _command(3, TEMPLATE + flags, d, tuning, turns)
        if twin == "constructed":
            argv = cmd[cmd.index("chronicler.main") + 1:]
            cmd = [PY, str(Path(__file__).resolve()), "_child", str(d), json.dumps({**spec, "argv": argv})]
        p = subprocess.run(cmd, cwd=REPO, env=_env(), capture_output=True, text=True)
        if p.returncode:
            row.update(rc=p.returncode, error=p.stderr[-2000:])
            shutil.rmtree(d)
            return row
        hists[twin] = _load(d / "chronicle_bundle.json")["history"]
        shutil.rmtree(d)
    a, b = hists["natural"], hists["constructed"]
    row["rc"] = 0
    row["wall_s"] = round(time.time() - t0, 1)
    row["identical_snapshots_before"] = next((i for i in range(len(b)) if a[i] != b[i]), len(b))
    row["natural"], row["constructed"] = _story(a, spec), _story(b, spec)
    return row


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main(argv):
    if argv and argv[0] == "_child":
        _constructed_child(Path(argv[1]), json.loads(argv[2]))
        return
    ap = argparse.ArgumentParser(prog="driver.py")
    ap.add_argument("command", choices=["run"])
    ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--groups", default="base,providers,procedural,constructed")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    groups = a.groups.split(",")
    jobs = [("run", job) for g in groups if g in GROUPS for job in GROUPS[g]]
    if "constructed" in groups:
        jobs += [("constructed", job) for job in CONSTRUCTED]
    t0 = time.time()

    def go(job):
        kind, args = job
        return run_one(out, *args) if kind == "run" else run_constructed(out, *args)

    with open(out / "metrics.jsonl", "a") as fh, ThreadPoolExecutor(a.jobs) as ex:
        for row in ex.map(go, jobs):
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            fh.flush()
            print(row["arm"], row["seed"], row.get("rc"), row.get("wall_s"), flush=True)
    print(f"{len(jobs)} runs in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main(sys.argv[1:])
