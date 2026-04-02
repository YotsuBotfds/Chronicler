"""Bundle assembly — writes chronicle_bundle.json for the viewer."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chronicler.models import ChronicleEntry, GapSummary, TurnSnapshot, WorldState

try:
    import pyarrow as pa
    import pyarrow.ipc as ipc
    HAS_ARROW = True
except ImportError:
    HAS_ARROW = False

logger = logging.getLogger(__name__)


def _strip_llm_fields(world_dict: dict) -> dict:
    """Remove LLM-generated fields from world state to prevent narration→state feedback.

    arc_summary is written by _update_arc_summary() from LLM output during narration.
    It must not persist into the authoritative bundle (M18 LLM isolation contract).
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
) -> dict[str, Any]:
    """Assemble all run data into a single dict for the viewer bundle."""
    return {
        "world_state": _strip_llm_fields(json.loads(world.model_dump_json())),
        "history": [json.loads(s.model_dump_json()) for s in history],
        "events_timeline": [
            json.loads(e.model_dump_json()) for e in world.events_timeline
        ],
        "named_events": [
            json.loads(ne.model_dump_json()) for ne in world.named_events
        ],
        "chronicle_entries": [entry.model_dump() for entry in chronicle_entries],
        "gap_summaries": [gs.model_dump() for gs in (gap_summaries or [])],
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
            "bundle_version": 1,
        },
    }


def write_bundle(bundle: dict[str, Any], path: Path,
                  world: WorldState | None = None) -> None:
    """Write assembled bundle to a JSON file.

    If *world* is provided and contains agent_events_raw, an Arrow IPC
    sidecar file ``agent_events.arrow`` is written next to the JSON bundle.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")

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
    })

    out_path = bundle_dir / "agent_events.arrow"
    with pa.OSFile(str(out_path), "wb") as f:
        writer = ipc.new_file(f, batch.schema)
        writer.write_batch(batch)
        writer.close()

    return out_path
