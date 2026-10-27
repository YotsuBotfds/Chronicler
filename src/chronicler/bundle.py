"""Bundle assembly — writes chronicle_bundle.json for the viewer."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chronicler.models import ChronicleEntry, GapSummary, TurnSnapshot, WorldState
from chronicler.bundle_codec import BUNDLE_VERSION, dumps_bundle
from chronicler.snapshot_pruning import PRUNED_CIV_STATS_KEY, prune_history

try:
    import pyarrow as pa
    import pyarrow.ipc as ipc
    HAS_ARROW = True
except ImportError:
    HAS_ARROW = False

logger = logging.getLogger(__name__)

# 4: events carry provenance (event_id, causes, region, civs, episode,
# duration; omitted while empty), chronicle entries carry causal_chains and
# causal links carry cause_id/effect_id/provenance. Version-3 readers ignore
# the additions; version-4 readers treat them as optional.
# 5: history snapshots leave out civilizations that are dead at that turn
# (civ_stats, capitals and the pairwise tables), keeping each one's final row;
# ``pruned_civ_stats`` restores the omitted civ_stats rows exactly
# (chronicler.snapshot_pruning). world_state is unchanged.
# An optional top-level ``historiography`` field (in-world accounts, its own
# ``version``) and chronicle entries' optional ``accounts`` need no bump:
# readers that do not know them ignore them. The same holds for the optional
# ``languages`` field (in-world languages and names, its own ``version``).
# 6: the file writes the history as changes between snapshots
# (``history_delta``) and does not repeat the timeline and named events inside
# ``world_state`` (chronicler.bundle_codec). Decoded, it is the version-5
# layout; assemble_bundle returns that layout and write_bundle encodes it.
LEGACY_BUNDLE_VERSION = BUNDLE_VERSION


def _strip_llm_fields(world_dict: dict) -> dict:
    """Remove LLM-generated fields from world state to prevent narration→state feedback.

    arc_summary is prompt-only narration context and must not persist into the
    authoritative bundle (M18 LLM isolation contract).
    """
    for civ in world_dict.get("civilizations", []):
        for gp in civ.get("great_persons", []):
            gp.pop("arc_summary", None)
    return world_dict


def assemble_bundle(
    world: WorldState,
    history: list[TurnSnapshot],
    chronicle_entries: list[ChronicleEntry],
    era_reflections: dict[int, str],
    sim_model: str,
    narrative_model: str,
    interestingness_score: float | None,
    gap_summaries: list[GapSummary] | None = None,
    historiography: dict[str, Any] | None = None,
    languages: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble all run data into a single dict for the viewer bundle.

    ``historiography`` (``chronicler.historiography.export``) and
    ``languages`` (``chronicler.languages.export``) are optional observational
    fields, added at the end only when present, so bundles of runs without
    them keep their exact bytes. So is ``narration_provenance``, the names
    table of narrated entries' provenance (``chronicler.narration_provenance``).
    """
    pruned_history, pruned_civ_stats = prune_history(s.model_dump(mode="json") for s in history)
    bundle = {
        "world_state": _strip_llm_fields(world.model_dump(mode="json")),
        "history": pruned_history,
        PRUNED_CIV_STATS_KEY: pruned_civ_stats,
        "events_timeline": [
            e.model_dump(mode="json") for e in world.events_timeline
        ],
        "named_events": [
            ne.model_dump(mode="json") for ne in world.named_events
        ],
        "chronicle_entries": [entry.model_dump(mode="json") for entry in chronicle_entries],
        "gap_summaries": [gs.model_dump(mode="json") for gs in (gap_summaries or [])],
        "era_reflections": {
            str(turn): text for turn, text in era_reflections.items()
        },
        "metadata": {
            "seed": world.seed,
            "total_turns": world.turn,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sim_model": sim_model,
            "narrative_model": narrative_model,
            "scenario_name": getattr(world, "scenario_name", None),
            "interestingness_score": interestingness_score,
            "bundle_version": LEGACY_BUNDLE_VERSION,
        },
    }
    if historiography is not None:
        bundle["historiography"] = historiography
    if languages is not None:
        bundle["languages"] = languages
    # Narrated entries' provenance names one table (absent without narration).
    from chronicler.narration_provenance import BUNDLE_FIELD, compact_entries
    provenance = compact_entries(bundle["chronicle_entries"])
    if provenance is not None:
        bundle[BUNDLE_FIELD] = provenance
    return bundle


def write_bundle(bundle: dict[str, Any], path: Path,
                  world: WorldState | None = None) -> None:
    """Write an assembled bundle to a JSON file, in the version-6 layout.

    Read it back with ``chronicler.bundle_codec.load_bundle``. If *world* is
    provided and contains agent_events_raw, an Arrow IPC sidecar file
    ``agent_events.arrow`` is written next to the JSON bundle.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Bundles are machine-consumed and timeline-heavy; compact encoding and
    # the snapshot deltas keep the single-file artifact within its size budget.
    path.write_text(dumps_bundle(bundle), encoding="utf-8")

    if world is not None:
        write_agent_events_arrow(world, path.parent)


def write_agent_events_arrow(world: WorldState, bundle_dir: Path) -> Path | None:
    """Serialize ``world.agent_events_raw`` as Arrow IPC.

    Returns the path written, or *None* when skipped (no events or no pyarrow).
    """
    if not getattr(world, "agent_events_raw", None):
        return None
    if not HAS_ARROW:
        logger.debug("pyarrow not available; skipping agent_events.arrow")
        return None

    events = world.agent_events_raw
    batch = pa.record_batch({
        "turn": pa.array([e.turn for e in events], type=pa.uint32()),
        "agent_id": pa.array([e.agent_id for e in events], type=pa.uint32()),
        "event_type": pa.array([e.event_type for e in events], type=pa.utf8()),
        "region": pa.array([e.region for e in events], type=pa.uint16()),
        "target_region": pa.array([e.target_region for e in events], type=pa.uint16()),
        "civ_affinity": pa.array([e.civ_affinity for e in events], type=pa.uint16()),
        "occupation": pa.array([e.occupation for e in events], type=pa.uint8()),
        "belief": pa.array([e.belief for e in events], type=pa.uint8()),
        "target_agent_id": pa.array([e.target_agent_id for e in events], type=pa.uint32()),
        "formed_turn": pa.array([e.formed_turn for e in events], type=pa.uint32()),
        # Migrations: index into models.MIGRATION_DRIVER_NAMES (255 elsewhere).
        # Readers treat a file without the column as recording no driver.
        "migration_driver": pa.array([e.migration_driver for e in events], type=pa.uint8()),
    })

    out_path = bundle_dir / "agent_events.arrow"
    with pa.OSFile(str(out_path), "wb") as f:
        writer = ipc.new_file(f, batch.schema)
        writer.write_batch(batch)
        writer.close()

    return out_path
