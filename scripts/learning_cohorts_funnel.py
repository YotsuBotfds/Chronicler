"""L5 learning cohorts: development activation funnel on template seeds.

    python scripts/learning_cohorts_funnel.py run OUT_DIR [--seeds 1,2,3] [--turns 200] [--jobs 2]
    python scripts/learning_cohorts_funnel.py report OUT_DIR/funnel.jsonl
    python scripts/learning_cohorts_funnel.py constructed [--turns 30]

Run with the native interpreter whose extension matches the source under test.
Arms per world: ``services`` (academy services only), ``learn`` and
``no_learning`` (the cost-retaining control), all hybrid with cities,
scholarship, techniques and academy services. Development seeds only; raw
output is deleted after extraction. Worlds are the units.

``constructed`` replays the native tests' declared-academy control (seed-42
world, a declared academy at a Scholar region, a 100-craft market, a
500-coin treasury and a declared exogenous restock of 20 crafts a turn) in
both modes, in process, and prints its funnel and the consumer read-outs.
It demonstrates the mechanism; it is not a natural-world result.
"""
import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PY = sys.executable
REPO = str(Path(__file__).resolve().parents[1])
BASE = ["--civs", "4", "--regions", "8", "--agents", "hybrid", "--simulate-only",
        "--cities", "--scholarship", "--techniques", "--academy-services"]
ARMS = {"services": [], "learn": ["--learning-cohorts"],
        "no_learning": ["--learning-cohorts", "--learning-cohort-mode", "no_learning"]}


def _strip(snapshot: dict) -> dict:
    return {k: v for k, v in snapshot.items() if k != "livelihoods"}


def extract(bundle_path: Path) -> dict:
    sys.path.insert(0, f"{REPO}/src")
    from chronicler.bundle_codec import load_bundle
    b = load_bundle(bundle_path)
    hist = b["history"]
    seats = ((b["world_state"].get("scholarship") or {}).get("seats") or [])
    academies = [s for s in seats if s.get("kind") == 0]
    out = {"turns": len(hist), "academies_founded": len(academies),
           "academy_turns_live": sum(max(0, (s.get("fallen_turn") or len(hist)) - s["founded_turn"]) for s in academies)}
    delivered = supplied = 0
    for snap in hist:
        services = ((snap.get("scholarship") or {}).get("learning_services") or {})
        for r in services.get("teaching_receipts") or []:
            if r.get("work_delivered"):
                delivered += 1
        for r in services.get("procurement_receipts") or []:
            if r.get("purchased"):
                supplied += 1
    out["academy_turns_teaching_delivered"] = delivered
    out["academy_purchase_turns"] = supplied
    record = None
    first_completion = None
    for snap in hist:
        lc = (snap.get("livelihoods") or {}).get("learning_cohorts")
        if lc is None:
            continue
        record = lc
        if first_completion is None and lc["counters"].get("completions"):
            first_completion = lc["source_turn"]
    if record is not None:
        out["counters"] = record["counters"]
        out["first_completion_turn"] = first_completion
        out["graduates"] = record["graduates"]
        out["parameters"] = record["parameters"]
    out["history"] = [_strip(s) for s in hist]
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


def compare(rows: list[dict]) -> list[dict]:
    """Per world: where learn and no_learning first differ, and civ stat gaps after."""
    by = {(r["seed"], r["arm"]): r for r in rows}
    out = []
    for seed in sorted({r["seed"] for r in rows}):
        learn, control, services = by.get((seed, "learn")), by.get((seed, "no_learning")), by.get((seed, "services"))
        if not learn or not control:
            continue
        diverge = next((i for i, (a, b) in enumerate(zip(learn["history"], control["history"])) if a != b), None)
        gaps = {"military": 0, "economy": 0, "culture": 0}
        turns_differing = 0
        for a, b in zip(learn["history"], control["history"]):
            if a == b:
                continue
            turns_differing += 1
            for civ, stats in a["civ_stats"].items():
                other = b["civ_stats"].get(civ)
                if other:
                    for k in gaps:
                        gaps[k] += abs(stats.get(k, 0) - other.get(k, 0))
        identical_off = None
        if services is not None:
            first_cohort = next((i for i, (a, b) in enumerate(zip(services["history"], learn["history"])) if a != b), None)
            identical_off = first_cohort
        lc, nc = learn.get("counters", {}), control.get("counters", {})
        out.append({
            "seed": seed,
            "academies_founded": learn["academies_founded"], "academy_turns_live": learn["academy_turns_live"],
            "academy_purchase_turns": learn["academy_purchase_turns"],
            "academy_turns_teaching_delivered": learn["academy_turns_teaching_delivered"],
            "cohorts_formed": lc.get("cohorts_formed", 0), "learners_enrolled": lc.get("learners_enrolled", 0),
            "learner_turns_reserved": lc.get("learner_turns_reserved", 0),
            "sessions": lc.get("sessions", 0), "learner_turns_attended": lc.get("learner_turns_attended", 0),
            "attendance_income_charged": round(lc.get("attendance_income_charged", 0.0), 6),
            "completions": lc.get("completions", 0), "capability_changes": lc.get("capability_changes", 0),
            "skill_granted": round(lc.get("skill_granted", 0.0), 6),
            "control_capability_changes": nc.get("capability_changes", 0),
            "first_completion_turn": learn.get("first_completion_turn"),
            "learn_vs_control_first_divergence": diverge,
            "learn_vs_control_turns_differing": turns_differing,
            "learn_vs_control_civ_stat_abs_gap": gaps,
            "services_vs_learn_first_divergence": identical_off,
            "exits": {k[5:]: v for k, v in lc.items() if k.startswith("exit_")},
            "no_session": {k[11:]: v for k, v in lc.items() if k.startswith("no_session_")},
        })
    return out


def constructed(turns: int) -> dict:
    sys.path.insert(0, f"{REPO}/src")
    import pyarrow as pa
    from chronicler.action_engine import ActionEngine
    from chronicler.agent_bridge import AgentBridge
    from chronicler.cities import set_cities_enabled
    from chronicler.learning_services import set_learning_services_enabled
    from chronicler.livelihoods import configure_livelihoods
    from chronicler.main import _build_parser
    from chronicler.scholarship_state import ACADEMY, ScholarshipState, Seat
    from chronicler.simulation import run_turn_result
    from chronicler.world_gen import generate_world

    def arm(mode):
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        world.agent_mode = "hybrid"
        set_cities_enabled(world, True)
        bridge = AgentBridge(world, mode="hybrid")
        rows = pa.record_batch(bridge._sim.get_snapshot()).to_pylist()
        person = next(r for r in rows if r["occupation"] == 3 and r["age"] >= 20
                      and world.regions[r["region"]].controller is not None)
        region = person["region"]
        owner = world.civ_index_map[world.regions[region].controller]
        for r in world.regions:
            r.stockpile.goods = {"grain": 100.0}
        world.regions[region].stockpile.goods["crafts"] = 100.0
        world.civilizations[owner].treasury = 500
        world.scholarship = ScholarshipState(seats=[Seat(region=region, kind=ACADEMY, name="Declared Academy",
                                                         founded_turn=0, founder=owner, lord=owner)])
        set_learning_services_enabled(world, True)
        configure_livelihoods(world, _build_parser().parse_args(
            ["--learning-cohorts", "--learning-cohort-mode", mode]), agent_mode="hybrid")
        return world, bridge, region

    arms = {mode: arm(mode) for mode in ("learn", "no_learning")}
    first_diff = None
    purpose_gap = []
    for _ in range(turns):
        for world, bridge, region in arms.values():
            goods = world.regions[region].stockpile.goods
            goods["crafts"] = goods.get("crafts", 0.0) + 20.0
            engine = ActionEngine(world)
            run_turn_result(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                            lambda w, events: "", seed=world.seed + world.turn, agent_bridge=bridge)
        (lw, lb, _), (nw, nb, _) = arms["learn"], arms["no_learning"]
        a, b = lw.model_dump(mode="json"), nw.model_dump(mode="json")
        a.pop("livelihoods"), b.pop("livelihoods")
        if first_diff is None and a != b:
            first_diff = lw.turn - 1
        ln = {r["agent_id"]: r for r in pa.record_batch(lb._sim.get_all_needs()).to_pylist()}
        nn = {r["agent_id"]: r for r in pa.record_batch(nb._sim.get_all_needs()).to_pylist()}
        grads = [g.agent_id for g in lw.livelihoods.learning_cohorts.graduates]
        both = [g for g in grads if g in ln and g in nn]
        if both:
            purpose_gap.append((lw.turn - 1, round(sum(ln[g]["purpose"] - nn[g]["purpose"] for g in both) / len(both), 6),
                                len(both)))
    out = {}
    for mode, (world, bridge, _) in arms.items():
        state = world.livelihoods.learning_cohorts
        out[mode] = {"counters": state.counters, "graduates": len(state.graduates),
                     "first_completion": min((g.completed_turn for g in state.graduates), default=None)}
        bridge.close()
    out["first_world_divergence_turn"] = first_diff
    out["graduate_mean_purpose_gap_by_turn"] = purpose_gap
    return out


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
    con = sub.add_parser("constructed")
    con.add_argument("--turns", type=int, default=30)
    args = ap.parse_args(argv)
    if args.cmd == "constructed":
        print(json.dumps(constructed(args.turns), sort_keys=True, indent=1))
        return 0
    if args.cmd == "run":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        seeds = [int(s) for s in args.seeds.split(",")]
        if any(s >= 100 for s in seeds):
            raise SystemExit("development seeds only (held cohorts are not inspected)")
        jobs = [(seed, arm) for seed in seeds for arm in ARMS]
        with ThreadPoolExecutor(max_workers=min(args.jobs, 2)) as pool:
            rows = list(pool.map(lambda job: run_one(out, job[0], job[1], args.turns), jobs))
        funnel = compare(rows)
        with open(out / "funnel.jsonl", "w") as fh:
            for row in funnel:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
        graduates = {f"{r['seed']}_{r['arm']}": r.get("graduates", []) for r in rows if r["arm"] != "services"}
        (out / "graduates.json").write_text(json.dumps(graduates, sort_keys=True, indent=1))
        args.path = str(out / "funnel.jsonl")
    for line in open(args.path):
        print(line.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
