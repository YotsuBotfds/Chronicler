"""Small paired check against an untouched public-main checkout, no LLM calls.

Usage: .venv/bin/python scripts/validate_fishery_experiment.py \
    --baseline-src /path/to/untouched/Chronicler/src --output /tmp/fishery.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BASELINE = "edf7299"
EXPERIMENT_FIELDS = ("fishery_stocks", "fishery_yield_ratios", "fishery_catch_budgets")


def run_fixture(source: Path, enabled: bool, turns: int) -> dict:
    sys.path.insert(0, str(source))
    from chronicler.models import ActionType, ResourceType
    from chronicler.simulation import run_turn
    from chronicler.world_gen import generate_world

    world = generate_world(seed=42, num_regions=4, num_civs=2)
    region = world.regions[0]
    region.terrain = "coast"
    region.resources = "maritime"
    region.population = 2000
    region.carrying_capacity = 3000
    region.resource_types = [ResourceType.FISH, 255, 255]
    region.resource_base_yields = [1.0, 0.0, 0.0]
    region.resource_effective_yields = [1.0, 0.0, 0.0]
    from chronicler.utils import sync_all_populations
    sync_all_populations(world)
    if enabled:
        world.fishery_experiment.enabled = True
    trace = []
    for turn in range(turns):
        run_turn(world, lambda *_: ActionType.DEVELOP, lambda *_: "", seed=42 + turn)
        trace.append({"turn": world.turn, "stock": getattr(region, "fishery_stocks", [1])[0],
                      "catch_budget": getattr(region, "fishery_catch_budgets", [None])[0]})
    state = world.model_dump(mode="json")
    # Preserve every shared field; remove only verified dormant aid additions.
    for field, default in (("mutual_aid_enabled", False), ("mutual_aid_state", {}),
                           ("mutual_aid_last_dispatch_turn", None), ("mutual_aid_last_transfers", [])):
        if field in state:
            assert state.pop(field) == default, (field, "aid unexpectedly active")
    state.pop("fishery_experiment", None)
    for row in state["regions"]:
        for field in EXPERIMENT_FIELDS:
            row.pop(field, None)
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    return {"canonical_state_sha256": hashlib.sha256(encoded).hexdigest(),
            "fish_trace": trace, "terminal_turn": world.turn}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--turns", type=int, default=12)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--enabled", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(run_fixture(args.source.resolve(), args.enabled, args.turns)))
        return
    if not args.baseline_src or args.turns < 1 or args.turns > 50:
        parser.error("provide --baseline-src and a turn count in [1, 50]")
    baseline_root = args.baseline_src.resolve().parent
    baseline_head = subprocess.check_output(
        ["git", "-C", str(baseline_root), "rev-parse", "HEAD"], text=True,
    ).strip()
    if not baseline_head.startswith(BASELINE):
        parser.error(f"baseline must be untouched public main {BASELINE}; got {baseline_head}")
    if subprocess.check_output(["git", "-C", str(baseline_root), "status", "--porcelain"], text=True).strip():
        parser.error("baseline checkout must be clean")
    source = Path(__file__).resolve().parents[1] / "src"

    def launch(src, enabled):
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--source", str(src),
                   "--turns", str(args.turns)]
        if enabled:
            command.append("--enabled")
        return json.loads(subprocess.check_output(command, text=True))

    control = launch(args.baseline_src, False)
    off = launch(source, False)
    on = launch(source, True)
    on_repeat = launch(source, True)
    off_matches = control == off
    on_deterministic = on == on_repeat
    depletion = on["fish_trace"][-1]["stock"] < off["fish_trace"][-1]["stock"]
    report = {"baseline_commit": baseline_head, "fixture_seed": 42, "turns": args.turns,
              "mode": "pure Python full turns; DEVELOP selector; no narrative calls",
              "comparison_exclusions": ["fishery_experiment", *EXPERIMENT_FIELDS,
                                        "mutual_aid_enabled", "mutual_aid_state",
                                        "mutual_aid_last_dispatch_turn", "mutual_aid_last_transfers"],
              "disabled_equals_untouched_public_main": off_matches,
              "enabled_repeat_deterministic": on_deterministic,
              "enabled_stock_lower_than_control": depletion,
              "control": control, "off": off, "on": on,
              "scope": "No comparison with private frozen candidate b665e198; no hybrid continuation claim"}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if not (off_matches and on_deterministic and depletion):
        raise SystemExit("paired fixture failed")


if __name__ == "__main__":
    main()
