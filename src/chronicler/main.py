"""Main entry point — orchestrates world generation, simulation, and chronicle output.

Usage:
    chronicler --seed 42 --turns 50 --civs 4 --regions 8 --output chronicle.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import anthropic

from chronicler.chronicle import ChronicleEntry, compile_chronicle
from chronicler.llm import LLMClient, create_clients
from chronicler.memory import MemoryStream, generate_reflection, should_reflect
from chronicler.models import Event, WorldState
from chronicler.narrative import NarrativeEngine
from chronicler.simulation import run_turn
from chronicler.world_gen import generate_world

DEFAULT_CONFIG = {
    "num_turns": 50,
    "num_civs": 4,
    "num_regions": 8,
    "reflection_interval": 10,
    "local_url": "http://localhost:1234/v1",  # LM Studio default
    "local_model": None,                       # Set to enable hybrid mode
    "narrative_model": "claude-sonnet-4-6",
}


def run_chronicle(
    seed: int = 42,
    num_turns: int = 50,
    num_civs: int = 4,
    num_regions: int = 8,
    output_path: Path = Path("output/chronicle.md"),
    state_path: Path | None = None,
    sim_client: LLMClient | None = None,
    narrative_client: LLMClient | None = None,
    reflection_interval: int = 10,
) -> None:
    """Run the full chronicle generation pipeline.

    Accepts two separate LLM clients:
    - sim_client: handles action selection (high volume, local model)
    - narrative_client: handles chronicle prose + reflections (Claude API)
    """
    engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)

    # Generate initial world
    world = generate_world(
        seed=seed,
        num_regions=num_regions,
        num_civs=num_civs,
    )

    # Initialize memory streams for each civilization
    memories: dict[str, MemoryStream] = {
        civ.name: MemoryStream(civilization_name=civ.name)
        for civ in world.civilizations
    }

    # Run simulation
    chronicle_entries: list[ChronicleEntry] = []
    era_reflections: dict[int, str] = {}

    mode = "hybrid (local sim + API narrative)" if type(sim_client).__name__ == "LocalClient" else "API-only"
    print(f"Generating chronicle for '{world.name}' — {num_turns} turns, {num_civs} civs [{mode}]")

    for turn_num in range(num_turns):
        # Run one turn
        chronicle_text = run_turn(
            world,
            action_selector=engine.action_selector,
            narrator=engine.narrator,
            seed=seed + turn_num,
        )

        # Record chronicle entry
        chronicle_entries.append(ChronicleEntry(
            turn=world.turn,
            text=chronicle_text,
        ))

        # Update memory streams with this turn's events
        turn_events = [e for e in world.events_timeline if e.turn == world.turn - 1]
        for event in turn_events:
            for actor in event.actors:
                if actor in memories:
                    memories[actor].add(
                        text=event.description or f"{event.event_type} occurred",
                        turn=world.turn,
                        importance=event.importance,
                    )

        # Generate era reflections at intervals (uses narrative_client for quality)
        if should_reflect(world.turn, interval=reflection_interval):
            era_start = world.turn - reflection_interval + 1
            era_end = world.turn
            reflection_texts: list[str] = []

            for civ_name, stream in memories.items():
                reflection = generate_reflection(
                    stream,
                    era_start=era_start,
                    era_end=era_end,
                    client=narrative_client,
                )
                reflection_texts.append(reflection)

            combined = "\n\n".join(reflection_texts)
            era_reflections[world.turn] = f"## Era: Turns {era_start}–{era_end}\n\n{combined}"
            print(f"  Era reflection generated for turns {era_start}-{era_end}")

        # Save state after EVERY turn (crash recovery — resume from last good state)
        if state_path:
            world.save(state_path)

        # Progress indicator
        if world.turn % 10 == 0:
            print(f"  Turn {world.turn}/{num_turns} complete")

    # Compile final chronicle
    output_text = compile_chronicle(
        world_name=world.name,
        entries=chronicle_entries,
        era_reflections=era_reflections,
        epilogue=f"Thus concludes the chronicle of {world.name}, spanning {num_turns} turns of history.",
    )

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text)
    print(f"\nChronicle written to {output_path} ({len(output_text)} characters)")

    # Save final state
    if state_path:
        world.save(state_path)
        print(f"Final world state saved to {state_path}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate an AI-driven civilization chronicle",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--turns", type=int, default=DEFAULT_CONFIG["num_turns"], help="Number of simulation turns")
    parser.add_argument("--civs", type=int, default=DEFAULT_CONFIG["num_civs"], help="Number of civilizations")
    parser.add_argument("--regions", type=int, default=DEFAULT_CONFIG["num_regions"], help="Number of regions")
    parser.add_argument("--output", type=str, default="output/chronicle.md", help="Output file path")
    parser.add_argument("--state", type=str, default="output/state.json", help="State file path")
    parser.add_argument("--resume", type=str, default=None, help="Resume from a saved state JSON file")
    parser.add_argument("--reflection-interval", type=int, default=DEFAULT_CONFIG["reflection_interval"])

    # Hybrid inference config
    parser.add_argument("--local-url", type=str, default=DEFAULT_CONFIG["local_url"],
                        help="LM Studio / local model API URL (OpenAI-compatible)")
    parser.add_argument("--local-model", type=str, default=DEFAULT_CONFIG["local_model"],
                        help="Local model name for simulation calls (enables hybrid mode)")
    parser.add_argument("--narrative-model", type=str, default=DEFAULT_CONFIG["narrative_model"],
                        help="Claude model for narrative generation")

    args = parser.parse_args()

    anthropic_client = anthropic.Anthropic()
    sim_client, narrative_client = create_clients(
        local_url=args.local_url,
        local_model=args.local_model,
        narrative_model=args.narrative_model,
        anthropic_client=anthropic_client,
    )

    run_chronicle(
        seed=args.seed,
        num_turns=args.turns,
        num_civs=args.civs,
        num_regions=args.regions,
        output_path=Path(args.output),
        state_path=Path(args.state),
        sim_client=sim_client,
        narrative_client=narrative_client,
        reflection_interval=args.reflection_interval,
    )


if __name__ == "__main__":
    main()
