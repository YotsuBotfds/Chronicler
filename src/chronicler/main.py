"""Main entry point — orchestrates world generation, simulation, and chronicle output.

Usage:
    chronicler --seed 42 --turns 50 --civs 4 --regions 8 --output chronicle.md

Default: fully local inference via LM Studio. No API key required.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from chronicler.artifact_io import atomic_write_text
from chronicler.bundle import assemble_bundle, write_bundle
from chronicler.climate import get_climate_phase
from chronicler.chronicle import compile_chronicle
from chronicler.models import ChronicleEntry, NarrativeRole
from chronicler.interestingness import find_boring_civs
from chronicler.llm import DEFAULT_LOCAL_URL, LLMClient, create_clients


def _tracks_tokens(client: Any) -> bool:
    """Check if an LLM client tracks token usage (API clients)."""
    return hasattr(client, "total_input_tokens") and isinstance(client.total_input_tokens, int)


logger = logging.getLogger(__name__)


def _token_counts(client: Any) -> tuple[int, int, int]:
    """Current (input, output, calls) counters of a token-tracking client."""
    if not _tracks_tokens(client):
        return (0, 0, 0)
    return (
        client.total_input_tokens,
        client.total_output_tokens,
        int(getattr(client, "call_count", 0) or 0),
    )


def _token_usage_since(client: Any, baseline: tuple[int, int, int]) -> tuple[int, int, int]:
    """Counters accrued since ``baseline``. A sequential batch shares one client
    across seeds, so each run reports its own delta (M44 NB-1)."""
    now = _token_counts(client)
    return (now[0] - baseline[0], now[1] - baseline[1], now[2] - baseline[2])


def _set_narrative_token_metadata(
    metadata: dict[str, Any],
    client: Any,
    baseline: tuple[int, int, int] = (0, 0, 0),
) -> None:
    """Populate canonical narrative token fields plus deprecated aliases."""
    if not _tracks_tokens(client):
        return
    inp, out, _ = _token_usage_since(client, baseline)
    metadata["narrative_input_tokens"] = inp
    metadata["narrative_output_tokens"] = out
    metadata["api_input_tokens"] = inp
    metadata["api_output_tokens"] = out


def _default_shadow_output_path(output_path: Path) -> Path:
    """Return the deterministic shadow artifact path for a run output dir."""
    return output_path.parent / "shadow.arrow"
from chronicler.memory import MemoryStream, generate_reflection, sanitize_civ_name, should_reflect
from chronicler.models import CivSnapshot, Event, RelationshipSnapshot, SettlementSummary, TurnSnapshot, WorldState
from chronicler.action_engine import ActionEngine
from chronicler.narrative import NarrativeEngine
from chronicler.simulation import run_turn_result
from chronicler.types import RunResult
from chronicler.world_gen import enrich_with_llm, generate_world
from chronicler.intelligence import border_pairs, compute_accuracy, _get_perceived_stat_with_accuracy
from chronicler.history_index import history_index

DEFAULT_CONFIG = {
    "seed": 42,
    "num_turns": 50,
    "num_civs": 4,
    "num_regions": 8,
    "reflection_interval": 10,
    "local_url": DEFAULT_LOCAL_URL,
}

# Turns between resumable state.json/memory checkpoints during a run. The final
# state is always written; 1 restores the historical every-turn checkpoint.
DEFAULT_STATE_EVERY = 10


def _resolve_state_every(args: argparse.Namespace) -> int:
    value = getattr(args, "state_every", None)
    if value is None:
        return DEFAULT_STATE_EVERY
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"--state-every must be a positive integer, got {value!r}")
    return value


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value}")
    return value


def _write_state_checkpoint(world: WorldState, path: Path) -> None:
    """Write an intermediate resumable checkpoint: compact JSON, atomic replace.

    The final save keeps ``WorldState.save``'s indented format; both load with
    ``WorldState.load`` into the same world. The in-world chronicles and
    languages (when those layers are on) are checkpointed beside it.
    """
    atomic_write_text(path, world.model_dump_json())
    from chronicler.historiography import save_sidecar
    save_sidecar(world, path, atomic=True)
    from chronicler.languages import save_sidecar as save_languages
    save_languages(world, path, atomic=True)


def _save_memory_streams(
    memories: dict[str, MemoryStream],
    output_dir: Path,
    reflection_counts: dict[str, int] | None = None,
) -> None:
    """Write every memory stream; ``reflection_counts`` writes only each
    stream's first N reflections (its content before this turn's reflection)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for civ_name, stream in memories.items():
        count = reflection_counts.get(civ_name) if reflection_counts is not None else None
        if count is not None and count != len(stream.reflections):
            view = MemoryStream(civilization_name=stream.civilization_name)
            view.entries = stream.entries
            view.reflections = stream.reflections[:count]
            stream = view
        stream.save(output_dir / f"memories_{sanitize_civ_name(civ_name)}.json")


class _SigintDeferral:
    """Let the in-flight turn finish on Ctrl-C so a consistent checkpoint can be saved.

    Installed only from the main thread over Python's default SIGINT handler.
    The first Ctrl-C records the request and restores the default handler, so
    a second Ctrl-C interrupts immediately as before.
    """

    def __init__(self) -> None:
        self.requested = False
        self._installed = False

    def __enter__(self) -> "_SigintDeferral":
        if (threading.current_thread() is threading.main_thread()
                and signal.getsignal(signal.SIGINT) is signal.default_int_handler):
            signal.signal(signal.SIGINT, self._handle)
            self._installed = True
        return self

    def _handle(self, signum, frame) -> None:
        self.requested = True
        signal.signal(signal.SIGINT, signal.default_int_handler)
        print("\nInterrupt received: finishing this turn to save a resumable checkpoint "
              "(press Ctrl-C again to stop immediately).", file=sys.stderr, flush=True)

    def __exit__(self, *exc_info) -> bool:
        if self._installed and signal.getsignal(signal.SIGINT) == self._handle:
            signal.signal(signal.SIGINT, signal.default_int_handler)
        return False


def _run_turn_deferring_sigint(*args, **kwargs):
    """``run_turn_result(...)`` with Ctrl-C deferred to the end of the turn."""
    with _SigintDeferral() as deferral:
        turn_result = run_turn_result(*args, **kwargs)
    return turn_result, deferral.requested


class _DummyClient:
    """Fallback LLM client for deterministic-only runs (no API calls)."""
    model = "dummy"

    def complete(self, prompt: str, max_tokens: int = 100, system: str | None = None) -> str:
        return "DEVELOP"


def _urban_counts_by_civ(world, civ_ids, settlement_ids, region_ids) -> dict[str, tuple[int, int]]:
    """``{civ name: (urban agents, agents)}`` from null-free snapshot columns.

    Same attribution as the row loop in ``execute_run``: the controller of an
    agent's region, else the civ of its affinity id, else the row is skipped;
    names in order of first attribution.
    """
    import numpy as np
    from chronicler.columnar import first_appearance

    names: list[str] = []
    code_of: dict[str, int] = {}

    def code(name: str) -> int:
        if name not in code_of:
            code_of[name] = len(names)
            names.append(name)
        return code_of[name]

    n_regions, n_civs = len(world.regions), len(world.civilizations)
    region_code = np.full(n_regions + 1, -1, dtype=np.int64)
    for idx, region in enumerate(world.regions):
        if region.controller is not None:
            region_code[idx] = code(region.controller)
    civ_code = np.full(n_civs + 1, -1, dtype=np.int64)
    for idx, civ in enumerate(world.civilizations):
        civ_code[idx] = code(civ.name)
    civ = np.asarray(civ_ids, dtype=np.int64)
    if region_ids is None:
        codes = np.full(len(civ), -1, dtype=np.int64)
    else:
        regions = np.asarray(region_ids, dtype=np.int64)
        codes = region_code[np.where((regions >= 0) & (regions < n_regions), regions, n_regions)]
    fallback = civ_code[np.where((civ >= 0) & (civ < n_civs), civ, n_civs)]
    codes = np.where(codes >= 0, codes, fallback)
    valid = codes >= 0
    totals = np.bincount(codes[valid], minlength=len(names))
    urban = np.bincount(codes[valid & (np.asarray(settlement_ids) > 0)], minlength=len(names))
    return {names[k]: (int(urban[k]), int(totals[k])) for k in first_appearance(codes[valid])}


def _governance_snapshot(civ):
    from chronicler.governance_runtime import governance_snapshot
    return governance_snapshot(civ)


def _create_ecology_runtime(world):
    """Create a dedicated EcologySimulator for --agents=off mode.

    Wraps construction so tests can mock this function without
    requiring the compiled Rust module.
    """
    try:
        from chronicler_agents import EcologySimulator
        if not isinstance(EcologySimulator, type):
            return None
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
        if not isinstance(PoliticsSimulator, type):
            return None
        from chronicler.politics import configure_politics_runtime
        pol_sim = PoliticsSimulator()
        configure_politics_runtime(pol_sim, world)
        return pol_sim
    except ImportError:
        return None


def _contact_snapshot_fields(world) -> dict:
    """Contact ledger per-turn summary for the viewer snapshot (empty when off)."""
    from chronicler.contact_ledger import ledger_enabled, snapshot_summary
    if not ledger_enabled(world):
        return {}
    return {"contact": snapshot_summary(world)}


def _epidemic_snapshot_fields(world) -> dict:
    """Epidemiology per-turn summary for the viewer snapshot (empty when off)."""
    from chronicler.epidemiology import epidemiology_enabled, snapshot_summary
    if not epidemiology_enabled(world):
        return {}
    return {"epidemics": snapshot_summary(world)}


def _pandemic_region_names(world) -> list[str]:
    """M18 pandemic regions, plus regions with an epidemic when epidemiology is on."""
    names = [p.region_name for p in world.pandemic_state]
    from chronicler.epidemiology import active_region_names, epidemiology_enabled
    if epidemiology_enabled(world):
        active = active_region_names(world)
        names += [r.name for r in world.regions if r.name in active and r.name not in names]
    return names


def _finance_snapshot_fields(world) -> dict:
    """Finance per-turn summary for the viewer snapshot (empty when off)."""
    from chronicler.finance import finance_enabled, snapshot_summary
    if not finance_enabled(world):
        return {}
    return {"finance": snapshot_summary(world)}


def _diplomacy_snapshot_fields(world) -> dict:
    """Diplomacy per-turn summary for the viewer snapshot (empty when off)."""
    from chronicler.diplomacy import diplomacy_enabled, snapshot_summary
    if not diplomacy_enabled(world):
        return {}
    return {"diplomacy": snapshot_summary(world)}


def _techniques_snapshot_fields(world) -> dict:
    """Techniques per-turn summary for the viewer snapshot (empty when off)."""
    from chronicler.techniques_state import techniques_on
    if not techniques_on(world):
        return {}
    from chronicler.techniques import snapshot_summary
    return {"techniques": snapshot_summary(world)}


def _maritime_snapshot_fields(world) -> dict:
    """Maritime per-turn summary for the viewer snapshot (empty when off)."""
    from chronicler.maritime import maritime_enabled, snapshot_summary
    if not maritime_enabled(world):
        return {}
    return {"maritime": snapshot_summary(world)}


def _gp_agendas_snapshot_fields(world) -> dict:
    """Great-person agenda per-turn summary for the viewer snapshot (empty when off)."""
    from chronicler.gp_agendas_state import gp_agendas_on
    if not gp_agendas_on(world):
        return {}
    from chronicler.gp_agendas import snapshot_summary
    return {"gp_agendas": snapshot_summary(world)}


def _nomads_snapshot_fields(world) -> dict:
    """Nomads per-turn summary for the viewer snapshot (empty when off)."""
    from chronicler.nomads_state import nomads_on
    if not nomads_on(world):
        return {}
    from chronicler.nomads import snapshot_summary
    return {"nomads": snapshot_summary(world)}


def _cities_snapshot_fields(world) -> dict:
    """Cities per-turn summary for the viewer snapshot (empty when off)."""
    from chronicler.cities_state import cities_on
    if not cities_on(world):
        return {}
    from chronicler.cities import snapshot_summary
    return {"cities": snapshot_summary(world)}


def _agent_movements_snapshot_fields(world) -> dict:
    """Agent movements per-turn summary for the viewer snapshot (empty when off)."""
    from chronicler.agent_movements_state import agent_movements_on
    if not agent_movements_on(world):
        return {}
    from chronicler.agent_movements import snapshot_summary
    return {"agent_movements": snapshot_summary(world)}


def _guilds_snapshot_fields(world) -> dict:
    """Guilds per-turn summary for the viewer snapshot (empty when off)."""
    from chronicler.guilds_state import guilds_on
    if not guilds_on(world):
        return {}
    from chronicler.guilds import snapshot_summary
    return {"guilds": snapshot_summary(world)}


def _food_snapshot_fields(world) -> dict:
    """Viewer-only food summary (empty unless mutual aid observes regional food)."""
    from chronicler.mutual_aid import mutual_aid_active, snapshot_summary
    if not mutual_aid_active(world):
        return {}
    return {"food": snapshot_summary(world)}


def _migration_snapshot_fields(world) -> dict:
    """Viewer-only agent migrations of the completed turn (empty without agent events).

    ``[from region index, to region index, agents]`` rows sorted by region
    pair, read through the exact history index; no state or RNG is touched.
    """
    if world.agent_mode not in ("hybrid", "shadow"):
        return {}
    from chronicler.history_index import history_index
    n_regions = len(world.regions)
    counts: dict[tuple[int, int], int] = {}
    for e in history_index(world).agent_migrations_for_turn(world, world.turn - 1):
        src, dst = int(e.region), int(e.target_region)
        if 0 <= src < n_regions and 0 <= dst < n_regions and src != dst:
            counts[(src, dst)] = counts.get((src, dst), 0) + 1
    return {"migration": [[src, dst, n] for (src, dst), n in sorted(counts.items())]}


def _war_snapshot_fields(world) -> dict:
    """M60 campaign fields for the viewer snapshot (empty when disabled)."""
    if not world.campaigns_enabled:
        return {}
    from chronicler.war.runtime import snapshot_summary
    return {"campaign": snapshot_summary(world)}


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
        `llm_actions` is accepted for backward compatibility but ignored.
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
    _narr_token_baseline = _token_counts(_narr)
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
    if getattr(args, "llm_actions", False):
        logger.warning(
            "--llm-actions is deprecated and ignored; simulation action selection remains deterministic"
        )
    _pause_every = pause_every or getattr(args, "pause_every", None)
    _state_every = _resolve_state_every(args)

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
    fresh_world = False
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
            worldgen=getattr(args, "worldgen", None),
        )
        start_turn = 0
        fresh_world = True

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
            except Exception as exc:
                logger.warning(
                    "LLM goal enrichment failed: %s; proceeding with empty goals",
                    exc,
                )
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

    # M60: campaign layer switch (persisted on the world for resume). New
    # worlds default to campaigns; resumed or supplied worlds keep theirs.
    campaigns = getattr(args, "campaigns", None)
    if campaigns is None and fresh_world:
        from chronicler.war.params import CAMPAIGNS_DEFAULT_FOR_NEW_WORLDS
        campaigns = CAMPAIGNS_DEFAULT_FOR_NEW_WORLDS
    if campaigns is not None:
        world.campaigns_enabled = campaigns

    # M28: Agent mode wiring
    agent_mode = getattr(args, "agents", "off")
    # Adjacent mutual aid (persisted on the world). It moves goods-economy
    # stocks, so an explicit --mutual-aid needs an agent mode; a default-on or
    # saved setting is simply dormant under --agents off.
    mutual_aid = getattr(args, "mutual_aid", None)
    if mutual_aid is True and agent_mode == "off":
        raise ValueError("Mutual aid requires an agent-backed goods economy (--agents hybrid, shadow or demographics-only)")
    if mutual_aid is None and fresh_world:
        from chronicler.mutual_aid import DEFAULT_ENABLED_FOR_NEW_WORLDS as _AID_DEFAULT
        mutual_aid = _AID_DEFAULT
    if mutual_aid is not None:
        world.mutual_aid_enabled = mutual_aid
    # Renewable fish stocks (persisted on the world). New worlds also get the
    # living-world calibration; loaded worlds keep their saved parameters.
    fisheries = getattr(args, "fisheries", None)
    if fisheries is None and fresh_world:
        from chronicler.experimental.fisheries import DEFAULT_ENABLED_FOR_NEW_WORLDS as _FISH_DEFAULT
        fisheries = _FISH_DEFAULT
    if fisheries is not None:
        from chronicler.experimental.fisheries import set_fisheries_enabled
        set_fisheries_enabled(world, fisheries, new_world=fresh_world)
    # Phase 8 governance runtime switch (persisted on the world).
    governance = getattr(args, "governance", None)
    if governance is None and fresh_world:
        from chronicler.governance_runtime import DEFAULT_ENABLED_FOR_NEW_WORLDS
        governance = DEFAULT_ENABLED_FOR_NEW_WORLDS
    if governance is not None:
        from chronicler.governance_runtime import set_governance_enabled
        set_governance_enabled(world, governance)
    agent_scale_mode = getattr(args, "agent_scale_mode", None) or "exact"
    if agent_scale_mode != "exact" and agent_mode == "off":
        raise ValueError("--agent-scale-mode fast requires an agent pool (--agents hybrid, shadow or demographics-only)")
    # Contact & trade-flow ledger switch (persisted on the world).
    contact_ledger = getattr(args, "contact_ledger", None)
    if contact_ledger is None and fresh_world:
        from chronicler.contact_ledger import DEFAULT_ENABLED_FOR_NEW_WORLDS as _LEDGER_DEFAULT
        contact_ledger = _LEDGER_DEFAULT
    if contact_ledger is not None:
        from chronicler.contact_ledger import set_contact_ledger_enabled
        set_contact_ledger_enabled(world, contact_ledger)
    # Regional SEIRS epidemiology (persisted on the world). It spreads along
    # the contact ledger, so an explicit --epidemiology needs the ledger; a
    # default-on setting stays off on a ledger-less new world.
    epidemiology = getattr(args, "epidemiology", None)
    from chronicler.contact_ledger import ledger_enabled as _ledger_on
    if epidemiology is True and not _ledger_on(world):
        raise ValueError("Epidemiology spreads along the contact ledger (--contact-ledger)")
    if epidemiology is None and fresh_world:
        from chronicler.epidemiology import DEFAULT_ENABLED_FOR_NEW_WORLDS as _EPI_DEFAULT
        epidemiology = _EPI_DEFAULT and _ledger_on(world)
    if epidemiology is not None:
        from chronicler.epidemiology import set_epidemiology_enabled
        set_epidemiology_enabled(world, epidemiology)
    # Money, credit and public finance switch (persisted on the world).
    finance = getattr(args, "finance", None)
    if finance is None and fresh_world:
        from chronicler.finance import DEFAULT_ENABLED_FOR_NEW_WORLDS as _FINANCE_DEFAULT
        finance = _FINANCE_DEFAULT
    if finance is not None:
        from chronicler.finance import set_finance_enabled
        set_finance_enabled(world, finance)
    # Diplomacy switch (persisted on the world): memory, treaties, polity ladder.
    diplomacy = getattr(args, "diplomacy", None)
    if diplomacy is None and fresh_world:
        from chronicler.diplomacy import DEFAULT_ENABLED_FOR_NEW_WORLDS as _DIPLOMACY_DEFAULT
        diplomacy = _DIPLOMACY_DEFAULT
    if diplomacy is not None:
        from chronicler.diplomacy import set_diplomacy_enabled
        set_diplomacy_enabled(world, diplomacy)
    # Techniques switch (persisted on the world): per-region practice that
    # diffuses along contact, inventions, and the era derived from them.
    techniques = getattr(args, "techniques", None)
    if techniques is None and fresh_world:
        from chronicler.techniques import DEFAULT_ENABLED_FOR_NEW_WORLDS as _TECHNIQUES_DEFAULT
        techniques = _TECHNIQUES_DEFAULT
    if techniques is not None:
        from chronicler.techniques import set_techniques_enabled
        set_techniques_enabled(world, techniques)
    # Maritime switch (persisted on the world): fleets, sea control, blockade,
    # piracy, naval campaigns and colonization by sea.
    maritime = getattr(args, "maritime", None)
    if maritime is None and fresh_world:
        from chronicler.maritime import DEFAULT_ENABLED_FOR_NEW_WORLDS as _MARITIME_DEFAULT
        maritime = _MARITIME_DEFAULT
    if maritime is not None:
        from chronicler.maritime import set_maritime_enabled
        set_maritime_enabled(world, maritime)
    # Great-person agendas switch (persisted on the world): generals,
    # merchants, prophets and scientists pursue objectives of their own.
    gp_agendas = getattr(args, "gp_agendas", None)
    if gp_agendas is None and fresh_world:
        from chronicler.gp_agendas import DEFAULT_ENABLED_FOR_NEW_WORLDS as _GP_AGENDAS_DEFAULT
        gp_agendas = _GP_AGENDAS_DEFAULT
    if gp_agendas is not None:
        from chronicler.gp_agendas import set_gp_agendas_enabled
        set_gp_agendas_enabled(world, gp_agendas)
    # Nomads switch (persisted on the world): subsistence modes seeded from
    # terrain, herds, raids and tribute, hordes and sedentarization.
    nomads = getattr(args, "nomads", None)
    if nomads is None and fresh_world:
        from chronicler.nomads import DEFAULT_ENABLED_FOR_NEW_WORLDS as _NOMADS_DEFAULT
        nomads = _NOMADS_DEFAULT
    if nomads is not None:
        from chronicler.nomads import set_nomads_enabled
        set_nomads_enabled(world, nomads)
    # Cities switch (persisted on the world): settlements grown into towns
    # and cities with commerce, dues, charters, revolts, sacks and falls.
    cities = getattr(args, "cities", None)
    if cities is None and fresh_world:
        from chronicler.cities import DEFAULT_ENABLED_FOR_NEW_WORLDS as _CITIES_DEFAULT
        cities = _CITIES_DEFAULT
    if cities is not None:
        from chronicler.cities import set_cities_enabled
        set_cities_enabled(world, cities)
    # Agent movements switch (persisted on the world): movements grounded in
    # people, with demands, reforms, crackdowns, risings, schisms, secession.
    agent_movements = getattr(args, "agent_movements", None)
    if agent_movements is None and fresh_world:
        from chronicler.agent_movements import DEFAULT_ENABLED_FOR_NEW_WORLDS as _MOVEMENTS_DEFAULT
        agent_movements = _MOVEMENTS_DEFAULT
    if agent_movements is not None:
        from chronicler.agent_movements import set_agent_movements_enabled
        set_agent_movements_enabled(world, agent_movements)
    # Guilds switch (persisted on the world): city guilds with privileges,
    # guild movements, the burgher faction and movement news.
    guilds = getattr(args, "guilds", None)
    if guilds is None and fresh_world:
        from chronicler.guilds import DEFAULT_ENABLED_FOR_NEW_WORLDS as _GUILDS_DEFAULT
        guilds = _GUILDS_DEFAULT
    if guilds is not None:
        from chronicler.guilds import set_guilds_enabled
        set_guilds_enabled(world, guilds)
    # In-world historiography (saved with the world in a state sidecar):
    # chroniclers and archives that record the run with their own biases.
    # Observational only; the simulation never reads it.
    historiography = getattr(args, "historiography", None)
    if historiography is None and fresh_world:
        from chronicler.historiography import DEFAULT_ENABLED_FOR_NEW_WORLDS as _HIST_DEFAULT
        historiography = _HIST_DEFAULT
    if historiography is not None:
        from chronicler.historiography import set_historiography_enabled
        set_historiography_enabled(world, historiography)
    from chronicler.historiography import historiography_on as _historiography_on
    # In-world languages and names (saved with the world in a state sidecar):
    # sound systems that drift and split, loanwords and the names each people
    # gives to the world. Observational only; the simulation never reads it.
    languages = getattr(args, "languages", None)
    if languages is None and fresh_world:
        from chronicler.languages import DEFAULT_ENABLED_FOR_NEW_WORLDS as _LANG_DEFAULT
        languages = _LANG_DEFAULT
    if languages is not None:
        from chronicler.languages import set_languages_enabled
        set_languages_enabled(world, languages)
    from chronicler.languages import languages_on as _languages_on
    agent_bridge = None
    if agent_mode in ("demographics-only", "shadow", "hybrid"):
        world.agent_mode = agent_mode
        from chronicler.agent_bridge import AgentBridge
        _use_sidecar = getattr(args, "validation_sidecar", False)
        _shadow_output = None
        if agent_mode == "shadow":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            _shadow_output = getattr(args, "shadow_output", None)
            if _shadow_output is None:
                _shadow_output = _default_shadow_output_path(output_path)
            else:
                _shadow_output = Path(_shadow_output)
        agent_bridge = AgentBridge(
            world,
            mode=agent_mode,
            shadow_output=_shadow_output,
            validation_sidecar=_use_sidecar,
            output_dir=output_path.parent if _use_sidecar else None,
            relationship_stats=getattr(args, "relationship_stats", False),
            agent_scale_mode=agent_scale_mode,
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
    mode_label = {"local": "local inference", "api": "Claude API", "gemini": "Gemini API"}.get(
        getattr(args, "narrator", "local"), "local inference"
    )
    print(f"  Sim model: {sim_model} | Narrative model: {narr_model} [{mode_label}]")

    # Pending injections list — shared mutable object with on_pause callback
    _pending = pending_injections if pending_injections is not None else []

    for turn_num in range(start_turn, num_turns):
        named_events_before = len(world.named_events)

        # Create action engine fresh each turn (needs current world state)
        action_engine = ActionEngine(world)

        def action_selector(civ, world, _engine=action_engine):
            return _engine.select_action(civ, seed=world.seed)

        # Run one turn — pending injections drain inside run_turn with accumulator
        source_turn = world.turn
        turn_result, _interrupt_requested = _run_turn_deferring_sigint(
            world,
            action_selector=action_selector,
            narrator=_noop_narrator or engine.narrator,
            seed=seed + turn_num,
            agent_bridge=agent_bridge,
            economy_tracker=economy_tracker,
            ecology_runtime=ecology_runtime,
            politics_runtime=politics_runtime,
            force_settlement_detection=(turn_num == num_turns - 1),
            pending_injections=_pending,
        )

        assert turn_result.observation.source_turn == source_turn
        assert turn_result.observation.completed_turn == source_turn + 1 == world.turn
        chronicle_text = turn_result.chronicle_text

        # Capture per-turn snapshot for viewer bundle
        # M24: cache accuracy for snapshot
        # Name-keyed cache entries can collide in externally supplied worlds.
        # Keep live reads for those worlds to preserve even discarded RNG draws.
        _unique_civ_names = len({c.name for c in world.civilizations}) == len(world.civilizations)
        _acc_cache: dict[tuple[str, str], float] = {}
        # Geography 2.0: procedural worlds keep civ-pair snapshot data
        # (relationships, accuracy, perception errors) for living civs only.
        # Civ records are never removed and secessions accumulate, so the
        # all-records matrices dominated big-world bundles. Template worlds
        # keep every record (unchanged bytes).
        if world.geography is not None:
            _pair_civs = [c for c in world.civilizations if c.regions]
            _pair_names: set[str] | None = {c.name for c in _pair_civs}
        else:
            _pair_civs = world.civilizations
            _pair_names = None
        # One border pass for all pairs (identical to per-pair region scans).
        _borders = border_pairs(world)
        for _obs in _pair_civs:
            for _tgt in _pair_civs:
                if _obs.name != _tgt.name:
                    _acc_cache[(_obs.name, _tgt.name)] = compute_accuracy(
                        _obs, _tgt, world, borders=_borders,
                    )
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
                    alive=len(civ.regions) > 0,
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
                    governance=(_governance_snapshot(civ) if world.governance is not None else None),
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
                    if _pair_names is None or civ_b in _pair_names
                }
                for civ_a, inner in world.relationships.items()
                if _pair_names is None or civ_a in _pair_names
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
            pandemic_regions=_pandemic_region_names(world),
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
                        for t in _pair_civs if t.name != obs_name
                    )
                    if acc > 0.0
                }
                for obs_name in (c.name for c in _pair_civs)
            },
            perception_errors={
                obs_name: {
                    tgt_name: {
                        stat: pv - getattr(tgt, stat)
                        for stat in ("military", "economy", "stability")
                        if (pv := _get_perceived_stat_with_accuracy(
                            obs, tgt, stat, world,
                            accuracy=(
                                _acc_cache[(obs_name, tgt_name)] if _unique_civ_names
                                else compute_accuracy(obs, tgt, world)
                            ),
                        )) is not None
                    }
                    for tgt in _pair_civs
                    for tgt_name in [tgt.name]
                    if tgt_name != obs_name and _acc_cache.get((obs_name, tgt_name), 0.0) > 0.0
                }
                for obs in _pair_civs
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
            **_war_snapshot_fields(world),
            **_contact_snapshot_fields(world),
            **_epidemic_snapshot_fields(world),
            **_finance_snapshot_fields(world),
            **_diplomacy_snapshot_fields(world),
            **_techniques_snapshot_fields(world),
            **_maritime_snapshot_fields(world),
            **_gp_agendas_snapshot_fields(world),
            **_nomads_snapshot_fields(world),
            **_cities_snapshot_fields(world),
            **_agent_movements_snapshot_fields(world),
            **_guilds_snapshot_fields(world),
            **_food_snapshot_fields(world),
            **_migration_snapshot_fields(world),
        )

        # M56b: Urban fraction aggregation from agent snapshot
        urban_by_civ: dict[str, tuple[int, int]] = {}  # civ_name -> (urban_count, total_count)
        agent_rows = turn_result.observation.phase10_agents
        if agent_bridge and agent_rows is not None:
            assert agent_rows.stamp.source_turn == source_turn
            assert agent_rows.stamp.stage == "phase10_entry"
            # Views with NumPy columns (AgentRows) take the columnar count;
            # other views and batches with nulls keep the row loop.
            urban_arrays = None
            if agent_rows.has("settlement_id") and hasattr(agent_rows, "arrays"):
                urban_arrays = agent_rows.arrays("civ_affinity", "settlement_id")
                if urban_arrays is not None and agent_rows.has("region"):
                    region_array = agent_rows.array("region")
                    urban_arrays = None if region_array is None else (*urban_arrays, region_array)
                elif urban_arrays is not None:
                    urban_arrays = (*urban_arrays, None)
            if urban_arrays is not None:
                urban_by_civ = _urban_counts_by_civ(world, *urban_arrays)
            elif agent_rows.has("settlement_id"):
                civ_col = agent_rows.ints("civ_affinity")
                sid_col = agent_rows.ints("settlement_id")
                region_col = agent_rows.ints("region") if agent_rows.has("region") else [None] * len(civ_col)
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
                del civ_col, sid_col, region_col

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

        # In-world chroniclers record the completed turn (reads the world only).
        if _historiography_on(world):
            from chronicler.historiography import observe_turn
            observe_turn(world)
        # The world's languages drift, split and name what their peoples know.
        if _languages_on(world):
            from chronicler.languages import observe_turn as observe_languages
            observe_languages(world)

        # Phase-10 rows are historical inputs only for synchronous capture.
        # Release the handoff before callbacks can mutate world or bridge state.
        del agent_rows, turn_result

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
            turn_events = history_index(world).events_for_turn(world, world.turn - 1)
            turn_named = world.named_events[named_events_before:]
            on_turn(snapshot, chronicle_text, turn_events, turn_named)

        # Update memory streams with this turn's events
        turn_events = history_index(world).events_for_turn(world, world.turn - 1)
        for event in turn_events:
            for actor in event.actors:
                if actor in memories:
                    memories[actor].add(
                        text=event.description or f"{event.event_type} occurred",
                        turn=world.turn,
                        importance=event.importance,
                    )

        # Save memory streams at this point of the turn on checkpoint turns, the
        # final turn and any turn a callback may end the run, so the files on
        # disk at those turns match an every-turn writer's exactly.
        _is_final_turn = turn_num == num_turns - 1
        _checkpoint_due = world.turn % _state_every == 0
        _pause_turn = bool(_pause_every and on_pause and world.turn % _pause_every == 0)
        _may_stop = _pause_turn or quit_check is not None
        output_dir = output_path.parent
        _memories_saved = _checkpoint_due or _is_final_turn or _may_stop
        if _memories_saved:
            _save_memory_streams(memories, output_dir)
        # Reflections only append; an interrupt checkpoint written after this
        # turn's reflection uses these counts to write the save-point content.
        _reflection_counts = {name: len(stream.reflections) for name, stream in memories.items()}

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

        # Resumable checkpoint every _state_every turns and before a pause; the
        # final state is written after the loop on every exit path.
        if state_path and ((_checkpoint_due and not _is_final_turn) or _pause_turn):
            _write_state_checkpoint(world, state_path)
            _state_saved = True
        else:
            _state_saved = False

        # Ctrl-C during the turn: save this completed turn, then stop.
        if _interrupt_requested:
            if not _memories_saved:
                _save_memory_streams(memories, output_dir, _reflection_counts)
            if state_path and not _state_saved:
                _write_state_checkpoint(world, state_path)
            if state_path:
                print(f"Interrupted after turn {world.turn}; resume with --resume {state_path}",
                      file=sys.stderr)
            raise KeyboardInterrupt

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

    # The in-world accounts as the bundle carries them (None while off); the
    # curated narration below reads them back through an AccountIndex.
    historiography_export = None
    account_index = None
    # The languages field, read back through a NameIndex for perspective names.
    languages_export = None
    name_index = None
    if _languages_on(world):
        from chronicler.languages import NameIndex, export as _export_languages
        languages_export = _export_languages(world)
        name_index = NameIndex(languages_export)
    if _historiography_on(world):
        from chronicler.historiography import AccountIndex, export as _export_historiography
        historiography_export = _export_historiography(world)
        account_index = AccountIndex(historiography_export, names=name_index)

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
            contested=account_index.contested_bonus() if account_index else None,
        )

        def progress_cb(completed: int, total: int, eta: float | None) -> None:
            eta_str = f" (ETA: {eta:.1f}s)" if eta is not None else ""
            print(f"  Narrating {completed}/{total}{eta_str}")

        # M45: Include retired persons for dead character arc context
        all_great_persons = list(gp_by_name.values()) if gp_by_name else None

        chronicle_entries = engine.narrate_batch(
            moments, history, on_progress=progress_cb,
            great_persons=all_great_persons,
            world=world,
            historiography=account_index,
            languages=name_index,
            social_edges=agent_bridge.read_social_edges() if agent_bridge is not None else None,
            dissolved_edges_by_turn=world.dissolved_edges_by_turn if hasattr(world, "dissolved_edges_by_turn") else None,
            agent_name_map=agent_bridge.named_agents if agent_bridge is not None else None,
            gini_by_civ=agent_bridge._gini_by_civ if agent_bridge is not None else None,
            economy_result=agent_bridge._economy_result if agent_bridge is not None else None,
            displacement_by_region=agent_bridge.displacement_by_region if agent_bridge is not None else None,
            dynasty_registry=agent_bridge.dynasty_registry if agent_bridge is not None else None,
        )

        print(f"API narration: curated {len(moments)} moments from {len(world.events_timeline)} events")

        # Token usage summary
        if _tracks_tokens(_narr):
            inp, out, calls = _token_usage_since(_narr, _narr_token_baseline)
            print(f"API narration: {calls} calls, "
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
        historiography=historiography_export,
        languages=languages_export,
    )
    # M44: narrator provenance metadata
    bundle["metadata"]["narrator_mode"] = _narrator_mode
    _set_narrative_token_metadata(bundle["metadata"], _narr, _narr_token_baseline)

    # M53: relationship stats metadata
    if agent_bridge is not None and agent_bridge._collect_rel_stats:
        bundle["metadata"]["relationship_stats"] = agent_bridge.relationship_stats

    # M57b: household stats metadata (always collected in agent modes)
    if agent_bridge is not None:
        household_stats = getattr(agent_bridge, "household_stats", [])
        if not isinstance(household_stats, list):
            household_stats = []
        bundle["metadata"]["household_stats"] = household_stats

    # M58a: merchant trip stats metadata
    if agent_bridge is not None:
        m_trip_stats = getattr(agent_bridge, "merchant_trip_stats", [])
        if not isinstance(m_trip_stats, list):
            m_trip_stats = []
        bundle["metadata"]["merchant_trip_stats"] = m_trip_stats

    # M59a: knowledge stats metadata
    if agent_bridge is not None:
        k_stats = getattr(agent_bridge, "knowledge_stats", [])
        if not isinstance(k_stats, list):
            k_stats = []
        bundle["metadata"]["knowledge_stats"] = k_stats

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
    parser.add_argument("--worldgen", choices=("auto", "template", "procedural"), default=None,
                        help="World generator: auto (default) uses the region templates up to "
                             "12 regions and procedural geography above; 'procedural' forces "
                             "heightmap/Voronoi geography at any size")
    parser.add_argument("--output", type=str, default="output/chronicle.md", help="Output file path")
    parser.add_argument("--state", type=str, default="output/state.json", help="State file path")
    parser.add_argument("--resume", type=str, default=None, help="Resume from a saved state JSON file")
    parser.add_argument("--state-every", type=_positive_int, default=None, metavar="K",
                        help=f"Write the resumable --state checkpoint and memory streams every K turns "
                             f"(default {DEFAULT_STATE_EVERY}; 1 = every turn). The final state is always "
                             f"written, and Ctrl-C finishes the current turn and checkpoints it.")
    parser.add_argument("--reflection-interval", type=int, default=None)
    parser.add_argument("--local-url", type=str, default=DEFAULT_CONFIG["local_url"],
                        help="LM Studio / local model API URL (OpenAI-compatible)")
    parser.add_argument("--sim-model", type=str, default=None,
                        help="Model name for simulation calls (default: LM Studio's loaded model)")
    parser.add_argument("--narrative-model", type=str, default=None,
                        help="Model name for narrative generation (default: LM Studio's loaded model)")
    parser.add_argument("--llm-actions", action="store_true", default=False,
                        help="Deprecated compatibility flag; ignored. Action selection is deterministic.")
    parser.add_argument("--scenario", type=str, default=None,
                        help="Path to a YAML scenario file")
    # --- M10 workflow flags ---
    parser.add_argument("--batch", type=int, default=None,
                        help="Run N chronicles with sequential seeds")
    parser.add_argument("--parallel", type=int, nargs="?", const=-1, default=None,
                        help="Parallel workers for batch mode (default: cpu_count-1).")
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
    parser.add_argument("--live-origin", action="append", default=None, metavar="ORIGIN",
                        help="Live mode: also accept a viewer served from ORIGIN (e.g. "
                             "http://localhost:5174); the Vite dev (5173) and preview (4173) "
                             "origins on localhost are always accepted. Repeatable.")
    parser.add_argument("--simulate-only", action="store_true",
                        help="Run simulation without LLM narrative generation")
    parser.add_argument("--agents", type=str, default="off",
                        choices=["off", "demographics-only", "shadow", "hybrid"],
                        help="Agent mode: off (aggregate), demographics-only, shadow (compare), hybrid (agent-driven)")
    parser.add_argument("--agent-scale-mode", choices=["exact", "fast"], default=None,
                        help="Native agent tick algorithms: exact (default; byte-identical reference "
                             "algorithms) or fast (bounded-work neighbour, marriage and formation "
                             "candidate sampling for large populations; changes results; not saved "
                             "in state, pass it again on --resume)")
    parser.add_argument("--mutual-aid", action=argparse.BooleanOptionalAction, default=None,
                        help="Adjacent same-polity food aid after repeated food stress, paid from the "
                             "treasury (agent modes; dormant with --agents off; default on for new "
                             "worlds; --no-mutual-aid disables; saved on resume)")
    parser.add_argument("--fisheries", action=argparse.BooleanOptionalAction, default=None,
                        help="Renewable fish stocks: fishing draws down a recovering stock that caps "
                             "the catch (default on for new worlds; --no-fisheries disables; saved on resume)")
    parser.add_argument("--campaigns", action=argparse.BooleanOptionalAction, default=None,
                        help="M60 campaigns: armies, logistics, battles, sieges, occupation and "
                             "negotiated peace replace instant WAR resolution (default on for new "
                             "worlds; --no-campaigns restores instant wars; saved on resume)")
    parser.add_argument("--governance", action=argparse.BooleanOptionalAction, default=None,
                        help="Phase 8 governance runtime: institutions, elites, legitimacy, ambitions, PSI "
                             "(default on for new worlds; --no-governance disables; saved on resume)")
    parser.add_argument("--contact-ledger", action=argparse.BooleanOptionalAction, default=None,
                        help="Contact & trade-flow ledger: decayed region x region flows of goods, "
                             "migrants, soldiers and pilgrims feeding trade_volume, movement spread, "
                             "merchant great persons, trade warmth, embargo/war shocks and plague spread "
                             "(default on for new worlds; --no-contact-ledger disables; saved on resume)")
    parser.add_argument("--epidemiology", action=argparse.BooleanOptionalAction, default=None,
                        help="Regional SEIRS epidemiology: pathogens spread along the contact ledger, "
                             "virgin-soil epidemics, quarantine and labour scarcity, replacing the hazard "
                             "plague and the M18 pandemic (default on for new worlds with the contact ledger; "
                             "--no-epidemiology opts out; saved on resume)")
    parser.add_argument("--finance", action=argparse.BooleanOptionalAction, default=None,
                        help="Money, credit and public finance: upkeep and court costs, state borrowing "
                             "from merchant houses and foreign lenders, debt service, default, debasement "
                             "and a per-civ price index feeding the governance PSI (default on for new "
                             "worlds; --no-finance opts out; saved on resume)")
    parser.add_argument("--diplomacy", action=argparse.BooleanOptionalAction, default=None,
                        help="Diplomacy: diplomatic memory (trust, grievances, goodwill), treaties "
                             "(peace, non-aggression, alliance, trade pact, tribute) and the polity "
                             "ladder client -> vassal -> personal union -> annexation (default on "
                             "for new worlds; --no-diplomacy opts out; saved on resume)")
    parser.add_argument("--techniques", action=argparse.BooleanOptionalAction, default=None,
                        help="Technology as diffusing techniques: per-region practice of about 30 "
                             "techniques spreads along contact flows, is invented from research "
                             "inputs and decays without practitioners; the era is derived from it "
                             "(default on for new worlds; --no-techniques opts out; saved on resume)")
    parser.add_argument("--maritime", action=argparse.BooleanOptionalAction, default=None,
                        help="Maritime layer: fleets built at coastal ports, sea-zone control, "
                             "blockades of enemy sea lanes and sea supply, escorted crossings and "
                             "amphibious landings, piracy and colonization by sea (default on for "
                             "new worlds; --no-maritime opts out; saved on resume)")
    parser.add_argument("--gp-agendas", action=argparse.BooleanOptionalAction, default=None,
                        help="Great-person agendas: generals seek campaigns and may seize the throne, "
                             "merchants open and protect trade routes, found trading houses and lend "
                             "to the crown, prophets spread the faith and found shrines, scientists "
                             "pursue the next era or an invention; alliances and rivalries weigh on "
                             "coups and succession (default on for new worlds; --no-gp-agendas opts out; "
                             "saved on resume)")
    parser.add_argument("--nomads", action=argparse.BooleanOptionalAction, default=None,
                        help="Pastoral and nomadic peoples: subsistence modes seeded from terrain "
                             "(steppe, desert and tundra favour herding), herds with drought and "
                             "dzud, seasonal pastures, raids and tribute, hordes under a strong khan "
                             "that fragment on his death, and sedentarization of conquerors (default "
                             "on for new worlds; --no-nomads opts out; saved on resume)")
    parser.add_argument("--cities", action=argparse.BooleanOptionalAction, default=None,
                        help="Cities as actors: settlements grown into towns and cities with "
                             "commerce and dues to their lord, a pull on rural migrants of the "
                             "realm, charters, urban revolts and free cities, sacks, walls and "
                             "falls; city markets that draw grain from the hinterland; needs an "
                             "agent mode to found cities (default on for new worlds; --no-cities "
                             "opts out; saved on resume)")
    parser.add_argument("--agent-movements", action=argparse.BooleanOptionalAction, default=None,
                        help="Movements grounded in people: agents with shared grievances (hunger, "
                             "foreign rule, an unanswered faith) join leagues, autonomist currents "
                             "and sects through their bonds, towns, migrants and merchants; at "
                             "scale they press factions and rulers, raise leaders, win lasting "
                             "reforms (poor relief, home rule, toleration) that later rulers may "
                             "repeal, suffer crackdowns and martyrs, split faiths or rise and "
                             "secede; needs an agent mode to found movements (default on for new "
                             "worlds; --no-agent-movements opts out; saved on resume)")
    parser.add_argument("--guilds", action=argparse.BooleanOptionalAction, default=None,
                        help="Guilds and burghers: cities that make wares or hold enough merchants "
                             "form guilds, which charters grant a monopoly and a say in civic "
                             "dues; levies, revoked charters, sacks and occupations threaten them "
                             "and a guild may rise as a movement for a guild charter; a burgher "
                             "faction presses rulers for trade, low tolls, charters and order; "
                             "news of movements travels as information packets and draws people "
                             "to like movements; needs cities (and an agent mode for guild "
                             "movements) (default on for new worlds; --no-guilds opts out; saved "
                             "on resume)")
    parser.add_argument("--historiography", action=argparse.BooleanOptionalAction, default=None,
                        help="In-world historiography: court and temple chroniclers record events "
                             "with their own biases (omissions, inflated victories, blamed enemies, "
                             "praised or condemned rulers, divine wrath) into archives that sacks, "
                             "conquest, fire and plague destroy. Observational: the simulation is "
                             "unchanged; the bundle gains a 'historiography' field and curated "
                             "narration cites the accounts (default on for new worlds; "
                             "--no-historiography opts out; saved with the state)")
    parser.add_argument("--languages", action=argparse.BooleanOptionalAction, default=None,
                        help="In-world languages and names: each people speaks a language with "
                             "its own sound system that drifts, splits into daughter languages "
                             "and borrows through contact; civs, regions, settlements, faiths and "
                             "persons get names in the languages that know them. Observational: "
                             "the simulation is unchanged; the bundle gains a 'languages' field "
                             "and narration glosses native names (default on for new worlds; "
                             "--no-languages opts out; saved with the state)")
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
    # --- M20a narration pipeline flags ---
    parser.add_argument("--narrate", type=Path, default=None,
                        help="Narrate a simulate-only bundle")
    parser.add_argument("--budget", type=int, default=50,
                        help="Number of moments to narrate")
    parser.add_argument("--narrate-output", type=Path, default=None,
                        help="Output path for narrated bundle")
    parser.add_argument("--narrator", type=str, default="local",
                        choices=["local", "api", "gemini", "mechanical"],
                        help="Narrator backend: local (LM Studio), api (Claude API), gemini (Gemini API), "
                             "or mechanical (no LLM: curated moments rendered from event descriptions "
                             "and their recorded causal chains; works with --simulate-only)")
    parser.add_argument("--relationship-stats", action="store_true",
                        help="Enable per-tick relationship distribution snapshots")
    parser.add_argument("--validation-sidecar", action="store_true",
                        help="Write heavy validation sidecars (graph snapshots, agent aggregates)")
    return parser


def _run_narrate(args: argparse.Namespace) -> None:
    """Load a simulate-only bundle, curate moments, and narrate them."""
    import json as _json
    from chronicler.curator import curate
    from chronicler.narration_inputs import from_bundle

    bundle_path = Path(args.narrate)
    if not bundle_path.exists():
        print(f"Error: Bundle not found: {bundle_path}", file=sys.stderr)
        sys.exit(1)

    with open(bundle_path) as f:
        bundle = _json.load(f)
    # Version 6 writes the history as deltas and version-5 histories leave dead
    # civs out: decode and restore their rows so curation and narration read
    # the history the run itself held in memory.
    from chronicler.snapshot_pruning import restore_bundle
    bundle = restore_bundle(bundle)

    # Events, history, world, characters and in-world indexes, read as the
    # live server's range narration reads them (chronicler.narration_inputs).
    # In-world accounts and names are absent in older bundles and in runs
    # with those layers off; --no-historiography / --no-languages ignore them.
    inputs = from_bundle(
        bundle, default_seed=42,
        historiography=getattr(args, "historiography", None) is not False,
        languages=getattr(args, "languages", None) is not False,
    )
    events = inputs.events
    history = inputs.history
    budget = args.budget

    # Create LLM clients
    sim_client, narrative_client = create_clients(
        local_url=args.local_url,
        sim_model=getattr(args, "sim_model", None),
        narrative_model=getattr(args, "narrative_model", None),
        narrator=getattr(args, "narrator", "local"),
    )

    # Curate moments
    moments, gap_summaries = curate(
        events=events,
        named_events=inputs.named_events,
        history=history,
        budget=budget,
        seed=inputs.seed,
        **inputs.curate_kwargs(),
    )

    print(f"Curated {len(moments)} moments from {len(events)} events (budget={budget})")

    # Narrate
    engine = NarrativeEngine(sim_client=sim_client, narrative_client=narrative_client)

    def progress_cb(completed: int, total: int, eta: float | None) -> None:
        eta_str = f" (ETA: {eta:.1f}s)" if eta is not None else ""
        print(f"  Narrating {completed}/{total}{eta_str}")

    chronicle_entries = engine.narrate_batch(
        moments, history, on_progress=progress_cb, **inputs.narrate_kwargs(),
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
    _set_narrative_token_metadata(result["metadata"], narrative_client)

    with open(output_path, "w", encoding="utf-8") as f:
        _json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Narrated {len(chronicle_entries)} entries -> {output_path}")


def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    if getattr(args, "compare", None) and not getattr(args, "analyze", None):
        parser.error("--compare requires --analyze")
    if getattr(args, "narrate_output", None) and not getattr(args, "narrate", None):
        parser.error("--narrate-output requires --narrate")

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

    if args.llm_actions:
        logger.warning(
            "--llm-actions is deprecated and ignored; simulation action selection remains deterministic"
        )
        args.llm_actions = False

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
                  "Install with: pip install -e \".[gemini]\"", file=sys.stderr)
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
            if getattr(args, "narrator", "local") == "mechanical":
                from chronicler.llm import MechanicalClient
                narrative_client = MechanicalClient()
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
        from chronicler.batch_manifest import BatchDestinationError
        try:
            batch_dir = run_batch(args, sim_client=sim_client, narrative_client=narrative_client, scenario_config=scenario_config)
        except BatchDestinationError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
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
