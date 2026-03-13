"""Fork mode — load a mid-run state and explore alternate futures."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

from chronicler.memory import MemoryStream
from chronicler.models import WorldState
from chronicler.types import RunResult


def run_fork(
    args: argparse.Namespace,
    sim_client: Any = None,
    narrative_client: Any = None,
    scenario_config: Any = None,
) -> RunResult:
    """Fork from a saved state with a new seed. Returns RunResult."""
    fork_path = Path(args.fork)
    fork_dir = fork_path.parent
    new_seed = args.seed
    new_turns = args.turns

    if new_seed is None:
        raise ValueError("--seed is required with --fork")
    if new_turns is None:
        raise ValueError("--turns is required with --fork")

    # Load parent state
    world = WorldState.load(fork_path)
    parent_seed = world.seed
    fork_turn = world.turn

    # Warn if parent used a scenario but --scenario not passed
    if world.scenario_name and not scenario_config:
        print(
            f"Note: parent run used scenario '{world.scenario_name}'; "
            f"forking without --scenario means event flavor and narrative "
            f"style will not be applied. Pass --scenario to preserve them."
        )

    # Load memory streams from parent directory
    memories: dict[str, MemoryStream] = {}
    for mem_file in fork_dir.glob("memories_*.json"):
        stream = MemoryStream.load(mem_file)
        memories[stream.civilization_name] = stream

    # Fill in any civs that don't have memory files
    for civ in world.civilizations:
        if civ.name not in memories:
            memories[civ.name] = MemoryStream(civilization_name=civ.name)

    # Apply new seed
    world.seed = new_seed

    # Set turns to fork_turn + new_turns
    fork_args = copy.copy(args)
    fork_args.turns = fork_turn + new_turns
    fork_args.seed = new_seed

    # Provenance header
    provenance = f"> Forked from seed {parent_seed} at turn {fork_turn}. New seed: {new_seed}."

    from chronicler.main import execute_run
    return execute_run(
        fork_args,
        sim_client=sim_client,
        narrative_client=narrative_client,
        world=world,
        memories=memories,
        scenario_config=scenario_config,
        provenance_header=provenance,
    )
