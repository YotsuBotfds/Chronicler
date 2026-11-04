#!/usr/bin/env python3
"""One fixed constructed case for create_example_worlds.py --institution-pressure.

Uses existing simulation, intervention and export paths; it does not guarantee
recovery or supply a new institution mechanism. Both arms have constructed starts.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CASES = ("conquest_learning_loss", "temple_patron_loss_drought")
CONDITIONS = {
    "seed": 42, "turns": 64, "regions": 8, "civilizations": 4,
    "opening_treasury": 200, "opening_culture": 60, "opening_stability": 60,
    "opening_seats": [[2, "academy", 1], [3, "academy", 2], [5, "temple school", 1]],
    "opening_temple": {"region": 5, "prestige": 80, "faith": "initial ruler's majority faith"},
    "opening_city_records": "none injected; native detection may found cities",
    "pressure_tick": 4, "recovery_support_tick": 12, "checkpoint_turn": 16,
    "conquest_learning_loss": "At 4, transfer Verdant to Selurian only if still Thornwall-owned; otherwise record unapplied, never choose another target. At 12, white peace and a temple with current-ruler faith/prestige200 support recovery.",
    "temple_patron_loss_drought": "At 4, withdraw Amber's temple patron and queue existing drought injection. At 12, reactivate that temple with current-ruler faith/prestige200. Drought is not labeled observed famine.",
}


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def pressure(world, temple, case: str, pending: list) -> dict | None:
    from chronicler.models import Infrastructure, InfrastructureType
    from chronicler.war.common import build_context
    from chronicler.war.occupation import annex_occupation, start_occupation
    from chronicler.war.peace import conclude_peace, open_war

    tick = world.turn
    if tick == 4 and case == CASES[0]:
        region = world.regions[2]
        attacker, defender = world.civilizations[3], world.civilizations[2]
        if region.controller != defender.name:
            return {"turn": tick, "applied": False, "operation": "original ownership changed; transfer unapplied", "actual": region.controller}
        ctx = build_context(world)
        war = next((row for row in world.war_state.wars if {row.attacker, row.defender} == {attacker.name, defender.name}), None)
        war = war or open_war(ctx, attacker, defender)
        occupation = start_occupation(ctx, region, attacker, war, None)
        annex_occupation(ctx, occupation, "consolidated")
        world.events_timeline.extend(ctx.events)
        return {"turn": tick, "applied": True, "operation": "existing occupation and annexation", "region": 2,
                "before": defender.name, "after": region.controller, "event_ids": [event.event_id for event in ctx.events]}
    if tick == 4:
        temple.active = False
        target = world.regions[5].controller
        if target:
            pending.append(("drought", target))
        return {"turn": tick, "applied": True, "operation": "temple deactivated; drought queued", "region": 5, "target": target}
    if tick != 12:
        return None
    region = world.regions[2 if case == CASES[0] else 5]
    if case == CASES[0]:
        ctx = build_context(world)
        names = {world.civilizations[2].name, world.civilizations[3].name}
        for war in list(world.war_state.wars):
            if war.attacker in names or war.defender in names:
                conclude_peace(ctx, war, "white_peace", None)
        world.events_timeline.extend(ctx.events)
        temple = next((row for row in region.infrastructure if row.type == InfrastructureType.TEMPLES), None)
    ruler = world.civ_map.get(region.controller)
    if ruler is None:
        return {"turn": tick, "applied": False, "operation": "recovery support unapplied: no ruler"}
    if temple is None:
        temple = Infrastructure(type=InfrastructureType.TEMPLES, builder_civ=ruler.name, built_turn=tick,
                                faith_id=ruler.civ_majority_faith, temple_prestige=0)
        region.infrastructure.append(temple)
    before = temple.temple_prestige
    temple.active, temple.faith_id, temple.temple_prestige = True, ruler.civ_majority_faith, 200
    return {"turn": tick, "applied": True, "operation": "declared temple recovery support", "region": region.name,
            "faith": temple.faith_id, "prestige_before": before, "prestige_after": 200, "external_prestige_change": 200 - before}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--arm", choices=("control", "pressure"), required=True)
    parser.add_argument("--output", type=Path, required=True, help="Fresh external case directory")
    parser.add_argument("--simulate-only", action="store_true", required=True)
    options = parser.parse_args()
    original = options.output.expanduser()
    output = original.resolve()
    if original.is_symlink() or output.exists() or output.is_relative_to(ROOT):
        parser.error("Use a fresh external directory; existing files and symlinks are preserved")
    if sys.version_info < (3, 13) or os.environ.get("PYTHONHASHSEED") != "0":
        parser.error("Use Python 3.13+ and PYTHONHASHSEED=0 for the exact checkpoint")
    sys.path.insert(0, str(ROOT / "src"))
    import chronicler
    import chronicler_agents.chronicler_agents as native
    if not Path(chronicler.__file__).resolve().is_relative_to(ROOT):
        raise RuntimeError("Interpreter imported another Chronicler checkout")
    if not any(native.__file__.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES) or not all(
        isinstance(getattr(native, key, None), type) for key in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")
    ):
        raise RuntimeError("A matching real native runtime is required; this helper never installs one")
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "src/chronicler", "chronicler-agents"], cwd=ROOT, text=True)
    if dirty:
        raise RuntimeError("Commit simulation/native source before generating this exact example")
    from chronicler import cities, faiths, scholarship
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    from chronicler.models import Infrastructure, InfrastructureType
    from chronicler.scholarship_state import ACADEMY, TEMPLE_SCHOOL, Seat
    from chronicler.world_gen import generate_world

    output.mkdir(parents=True, exist_ok=False)
    manifest = {"kind": "constructed-institution-pressure", "version": 1, "state": "planned", "case": options.case,
                "arm": options.arm, "conditions": CONDITIONS, "interventions": [],
                "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "native_source_tree": subprocess.check_output(["git", "rev-parse", "HEAD:chronicler-agents"], cwd=ROOT, text=True).strip(),
                "helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "native_sha256": hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
                "limits": ["Constructed opening institutions/resources and explicit interventions, not natural starts.",
                           "No seed search, guaranteed recovery, isolated welfare effect or general benefit claim.",
                           "A school is not a faith; missing city/seat rows do not establish destruction."]}
    receipt = output / "institution-case.json"
    write(receipt, manifest)
    try:
        world = generate_world(seed=42)
        world.agent_mode = "hybrid"
        cities.set_cities_enabled(world, True)
        scholarship.set_scholarship_enabled(world, True)
        for civ in world.civilizations:
            civ.treasury, civ.culture, civ.stability = 200, 60, 60
        for region, kind, level in ((2, ACADEMY, 1), (3, ACADEMY, 2), (5, TEMPLE_SCHOOL, 1)):
            owner = world.civ_index_map[world.regions[region].controller]
            slot = world.civilizations[owner].civ_majority_faith
            world.scholarship.seats.append(Seat(region=region, kind=kind, name=f'Constructed opening {"academy" if kind == ACADEMY else "temple school"} of {world.regions[region].name}',
                founded_turn=0, founder=owner, lord=owner, faith=faiths.uid_or_slot(world, slot), level=level,
                peak_level=level, scholars=8., peak_scholars=8., level_turn=0))
        temple = Infrastructure(type=InfrastructureType.TEMPLES, builder_civ=world.regions[5].controller, built_turn=0,
                                faith_id=world.civilizations[1].civ_majority_faith, temple_prestige=80)
        world.regions[5].infrastructure.append(temple)
        world.save(output / "constructed_initial_state.json")

        def pause(current, memories, pending):
            if options.arm == "pressure":
                row = pressure(current, temple, options.case, pending)
                if row:
                    manifest["interventions"].append(row)
                    write(receipt, manifest)
            return True

        args = _build_parser().parse_args(["--seed", "42", "--turns", "64", "--civs", "4", "--regions", "8", "--agents", "hybrid",
            "--simulate-only", "--cities", "--scholarship", "--pause-every", "1", "--checkpoint-turns", "16",
            "--output", str(output / "chronicle.md"), "--state", str(output / "state.json")])
        execute_run(args, world=world, on_pause=pause, pause_every=1,
                    provenance_header=f"Fixed constructed institution example: {options.case}; {options.arm}. No seed search or parameter tuning.")
        bundle = load_bundle(output / "chronicle_bundle.json")
        if [row["turn"] for row in bundle["history"]] != list(range(1, 65)) or not (output / "checkpoint_turn_16.ckpt").is_file():
            raise RuntimeError("The declared 64-turn history and checkpoint16 did not complete")
        by_id = {event["event_id"]: event for event in bundle["events_timeline"] if event.get("event_id")}
        returns = [{"source_tick": event["turn"], "snapshot_turn": event["turn"] + 1, "event_id": event.get("event_id"),
                    "description": event["description"], "prior_falls": [cause for cause in event.get("causes", []) if by_id.get(cause, {}).get("event_type") == "seat_fell"]}
                   for event in bundle["events_timeline"] if event["event_type"] == "seat_founded"
                   and any(by_id.get(cause, {}).get("event_type") == "seat_fell" for cause in event.get("causes", []))]
        manifest.update(state="completed", observations={"reestablishments": returns,
            "recorded_final_civ_population_sum": sum(civ["population"] for civ in bundle["world_state"]["civilizations"])},
            artifacts={name: {"bytes": (output / name).stat().st_size, "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
                       for name in ("constructed_initial_state.json", "chronicle_bundle.json", "state.json", "checkpoint_turn_16.ckpt")})
        write(receipt, manifest)
    except BaseException as error:
        manifest.update(state="failed", error=f"{type(error).__name__}: {error}")
        write(receipt, manifest)
        raise
    print(f"Created constructed institution example: {output / 'chronicle_bundle.json'}")


if __name__ == "__main__":
    main()
