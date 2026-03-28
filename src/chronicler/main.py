"""Main entry point — orchestrates world generation, simulation, and chronicle output.

Usage:
    chronicler --seed 42 --turns 50 --civs 4 --regions 8 --output chronicle.md

Default: fully local inference via LM Studio. No API key required.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from chronicler.bundle import assemble_bundle, write_bundle
from chronicler.climate import get_climate_phase
from chronicler.chronicle import compile_chronicle
from chronicler.models import ChronicleEntry, NarrativeRole
from chronicler.interestingness import find_boring_civs
from chronicler.llm import DEFAULT_LOCAL_URL, LLMClient, create_clients


def _tracks_tokens(client: Any) -> bool:
    """Check if an LLM client tracks token usage (API clients)."""
    return hasattr(client, "total_input_tokens") and isinstance(client.total_input_tokens, int)
from chronicler.memory import MemoryStream, generate_reflection, sanitize_civ_name, should_reflect
from chronicler.models import CivSnapshot, Event, RelationshipSnapshot, SettlementSummary, TurnSnapshot, WorldState
from chronicler.action_engine import ActionEngine
from chronicler.narrative import NarrativeEngine
from chronicler.simulation import apply_injected_event, run_turn
from chronicler.types import RunResult
from chronicler.world_gen import enrich_with_llm, generate_world
from chronicler.intelligence import compute_accuracy, get_perceived_stat

DEFAULT_CONFIG = {
    "seed": 42,
    "num_turns": 50,
    "num_civs": 4,
    "num_regions": 8,
    "reflection_interval": 10,
    "local_url": DEFAULT_LOCAL_URL,
}


class _DummyClient:
    """Fallback LLM client for deterministic-only runs (no API calls)."""
    model = "dummy"

    def complete(self, prompt: str, max_tokens: int = 100, system: str | None = None) -> str:
        return "DEVELOP"


def _create_ecology_runtime(world):
    """Create a dedicated EcologySimulator for --agents=off mode.

    Wraps construction so tests can mock this function without
    requiring the compiled Rust module.
    """
    try:
        from chronicler_agents import EcologySimulator
        from chronicler.agent_bridge import configure_ecology_runtime
        eco_sim = EcologySimulator()
        # Wire river topology and ecology config from tuning overrides
        configure_ecology_runtime(eco_sim, world)
        return eco_sim
    except ImportError:
        return None


def _create_politics_runtime(world):
    """Create a dedicated PoliticsSimulator for --agents=off mode.

    Wraps construction so tests can mock this function without
    requiring the compiled Rust module.
    """
    try:
        from chronicler_agents import PoliticsSimulator
        from chronicler.politics import configure_politics_runtime
        pol_sim = PoliticsSimulator()
        configure_politics_runtime(pol_sim, world)
        return pol_sim
    except ImportError:
        return None


def execute_run(
    args: argparse.Namespace,
    sim_client: LLMClient | None = None,
    narrative_client: LLMClient | None = None,
    world: WorldState | None = None,
    memories: dict[str, MemoryStream] | None = None,
    on_pause: Callable[[WorldState, dict[str, MemoryStream], list], bool] | None = None,
    pause_every: int | None = None,
    pending_injections: list[tuple[str, str]] | None = None,
    scenario_config: Any | None = None,
    provenance_header: str | None = None,
    on_turn: Callable | None = None,
    quit_check: Callable[[], bool] | None = None,
) -> RunResult:
    """Shared entry point for single runs, batch, fork, and interactive modes.

    Accepts an args namespace plus optional pre-loaded world, memories, and
    callbacks. Returns a RunResult with aggregate stats.

    Parameters
    ----------
    args : argparse.Namespace
        Must contain: seed, turns, civs, regions, output, state, resume,
        reflection_interval, llm_actions, scenario (and optionally pause_every).
    sim_client, narrative_client : LLMClient or None
        LLM clients for simulation and narration. Falls back to _DummyClient.
    world : WorldState or None
        Pre-loaded world state (for fork/resume). Generated if None.
    memories : dict or None
        Pre-loaded memory streams. Initialized fresh if None.
    on_pause : callable or None
        Called every pause_every turns with (world, memories).
    pause_every : int or None
        Turn interval for on_pause callback. Overrides args.pause_every.
    pending_injections : list or None
        List of (event_type, target_civ_name) tuples to drain before turns.
    scenario_config : ScenarioConfig or None
        Scenario overrides to apply to the world.
    provenance_header : str or None
        Optional header text prepended to the compiled chronicle.
    """
    # Fallback clients
    _sim = sim_client or _DummyClient()
    _narr = narrative_client or _DummyClient()
    _narrator_mode = getattr(args, "narrator", "local")
    _api_mode = _narrator_mode != "local"

    # Extract run parameters from args
    seed = args.seed
    num_turns = args.turns
    num_civs = args.civs
    num_regions = args.regions
    output_path = Path(args.output)
    state_path = Path(args.state) if args.state else None
    resume_path = Path(args.resume) if getattr(args, "resume", None) else None
    reflection_interval = getattr(args, "reflection_interval", 10) or 10
    use_llm_actions = getattr(args, "llm_actions", False)
    _pause_every = pause_every or getattr(args, "pause_every", None)

    # Use scenario_config from arg if not passed directly
    if scenario_config is None:
        sc_path = getattr(args, "scenario", None)
        if sc_path:
            from chronicler.scenario import load_scenario
            scenario_config = load_scenario(Path(sc_path))

    # Extract presentation-layer config for narrative engine
    event_flavor = scenario_config.event_flavor if scenario_config else None
    narrative_style = scenario_config.narrative_style if scenario_config else None
    engine = NarrativeEngine(
        sim_client=_sim,
        narrative_client=_narr,
        event_flavor=event_flavor,
        narrative_style=narrative_style,
    )

    # In simulate-only mode, replace narrator with a no-op
    _simulate_only = getattr(args, "simulate_only", False)
    if _simulate_only or _api_mode:
        _noop_narrator = lambda world, events: ""
    else:
        _noop_narrator = None

    # World setup
    if world is not None:
        start_turn = world.turn
    elif resume_path:
        world = WorldState.load(resume_path)
        start_turn = world.turn
        print(f"Resuming from {resume_path} at turn {start_turn}")
    else:
        world = generate_world(
            seed=seed,
            num_regions=num_regions,
            num_civs=num_civs,
        )
        start_turn = 0

        # Apply scenario overrides if provided
        if scenario_config:
            from chronicler.scenario import apply_scenario
            apply_scenario(world, scenario_config)
            print(f"  Scenario: {scenario_config.name}")
            if scenario_config.description:
                print(f"    {scenario_config.description}")

        # Enrich civs with LLM-generated goals
        if sim_client:
            try:
                enrich_with_llm(world, sim_client)
            except Exception:
                pass  # Goals remain empty on failure — non-fatal

    # Apply tuning overrides to world state
    if getattr(args, "tuning_overrides", None):
        world.tuning_overrides = args.tuning_overrides

    # Apply preset (values don't override explicit tuning or CLI flags)
    if getattr(args, "preset", None):
        from chronicler.tuning import apply_preset
        apply_preset(world.tuning_overrides, args.preset)

    # Wire CLI simulation multipliers into tuning_overrides
    from chronicler.tuning import (
        K_AGGRESSION_BIAS, K_TECH_DIFFUSION_RATE, K_RESOURCE_ABUNDANCE,
        K_TRADE_FRICTION, K_SEVERITY_MULTIPLIER, K_CULTURAL_DRIFT_SPEED,
        K_RELIGION_INTENSITY, K_SECESSION_LIKELIHOOD,
    )
    _multiplier_flags = {
        "aggression_bias": K_AGGRESSION_BIAS,
        "tech_diffusion_rate": K_TECH_DIFFUSION_RATE,
        "resource_abundance": K_RESOURCE_ABUNDANCE,
        "trade_friction": K_TRADE_FRICTION,
        "severity_multiplier": K_SEVERITY_MULTIPLIER,
        "cultural_drift_speed": K_CULTURAL_DRIFT_SPEED,
        "religion_intensity": K_RELIGION_INTENSITY,
        "secession_likelihood": K_SECESSION_LIKELIHOOD,
    }
    for attr, key in _multiplier_flags.items():
        val = getattr(args, attr, None)
        if val is not None:
            world.tuning_overrides[key] = val

    # M28: Agent mode wiring
    agent_mode = getattr(args, "agents", "off")
    agent_bridge = None
    if agent_mode in ("demographics-only", "shadow", "hybrid"):
        world.agent_mode = agent_mode
        from chronicler.agent_bridge import AgentBridge
        _use_sidecar = getattr(args, "validation_sidecar", False)
        agent_bridge = AgentBridge(
            world,
            mode=agent_mode,
            validation_sidecar=_use_sidecar,
            output_dir=output_path.parent if _use_sidecar else None,
            relationship_stats=getattr(args, "relationship_stats", False),
        )

    # M54a: Off-mode ecology runtime (Rust ecology without agent pool)
    ecology_runtime = None
    if agent_mode == "off":
        ecology_runtime = _create_ecology_runtime(world)

    # M54c: Off-mode politics runtime (Rust politics without agent pool)
    politics_runtime = None
    if agent_mode == "off":
        politics_runtime = _create_politics_runtime(world)

    # M43b: Economy tracker (persists across turns for EMA-based shock detection)
    economy_tracker = None
    if agent_bridge is not None:
        from chronicler.economy import EconomyTracker
        economy_tracker = EconomyTracker()

    # Initialize memory streams if not provided
    if memories is None:
        memories = {
            civ.name: MemoryStream(civilization_name=civ.name)
            for civ in world.civilizations
        }

    # Run simulation
    chronicle_entries: list[ChronicleEntry] = []
    era_reflections: dict[int, str] = {}
    gap_summaries = None  # Set by curated narration in API mode
    history: list[TurnSnapshot] = []

    remaining = num_turns - start_turn
    sim_model = getattr(_sim, "model", "unknown") or "LM Studio default"
    narr_model = getattr(_narr, "model", "unknown") or "LM Studio default"
    print(f"Generating chronicle for '{world.name}' — {remaining} turns, {len(world.civilizations)} civs")
    print(f"  Sim model: {sim_model} | Narrative model: {narr_model} [local inference]")

    # Pending injections list — shared mutable object with on_pause callback
    _pending = pending_injections if pending_injections is not None else []

    for turn_num in range(start_turn, num_turns):
        # Drain pending injections before each turn
        while _pending:
            event_type, target_civ = _pending.pop(0)
            injected_events = apply_injected_event(event_type, target_civ, world)
            world.events_timeline.extend(injected_events)

        named_events_before = len(world.named_events)

        # Create action engine fresh each turn (needs current world state)
        action_engine = ActionEngine(world)

        if use_llm_actions and sim_client:
            def action_selector(civ, world, _engine=action_engine, _narr=engine):
                try:
                    action = _narr.select_action(civ, world)
                    eligible = _engine.get_eligible_actions(civ)
                    if action in eligible:
                        return action
                except Exception:
                    pass
                return _engine.select_action(civ, seed=world.seed)
        else:
            def action_selector(civ, world, _engine=action_engine):
                return _engine.select_action(civ, seed=world.seed)

        # Run one turn
        chronicle_text = run_turn(
            world,
            action_selector=action_selector,
            narrator=_noop_narrator or engine.narrator,
            seed=seed + turn_num,
            agent_bridge=agent_bridge,
            economy_tracker=economy_tracker,
            ecology_runtime=ecology_runtime,
            politics_runtime=politics_runtime,
            force_settlement_detection=(turn_num == num_turns - 1),
        )

        # Capture per-turn snapshot for viewer bundle
        # M24: cache accuracy for snapshot
        _acc_cache: dict[tuple[str, str], float] = {}
        for _obs in world.civilizations:
            for _tgt in world.civilizations:
                if _obs.name != _tgt.name:
                    _acc_cache[(_obs.name, _tgt.name)] = compute_accuracy(_obs, _tgt, world)
        snapshot = TurnSnapshot(
            turn=world.turn,
            civ_stats={
                civ.name: CivSnapshot(
                    population=civ.population,
                    military=civ.military,
                    economy=civ.economy,
                    culture=civ.culture,
                    stability=civ.stability,
                    treasury=civ.treasury,
                    asabiya=civ.asabiya,
                    asabiya_variance=civ.asabiya_variance,
                    tech_era=civ.tech_era,
                    trait=civ.leader.trait,
                    regions=list(civ.regions),
                    leader_name=civ.leader.name,
                    alive=True,
                    is_vassal=any(vr.vassal == civ.name for vr in world.vassal_relations),
                    is_fallen_empire=(civ.peak_region_count >= 5 and len(civ.regions) == 1),
                    in_twilight=(civ.decline_turns >= 20 and len(civ.regions) == 1),
                    federation_name=next((f.name for f in world.federations if civ.name in f.members), None),
                    prestige=civ.prestige,
                    capital_region=civ.capital_region,
                    great_persons=[{"name": gp.name, "role": gp.role, "trait": gp.trait} for gp in civ.great_persons if gp.active],
                    traditions=list(civ.traditions),
                    folk_heroes=[{"name": fh["name"], "role": fh["role"]} for fh in civ.folk_heroes],
                    active_crisis=civ.succession_crisis_turns_remaining > 0,
                    civ_stress=civ.civ_stress,
                    active_focus=civ.active_focus,
                    factions=civ.factions.model_copy(deep=True),
                    action_counts=dict(civ.action_counts),
                    max_precap_weight=civ.max_precap_weight,
                    last_action=(world.action_history.get(civ.name, [])[-1] if world.action_history.get(civ.name) else None),
                    gini=getattr(agent_bridge, '_gini_by_civ', {}).get(civ_idx, 0.0) if agent_bridge else 0.0,
                    war_weariness=civ.war_weariness,
                    peace_momentum=civ.peace_momentum,
                )
                for civ_idx, civ in enumerate(world.civilizations)
            },
            ecology={r.name: r.ecology.model_dump() for r in world.regions},
            region_control={
                region.name: region.controller
                for region in world.regions
            },
            relationships={
                civ_a: {
                    civ_b: RelationshipSnapshot(disposition=rel.disposition.value)
                    for civ_b, rel in inner.items()
                }
                for civ_a, inner in world.relationships.items()
            },
            vassal_relations=[vr.model_dump() for vr in world.vassal_relations],
            federations=[f.model_dump() for f in world.federations],
            proxy_wars=[pw.model_dump() for pw in world.proxy_wars],
            exile_modifiers=[em.model_dump() for em in world.exile_modifiers],
            capitals={civ.name: civ.capital_region for civ in world.civilizations if civ.capital_region},
            peace_turns=world.peace_turns,
            region_cultural_identity={r.name: r.cultural_identity for r in world.regions},
            movements_summary=[{"id": m.id, "value_affinity": m.value_affinity, "adherent_count": len(m.adherents), "origin_civ": m.origin_civ} for m in world.movements],
            stress_index=world.stress_index,
            pandemic_regions=[p.region_name for p in world.pandemic_state],
            climate_phase=get_climate_phase(world.turn, world.climate_config).value,
            active_conditions=[
                {"type": c.condition_type, "severity": c.severity, "duration": c.duration}
                for c in world.active_conditions
            ],
            per_pair_accuracy={
                obs_name: {
                    tgt_name: acc
                    for tgt_name, acc in (
                        (t.name, _acc_cache[(obs_name, t.name)])
                        for t in world.civilizations if t.name != obs_name
                    )
                    if acc > 0.0
                }
                for obs_name in (c.name for c in world.civilizations)
            },
            perception_errors={
                obs_name: {
                    tgt_name: {
                        stat: pv - getattr(tgt, stat)
                        for stat in ("military", "economy", "stability")
                        if (pv := get_perceived_stat(obs, tgt, stat, world)) is not None
                    }
                    for tgt in world.civilizations
                    for tgt_name in [tgt.name]
                    if tgt_name != obs_name and _acc_cache.get((obs_name, tgt_name), 0.0) > 0.0
                }
                for obs in world.civilizations
                for obs_name in [obs.name]
            },
            # M56a: Settlement summary
            settlement_source_turn=getattr(world, '_settlement_source_turn', 0),
            settlement_count=sum(
                len([s for s in r.settlements if s.status.value in ("active", "dissolving")])
                for r in world.regions
            ),
            candidate_count=len(world.settlement_candidates),
            total_settlement_population=sum(
                s.population_estimate
                for r in world.regions for s in r.settlements
                if s.status.value in ("active", "dissolving")
            ),
            active_settlements=sorted(
                [
                    SettlementSummary(
                        settlement_id=s.settlement_id, name=s.name,
                        region_name=s.region_name, population_estimate=s.population_estimate,
                        centroid_x=s.centroid_x, centroid_y=s.centroid_y,
                        founding_turn=s.founding_turn, status=s.status.value,
                    )
                    for r in world.regions for s in r.settlements
                    if s.status.value in ("active", "dissolving")
                ],
                key=lambda ss: (ss.region_name, ss.settlement_id),
            ),
            founded_this_turn=sorted(getattr(world, '_settlement_founded_this_turn', [])),
            dissolved_this_turn=sorted(getattr(world, '_settlement_dissolved_this_turn', [])),
        )

        # M56b: Urban fraction aggregation from agent snapshot
        urban_by_civ: dict[str, tuple[int, int]] = {}  # civ_name -> (urban_count, total_count)
        if agent_bridge and hasattr(world, '_agent_snapshot') and world._agent_snapshot is not None:
            snap = world._agent_snapshot
            if "settlement_id" in snap.column_names:
                civ_col = snap.column("civ_affinity").to_pylist()
                sid_col = snap.column("settlement_id").to_pylist()
                region_col = snap.column("region").to_pylist() if "region" in snap.column_names else [None] * len(civ_col)
                for civ_id, region_id, sid in zip(civ_col, region_col, sid_col):
                    civ_name = None
                    try:
                        region_idx = int(region_id)
                    except (TypeError, ValueError):
                        region_idx = -1
                    if 0 <= region_idx < len(world.regions):
                        controller = world.regions[region_idx].controller
                        if controller is not None:
                            civ_name = controller
                    if civ_name is None:
                        try:
                            civ_idx = int(civ_id)
                        except (TypeError, ValueError):
                            civ_idx = -1
                        if 0 <= civ_idx < len(world.civilizations):
                            civ_name = world.civilizations[civ_idx].name
                    if civ_name is None:
                        continue
                    u, t = urban_by_civ.get(civ_name, (0, 0))
                    urban_by_civ[civ_name] = (u + (1 if sid > 0 else 0), t + 1)

        for civ_name, cs in snapshot.civ_stats.items():
            if civ_name in urban_by_civ:
                u, t = urban_by_civ[civ_name]
                cs.urban_agents = u
                cs.urban_fraction = u / t if t > 0 else 0.0

        total_urban = sum(u for u, _ in urban_by_civ.values())
        total_agents = sum(t for _, t in urban_by_civ.values())
        snapshot.urban_agent_count = total_urban
        snapshot.urban_fraction = total_urban / total_agents if total_agents > 0 else 0.0

        history.append(snapshot)

        # Record chronicle entry
        chronicle_entries.append(ChronicleEntry(
            turn=world.turn, covers_turns=(world.turn, world.turn),
            events=[], named_events=[],
            narrative=chronicle_text, importance=5.0,
            narrative_role=NarrativeRole.RESOLUTION,
            causal_links=[],
        ))

        # on_turn callback — fires after each turn's data is captured
        if on_turn is not None:
            turn_events = [e for e in world.events_timeline if e.turn == world.turn - 1]
            turn_named = world.named_events[named_events_before:]
            on_turn(snapshot, chronicle_text, turn_events, turn_named)

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

        # Save memory streams every turn
        output_dir = output_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        for civ_name, stream in memories.items():
            safe_name = sanitize_civ_name(civ_name)
            stream.save(output_dir / f"memories_{safe_name}.json")

        # Generate era reflections at intervals
        if not _api_mode and should_reflect(world.turn, interval=reflection_interval):
            era_start = world.turn - reflection_interval + 1
            era_end = world.turn
            reflection_texts: list[str] = []

            for civ_name, stream in memories.items():
                reflection = generate_reflection(
                    stream,
                    era_start=era_start,
                    era_end=era_end,
                    client=_narr,
                )
                reflection_texts.append(reflection)

            combined = "\n\n".join(reflection_texts)
            era_reflections[world.turn] = f"## Era: Turns {era_start}\u2013{era_end}\n\n{combined}"
            print(f"  Era reflection generated for turns {era_start}-{era_end}")

        # Save state after EVERY turn (crash recovery — resume from last good state)
        if state_path:
            world.save(state_path)

        # on_pause callback — returns False to quit early
        if _pause_every and on_pause and world.turn % _pause_every == 0:
            should_continue = on_pause(world, memories, _pending)
            if not should_continue:
                break

        # quit_check — for graceful mid-run shutdown (e.g., live mode quit)
        if quit_check is not None and quit_check():
            break

        # Progress indicator
        if world.turn % 10 == 0:
            print(f"  Turn {world.turn}/{num_turns} complete")

    # M44: Post-loop curated narration for API mode
    if _api_mode:
        from chronicler.curator import curate

        # Collect named character names for curator scoring
        named_chars = set()
        for gp_list in (getattr(civ, "great_persons", []) for civ in world.civilizations):
            for gp in gp_list:
                if gp.active and gp.agent_id is not None:
                    named_chars.add(gp.name)

        # M45: Build gp_by_name for arc scoring
        gp_by_name = {}
        for civ in world.civilizations:
            for gp in civ.great_persons:
                if gp.active and gp.agent_id is not None:
                    gp_by_name[gp.name] = gp
        for gp in world.retired_persons:
            if gp.death_turn is not None:
                gp_by_name[gp.name] = gp

        moments, gap_summaries = curate(
            events=world.events_timeline,
            named_events=world.named_events,
            history=history,
            budget=getattr(args, "budget", 50),
            seed=seed,
            named_characters=named_chars if named_chars else None,
            gp_by_name=gp_by_name if gp_by_name else None,
        )

        def progress_cb(completed: int, total: int, eta: float | None) -> None:
            eta_str = f" (ETA: {eta:.1f}s)" if eta is not None else ""
            print(f"  Narrating {completed}/{total}{eta_str}")

        # M45: Include retired persons for dead character arc context
        all_great_persons = list(gp_by_name.values()) if gp_by_name else None

        chronicle_entries = engine.narrate_batch(
            moments, history, gap_summaries, on_progress=progress_cb,
            great_persons=all_great_persons,
            gp_by_name=gp_by_name if gp_by_name else None,
            world=world,
        )

        print(f"API narration: curated {len(moments)} moments from {len(world.events_timeline)} events")

        # Token usage summary
        if _tracks_tokens(_narr):
            inp = _narr.total_input_tokens
            out = _narr.total_output_tokens
            print(f"API narration: {_narr.call_count} calls, "
                  f"{inp/1000:.1f}K input + {out/1000:.1f}K output tokens")

    if agent_bridge is not None:
        agent_bridge.write_final_sidecar_snapshot(world)
        agent_bridge.close()

    # Compile final chronicle
    actual_turns = world.turn - start_turn
    if world.turn < num_turns:
        epilogue = f"> Chronicle ended early at turn {world.turn} of {num_turns}."
    else:
        epilogue = f"Thus concludes the chronicle of {world.name}, spanning {actual_turns} turns of history."
    output_text = compile_chronicle(
        world_name=world.name,
        entries=chronicle_entries,
        era_reflections=era_reflections,
        epilogue=epilogue,
        gap_summaries=gap_summaries,
    )

    # Prepend provenance header if provided
    if provenance_header:
        output_text = provenance_header + "\n\n" + output_text

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text, encoding="utf-8")
    print(f"\nChronicle written to {output_path} ({len(output_text)} characters)")

    # Save final state
    if state_path:
        world.save(state_path)
        print(f"Final world state saved to {state_path}")

    # --- Compute RunResult ---
    output_dir = output_path.parent

    # Count events from start_turn onward only
    war_count = sum(
        1 for e in world.events_timeline
        if e.turn >= start_turn and e.event_type == "war"
    )
    collapse_count = sum(
        1 for e in world.events_timeline
        if e.turn >= start_turn and e.event_type == "collapse"
    )
    tech_advancement_count = sum(
        1 for e in world.events_timeline
        if e.turn >= start_turn and e.event_type == "tech_advancement"
    )
    named_event_count = sum(
        1 for ne in world.named_events
        if ne.turn >= start_turn
    )

    # Count reflections from start_turn onward
    reflection_count = 0
    for stream in memories.values():
        reflection_count += sum(
            1 for r in stream.reflections if r.turn >= start_turn
        )

    # Action distribution from civ.action_counts
    action_distribution: dict[str, dict[str, int]] = {}
    all_action_types: set[str] = set()
    for civ in world.civilizations:
        action_distribution[civ.name] = dict(civ.action_counts)
        all_action_types.update(civ.action_counts.keys())
    distinct_action_count = len(all_action_types)

    # Max stat swing: variance of total stats across civs
    if world.civilizations:
        totals = [
            civ.population + civ.military + civ.economy + civ.culture + civ.stability
            for civ in world.civilizations
        ]
        mean_total = sum(totals) / len(totals)
        variance = sum((t - mean_total) ** 2 for t in totals) / len(totals)
        max_stat_swing = float(variance)
    else:
        max_stat_swing = 0.0

    # Dominant faction: civ with highest total stats
    if world.civilizations:
        dominant_civ = max(
            world.civilizations,
            key=lambda c: c.population + c.military + c.economy + c.culture + c.stability,
        )
        dominant_faction = dominant_civ.name
    else:
        dominant_faction = ""

    total_turns = world.turn - start_turn

    result = RunResult(
        seed=seed,
        output_dir=output_dir,
        war_count=war_count,
        collapse_count=collapse_count,
        named_event_count=named_event_count,
        distinct_action_count=distinct_action_count,
        reflection_count=reflection_count,
        tech_advancement_count=tech_advancement_count,
        max_stat_swing=max_stat_swing,
        action_distribution=action_distribution,
        dominant_faction=dominant_faction,
        total_turns=total_turns,
    )
    result.boring_civs = find_boring_civs(result)

    # Write viewer bundle
    from chronicler.interestingness import score_run
    sim_model_name = getattr(_sim, "model", "unknown") or "unknown"
    narr_model_name = getattr(_narr, "model", "unknown") or "unknown"
    interestingness_weights = None
    if scenario_config and hasattr(scenario_config, "interestingness_weights"):
        interestingness_weights = scenario_config.interestingness_weights
    bundle = assemble_bundle(
        world=world,
        history=history,
        chronicle_entries=chronicle_entries,
        era_reflections=era_reflections,
        sim_model=sim_model_name,
        narrative_model=narr_model_name,
        interestingness_score=score_run(result, interestingness_weights),
        gap_summaries=gap_summaries,
    )
    # M44: narrator provenance metadata
    bundle["metadata"]["narrator_mode"] = _narrator_mode
    if _tracks_tokens(_narr):
        bundle["metadata"]["api_input_tokens"] = _narr.total_input_tokens
        bundle["metadata"]["api_output_tokens"] = _narr.total_output_tokens

    # M53: relationship stats metadata
    if agent_bridge is not None and agent_bridge._collect_rel_stats:
        bundle["metadata"]["relationship_stats"] = agent_bridge.relationship_stats

    # M57b: household stats metadata (always collected in agent modes)
    if agent_bridge is not None:
        bundle["metadata"]["household_stats"] = agent_bridge.household_stats

    bundle_path = output_path.parent / "chronicle_bundle.json"
    write_bundle(bundle, bundle_path, world=world)
    print(f"Viewer bundle written to {bundle_path}")

    return result


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
    resume_path: Path | None = None,
    use_llm_actions: bool = False,
    scenario_config: "ScenarioConfig | None" = None,
) -> None:
    """Legacy wrapper — delegates to execute_run().

    Preserves the original API for backward compatibility.
    """
    args = argparse.Namespace(
        seed=seed,
        turns=num_turns,
        civs=num_civs,
        regions=num_regions,
        output=str(output_path),
        state=str(state_path) if state_path else None,
        resume=str(resume_path) if resume_path else None,
        reflection_interval=reflection_interval,
        llm_actions=use_llm_actions,
        scenario=None,  # Pass scenario_config directly
        pause_every=None,
    )
    execute_run(
        args,
        sim_client=sim_client,
        narrative_client=narrative_client,
        scenario_config=scenario_config,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Generate an AI-driven civilization chronicle (local inference via LM Studio)",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--turns", type=int, default=None, help="Number of simulation turns")
    parser.add_argument("--civs", type=int, default=None, help="Number of civilizations")
    parser.add_argument("--regions", type=int, default=None, help="Number of regions")
    parser.add_argument("--output", type=str, default="output/chronicle.md", help="Output file path")
    parser.add_argument("--state", type=str, default="output/state.json", help="State file path")
    parser.add_argument("--resume", type=str, default=None, help="Resume from a saved state JSON file")
    parser.add_argument("--reflection-interval", type=int, default=None)
    parser.add_argument("--local-url", type=str, default=DEFAULT_CONFIG["local_url"],
                        help="LM Studio / local model API URL (OpenAI-compatible)")
    parser.add_argument("--sim-model", type=str, default=None,
                        help="Model name for simulation calls (default: LM Studio's loaded model)")
    parser.add_argument("--narrative-model", type=str, default=None,
                        help="Model name for narrative generation (default: LM Studio's loaded model)")
    parser.add_argument("--llm-actions", action="store_true", default=False,
                        help="Use LLM for action selection (default: deterministic engine)")
    parser.add_argument("--scenario", type=str, default=None,
                        help="Path to a YAML scenario file")
    # --- M10 workflow flags ---
    parser.add_argument("--batch", type=int, default=None,
                        help="Run N chronicles with sequential seeds")
    parser.add_argument("--parallel", type=int, nargs="?", const=-1, default=None,
                        help="Parallel workers for batch mode (default: cpu_count-1). "
                             "Mutually exclusive with --llm-actions.")
    parser.add_argument("--fork", type=str, default=None,
                        help="Fork from a saved state.json with a new seed")
    parser.add_argument("--interactive", action="store_true", default=False,
                        help="Interactive mode: pause at intervals for commands")
    parser.add_argument("--pause-every", type=int, default=None,
                        help="Pause interval in turns for interactive mode (default: reflection_interval)")
    parser.add_argument("--live", action="store_true", default=False,
                        help="Live mode: start WebSocket server for viewer connection")
    parser.add_argument("--live-port", type=int, default=8765,
                        help="WebSocket server port for live mode (default: 8765)")
    parser.add_argument("--simulate-only", action="store_true",
                        help="Run simulation without LLM narrative generation")
    parser.add_argument("--agents", type=str, default="off",
                        choices=["off", "demographics-only", "shadow", "hybrid"],
                        help="Agent mode: off (aggregate), demographics-only, shadow (compare), hybrid (agent-driven)")
    parser.add_argument("--tuning", type=str, default=None,
                        help="Path to tuning YAML file for constant overrides")
    parser.add_argument("--seed-range", type=str, default=None,
                        help="Seed range for batch mode (e.g., 1-200)")
    parser.add_argument("--analyze", type=str, default=None,
                        help="Analyze a batch directory and produce batch_report.json")
    parser.add_argument("--compare", type=str, default=None,
                        help="Compare against a baseline batch_report.json (delta-only output)")
    parser.add_argument("--checkpoints", type=str, default=None,
                        help="Comma-separated checkpoint turns for analytics (e.g., 25,50,100)")
    # --- Simulation multipliers (Tier 1 knobs) ---
    parser.add_argument("--aggression-bias", type=float, default=None,
                        help="WAR/EXPAND weight multiplier (default 1.0, >1 = more aggressive)")
    parser.add_argument("--tech-diffusion-rate", type=float, default=None,
                        help="Tech spread probability multiplier (default 1.0)")
    parser.add_argument("--resource-abundance", type=float, default=None,
                        help="Global resource production multiplier (default 1.0)")
    parser.add_argument("--trade-friction", type=float, default=None,
                        help="Trade route cost multiplier (default 1.0, >1 = harder trade)")
    parser.add_argument("--severity-multiplier", type=float, default=None,
                        help="Global negative event severity multiplier (default 1.0)")
    parser.add_argument("--cultural-drift-speed", type=float, default=None,
                        help="Cultural value drift multiplier (default 1.0)")
    parser.add_argument("--religion-intensity", type=float, default=None,
                        help="Religious event frequency multiplier (default 1.0)")
    parser.add_argument("--secession-likelihood", type=float, default=None,
                        help="Secession check weight multiplier (default 1.0)")
    parser.add_argument("--preset", type=str, default=None,
                        choices=["pangaea", "archipelago", "golden-age", "dark-age", "ice-age", "silk-road"],
                        help="Preset parameter bundle (values don't override explicit flags)")
    parser.add_argument("--narrative-voice", type=str, default=None,
                        choices=["chronicle", "epic", "academic", "journalistic", "mythic"],
                        help="Narrative voice preset for LLM narration")
    # --- M20a narration pipeline flags ---
    parser.add_argument("--narrate", type=Path, default=None,
                        help="Narrate a simulate-only bundle")
    parser.add_argument("--budget", type=int, default=50,
                        help="Number of moments to narrate")
    parser.add_argument("--narrate-output", type=Path, default=None,
                        help="Output path for narrated bundle")
    parser.add_argument("--narrator", type=str, default="local",
                        choices=["local", "api", "gemini"],
                        help="Narrator backend: local (LM Studio), api (Claude API), or gemini (Gemini API)")
    parser.add_argument("--relationship-stats", action="store_true",
                        help="Enable per-tick relationship distribution snapshots")
    parser.add_argument("--validation-sidecar", action="store_true",
                        help="Write heavy validation sidecars (graph snapshots, agent aggregates)")
    return parser


def _run_narrate(args: argparse.Namespace) -> None:
    """Load a simulate-only bundle, curate moments, and narrate them."""
    import json as _json
    from chronicler.curator import curate
    from chronicler.models import Event, NamedEvent, TurnSnapshot, WorldState

    bundle_path = Path(args.narrate)
    if not bundle_path.exists():
        print(f"Error: Bundle not found: {bundle_path}", file=sys.stderr)
        sys.exit(1)

    with open(bundle_path) as f:
        bundle = _json.load(f)

    # Deserialize events, named_events, history
    events = [Event.model_validate(e) for e in bundle.get("events_timeline", bundle.get("events", []))]
    named_events = [NamedEvent.model_validate(ne) for ne in bundle.get("named_events", [])]
    history = [TurnSnapshot.model_validate(snap) for snap in bundle.get("history", [])]
    world = None
    if bundle.get("world_state") is not None:
        world = WorldState.model_validate(bundle["world_state"])
    seed = bundle.get("metadata", {}).get("seed", 42)
    budget = args.budget

    # Create LLM clients
    sim_client, narrative_client = create_clients(
        local_url=args.local_url,
        sim_model=getattr(args, "sim_model", None),
        narrative_model=getattr(args, "narrative_model", None),
        narrator=getattr(args, "narrator", "local"),
    )

    # M40: Collect named character names for curator scoring
    named_chars = set()
    for civ_data in bundle.get("world_state", {}).get("civilizations", []):
        for gp in civ_data.get("great_persons", []):
            if gp.get("active") and gp.get("agent_id") is not None:
                named_chars.add(gp.get("name", ""))

    # M45: Build gp_by_name for arc scoring
    from chronicler.models import GreatPerson as _GP
    gp_by_name = {}
    for civ_data in bundle.get("world_state", {}).get("civilizations", []):
        for gp_data in civ_data.get("great_persons", []):
            if gp_data.get("active") and gp_data.get("agent_id") is not None:
                gp_by_name[gp_data.get("name", "")] = _GP(**gp_data)
    for gp_data in bundle.get("world_state", {}).get("retired_persons", []):
        if gp_data.get("death_turn") is not None:
            gp_by_name[gp_data.get("name", "")] = _GP(**gp_data)

    # Curate moments
    moments, gap_summaries = curate(
        events=events,
        named_events=named_events,
        history=history,
        budget=budget,
        seed=seed,
        named_characters=named_chars if named_chars else None,
        gp_by_name=gp_by_name if gp_by_name else None,
    )

    print(f"Curated {len(moments)} moments from {len(events)} events (budget={budget})")

    # Narrate
    engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)

    def progress_cb(completed: int, total: int, eta: float | None) -> None:
        eta_str = f" (ETA: {eta:.1f}s)" if eta is not None else ""
        print(f"  Narrating {completed}/{total}{eta_str}")

    # M45: Include retired persons for dead character arc context
    all_great_persons = list(gp_by_name.values()) if gp_by_name else None

    chronicle_entries = engine.narrate_batch(
        moments, history, gap_summaries, on_progress=progress_cb,
        great_persons=all_great_persons,
        gp_by_name=gp_by_name if gp_by_name else None,
        world=world,
    )

    # M44: Token summary
    if _tracks_tokens(narrative_client):
        inp = narrative_client.total_input_tokens
        out = narrative_client.total_output_tokens
        print(f"API narration: {narrative_client.call_count} calls, "
              f"{inp/1000:.1f}K input + {out/1000:.1f}K output tokens")

    # Write output
    output_path = args.narrate_output
    if output_path is None:
        output_path = bundle_path.parent / f"{bundle_path.stem}_narrated.json"

    result = {
        "chronicle_entries": [entry.model_dump() for entry in chronicle_entries],
        "gap_summaries": [gs.model_dump() for gs in gap_summaries],
        "metadata": bundle.get("metadata", {}),
    }

    # M44: narrator provenance
    result["metadata"]["narrator_mode"] = getattr(args, "narrator", "local")
    if _tracks_tokens(narrative_client):
        result["metadata"]["api_input_tokens"] = narrative_client.total_input_tokens
        result["metadata"]["api_output_tokens"] = narrative_client.total_output_tokens

    with open(output_path, "w", encoding="utf-8") as f:
        _json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Narrated {len(chronicle_entries)} entries -> {output_path}")


def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    # --- Mutual exclusion validation ---
    mode_flags = []
    if args.batch:
        mode_flags.append("--batch")
    if args.fork:
        mode_flags.append("--fork")
    if args.interactive:
        mode_flags.append("--interactive")
    if args.live:
        mode_flags.append("--live")
    if args.resume:
        mode_flags.append("--resume")
    if getattr(args, "analyze", None):
        mode_flags.append("--analyze")
    if getattr(args, "narrate", None):
        mode_flags.append("--narrate")
    if len(mode_flags) > 1:
        print(f"Error: {' and '.join(mode_flags)} are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    if args.parallel is not None and args.llm_actions:
        print("Error: Cannot use --parallel with --llm-actions", file=sys.stderr)
        sys.exit(1)

    # Parse --seed-range into seed + batch count
    if getattr(args, "seed_range", None):
        parts = args.seed_range.split("-")
        if len(parts) != 2:
            print("Error: --seed-range must be START-END (e.g., 1-200)", file=sys.stderr)
            sys.exit(1)
        try:
            start, end = int(parts[0]), int(parts[1])
        except ValueError:
            print("Error: --seed-range values must be integers (e.g., 1-200)", file=sys.stderr)
            sys.exit(1)
        if start > end:
            print(f"Error: --seed-range start ({start}) must be <= end ({end})", file=sys.stderr)
            sys.exit(1)
        args.seed = start
        args.batch = end - start + 1

    # --- M44: --narrator api validation ---
    if getattr(args, "narrator", "local") == "api":
        if getattr(args, "simulate_only", False):
            print("Error: --narrator api and --simulate-only are contradictory", file=sys.stderr)
            sys.exit(1)
        if args.live:
            print("Error: --narrator api is incompatible with --live (API latency)", file=sys.stderr)
            sys.exit(1)
        if args.parallel is not None and args.batch:
            print("Error: --narrator api is incompatible with --batch --parallel", file=sys.stderr)
            sys.exit(1)
        try:
            import anthropic  # noqa: F401
        except ImportError:
            print("Error: --narrator api requires the anthropic package. "
                  "Install with: pip install chronicler[api]", file=sys.stderr)
            sys.exit(1)
        import os
        if "ANTHROPIC_API_KEY" not in os.environ:
            print("Error: --narrator api requires ANTHROPIC_API_KEY environment variable",
                  file=sys.stderr)
            sys.exit(1)

    # --- --narrator gemini validation ---
    if getattr(args, "narrator", "local") == "gemini":
        if getattr(args, "simulate_only", False):
            print("Error: --narrator gemini and --simulate-only are contradictory", file=sys.stderr)
            sys.exit(1)
        if args.live:
            print("Error: --narrator gemini is incompatible with --live (API latency)", file=sys.stderr)
            sys.exit(1)
        if args.parallel is not None and args.batch:
            print("Error: --narrator gemini is incompatible with --batch --parallel", file=sys.stderr)
            sys.exit(1)
        try:
            from google import genai  # noqa: F401
        except ImportError:
            print("Error: --narrator gemini requires the google-genai package. "
                  "Install with: pip install google-genai", file=sys.stderr)
            sys.exit(1)
        import os
        if "GOOGLE_API_KEY" not in os.environ:
            print("Error: --narrator gemini requires GOOGLE_API_KEY environment variable",
                  file=sys.stderr)
            sys.exit(1)

    # Skip LLM client and scenario resolution for live mode — run_live
    # handles both after receiving params from the client's start command.
    # Also skip for --analyze, which only reads already-written bundles.
    # Handle --narrate early: it manages its own LLM clients
    if getattr(args, "narrate", None):
        _run_narrate(args)
        return

    if not args.live and not getattr(args, "analyze", None):
        if getattr(args, "simulate_only", False):
            sim_client = _DummyClient()
            narrative_client = _DummyClient()
        else:
            sim_client, narrative_client = create_clients(
                local_url=args.local_url,
                sim_model=args.sim_model,
                narrative_model=args.narrative_model,
                narrator=args.narrator,
            )

        # Resolve scenario
        scenario_config = None
        if args.scenario:
            from chronicler.scenario import load_scenario, resolve_scenario_params
            scenario_config = load_scenario(Path(args.scenario))
            params = resolve_scenario_params(scenario_config, args)
            args.seed = params["seed"]
            args.turns = params["num_turns"]
            args.civs = params["num_civs"]
            args.regions = params["num_regions"]
            args.reflection_interval = params["reflection_interval"]
        else:
            args.seed = args.seed if args.seed is not None else DEFAULT_CONFIG.get("seed", 42)
            args.turns = args.turns if args.turns is not None else DEFAULT_CONFIG["num_turns"]
            args.civs = args.civs if args.civs is not None else DEFAULT_CONFIG["num_civs"]
            args.regions = args.regions if args.regions is not None else DEFAULT_CONFIG["num_regions"]
            args.reflection_interval = args.reflection_interval if args.reflection_interval is not None else DEFAULT_CONFIG["reflection_interval"]
    else:
        sim_client = None
        narrative_client = None
        scenario_config = None

    # Load tuning YAML if provided (single-run and non-batch modes)
    if not args.live and not getattr(args, "analyze", None):
        if getattr(args, "tuning", None):
            from chronicler.tuning import load_tuning
            args.tuning_overrides = load_tuning(Path(args.tuning))
        elif not hasattr(args, "tuning_overrides"):
            args.tuning_overrides = {}

    # --- Dispatch ---
    if getattr(args, "analyze", None):
        import json as _json
        from chronicler.analytics import generate_report, format_text_report, format_delta_report
        analyze_dir = Path(args.analyze)
        checkpoints = None
        if getattr(args, "checkpoints", None):
            checkpoints = [int(x.strip()) for x in args.checkpoints.split(",")]
        report = generate_report(analyze_dir, checkpoints=checkpoints)
        report_path = analyze_dir / "batch_report.json"
        with open(report_path, "w") as f:
            _json.dump(report, f, indent=2)
        if getattr(args, "compare", None):
            with open(args.compare) as f:
                baseline = _json.load(f)
            print(format_delta_report(baseline, report))
        else:
            print(format_text_report(report))
        print(f"\nReport written to: {report_path}")

    elif args.batch:
        from chronicler.batch import run_batch
        batch_dir = run_batch(args, sim_client=sim_client, narrative_client=narrative_client, scenario_config=scenario_config)
        print(f"\nBatch complete: {batch_dir}")

    elif args.fork:
        from chronicler.fork import run_fork
        result = run_fork(args, sim_client=sim_client, narrative_client=narrative_client, scenario_config=scenario_config)
        print(f"\nFork complete: {result.output_dir}")

    elif args.interactive:
        from chronicler.interactive import run_interactive
        result = run_interactive(args, sim_client=sim_client, narrative_client=narrative_client, scenario_config=scenario_config)
        print(f"\nInteractive session complete: {result.output_dir}")

    elif args.live:
        from chronicler.live import run_live
        result = run_live(args)
        print(f"\nLive session complete: {result.output_dir}")

    else:
        # Single run (default) or resume
        world = None
        memories = None
        if args.resume:
            resume_path = Path(args.resume)
            world = WorldState.load(resume_path)
            memories = {}
            for mem_file in resume_path.parent.glob("memories_*.json"):
                stream = MemoryStream.load(mem_file)
                memories[stream.civilization_name] = stream
            print(f"Resuming from {resume_path} at turn {world.turn}")

        result = execute_run(
            args,
            sim_client=sim_client,
            narrative_client=narrative_client,
            world=world,
            memories=memories,
            scenario_config=scenario_config,
        )
        print(f"\nChronicle complete: {result.output_dir}")


if __name__ == "__main__":
    main()
