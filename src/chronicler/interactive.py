"""Interactive mode — pause at intervals, accept commands, resume."""
from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

from chronicler.memory import MemoryStream, sanitize_civ_name
from chronicler.models import WorldState
from chronicler.types import RunResult
from chronicler.world_gen import DEFAULT_EVENT_PROBABILITIES


VALID_INJECTABLE_EVENTS = set(DEFAULT_EVENT_PROBABILITIES.keys())
VALID_STATS = {"population", "military", "economy", "culture", "stability", "treasury"}
CORE_STATS = {"population", "military", "economy", "culture", "stability"}


def parse_command(raw: str) -> tuple[str, Any]:
    """Parse a user command string. Returns (command_name, args_or_error_msg)."""
    raw = raw.strip()
    if not raw:
        return ("error", "Empty command. Type 'help' for available commands.")

    try:
        tokens = shlex.split(raw)
    except ValueError as e:
        return ("error", f"Parse error: {e}")

    cmd = tokens[0].lower()

    if cmd in ("continue", "quit", "help", "fork"):
        return (cmd, None)

    if cmd == "inject":
        if len(tokens) < 3:
            return ("error", "Usage: inject <event_type> \"<civ_name>\"")
        event_type = tokens[1]
        civ_name = tokens[2]
        if event_type not in VALID_INJECTABLE_EVENTS:
            return ("error", f"Invalid event type '{event_type}'. Valid types: {sorted(VALID_INJECTABLE_EVENTS)}")
        return ("inject", (event_type, civ_name))

    if cmd == "set":
        if len(tokens) < 4:
            return ("error", 'Usage: set "<civ_name>" <stat> <value>')
        civ_name = tokens[1]
        stat = tokens[2].lower()
        if stat not in VALID_STATS:
            return ("error", f"Invalid stat '{stat}'. Valid stats: {sorted(VALID_STATS)}")
        try:
            value = int(tokens[3])
        except ValueError:
            return ("error", f"Value must be an integer, got '{tokens[3]}'")
        if stat in CORE_STATS and not (1 <= value <= 10):
            return ("error", f"Value for {stat} must be 1-10, got {value}")
        if stat == "treasury" and value < 0:
            return ("error", f"Treasury must be >= 0, got {value}")
        return ("set", (civ_name, stat, value))

    return ("error", f"Unknown command '{cmd}'. Type 'help' for available commands.")


def format_state_summary(world: WorldState, total_turns: int) -> str:
    """Format a text summary of current world state for display at pause."""
    lines = []
    era = world.civilizations[0].tech_era.value.upper() if world.civilizations else "UNKNOWN"
    lines.append(f"=== Turn {world.turn} / {total_turns} | Era: {era} ===")
    lines.append("")
    lines.append("Faction Standings:")
    for civ in world.civilizations:
        lines.append(
            f"  {civ.name:20s} — pop:{civ.population} mil:{civ.military} "
            f"eco:{civ.economy} cul:{civ.culture} stb:{civ.stability} "
            f"tre:{civ.treasury} | Leader: {civ.leader.name} ({civ.leader.trait})"
        )
    lines.append("")

    # Relationships
    lines.append("Relationships:")
    printed_pairs: set[tuple[str, str]] = set()
    for src, targets in world.relationships.items():
        for dst, rel in targets.items():
            pair = tuple(sorted([src, dst]))
            if pair not in printed_pairs:
                printed_pairs.add(pair)
                lines.append(f"  {src} ↔ {dst}: {rel.disposition.value.upper()}")
    lines.append("")

    # Recent events
    recent = [e for e in world.events_timeline if e.turn >= max(0, world.turn - 5)]
    if recent:
        lines.append("Recent Events (last 5 turns):")
        for event in recent[-10:]:
            lines.append(f"  T{event.turn}: {event.description}")
        lines.append("")

    # Active conditions
    if world.active_conditions:
        lines.append("Active Conditions:")
        for cond in world.active_conditions:
            civs = ", ".join(cond.affected_civs)
            lines.append(
                f"  {cond.condition_type} on {civs} — "
                f"severity {cond.severity}, {cond.duration} turns remaining"
            )
        lines.append("")

    return "\n".join(lines)


def _print_help() -> None:
    """Print available commands."""
    print("\nAvailable commands:")
    print("  continue                         — Resume simulation until next pause")
    print('  inject <event_type> "<civ>"       — Queue event for next turn')
    print('  set "<civ>" <stat> <value>        — Modify a civ stat')
    print("  fork                             — Save current state as fork point")
    print("  quit                             — Compile chronicle and exit")
    print("  help                             — Show this message")
    print(f"\nValid event types: {sorted(VALID_INJECTABLE_EVENTS)}")
    print(f"Valid stats: {sorted(VALID_STATS)} (1-10 for core stats, 0+ for treasury)")
    print()


def interactive_pause(
    world: WorldState,
    memories: dict[str, MemoryStream],
    pending_injections: list,
    total_turns: int = 0,
    output_dir: Path = Path("output"),
) -> bool:
    """Pause handler for interactive mode. Returns True to continue, False to quit."""
    print("\n" + format_state_summary(world, total_turns))

    while True:
        try:
            raw = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            print("\nQuitting...")
            return False

        cmd, cmd_args = parse_command(raw)

        if cmd == "continue":
            return True

        elif cmd == "quit":
            return False

        elif cmd == "help":
            _print_help()

        elif cmd == "fork":
            fork_dir = output_dir / f"fork_save_t{world.turn}"
            fork_dir.mkdir(parents=True, exist_ok=True)
            world.save(fork_dir / "state.json")
            for civ_name, stream in memories.items():
                stream.save(fork_dir / f"memories_{sanitize_civ_name(civ_name)}.json")
            print(f"Fork saved to {fork_dir}")

        elif cmd == "inject":
            event_type, civ_name = cmd_args
            civ_names = [c.name for c in world.civilizations]
            if civ_name not in civ_names:
                print(f"Error: Civ '{civ_name}' not found. Valid civs: {civ_names}")
                continue
            pending_injections.append((event_type, civ_name))
            print(f"Queued: {event_type} -> {civ_name} (fires next turn)")

        elif cmd == "set":
            civ_name, stat, value = cmd_args
            civ = next((c for c in world.civilizations if c.name == civ_name), None)
            if civ is None:
                civ_names = [c.name for c in world.civilizations]
                print(f"Error: Civ '{civ_name}' not found. Valid civs: {civ_names}")
                continue
            setattr(civ, stat, value)
            print(f"Set {civ_name}.{stat} = {value}")

        elif cmd == "error":
            print(f"Error: {cmd_args}")


def run_interactive(
    args: argparse.Namespace,
    sim_client: Any = None,
    narrative_client: Any = None,
    scenario_config: Any = None,
) -> RunResult:
    """Run in interactive mode with pauses at configured intervals."""
    pause_every = args.pause_every or getattr(args, 'reflection_interval', None) or 10
    total_turns = args.turns or 50
    output_dir = Path(args.output).parent

    pending_injections: list[tuple[str, str]] = []

    def on_pause(world, memories, injections):
        return interactive_pause(
            world, memories, injections,
            total_turns=total_turns,
            output_dir=output_dir,
        )

    from chronicler.main import execute_run
    return execute_run(
        args,
        sim_client=sim_client,
        narrative_client=narrative_client,
        on_pause=on_pause,
        pause_every=pause_every,
        pending_injections=pending_injections,
        scenario_config=scenario_config,
    )
