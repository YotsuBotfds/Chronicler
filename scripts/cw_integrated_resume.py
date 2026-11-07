"""Plan and run enabled exact resume at observed CW6 FULL lifecycle states.

Plan requires a real integrated pilot bundle. Run uses the existing identity
comparator and preserves explicit missing lifecycle coverage. Neither command
uses held seeds. No execution starts merely from importing this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checkpoint_identity as CI
import cw_integrated_screen as CW

KINDS = ("army_meal_or_requisition", "war_injury_or_release", "moving_timber_escrow",
         "paid_infrastructure_work", "dated_health_report_or_guard", "personal_a6_memory", "x1_displacement")


def transition_points(bundle):
    """Return completed-turn checkpoints whose *saved states* really activated.

    This reads records only; it does not alter source worlds to force events.
    First occurrences and category priority are deterministic and preregistered.
    """
    found = {}
    for snap in bundle.get("history") or []:
        turn = snap["turn"]
        lv = snap.get("livelihoods") or {}
        d4 = (lv.get("war_requisition") or {}).get("frame") or {}
        active_army = any((e.get("kind") == "consumption" and e.get("demanded_rations", 0) > 0)
                         or (e.get("kind") in ("requisition", "cargo_seizure") and e.get("removed_milli", 0) > 0)
                         for e in d4.get("events") or [])
        d3 = (lv.get("war_consequences") or {}).get("frame") or {}
        active_injury = any(e.get("kind") in ("wounded", "released") for e in d3.get("events") or [])
        orders = lv.get("timber_orders") or {}
        moving = any(o.get("status") == "moving" and o.get("cargo_milli", 0) > 0 and o.get("cash", 0) > 0
                     for o in orders.get("orders") or [])
        infrastructure = lv.get("infrastructure_condition") or {}
        paid_work = any(r.get("delivered", 0) > 0 and any(m.get("worked", 0) > 0 and m.get("wages_milli", 0) > 0
                        for m in r.get("members") or []) for r in infrastructure.get("receipts") or [])
        ph = lv.get("public_health") or {}
        pending_reports = any(r.get("delivery", -1) > turn - 1 for r in ph.get("reports") or [])
        guards = any(member.get("wage_paid_milli", 0) > 0
                     for team in ph.get("guards") or [] for member in team.get("members") or [])
        a6 = (lv.get("adaptive_livelihoods") or {}).get("frame") or {}
        personal = any(a6.get(key) for key in ("work", "refusals", "quick_departures", "trade")) or a6.get("rows_installed", 0) > 0
        x1 = ((lv.get("residence_ledger") or {}).get("frame") or {}).get("totals") or {}
        active = (active_army, active_injury, moving, paid_work, pending_reports or guards, personal, x1.get("displaced", 0) > 0)
        for kind, yes in zip(KINDS, active, strict=True):
            if yes and kind not in found:
                found[kind] = turn
    # Keep one active checkpoint per category, then before/after coverage at
    # the first military meal and first escrowed moving shipment, at most nine.
    last = len(bundle.get("history") or [])
    points = {turn for turn in found.values() if 0 < turn < last}
    for kind in ("army_meal_or_requisition", "moving_timber_escrow"):
        turn = found.get(kind)
        if turn is not None and 0 < turn - 1 < last:
            points.add(turn - 1)
    return {"categories": found, "missing": [kind for kind in KINDS if kind not in found], "ks": sorted(points),
            "not_resumable": [kind for kind, turn in found.items() if turn not in points]}


def cli_for(stratum, seed):
    cli = list(CW.BASE)
    i = cli.index("--turns")
    del cli[i:i + 2]
    cli.remove("--simulate-only")  # run_case adds the simulator-only outputs.
    cli += list(CW.ARMS["FULL"][0]) + ["--seed", str(seed)]
    if stratum == "procedural":
        cli += list(CW.SCREEN.procedural)
    return cli


def make_plan(bundle_path, stratum, seed):
    path = Path(bundle_path).resolve()
    bundle = CW.load_bundle_file(path)
    validate_pilot_world(bundle, stratum, seed)
    if len(bundle.get("history") or []) != 200 or bundle.get("metadata", {}).get("total_turns") != 200:
        raise ValueError("active resume selection requires the complete 200-turn integrated pilot")
    metrics, problems = CW.extract(bundle, CW.ARMS["FULL"][0])
    if problems:
        raise ValueError("cannot choose resume transitions from invalid pilot: " + "; ".join(problems))
    return {"schema_version": 1, "stratum": stratum, "seed": seed, "turns": metrics["turns"],
            "bundle": str(path), "bundle_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "event_sidecar": metrics["event_sidecar"],
            "source_identity": CW.SR.source_identity(CW.SCREEN), "transitions": transition_points(bundle),
            "cli": cli_for(stratum, seed), "comparator": "checkpoint_identity.run_case / cities_identity.compare"}


def validate_pilot_world(bundle, stratum, seed):
    if (stratum, seed) not in (("template", 5), ("procedural", 19)):
        raise ValueError("CW6 resume plans use registered timing pilots template5/procedural19 only")
    world = bundle.get("world_state") or {}
    metadata = bundle.get("metadata") or {}
    if metadata.get("seed") != seed or world.get("seed") != seed:
        raise ValueError("pilot bundle metadata/world seed differs from requested resume world")
    expected_regions = 8 if stratum == "template" else 32
    geography = world.get("geography")
    if len(world.get("regions") or []) != expected_regions or (geography is not None) != (stratum == "procedural"):
        raise ValueError("pilot bundle geography/region count differs from requested resume stratum")


def run_plan(plan_path, output):
    plan = json.loads(Path(plan_path).read_text())
    if plan.get("schema_version") != 1 or not plan.get("transitions", {}).get("ks"):
        raise ValueError("resume plan has no valid active transition checkpoints")
    if CW.SR.identity_key(plan["source_identity"]) != CW.SR.identity_key(CW.SR.source_identity(CW.SCREEN)):
        raise ValueError("resume source/extension/runner/registry identity differs from the real pilot plan")
    bundle_path = Path(plan["bundle"])
    if not bundle_path.is_file() or hashlib.sha256(bundle_path.read_bytes()).hexdigest() != plan["bundle_sha256"]:
        raise ValueError("pilot bundle used to choose transitions is missing or changed")
    validate_plan_configuration(plan, CW.load_bundle_file(bundle_path))
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("resume output already exists; preserve it and choose a new output path")
    if shutil.disk_usage(output.parent).free < 2 * 1024**3:
        raise ValueError("resume refuses to start with less than 2GiB available disk")
    output.mkdir(parents=True)
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    (output / "source.txt").write_text("\n".join(plan["source_identity"]) + "\n")
    name = f"cw6_full_{plan['stratum']}{plan['seed']}"
    CI.CASES[name] = (plan["cli"], plan["turns"], 0, "spread")
    # One process at a time throughout; do not contend with native builds or
    # change the 110-second offline-test budget to hide resource contention.
    report = CI.run_case(output, name, ks=plan["transitions"]["ks"], jobs=1, extra=[], keep=False, resume_hash_seed="0")
    report["active_transitions"] = plan["transitions"]
    report["bundle_sha256"] = plan["bundle_sha256"]
    report["event_sidecar"] = plan["event_sidecar"]
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def validate_plan_configuration(plan, bundle):
    validate_pilot_world(bundle, plan.get("stratum"), plan.get("seed"))
    if plan.get("cli") != cli_for(plan["stratum"], plan["seed"]):
        raise ValueError("resume plan CLI differs from the exact declared FULL pilot configuration")
    if plan.get("turns") != 200 or len(bundle.get("history") or []) != 200 \
            or bundle.get("metadata", {}).get("total_turns") != 200:
        raise ValueError("resume plan does not describe the complete 200-turn integrated pilot")
    if plan.get("transitions") != transition_points(bundle):
        raise ValueError("resume plan selected transitions differ from the actual pilot states")
    sidecar = plan.get("event_sidecar")
    if not isinstance(sidecar, dict) or sidecar.get("present") is not True or sidecar != bundle.get("_cw6_events"):
        raise ValueError("resume plan event sidecar identity differs from the validated pilot")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("plan")
    p.add_argument("bundle")
    p.add_argument("output")
    p.add_argument("--stratum", choices=("template", "procedural"), required=True)
    p.add_argument("--seed", type=int, required=True)
    r = commands.add_parser("run")
    r.add_argument("plan")
    r.add_argument("output")
    args = parser.parse_args(argv)
    if args.command == "plan":
        output = Path(args.output)
        if output.exists():
            parser.error("plan output already exists; preserve the previous evidence")
        output.write_text(json.dumps(make_plan(args.bundle, args.stratum, args.seed), indent=2) + "\n")
        return 0
    return 0 if run_plan(args.plan, args.output).get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
