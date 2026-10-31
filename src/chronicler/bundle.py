"""Chronicle bundle assembly and export."""
from __future__ import annotations

import json
from pathlib import Path

from chronicler.artifact_io import atomic_write_bytes, atomic_write_json
from chronicler.bundle_codec import BUNDLE_VERSION, pack_bundle
from chronicler.models import WorldState

try:
    import pyarrow as pa
    import pyarrow.ipc as ipc
    HAS_ARROW = True
except ImportError:
    HAS_ARROW = False


def write_bundle(
    bundle: dict,
    path: Path,
    world: WorldState | None = None,
) -> None:
    """Write the chronicle bundle as JSON and optional Arrow sidecars.

    Args:
        bundle: The bundle dict to write.
        path: Output path for the JSON bundle.
        world: WorldState for agent events. If None, no agent_events.arrow is written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, pack_bundle(bundle))

    if world is not None:
        write_agent_events_arrow(world, path.parent)


def write_agent_events_arrow(world: WorldState, output_dir: Path) -> Path | None:
    """Write agent_events.arrow if agent events exist and pyarrow is available."""
    if not HAS_ARROW:
        return None
    if not world.agent_events_raw:
        return None

    events = world.agent_events_raw
    table = pa.table({
        "turn": pa.array([e.turn for e in events], type=pa.uint32()),
        "agent_id": pa.array([e.agent_id for e in events], type=pa.uint32()),
        "event_type": pa.array([e.event_type for e in events], type=pa.utf8()),
        "region": pa.array([e.region for e in events], type=pa.uint16()),
        "target_region": pa.array([e.target_region for e in events], type=pa.uint16()),
        "civ_affinity": pa.array([e.civ_affinity for e in events], type=pa.uint16()),
        "occupation": pa.array([e.occupation for e in events], type=pa.uint8()),
        "belief": pa.array([e.belief for e in events], type=pa.uint8()),
        "target_agent_id": pa.array(
            [e.target_agent_id for e in events], type=pa.uint32()
        ),
        "formed_turn": pa.array([e.formed_turn for e in events], type=pa.uint32()),
    })

    arrow_path = Path(output_dir) / "agent_events.arrow"
    sink = pa.OSFile(str(arrow_path), "wb")
    writer = ipc.new_file(sink, table.schema)
    writer.write_table(table)
    writer.close()
    sink.close()
    atomic_write_bytes(arrow_path, arrow_path.read_bytes()) if False else None
    return arrow_path


def assemble_bundle(
    world: WorldState,
    history: list,
    chronicle_entries: list,
    era_reflections: dict,
    sim_model: str | None,
    narrative_model: str | None,
    interestingness_score: float | None,
    sim_input_tokens: int = 0,
    sim_output_tokens: int = 0,
    narrative_input_tokens: int = 0,
    narrative_output_tokens: int = 0,
    extra_metadata: dict | None = None,
) -> dict:
    """Assemble the chronicle bundle dict from world, history, and narrative.

    Bundle version 5 (docs/performance/dead-civ-pruning.md): civs with no
    regions are left out of every snapshot's civ_stats.  The omitted rows are
    recorded in pruned_civ_stats; chronicle.bundle_codec.restore_bundle()
    returns the full version-4 layout, and is applied when the bundle is read
    for analysis.  Civilization order within the dicts follows the world's
    civilizations list (insertion order).
    """
    from datetime import datetime

    events = [e.model_dump(mode="json") for e in world.events_timeline]
    named = [e.model_dump(mode="json") for e in world.named_events]
    entries = [e.model_dump(mode="json") for e in chronicle_entries]
    reflections = {str(k): v for k, v in era_reflections.items()}

    # Prune dead-civ civ_stats rows.  Bundle version 5 drops them; the
    # reader-side restore_bundle() puts them back.
    pruned_civ_stats: dict[str, dict] = {}
    pruned_history = []
    for snapshot in history:
        snapshot_dict = snapshot.model_dump(mode="json") if hasattr(snapshot, "model_dump") else snapshot
        civ_stats = snapshot_dict.get("civ_stats", {})
        alive_stats = {}
        dead_stats = {}
        for civ_name, civ_data in civ_stats.items():
            regions = civ_data.get("regions")
            if regions is not None and len(regions) == 0:
                dead_stats[civ_name] = civ_data
            elif civ_data.get("alive") is False:
                dead_stats[civ_name] = civ_data
            else:
                alive_stats[civ_name] = civ_data
        turn_key = str(snapshot_dict.get("turn", len(pruned_history)))
        if dead_stats:
            pruned_civ_stats[turn] = dead_stats  # type: ignore[name-defined]
        snapshot_dict = dict(snapshot_dict)
        snapshot_dict["civ_stats"] = alive_stats
        pruned_history.append(snapshot_dict)

    world_state = json.loads(world.model_dump_json())
    # Strip LLM-generated arc_summary from great persons (C-13 audit: must not persist).
    for civ_data in world_state.get("civilizations", []):
        for gp_data in civ_data.get("great_persons", []):
            gp_data.pop("arc_summary", None)
    # Strip transient turn fields (not part of the persisted schema).
    for civ_data in world_state.get("civilizations", []):
        for key in ("max_precap_weight", "regions_start_of_turn", "was_in_twilight", "capital_start_of_turn"):
            civ_data.pop(key, None)
    for region_data in world_state.get("regions", []):
        region_data.pop("resource_current_yields", None)

    metadata = {
        "seed": world.seed,
        "total_turns": world.turn,
        "generated_at": datetime.now().isoformat(),
        "sim_model": sim_model,
        "narrative_model": narrative_model,
        "scenario_name": world.scenario_name,
        "interestingness_score": interestingness_score,
        "bundle_version": BUNDLE_VERSION,
        "sim_input_tokens": sim_input_tokens,
        "sim_output_tokens": sim_output_tokens,
        "narrative_input_tokens": narrative_input_tokens,
        "narrative_output_tokens": narrative_output_tokens,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    return {
        "world_state": world_state,
        "history": pruned_history,
        "events_timeline": events,
        "named_events": named,
        "chronicle_entries": entries,
        "era_reflections": reflections,
        "metadata": metadata,
        "pruned_civ_stats": pruned_civ_stats,
    }
