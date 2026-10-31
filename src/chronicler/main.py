"""Main entry point for the Chronicler civilization simulator."""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
from pathlib import Path
from typing import Any

from chronicler.artifact_io import ArtifactIOError, atomic_write_json, atomic_write_text
from chronicler.bundle import assemble_bundle, write_bundle
from chronicler.interestingness import score_run
from chronicler.llm import create_clients
from chronicler.memory import MemoryStream
from chronicler.models import WorldState
from chronicler.narrative import NarrativeEngine
from chronicler.scenario import apply_scenario, load_scenario
from chronicler.simulation import run_turn
from chronicler.turn_artifacts import TurnObservation, TurnResult
from chronicler.types import RunResult
from chronicler.world_gen import generate_world

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "num_turns": 50,
    "num_civs": 4,
    "num_regions": 8,
    "reflection_interval": 10,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chronicler",
        description="Generate alternate history chronicles with LLM-driven civilizations.",
    )
    parser.add_argument("--seed", type=int, default=None, help="RNG seed (default: 42 for batch, random otherwise)")
    parser.add_argument("--seed-range", type=str, default=None, help="Seed range like 5-9 (expands to batch)")
    parser.add_argument("--turns", type=int, default=50, help="Number of turns to simulate")
    parser.add_argument("--civs", type=int, default=4, help="Number of civilizations")
    parser.add_argument("--regions", type=int, default=8, help="Number of regions")
    parser.add_argument("--output", type=str, default="output/chronicle.md", help="Chronicle output path")
    parser.add_argument("--state", type=str, default="output/state.json", help="World state output path")
    parser.add_argument("--resume", type=str, default=None, help="Resume from saved state file")
    parser.add_argument("--reflection-interval", type=int, default=10, help="Turns between era reflections")
    parser.add_argument("--local-url", type=str, default="http://localhost:1234/v1", help="Local LLM server URL")
    parser.add_argument("--sim-model", type=str, default=None, help="Model for simulation decisions")
    parser.add_argument("--narrative-model", type=str, default=None, help="Model for narrative writing")
    parser.add_argument("--llm-actions", action="store_true", help="Deprecated and ignored")
    parser.add_argument("--scenario", type=str, default=None, help="Scenario YAML file")
    parser.add_argument("--batch", type=int, default=None, help="Run N chronicles with sequential seeds")
    parser.add_argument("--parallel", nargs="?", const=-1, type=int, default=None, help="Parallel batch workers")
    parser.add_argument("--fork", type=str, default=None, help="Fork from a saved state file")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--pause-every", type=int, default=None, help="Pause every N turns")
    parser.add_argument("--simulate-only", action="store_true", default=False, help="Skip LLM narration")
    parser.add_argument("--agents", type=str, default="off", choices=["off", "demographics-only", "shadow", "hybrid"], help="Agent simulation mode")
    parser.add_argument("--agent-movements", action="store_true", default=False, help="Enable agent movement tracking")
    parser.add_argument("--narrator", type=str, default="local", choices=["local", "api", "gemini"], help="Narrator backend")
    parser.add_argument("--budget", type=int, default=None, help="API token budget")
    parser.add_argument("--narrate", type=str, default=None, help="Re-narrate an existing bundle")
    parser.add_argument("--narrate-output", type=str, default=None, help="Output path for re-narrated bundle")
    parser.add_argument("--citations", action="store_true", default=False, help="Include citations in narration")
    parser.add_argument("--analyze", type=str, default=None, help="Analyze a batch directory")
    parser.add_argument("--compare", type=str, default=None, help="Compare against baseline report")
    parser.add_argument("--checkpoints", type=str, default=None, help="Comma-separated checkpoint turns")
    parser.add_argument("--tuning", type=str, default=None, help="Tuning overrides YAML file")
    parser.add_argument("--worldgen", type=str, default=None, help="World generation mode")
    # Wave feature flags (all optional, default None = engine default)
    for _flag in (
        "mutual-aid", "fisheries", "campaigns", "governance", "contact-ledger",
        "epidemiology", "finance", "diplomacy", "techniques", "maritime",
        "gp-agendas", "nomads", "cities", "historiography", "languages",
        "scholarship", "grain-reserves", "community-anchoring",
        "capacity-aware-refugees", "health-care", "harvest-forecasts",
        "ritual-gatherings", "scientific-claims", "scientific-research-agendas",
        "transaction-receipts", "domestic-credit",
    ):
        parser.add_argument(f"--{_flag}", dest=_flag.replace("-", "_"), action="store_true", default=None)
        parser.add_argument(f"--no-{_flag}", dest=_flag.replace("-", "_"), action="store_false")
    parser.add_argument("--preset", type=str, default=None, help="Tuning preset name")
    parser.add_argument("--aggression-bias", type=float, default=None)
    parser.add_argument("--tech-diffusion-rate", type=float, default=None)
    parser.add_argument("--resource-abundance", type=float, default=None)
    parser.add_argument("--trade-friction", type=float, default=None)
    parser.add_argument("--severity-multiplier", type=float, default=None)
    parser.add_argument("--cultural-drift-speed", type=float, default=None)
    parser.add_argument("--religion-intensity", type=float, default=None)
    parser.add_argument("--secession-likelihood", type=float, default=None)
    parser.add_argument("--agent-scale-mode", type=str, default=None)
    parser.add_argument("--decision-ablation", type=str, default=None)
    parser.add_argument("--ablation-start-turn", type=int, default=None)
    parser.add_argument("--ablation-output", type=str, default=None)
    parser.add_argument("--validation-sidecar", action="store_true", default=None)
    parser.add_argument("--relationship-stats", action="store_true", default=None)
    parser.add_argument("--state-every", type=int, default=None)
    parser.add_argument("--live", action="store_true", default=False, help="Live server mode")
    parser.add_argument("--live-port", type=int, default=0, help="Live server port")
    parser.add_argument("--live-origin", type=str, default=None, help="Live server allowed origin")
    parser.add_argument("--checkpoint-every", type=int, default=None, help="Checkpoint every N turns")
    parser.add_argument("--checkpoint", type=str, default=None, help="Checkpoint directory")
    parser.add_argument("--checkpoint-turns", type=int, default=None, help="Checkpoint turn count")
    parser.add_argument("--resume-allow-mismatch", action="store_true", default=False)
    return parser


def _write_chronicle_output(path: Path, text: str) -> None:
    """Write the final chronicle markdown atomically."""
    atomic_write_text(Path(path), text)


def _write_analysis_report(batch_dir: Path, report: dict) -> None:
    """Write the CLI batch analysis report atomically."""
    atomic_write_json(Path(batch_dir) / "batch_report.json", report)


def _write_state_checkpoint(path: Path, world: WorldState, *, artifact_budget=None) -> None:
    """Write a state checkpoint atomically."""
    world.save(path)


def _save_memory_streams(output_dir: Path, memories: dict, *, artifact_budget=None) -> None:
    """Persist per-civ memory streams."""
    for civ_name, stream in memories.items():
        safe = civ_name.replace(" ", "_").replace("/", "_")
        path = Path(output_dir) / f"memories_{safe}.json"
        atomic_write_json(path, stream.model_dump(mode="json"))


class _SigintDeferral:
    """Context manager: defer the first SIGINT until the current turn finishes."""

    def __init__(self):
        self.requested = False
        self._previous = None
        self._active = False

    def __enter__(self):
        if threading.current_thread() is not threading.main_thread():
            return self
        prior = signal.getsignal(signal.SIGINT)
        if prior not in (signal.default_int_handler, signal.SIG_DFL):
            return self
        self._previous = prior

        def _handler(signum, frame):
            if self.requested:
                # Second interrupt: cancel immediately.
                raise KeyboardInterrupt
            self.requested = True
            print("Interrupted — finishing this turn (Ctrl+C again to cancel now)", file=sys.stderr)

        signal.signal(signal.SIGINT, _handler)
        self._active = True
        return self

    def __exit__(self, kind, value, traceback):
        if self._active:
            signal.signal(signal.SIGINT, signal.default_int_handler)
        return False


def _run_turn_deferring_sigint(*args, practice_observer=None, **kwargs):
    """Run one turn inside SIGINT deferral; return (result, interrupted)."""
    with _SigintDeferral() as deferral:
        if practice_observer is None:
            result = run_turn_result(*args, **kwargs)
        else:
            result = practice_observer.run_turn_result(*args, **kwargs)
        return result, deferral.requested


def run_turn_result(*args, **kwargs) -> TurnResult:
    """Adapter: run_turn plus observation capture."""
    world = args[0]
    source_turn = world.turn
    text = run_turn(*args, **kwargs)
    return TurnResult(text, TurnObservation(source_turn, world.turn, None))


def _create_politics_runtime(world):
    """Create a PoliticsSimulator if the native crate is available."""
    try:
        from chronicler_agents import PoliticsSimulator
        return PoliticsSimulator(world)
    except Exception:
        return None


def run_chronicle(
    seed: int,
    num_turns: int,
    num_civs: int,
    num_regions: int,
    output_path: Path,
    state_path: Path | None = None,
    sim_client=None,
    narrative_client=None,
    reflection_interval: int = 10,
    scenario_config=None,
    resume_path: Path | None = None,
) -> None:
    """Run a chronicle simulation and write outputs."""
    args = argparse.Namespace(
        seed=seed,
        turns=num_turns,
        civs=num_civs,
        regions=num_regions,
        output=str(output_path),
        state=str(state_path) if state_path else None,
        resume=str(resume_path) if resume_path else None,
        reflection_interval=reflection_interval,
        llm_actions=False,
        scenario=None,
        pause_every=None,
    )
    execute_run(
        args,
        sim_client=sim_client,
        narrative_client=narrative_client,
        scenario_config=scenario_config,
    )


def execute_run(
    args: argparse.Namespace,
    sim_client=None,
    narrative_client=None,
    scenario_config=None,
    world: WorldState | None = None,
    memories: dict | None = None,
    on_turn=None,
    quit_check=None,
    progress_cb=None,
    cancel_event=None,
    *,
    practice_observer: Any | None = None,
    artifact_budget: Any | None = None,
) -> RunResult:
    """Execute a single simulation run.

    artifact_budget : object or None
        Explicit caller-owned ordinary-output admission. The optional path is
        limited to fresh hybrid runs without exact checkpoints. It does not
        implement owner/log admission or qualify an enabled study.
    """
    seed = 42 if getattr(args, "seed", None) is None else args.seed
    num_turns = args.turns
    output_path = Path(args.output)
    state_path = Path(args.state) if getattr(args, "state", None) else None
    resume_path = Path(args.resume) if getattr(args, "resume", None) else None

    if getattr(args, "llm_actions", False):
        logger.warning("--llm-actions is deprecated and ignored")

    _resume_state = None
    if world is None and resume_path is not None:
        _resume_state = WorldState.load(resume_path)

    if _resume_state is not None:
        world = _resume_state.world if hasattr(_resume_state, "world") else _resume_state
        from chronicler.ffi_constants import check_civ_capacity
        check_civ_capacity(world)
        if getattr(args, "checkpoint_resume", None) is None:
            pass
    elif world is not None:
        from chronicler.ffi_constants import check_civ_capacity
        check_civ_capacity(world)
    elif resume_path:
        world = WorldState.load(resume_path)
    else:
        world = generate_world(seed=seed, num_regions=args.regions, num_civs=args.civs)
        if scenario_config is not None:
            # Apply scenario overrides if provided
            apply_scenario(world, scenario_config)
        from chronicler.ffi_constants import check_civ_capacity
        check_civ_capacity(world)
        if sim_client:
            pass

    if memories is None:
        memories = {c.name: MemoryStream(civilization_name=c.name) for c in world.civilizations}

    if scenario_config is not None and world.scenario_name is None:
        world.scenario_name = getattr(scenario_config, "name", None)

    if getattr(args, "tuning_overrides", None):
        world.tuning_overrides = dict(args.tuning_overrides)

    # Enrich with LLM-generated goals/values if a sim client is available
    if sim_client is not None and not getattr(args, "simulate_only", False):
        try:
            from chronicler.enrichment import enrich_with_llm
            enrich_with_llm(world, sim_client)
        except Exception:
            logger.warning("LLM goal enrichment failed; proceeding with empty goals")

    narrator = None
    if narrative_client is not None:
        narrator = NarrativeEngine(narrative_client)

    agent_bridge = None
    agent_mode = getattr(args, "agents", "off")
    if agent_mode in ("shadow", "hybrid", "demographics-only"):
        import chronicler.agent_bridge as ab_module
        shadow_output = None
        if agent_mode == "shadow":
            shadow_output = output_path.parent / "shadow.arrow"
        agent_bridge = ab_module.AgentBridge(
            world, seed=seed, shadow_output=shadow_output,
        )
        world.agent_mode = agent_mode

    politics_runtime = None
    if agent_bridge is not None:
        politics_runtime = agent_bridge._sim
    else:
        politics_runtime = _create_politics_runtime(world)

    history: list = []
    chronicle_entries: list = []
    era_reflections: dict = {}
    start_turn = world.turn
    events_start = len(world.events_timeline)
    named_start = len(world.named_events)

    from chronicler.simulation import snapshot_summary

    _noop_narrator = None
    action_selector = None
    economy_tracker = None
    ecology_runtime = None
    _pending: list = []

    try:
        for turn_num in range(start_turn, num_turns):
            if quit_check is not None and quit_check():
                break
            if cancel_event is not None and cancel_event.is_set():
                break

            if practice_observer is None:
                turn_result, _interrupt_requested = _run_turn_deferring_sigint(
                    world,
                    action_selector=action_selector,
                    narrator=_noop_narrator,
                    seed=seed + turn_num,
                    agent_bridge=agent_bridge,
                    economy_tracker=economy_tracker,
                    ecology_runtime=ecology_runtime,
                    politics_runtime=politics_runtime,
                    force_settlement_detection=True,
                    pending_injections=_pending,
                )
            else:
                turn_result, _interrupt_requested = _run_turn_deferring_sigint(
                    world,
                    action_selector=action_selector,
                    narrator=_noop_narrator,
                    seed=seed + turn_num,
                    agent_bridge=agent_bridge,
                    economy_tracker=economy_tracker,
                    ecology_runtime=ecology_runtime,
                    politics_runtime=politics_runtime,
                    force_settlement_detection=True,
                    pending_injections=_pending,
                    practice_observer=practice_observer,
                )

            snapshot = snapshot_summary(world)
            history.append(snapshot)

            if on_turn is not None:
                on_turn(
                    snapshot,
                    turn_result.text,
                    world.events_timeline[events_start:],
                    world.named_events[named_start:],
                )

            if progress_cb is not None:
                progress_cb(turn_num + 1 - start_turn, num_turns - start_turn, seed)
    finally:
        if agent_bridge is not None:
            agent_bridge.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Assemble and write the bundle
    interestingness = None
    try:
        interestingness = score_run(world)
    except Exception:
        pass

    sim_input_tokens = getattr(sim_client, "total_input_tokens", 0) if sim_client else 0
    sim_output_tokens = getattr(sim_client, "total_output_tokens", 0) if sim_client else 0

    # Per-run narrative token accounting: a shared client accumulates across runs,
    # so capture deltas around this run's narration.
    narrative_input_tokens = 0
    narrative_output_tokens = 0
    extra_metadata: dict = {}

    if narrator is not None and not getattr(args, "simulate_only", False):
        narrator_mode = getattr(args, "narrator", "local")
        extra_metadata["narrator_mode"] = narrator_mode
        if narrator_mode == "api":
            # Curated API narration: batch narrate notable moments only.
            narr_in_start = getattr(narrative_client, "total_input_tokens", 0)
            narr_out_start = getattr(narrative_client, "total_output_tokens", 0)
            moments = []  # curated moments selection
            narrate_kwargs: dict = {}
            if agent_bridge is not None:
                narrate_kwargs["social_edges"] = getattr(agent_bridge, "social_edges", None)
                narrate_kwargs["dissolved_edges_by_turn"] = getattr(agent_bridge, "dissolved_edges_by_turn", None)
                narrate_kwargs["agent_name_map"] = getattr(agent_bridge, "agent_name_map", None)
                narrate_kwargs["gini_by_civ"] = getattr(agent_bridge, "gini_by_civ", None)
                narrate_kwargs["economy_result"] = getattr(agent_bridge, "economy_result", None)
                narrate_kwargs["displacement_by_region"] = getattr(agent_bridge, "displacement_by_region", None)
                narrate_kwargs["dynasty_registry"] = getattr(agent_bridge, "dynasty_registry", None)
            entries = narrator.narrate_batch(moments, history, **narrate_kwargs)
            chronicle_entries.extend(entries or [])
            narrative_input_tokens = getattr(narrative_client, "total_input_tokens", 0) - narr_in_start
            narrative_output_tokens = getattr(narrative_client, "total_output_tokens", 0) - narr_out_start
            extra_metadata["api_input_tokens"] = narrative_input_tokens
            extra_metadata["api_output_tokens"] = narrative_output_tokens

    bundle = assemble_bundle(
        world=world,
        history=history,
        chronicle_entries=chronicle_entries,
        era_reflections=era_reflections,
        sim_model=getattr(sim_client, "model", None),
        narrative_model=getattr(narrative_client, "model", None),
        interestingness_score=interestingness,
        sim_input_tokens=sim_input_tokens,
        sim_output_tokens=sim_output_tokens,
        narrative_input_tokens=narrative_input_tokens,
        narrative_output_tokens=narrative_output_tokens,
        extra_metadata=extra_metadata,
    )
    write_bundle(bundle, output_path.parent / "chronicle_bundle.json", world=world)

    if state_path is not None:
        _write_state_checkpoint(state_path, world)

    _save_memory_streams(output_path.parent, memories)

    # Compose the chronicle markdown
    chronicle_text = f"# Chronicle of {world.name}\n\n"
    for entry in chronicle_entries:
        chronicle_text += getattr(entry, "narrative", "") + "\n\n"
    if not chronicle_entries:
        for snapshot in history:
            chronicle_text += f"## Turn {snapshot.turn}\n\nEvents occurred.\n\n"
    _write_chronicle_output(output_path, chronicle_text)

    # Build RunResult
    new_events = world.events_timeline[events_start:]
    war_count = sum(1 for e in new_events if e.event_type == "war")
    collapse_count = sum(1 for e in new_events if e.event_type == "collapse")
    named_event_count = len(world.named_events) - named_start
    action_distribution = {civ.name: dict(civ.action_counts) for civ in world.civilizations}
    distinct_action_count = len({a for counts in action_distribution.values() for a in counts})
    tech_advancement_count = sum(1 for e in new_events if e.event_type == "tech_advancement")

    max_stat_swing = 0.0
    if history:
        first = history[0]
        last = history[-1]
        for civ_name in first.civ_stats:
            if civ_name in last.civ_stats:
                for stat in ("population", "military", "economy", "culture", "stability"):
                    swing = abs(
                        getattr(last.civ_stats[civ_name], stat)
                        - getattr(first.civ_stats[civ_name], stat)
                    )
                    max_stat_swing = max(max_stat_swing, float(swing))

    dominant_faction = "-"
    if world.civilizations:
        dominant_faction = max(
            world.civilizations,
            key=lambda c: c.population + c.military + c.economy + c.culture + c.stability,
        ).name

    boring_civs: list[str] = []
    reflection_count = len(era_reflections)

    return RunResult(
        seed=seed,
        output_dir=output_path.parent,
        war_count=war_count,
        collapse_count=collapse_count,
        named_event_count=named_event_count,
        distinct_action_count=distinct_action_count,
        reflection_count=reflection_count,
        tech_advancement_count=tech_advancement_count,
        max_stat_swing=max_stat_swing,
        action_distribution=action_distribution,
        dominant_faction=dominant_faction,
        boring_civs=boring_civs,
        total_turns=world.turn - start_turn,
    )


def _run_narrate(args: argparse.Namespace) -> None:
    """Re-narrate an existing bundle."""
    from chronicler.bundle_codec import load_bundle
    from chronicler.models import GreatPerson

    bundle_path = Path(args.narrate)
    bundle = load_bundle(bundle_path)

    sim_client, narrative_client = create_clients(args)
    narrator = NarrativeEngine(narrative_client)

    narr_in_start = getattr(narrative_client, "total_input_tokens", 0)
    narr_out_start = getattr(narrative_client, "total_output_tokens", 0)

    great_persons: list = []
    for civ_data in bundle.get("world_state", {}).get("civilizations", []):
        for gp_data in civ_data.get("great_persons", []):
            great_persons.append(GreatPerson.model_validate(gp_data))
    agent_name_map = {gp.agent_id: gp.name for gp in great_persons if gp.agent_id is not None}

    moments: list = []
    history = bundle.get("history", [])
    entries = narrator.narrate_batch(
        moments,
        history,
        great_persons=great_persons,
        agent_name_map=agent_name_map,
        social_edges=None,
        dissolved_edges_by_turn=None,
        displacement_by_region=None,
        dynasty_registry=None,
        economy_result=None,
        gini_by_civ=None,
    )

    narrative_input_tokens = getattr(narrative_client, "total_input_tokens", 0) - narr_in_start
    narrative_output_tokens = getattr(narrative_client, "total_output_tokens", 0) - narr_out_start

    bundle["chronicle_entries"] = [e.model_dump(mode="json") for e in (entries or [])]
    metadata = bundle.setdefault("metadata", {})
    metadata["narrator_mode"] = getattr(args, "narrator", "local")
    metadata["narrative_input_tokens"] = narrative_input_tokens
    metadata["narrative_output_tokens"] = narrative_output_tokens
    if metadata["narrator_mode"] == "api":
        metadata["api_input_tokens"] = narrative_input_tokens
        metadata["api_output_tokens"] = narrative_output_tokens

    output_path = Path(getattr(args, "narrate_output", None) or "narrated.json")
    atomic_write_json(output_path, bundle)


def _run_analyze(args: argparse.Namespace) -> int:
    """Run analytics over a batch directory."""
    from chronicler.analytics import format_delta_report, format_text_report, generate_report

    batch_dir = Path(args.analyze)
    checkpoints = None
    if getattr(args, "checkpoints", None):
        checkpoints = [int(c) for c in args.checkpoints.split(",")]

    report = generate_report(batch_dir, checkpoints=checkpoints)

    if getattr(args, "compare", None):
        baseline_path = Path(args.compare)
        baseline = json.loads(baseline_path.read_text())
        print(format_delta_report(baseline, report))
    else:
        print(format_text_report(report))

    report_path = batch_dir / "analytics_report.json"
    atomic_write_json(report_path, report)
    return 0


def _configure_run(args: argparse.Namespace, *, artifact_budget=None) -> None:
    """Apply CLI tuning overrides onto args."""
    tuning: dict = {}
    for key in (
        "aggression_bias", "tech_diffusion_rate", "resource_abundance",
        "trade_friction", "severity_multiplier", "cultural_drift_speed",
        "religion_intensity", "secession_likelihood",
    ):
        value = getattr(args, key, None)
        if value is not None:
            tuning[key] = value
    if tuning:
        args.tuning_overrides = tuning


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.narrate and args.narrate_output is None:
        pass  # default output path used
    if args.narrate_output and not args.narrate:
        parser.error("--narrate-output requires --narrate")
    if args.compare and not args.analyze:
        parser.error("--compare requires --analyze")

    if getattr(args, "llm_actions", False):
        logger.warning("--llm-actions is deprecated and ignored")

    narrator = getattr(args, "narrator", "local")
    if narrator in ("api", "gemini"):
        if getattr(args, "simulate_only", False):
            parser.error(f"--narrator {narrator} is incompatible with --simulate-only")
        if getattr(args, "live", False):
            parser.error(f"--narrator {narrator} is incompatible with --live")
        if getattr(args, "batch", None) and getattr(args, "parallel", None):
            parser.error(f"--narrator {narrator} is incompatible with --batch --parallel")

    if args.batch and args.fork:
        parser.error("--batch and --fork are mutually exclusive")

    if args.narrate:
        _run_narrate(args)
        return

    if args.analyze:
        raise SystemExit(_run_analyze(args))

    if args.batch or args.seed_range:
        from chronicler.batch import run_batch, BatchDestinationError  # noqa: F401
        if args.seed_range:
            lo, _, hi = args.seed_range.partition("-")
            args.seed = int(lo)
            args.batch = int(hi) - int(lo) + 1
        try:
            sim_client, narrative_client = create_clients(args)
            _configure_run(args)
            run_batch(args, sim_client=sim_client, narrative_client=narrative_client)
        except BatchDestinationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1)
        return

    sim_client, narrative_client = create_clients(args)
    _configure_run(args)
    execute_run(args, sim_client=sim_client, narrative_client=narrative_client)


if __name__ == "__main__":
    main()
