#!/usr/bin/env python3
"""Run the frozen modest crisis evaluation; preserve neutral and adverse outcomes.

See docs/integration/crisis-held-evaluation-2026-11-03.md. These are new seeds
inside constructed stress families, not scientific or household qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (202, 303, 404)
TURNS = 20
ARMS = {"care": ("care_off", "care_on"), "forecast": ("normal", "shuffle")}
DECLARATION = ROOT / "docs/integration/crisis-held-evaluation-2026-11-03.md"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def normalized_world(world: dict, family: str) -> str:
    """Remove only the predeclared intervention from the opening witness."""
    raw = json.loads(json.dumps(world))
    if family == "care":
        raw["health_care"]["care_enabled"] = False
    elif family == "forecast":
        raw["harvest_forecasts"]["policy"] = "normal"
    else:
        raise ValueError("unknown declared family")
    return sha(json.dumps(raw, sort_keys=True, allow_nan=False).encode())


def initial_world(seed: int, family: str):
    from chronicler.world_gen import generate_world

    regions, civs = (8, 4) if family == "care" else (4, 2)
    world = generate_world(seed=seed, num_regions=regions, num_civs=civs)
    world.agent_mode = "hybrid"
    if family == "care":
        from chronicler.health_care import set_health_care_enabled
        for region in world.regions:
            region.resource_types = [0, 255, 255]
            region.resource_base_yields = [0.05, 0.0, 0.0]
            region.resource_effective_yields = [0.05, 0.0, 0.0]
            region.stockpile.goods = {"grain": 0.0}
            region.ecology.soil = region.ecology.water = 0.2
        set_health_care_enabled(world, True)
        world.health_care.injury_rate = 0.25
        world.health_care.recovery_work = 10.0
        world.health_care.care_enabled = False
    elif family == "forecast":
        # Same finite-resource construction as the forecast development case,
        # with the declared seed replacing its development seed.
        from chronicler.contact_ledger import set_contact_ledger_enabled
        from chronicler.grain_reserves import set_grain_reserves_enabled, _ensure
        from chronicler.grain_storage import enable_storage
        from chronicler.grain_storage_state import StorageAsset
        from chronicler.harvest_forecasts import set_harvest_forecasts_enabled
        from chronicler.transaction_receipts import set_transaction_receipts_enabled
        for ci, civ in enumerate(world.civilizations):
            civ.regions = [world.regions[2 * ci].name, world.regions[2 * ci + 1].name]
            civ.capital_region = world.regions[2 * ci].name
            civ.population = 120
            civ.treasury = 45
        for rid, region in enumerate(world.regions):
            region.controller = world.civilizations[rid // 2].name
            region.population = 60
            region.carrying_capacity = 100
            region.adjacencies = [r.name for j, r in enumerate(world.regions) if j != rid]
            region.stockpile.goods = {"grain": 0.0} if rid == 0 else {"grain": 150.0, "salt": 150.0}
            region.resource_types = [255, 255, 255] if rid == 0 else [0, 255, 255]
            yields = [0.0, 0.0, 0.0] if rid == 0 else [1.8, 0.0, 0.0]
            region.resource_base_yields = list(yields)
            region.resource_effective_yields = list(yields)
            if rid:
                region.ecology.soil = region.ecology.water = 1.0
        set_grain_reserves_enabled(world, True)
        for rid, granary in enumerate(_ensure(world).granaries):
            granary.owner, granary.grain = rid // 2, 0.0
        enable_storage(world).assets = [StorageAsset(capacity=100.0, condition=1.0, owner=rid // 2)
                                         for rid in range(4)]
        set_contact_ledger_enabled(world, True)
        set_harvest_forecasts_enabled(world, True)
        set_transaction_receipts_enabled(world, True)
    else:
        raise ValueError("unknown declared family")
    return world


class StartWitness:
    def __init__(self, directory: Path, family: str):
        self.directory, self.family, self.start = directory, family, None

    def bind(self, save, run_config):
        import numpy as np
        from chronicler.run_checkpoint import read_checkpoint
        checkpoint = read_checkpoint(save(str(self.directory / "start.ckpt")))
        try:
            if not checkpoint.exact or checkpoint.state.world.turn != 0:
                raise RuntimeError("opening checkpoint is not an exact turn-zero state")
            self.start = {
                "normalized_world_sha256": normalized_world(checkpoint.state.world.model_dump(mode="json"), self.family),
                "native_sha256": sha(bytes(checkpoint.state.agent_bridge._sim.checkpoint_state())),
                "python_rng_sha256": sha(pickle.dumps(random.getstate())),
                "numpy_rng_sha256": sha(pickle.dumps(np.random.get_state())),
                "runtime_fields": [key for key in ("agent_bridge", "ecology_runtime", "politics_runtime", "economy_tracker")
                                   if getattr(checkpoint.state, key) is not None],
            }
        finally:
            checkpoint.state.agent_bridge.close()

    def live_record(self):
        return None

    def turn_end(self, world):
        return False


def summarize_history(history: list[dict]) -> dict:
    """Preserve coverage and avoid repeatedly counting cumulative outcomes."""
    from scripts.crisis_distribution_summary import summarize

    if not history:
        raise ValueError("cannot summarize an empty trajectory")
    food = [row.get("food_accounting") for row in history]
    for snapshot, observation in zip(history, food):
        if (observation is None or observation.get("source_turn") != snapshot["turn"] - 1
                or observation.get("completed_turn") != snapshot["turn"]):
            raise ValueError("food observation clock differs from its history snapshot")
    distribution = summarize(food)
    known_means = [row["weighted_mean"] for row in distribution["timeline"] if row["weighted_mean"] is not None]
    care_rows = [row["health_care"] for row in history if isinstance(row.get("health_care"), dict)]
    forecasts = [row["harvest_forecasts"] for row in history if isinstance(row.get("harvest_forecasts"), dict)]
    reserves = [row["grain_reserves"] for row in history if isinstance(row.get("grain_reserves"), dict)]
    native_checked = public_checked = 0
    max_native_relative = max_public_absolute = 0.0
    for frame in food:
        for row in frame["regions"]:
            native = row.get("native")
            if native is not None:
                residual, tolerance = native["balance_residual"], native["balance_tolerance"]
                if not math.isfinite(residual) or not math.isfinite(tolerance) or tolerance <= 0:
                    raise ValueError("invalid native balance evidence")
                max_native_relative = max(max_native_relative, abs(residual) / tolerance)
                native_checked += 1
                if abs(residual) > tolerance:
                    raise ValueError("native food balance exceeded recorded tolerance")
            public = row.get("public")
            if public is not None and public.get("balance_residual") is not None:
                residual = public["balance_residual"]
                if not math.isfinite(residual) or abs(residual) > 1e-7:
                    raise ValueError("public food balance exceeded 1e-7 tolerance")
                max_public_absolute = max(max_public_absolute, abs(residual))
                public_checked += 1
    outcomes = {}
    for frame in forecasts:
        for row in frame.get("outcomes", []):
            if row.get("brier") is not None:
                key = row["id"]
                # Outcomes are cumulative dated observations, not new samples.
                evidence = {k: row.get(k) for k in ("id", "probability", "outcome_shortfall", "brier", "resolved_turn")}
                if key in outcomes and outcomes[key] != evidence:
                    raise ValueError("resolved forecast evidence changed between snapshots")
                outcomes[key] = evidence
    final_counters = forecasts[-1].get("counters", {}) if forecasts else {}
    metrics = {
        "final_weighted_sufficiency": distribution["timeline"][-1]["weighted_mean"],
        "mean_turn_weighted_sufficiency": math.fsum(known_means) / len(known_means) if known_means else None,
        "deficit_region_turns": sum(r["weighted"] and r["sufficiency"] < 1
                                    for row in distribution["timeline"] for r in row["regions"]),
        "care_worker_turns": math.fsum(row.get("care_work", 0.0) for row in care_rows) if care_rows else None,
        "care_recipient_turns": sum(row.get("care_recipients", 0) for row in care_rows) if care_rows else None,
        "recovery_progress": math.fsum(row.get("recovery_progress", 0.0) for row in care_rows) if care_rows else None,
        "procurement_coins": math.fsum(row["paid"] for frame in forecasts
                                       for row in frame.get("procurement_decisions", {}).get("rows", [])) if forecasts else None,
        "public_spoiled": math.fsum(row["amount"] for frame in reserves for row in frame.get("flows", [])
                                    if row["kind"] == "spoiled") if reserves else None,
        "forecast_resolved": final_counters.get("resolved") if forecasts else None,
        "forecast_unscored": final_counters.get("unscored") if forecasts else None,
        "forecast_mean_brier": math.fsum(r["brier"] for r in outcomes.values()) / len(outcomes) if outcomes else None,
    }
    return {"metrics": metrics, "coverage": {"recorded_turns": len(history), "known_mean_turns": len(known_means),
            "care_turns": len(care_rows), "forecast_turns": len(forecasts), "reserve_turns": len(reserves),
            "known_scored_report_ids": len(outcomes), "native_balance_rows": native_checked,
            "public_balance_rows": public_checked, "max_native_residual_fraction_of_tolerance": max_native_relative,
            "max_public_absolute_residual": max_public_absolute},
            "distribution": distribution, "scored_reports": list(outcomes.values())}


def differences(control: dict, intervention: dict) -> dict:
    return {key: (intervention[key] - value if value is not None and intervention[key] is not None else None)
            for key, value in control.items()}


def generate(output: Path) -> dict:
    import numpy as np
    import chronicler_agents.chronicler_agents as native
    from chronicler import main
    from chronicler.bundle_codec import load_bundle
    from chronicler.models import WorldState

    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest = {"schema_version": 1, "kind": "modest-held-crisis-evaluation", "state": "running",
        "seeds": SEEDS, "turns": TURNS, "declaration_sha256": sha(DECLARATION.read_bytes()),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "rust_tree": subprocess.check_output(["git", "rev-parse", "HEAD:chronicler-agents"], cwd=ROOT, text=True).strip(),
        "source_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        "native_sha256": sha(Path(native.__file__).read_bytes()), "python": sys.version,
        "thread_environment": {name: os.environ.get(name) for name in
            ("PYTHONHASHSEED", "RAYON_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        "qualification": "held seeds in constructed families; no general efficacy or household welfare claim",
        "pairs": []}
    write_json(output / "evaluation.json", manifest)
    for family, arms in ARMS.items():
        for seed in SEEDS:
            pair = {"family": family, "seed": seed, "state": "running", "arms": {}}
            manifest["pairs"].append(pair)
            common = initial_world(seed, family).model_dump_json()
            witnesses = []
            for arm in arms:
                directory = output / f"{family}-{seed}-{arm}"
                directory.mkdir(mode=0o700)
                try:
                    world = WorldState.model_validate_json(common)
                    if family == "care":
                        world.health_care.care_enabled = arm == "care_on"
                    else:
                        world.harvest_forecasts.policy = arm
                    random.seed(seed)
                    np.random.seed(seed)
                    witness = StartWitness(directory, family)
                    args = main._build_parser().parse_args(["--seed", str(seed), "--turns", str(TURNS),
                        "--regions", str(len(world.regions)), "--civs", str(len(world.civilizations)),
                        "--agents", "hybrid", "--simulate-only", "--checkpoint-turns", str(TURNS),
                        "--output", str(directory / "chronicle.md"), "--state", str(directory / "state.json")])
                    main.execute_run(args, world=world, turn_boundary=witness)
                    if witness.start is None:
                        raise RuntimeError("missing initial witness")
                    witnesses.append(witness.start)
                    bundle_path = directory / "chronicle_bundle.json"
                    bundle = load_bundle(bundle_path)
                    if [row["turn"] for row in bundle["history"]] != list(range(1, TURNS + 1)):
                        raise RuntimeError("full-main history is incomplete or misdated")
                    summary = summarize_history(bundle["history"])
                    write_json(directory / "summary.json", summary)
                    pair["arms"][arm] = {"state": "completed", "start": witness.start,
                        "bundle_sha256": sha(bundle_path.read_bytes()), "metrics": summary["metrics"],
                        "coverage": summary["coverage"], "directory": directory.name}
                except Exception as exc:
                    pair["arms"][arm] = {"state": "failed", "reason": f"{type(exc).__name__}: {exc}"}
                write_json(output / "evaluation.json", manifest)
            if all(row["state"] == "completed" for row in pair["arms"].values()):
                if len(witnesses) != 2 or witnesses[0] != witnesses[1]:
                    pair.update(state="invalid", reason="initial world/native/RNG witnesses differ")
                else:
                    pair.update(state="completed", matched_initial_state=True,
                        intervention_minus_control=differences(pair["arms"][arms[0]]["metrics"], pair["arms"][arms[1]]["metrics"]))
            else:
                pair["state"] = "failed"
            write_json(output / "evaluation.json", manifest)
    manifest["state"] = "completed" if all(pair["state"] == "completed" for pair in manifest["pairs"]) else "partial"
    write_json(output / "evaluation.json", manifest)
    return manifest


def main_cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--simulate-only", action="store_true", required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.output.is_symlink() or output.exists() or output.is_relative_to(ROOT):
        parser.error("choose a fresh external output directory")
    if sys.version_info < (3, 13) or os.environ.get("PYTHONHASHSEED") != "0" or sys.flags.hash_randomization:
        parser.error("requires CPython3.13+ and PYTHONHASHSEED=0")
    os.umask(0o077)
    result = generate(output)
    print(json.dumps({"state": result["state"], "output": str(output)}))
    if result["state"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main_cli()
