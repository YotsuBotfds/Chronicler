#!/usr/bin/env python3
"""One constructed, bounded crisis case using the existing exact what-if runner.

Finite regional inventories and a three-node map are explicit initial conditions.
No cargo, native person, arrival or result is injected. The real planner must
reserve and load a trip before this example admits the transport intervention.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import json
import os
from pathlib import Path
import queue
import random
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = {
    "seed": 42, "regions": 3, "civilizations": 1,
    "model_population": [400, 20, 400], "carrying_capacity": 400,
    "opening_grain": [2000.0, 300.0, 0.0], "adjacency": [[1], [0, 2], [1]],
    "grain_resource_slots": [[0, 255, 255], [0, 255, 255], [255, 255, 255]],
    "resource_yields": [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
    "admission": "Real reserved then departed 0-to-2 grain trip, positive cargo and destination food sufficiency below one, within six completed turns.",
    "intervention": {"control": "regional_transport_disruption", "region_id": 2, "duration": 2},
    "continuation_turns": 8,
}


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def constructed_world():
    from chronicler.transaction_receipts import set_transaction_receipts_enabled
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42, num_regions=3, num_civs=1)
    world.agent_mode = "hybrid"
    civ = world.civilizations[0]
    civ.regions = [region.name for region in world.regions]
    civ.capital_region = world.regions[0].name
    for i, region in enumerate(world.regions):
        region.controller = civ.name
        region.population = CONDITIONS["model_population"][i]
        region.carrying_capacity = CONDITIONS["carrying_capacity"]
        region.stockpile.goods = {"grain": CONDITIONS["opening_grain"][i]}
        region.adjacencies = [world.regions[j].name for j in CONDITIONS["adjacency"][i]]
        region.route_suspensions.clear()
        region.resource_types = list(CONDITIONS["grain_resource_slots"][i])
        region.resource_base_yields = list(CONDITIONS["resource_yields"][i])
    civ.population = sum(r.population for r in world.regions)
    set_transaction_receipts_enabled(world, True)
    return world


class CheckpointBinding:
    """Use execute_run's existing whole-runtime checkpoint boundary."""
    def bind(self, save, run_config):
        self.save = save

    def live_record(self):
        return None

    def turn_end(self, world):
        return False

    def save_private(self, path):
        return self.save(str(path))


def observations(bundle):
    """Export recorded measures; absent observations remain null."""
    rows = []
    for snapshot in bundle["history"]:
        accounting = snapshot.get("food_accounting") or {}
        rows.append({"snapshot_turn": snapshot["turn"],
            "regional_observations": snapshot.get("regional_observations"),
            "food_accounting": accounting or None,
            "transport": (snapshot.get("transaction_receipts") or {}).get("rows"),
            "civilizations": snapshot.get("civ_stats")})
    return rows


def generate(output: Path) -> dict:
    from chronicler import main
    from chronicler.what_if import WhatIfPairs
    import chronicler_agents.chronicler_agents as native
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest = {"kind": "constructed-crisis-transport", "schema_version": 1,
        "state": "implementing", "conditions": CONDITIONS, "admission": None,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "native_source_tree": subprocess.check_output(["git", "rev-parse", "HEAD:chronicler-agents"], cwd=ROOT, text=True).strip(),
        "native_sha256": hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limits": ["Constructed finite inventories and geography; development case, not held evaluation.",
            "Native sufficiency is regional available food / native demand, not household meals or access.",
            "The intervention closes every route incident to region 2; it is not an individual edge control.",
            "Eight-turn trajectories do not demonstrate general recovery, balance or policy superiority."]}
    receipt = output / "crisis-case.json"
    write(receipt, manifest)
    world = constructed_world()
    world.save(output / "constructed_initial_state.json")
    binding = CheckpointBinding()
    pairs = WhatIfPairs(output, queue.Queue(), binding)
    reserved = set()
    def pause(current, memories, pending):
        frame = current.transaction_receipts
        if not frame.complete or frame.dropped_rows:
            raise RuntimeError("Incomplete transport observations cannot admit this example")
        for row in frame.frame:
            if (row.operation, row.origin_region, row.dest_region, row.good_slot) == ("reserved", 0, 2, 0):
                reserved.add(row.voyage_id)
        departed = [row for row in frame.frame if row.operation == "departed" and row.voyage_id in reserved]
        if not departed:
            if current.turn >= 6:
                raise RuntimeError("Declared case failed admission: no loaded trip by turn six")
            return True
        voyage = departed[0]
        sufficiency = current._economy_result.food_sufficiency[current.regions[2].name]
        if not (voyage.quantity > 0 and sufficiency < 1):
            raise RuntimeError("Declared case failed admission: no cargo or no destination shortfall")
        before = (current.model_dump_json(), bytes(current._agent_bridge._sim.checkpoint_state()), random.getstate())
        request = {"type": "what_if_prepare", "request_id": "crisis-route",
            **CONDITIONS["intervention"], "turns": CONDITIONS["continuation_turns"]}
        pairs.prepare(request, current)
        pairs.run("crisis-route")
        job = pairs.jobs["crisis-route"]
        job.thread.join(2 * 120 + 10)
        if job.thread.is_alive() or job.state != "complete":
            raise RuntimeError(f"Exact pair did not complete: {job.message}")
        if before != (current.model_dump_json(), bytes(current._agent_bridge._sim.checkpoint_state()), random.getstate()):
            raise RuntimeError("Paired exploration changed the original world")
        bundles = {arm: job.result[arm]["bundle"] for arm in ("baseline", "intervention")}
        def transport(arm):
            return [row for s in bundles[arm]["history"] if s["turn"] > current.turn
                    for row in (s.get("transaction_receipts") or {}).get("rows", [])]
        normal, disrupted = transport("baseline"), transport("intervention")
        arrived = [r for r in normal if r["operation"] == "arrived" and r["voyage_id"] == voyage.voyage_id]
        returned = [r for r in disrupted if r["operation"] == "returned" and r["voyage_id"] == voyage.voyage_id]
        recovered = [r for r in disrupted if r["operation"] == "arrived" and r["dest_region"] == 2
                     and r["good_slot"] == 0 and r["voyage_id"] != voyage.voyage_id]
        if not arrived or not returned or not recovered:
            raise RuntimeError("Declared case failed outcome admission: arrival/return/reopened delivery missing")
        manifest.update(state="validated", admission={"snapshot_turn": current.turn,
            "voyage_id": voyage.voyage_id, "gross_cargo": voyage.quantity,
            "destination_sufficiency": sufficiency, "baseline_arrival": arrived,
            "disruption_return": returned, "recovery_arrivals": recovered,
            "original_unchanged": True}, exact_pair_directory=str(job.directory),
            pair_manifest=job.manifest)
        for arm in bundles:
            write(output / f"{arm}-observations.json", observations(bundles[arm]))
        write(receipt, manifest)
        return False
    try:
        args = main._build_parser().parse_args(["--seed", "42", "--turns", "14", "--regions", "3", "--civs", "1",
            "--agents", "hybrid", "--transaction-receipts", "--simulate-only", "--pause-every", "1",
            "--output", str(output / "original" / "chronicle.md"), "--state", str(output / "original" / "state.json")])
        main.execute_run(args, world=world, on_pause=pause, pause_every=1, turn_boundary=binding)
    except BaseException as exc:
        manifest.update(state="failed", failure=f"{type(exc).__name__}: {exc}")
        write(receipt, manifest)
        raise
    finally:
        pairs.close()
    checkpoint = Path(manifest["exact_pair_directory"]) / "common.ckpt"
    live = [sys.executable, "-m", "chronicler.main", "--live", "--live-port", "0", "--resume", str(checkpoint),
        "--turns", "14", "--simulate-only", "--output", str(output / "live" / "chronicle.md"),
        "--state", str(output / "live" / "state.json")]
    (output / "WALKTHROUGH.txt").write_text(
        "Constructed transport crisis (not a natural start or scientific evaluation).\n"
        f"Read crisis-case.json and both *-observations.json files. Start is snapshot {manifest['admission']['snapshot_turn']}.\n"
        "Open either exact-pair arm's chronicle_bundle.json in the viewer; choose Trade / Food and inspect the destination.\n"
        "The same original loaded-cargo checkpoint can be resumed paused using:\n"
        + shlex.join(["env", f"PYTHONPATH={ROOT / 'src'}", "PYTHONHASHSEED=0", *live]) + "\n"
        "Use a fresh live output directory each time. Select the destination, preview regional transport disruption for two turns,\n"
        "then run an eight-turn comparison. The baseline stays unchanged. Inspect returned cargo and reopened delivery;\n"
        "nearby events do not establish an additional cause. Exact continuation requires the same Python/native source identity.\n",
        encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Fresh external directory; never overwritten")
    parser.add_argument("--simulate-only", action="store_true", required=True)
    options = parser.parse_args()
    raw = options.output.expanduser()
    output = raw.resolve()
    if raw.is_symlink() or output.exists() or output.is_relative_to(ROOT):
        parser.error("Choose a fresh external directory; existing paths and symlinks are preserved")
    if sys.version_info < (3, 13) or os.environ.get("PYTHONHASHSEED") != "0" or sys.flags.hash_randomization:
        parser.error("Use Python 3.13+ started with PYTHONHASHSEED=0")
    sys.path.insert(0, str(ROOT / "src"))
    import chronicler
    import chronicler_agents.chronicler_agents as native
    if not Path(chronicler.__file__).resolve().is_relative_to(ROOT):
        parser.error("Interpreter imported another checkout")
    if not any(native.__file__.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES):
        parser.error("A matching real native extension is required; this helper never installs one")
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "src/chronicler", "chronicler-agents"], cwd=ROOT, text=True)
    if dirty:
        parser.error("Commit simulation/native source before creating an exact example")
    os.umask(0o077)
    result = generate(output)
    print(f"Validated constructed case: {output / 'crisis-case.json'}; start turn {result['admission']['snapshot_turn']}")


if __name__ == "__main__":
    main()
