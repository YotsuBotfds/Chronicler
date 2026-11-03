#!/usr/bin/env python3
"""Finite receiving-academy development case, with real merchant resupply.

The old suspicious-diplomacy/no-stock case remains a negative control. This
separately declared variant permits trade and endows supplier markets; it never
creates people, cargo, deliveries, purchases or teaching receipts directly.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import pickle
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = {
    "seed": 42, "regions": 5, "civilizations": 2, "common_turn": 3, "final_turn": 16,
    "opening_grain": [100., 0., 0., 0., 0.],
    "opening_crafts": [200., 20., 8., 0., 0.],
    "receiver": 2, "receiver_base_yield_multiplier": .25,
    "receiver_owner_treasury": 500, "native_liquid_requirement": 1.,
    "diplomacy": "both starting realms neutral, enabling the generated cross-realm merchant edges",
    "arms": {"open": "services enabled and routes open", "closed": "receiver route counter set to 3; two economy phases blocked before reopening",
             "paused": "resource-backed work/accounting paused; routes open and legacy scholarship effect continues"},
    "qualification": "constructed post-negative development variant, not held-out or a diplomatic intervention estimate",
}


def _json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def initial_world():
    from chronicler.cities import set_cities_enabled
    from chronicler.learning_services import set_learning_services_enabled
    from chronicler.models import Disposition
    from chronicler.scholarship_state import ACADEMY, ScholarshipState, Seat
    from chronicler.techniques import set_techniques_enabled
    from chronicler.transaction_receipts import set_transaction_receipts_enabled
    from chronicler.world_gen import generate_world

    world = generate_world(seed=42, num_regions=5, num_civs=2)
    world.agent_mode = "hybrid"
    set_cities_enabled(world, True)
    set_techniques_enabled(world, True)
    for i, region in enumerate(world.regions):
        region.stockpile.goods = {"grain": CONDITIONS["opening_grain"][i],
                                  "crafts": CONDITIONS["opening_crafts"][i]}
    receiver = world.regions[2]
    receiver.resource_base_yields = [.25 * v for v in receiver.resource_base_yields]
    world.household_mobility_liquid_requirement = 1.
    for rows in world.relationships.values():
        for relationship in rows.values():
            relationship.disposition = Disposition.NEUTRAL
    owner = world.civ_index_map[receiver.controller]
    world.civilizations[owner].treasury = 500
    world.scholarship = ScholarshipState(seats=[Seat(region=2, kind=ACADEMY,
        name="Constructed receiving academy", founded_turn=0, founder=owner, lord=owner)])
    set_learning_services_enabled(world, True)
    set_transaction_receipts_enabled(world, True)
    return world


class Capture:
    def __init__(self, directory):
        self.directory = directory
        self.rows = []
        self.rng_by_turn = {}

    def bind(self, save, run_config):
        import numpy as np
        from chronicler.run_checkpoint import read_checkpoint
        from scripts.crisis_migration_example import _agents
        self.save = save
        cp = read_checkpoint(save(str(self.directory / "start.ckpt")))
        try:
            w = cp.state.world
            self.before = _agents(cp.state.agent_bridge)
            self.offset = len(w.agent_events_raw)
            self.start = {"turn": w.turn, "world_sha256": _sha(w.model_dump_json().encode()),
                "native_sha256": _sha(bytes(cp.state.agent_bridge._sim.checkpoint_state())),
                "python_rng_sha256": _sha(pickle.dumps(random.getstate())),
                "numpy_rng_sha256": _sha(pickle.dumps(np.random.get_state()))}
        finally:
            cp.state.agent_bridge.close()

    def live_record(self):
        return None

    def turn_end(self, world):
        import numpy as np
        from chronicler.models import migration_driver_name
        from scripts.crisis_migration_example import _agents
        after = _agents(world._agent_bridge)
        moves = []
        for event in world.agent_events_raw[self.offset:]:
            if event.event_type == "migration":
                row = asdict(event)
                row.update(pre_region=self.before.get(event.agent_id, {}).get("region"),
                    post_region=after.get(event.agent_id, {}).get("region"),
                    driver_name=migration_driver_name(event.migration_driver))
                moves.append(row)
        self.rows.append({"source_turn": world.turn - 1, "migration_events": moves,
            "market_prices": world._economy_result.market_prices,
            "closing_crafts": [r.stockpile.goods.get("crafts", 0.) for r in world.regions],
            "imports_by_region": world._economy_result.imports_by_region,
            "receiver_route_suspension": world.regions[2].route_suspensions.get("trade_route", 0),
            "native_non_scholars_receiver": sum(r["region"] == 2 and r["occupation"] != 3 for r in after.values())})
        self.before, self.offset = after, len(world.agent_events_raw)
        self.rng = random.getstate(), np.random.get_state()
        self.rng_by_turn[world.turn] = self.rng
        return False


def _args(directory, turns):
    from chronicler import main
    return main._build_parser().parse_args(["--seed", "42", "--turns", str(turns), "--regions", "5", "--civs", "2",
        "--agents", "hybrid", "--simulate-only", "--checkpoint-turns", f"3,8,{turns}",
        "--output", str(directory / "chronicle.md"), "--state", str(directory / "state.json")])


def generate(output):
    import numpy as np
    import chronicler_agents.chronicler_agents as native
    from chronicler import main
    from chronicler.bundle_codec import load_bundle
    from chronicler.economy import build_merchant_route_graph
    from chronicler.learning_services import set_learning_services_enabled
    from chronicler.run_checkpoint import read_checkpoint
    from chronicler.world_gen import generate_world

    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest = {"kind": "receiving-service-resupply", "schema_version": 1, "state": "starting", "conditions": CONDITIONS,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "native_source_tree": subprocess.check_output(["git", "rev-parse", "HEAD:chronicler-agents"], cwd=ROOT, text=True).strip(),
        "native_sha256": _sha(Path(native.__file__).read_bytes()), "helper_sha256": _sha(Path(__file__).read_bytes()),
        "source_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)),
        "limits": ["Regional non-Scholar count is a potential learner bound; enrollment and household access are unmodeled.",
            "Finite opening endowments include goods above storage capacity; the real economy applies its cap.",
            "The initial yield multiplier retains the generated effective yield; it is not an injected drought.",
            "Route closure can alter migration and other goods as well as academy supplies.",
            "Unknown work when no request is submitted is not measured zero delivery.",
            "Pausing resource-backed services restores the legacy unmetered scholarship effect; it does not disable learning."]}
    _json(output / "case.json", manifest)
    try:
        generated = generate_world(seed=42, num_regions=5, num_civs=2)
        world = initial_world()
        def edges(w):
            return sorted((r["from_region"], r["to_region"]) for r in build_merchant_route_graph(w).to_pylist())
        manifest["graph_diagnosis"] = {"original": edges(generated), "declared_variant": edges(world),
            "original_relationships": {a: {b: r.disposition.value for b, r in rows.items()} for a, rows in generated.relationships.items()}}
        world.save(output / "initial-world.json")
        prefix = output / "common"; prefix.mkdir()
        random.seed(42); np.random.seed(42)
        common = Capture(prefix)
        main.execute_run(_args(prefix, 3), world=world, turn_boundary=common)
        common_rng = common.rng
        common_bundle = load_bundle(prefix / "chronicle_bundle.json")
        _json(prefix / "market-trace.json", common.rows)
        arrivals = [e for r in common.rows for e in r["migration_events"]
            if (e["region"], e["target_region"], e["pre_region"], e["post_region"]) == (1, 2, 1, 2)]
        common_path = prefix / "checkpoint_turn_3.ckpt"
        manifests, histories, traces, captures = {}, {}, {}, {}
        for name in ("open", "closed", "paused"):
            directory = output / name; directory.mkdir()
            cp = read_checkpoint(common_path)
            if not cp.exact:
                raise RuntimeError("common checkpoint must be exact")
            before = {"world": _sha(cp.state.world.model_dump_json().encode()),
                "native": _sha(bytes(cp.state.agent_bridge._sim.checkpoint_state()))}
            if name == "closed":
                cp.state.world.regions[2].route_suspensions["trade_route"] = 3
            elif name == "paused":
                set_learning_services_enabled(cp.state.world, False)
            random.setstate(common_rng[0]); np.random.set_state(common_rng[1])
            capture = Capture(directory)
            main.execute_run(_args(directory, 16), checkpoint_resume=cp, turn_boundary=capture)
            bundle = load_bundle(directory / "chronicle_bundle.json")
            histories[name], traces[name], captures[name] = bundle["history"], capture.rows, capture
            _json(directory / "market-trace.json", capture.rows)
            manifests[name] = {"common_before_control": before, "start": capture.start,
                               "bundle": str(directory / "chronicle_bundle.json")}
        if len({json.dumps(r["common_before_control"], sort_keys=True) for r in manifests.values()}) != 1:
            raise RuntimeError("arms did not share world/native common state")
        if any(len({r["start"][key] for r in manifests.values()}) != 1 for key in
               ("native_sha256", "python_rng_sha256", "numpy_rng_sha256")):
            raise RuntimeError("arms did not share initial native/Python/NumPy RNG state")
        if any(h[:3] != common_bundle["history"] for h in histories.values()):
            raise RuntimeError("shared prior history changed")
        # Independently resume the open arm at turn eight through the full coordinator.
        cp = read_checkpoint(output / "open" / "checkpoint_turn_8.ckpt")
        resume_dir = output / "open-resumed"; resume_dir.mkdir()
        random.setstate(captures["open"].rng_by_turn[8][0])
        np.random.set_state(captures["open"].rng_by_turn[8][1])
        replay = Capture(resume_dir)
        main.execute_run(_args(resume_dir, 16), checkpoint_resume=cp, turn_boundary=replay)
        replay_bundle = load_bundle(resume_dir / "chronicle_bundle.json")
        finals = [read_checkpoint(d / "checkpoint_turn_16.ckpt") for d in (output / "open", resume_dir)]
        try:
            exact = {"history": histories["open"] == replay_bundle["history"],
                "world": finals[0].state.world.model_dump_json() == finals[1].state.world.model_dump_json(),
                "native": finals[0].state.agent_bridge._sim.checkpoint_state() == finals[1].state.agent_bridge._sim.checkpoint_state(),
                "python_rng": captures["open"].rng[0] == replay.rng[0],
                "numpy_rng": pickle.dumps(captures["open"].rng[1]) == pickle.dumps(replay.rng[1])}
        finally:
            for cp in finals: cp.state.agent_bridge.close()
        if not all(exact.values()):
            raise RuntimeError("post-resupply exact continuation mismatch")
        analysis = {}
        for name, history in histories.items():
            selected = history[3:]
            transport = [r for s in selected for r in (s.get("transaction_receipts") or {}).get("rows", [])]
            service = [(s["turn"] - 1, (s.get("scholarship") or {}).get("learning_services") or {}) for s in selected]
            purchases = [r for source, frame in service for r in frame.get("procurement_receipts", []) if r["region"] == 2 and r["source_turn"] == source]
            teaching = [(source, r) for source, frame in service for r in frame.get("teaching_receipts", []) if r["region"] == 2 and r["source_turn"] == source]
            positive = [{"source_turn": source, **r} for source, r in teaching if (r["work_delivered"] or 0) > 0]
            for snapshot in history:
                for r in snapshot["food_accounting"]["regions"]:
                    n = r["native"]
                    if n is not None and abs(n["balance_residual"]) > n["balance_tolerance"]:
                        raise RuntimeError("native food ledger failed")
                frame = snapshot["transaction_receipts"]
                if not frame["complete"] or frame["dropped_rows"]:
                    raise RuntimeError("incomplete merchant evidence")
                balance = ((snapshot.get("scholarship") or {}).get("learning_services") or {}).get("material_balance")
                if balance is not None and abs(balance["residual"]) > balance["absolute_tolerance"]:
                    raise RuntimeError("academy material ledger failed")
            analysis[name] = {"craft_arrivals": [r for r in transport if r["operation"] == "arrived" and r["dest_region"] == 2 and r["good_slot"] == 8],
                "craft_returns": [r for r in transport if r["operation"] == "returned" and r["good_slot"] == 8],
                "craft_cancellations": [r for r in transport if r["operation"] == "reservation_cancelled" and r["good_slot"] == 8],
                "purchases": purchases, "positive_teaching": positive,
                "paid": sum(r["paid"] for r in purchases),
                "crafts_purchased": sum(r["purchased"] for r in purchases),
                "known_work_delivered_sum": sum(r["work_delivered"] for _, r in teaching if r["work_delivered"] is not None),
                "native_delivery_rows": sum(r["work_delivered"] is not None for _, r in teaching),
                "unknown_work_rows": sum(r["work_delivered"] is None for _, r in teaching),
                "work_requested_sum": sum(r["work_requested"] for _, r in teaching)}
        # Bind actual food-distress evidence and the phases of physical recovery.
        distress = []
        for event in arrivals:
            frame = common_bundle["history"][event["turn"]]
            samples = {r["group_id"]: r for r in frame["household_mobility"]["samples"]}
            sample = samples.get(event["agent_id"])
            if (sample is not None and sample["local_food_sufficiency"] < 1 and
                    event["driver_name"] in {"famine_memory", "material_need", "low_satisfaction", "opp_food"}):
                distress.append(event)
        def chains(name):
            rows = []
            for receipt in analysis[name]["purchases"]:
                source = receipt["source_turn"]
                if not (receipt["purchased"] > 0 and receipt["paid"] > 0 and
                        receipt["craft_price"] > 0 and receipt["market_stock"] >= receipt["purchased"]):
                    continue
                prior = histories[name][source - 1]["transaction_receipts"]["rows"]
                cargo = [r for r in prior if r["operation"] == "arrived" and r["dest_region"] == 2 and r["good_slot"] == 8]
                next_work = [r for r in analysis[name]["positive_teaching"] if r["source_turn"] == source + 1 and
                             r["held_before"] >= r["crafts_used"] > 0]
                if cargo and next_work:
                    rows.append({"arrival_source": source - 1, "purchase_source": source,
                        "teaching_source": source + 1, "arrivals": cargo, "purchase": receipt, "teaching": next_work})
            return rows
        open_chains, closed_chains = chains("open"), chains("closed")
        def work(name, source):
            frame = histories[name][source]["scholarship"]["learning_services"]
            return next((r for r in frame["teaching_receipts"] if r["region"] == 2 and r["source_turn"] == source), None)
        gap = work("closed", 7)
        interruption = bool(analysis["closed"]["craft_cancellations"] and gap is not None and
            gap["held_before"] == 0 and gap["work_requested"] == 0 and gap["work_delivered"] is None and
            (work("open", 7)["work_delivered"] or 0) > 0)
        recovery_chains = [r for r in closed_chains if r["arrival_source"] >= 6 and r["teaching_source"] > 7]
        source2 = common_bundle["history"][2]
        prior_bound = source2["scholarship"]["learning_services"]["teaching_receipts"][0]["learner_upper_bound"]
        following_bound = source2["scholarship"]["learning_services"]["procurement_receipts"][0]["learner_upper_bound"]
        receiver_native = source2["food_accounting"]["regions"][2]["native"]
        receiving_pressure = bool(following_bound > prior_bound and receiver_native["sufficiency"] < 1 and
            work("open", 3)["learner_upper_bound"] == following_bound)
        positive = bool(distress and receiving_pressure and open_chains)
        recovery = bool(interruption and recovery_chains)
        manifest.update(state="validated" if positive and recovery else "partial", arms=manifests, analysis=analysis,
            admission={"distress_associated_arrivals": distress, "common_history_complete": True,
                "real_open_resupply_and_teaching": positive, "reopened_resupply_and_teaching": recovery,
                "receiving_pressure": {"admitted": receiving_pressure, "pre_native_learner_upper_bound": prior_bound,
                    "post_native_learner_upper_bound": following_bound, "receiver_sufficiency": receiver_native["sufficiency"]},
                "open_chains": open_chains, "closed_recovery_chains": recovery_chains,
                "closed_source7_unknown_work": gap, "service_interruption": interruption}, exact_resume=exact)
        _json(output / "case.json", manifest)
        (output / "WALKTHROUGH.txt").write_text(
            "Constructed receiving-service comparison; read case.json for initial conditions and limits.\n"
            "Open open/chronicle_bundle.json and closed/chronicle_bundle.json in the existing viewer comparison.\n"
            "Select region 2, Trade / Food and Learning. Inspect dated merchant arrivals, market purchases,\n"
            "then next-turn actual native Scholar work; these are different phases and different receipts.\n"
            "paused/chronicle_bundle.json pauses resource-backed work/accounting; legacy scholarship learning remains active.\n"
            "A non-Scholar count is a potential learner bound, not enrollment or food access.\n", encoding="utf-8")
    except BaseException as exc:
        manifest.update(state="failed", reason=f"{type(exc).__name__}: {exc}")
        _json(output / "case.json", manifest)
        raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--simulate-only", action="store_true", required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if args.output.is_symlink() or output.exists() or output.is_relative_to(ROOT):
        parser.error("choose a fresh external output directory")
    if sys.version_info < (3, 13) or os.environ.get("PYTHONHASHSEED") != "0" or sys.flags.hash_randomization:
        parser.error("requires Python3.13+ started with PYTHONHASHSEED=0")
    os.umask(0o077)
    result = generate(output)
    print(json.dumps({"state": result["state"], "output": str(output)}))
    return 0 if result["state"] == "validated" else 2


if __name__ == "__main__":
    sys.exit(main())
