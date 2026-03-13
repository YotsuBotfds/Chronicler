"""Bundle assembly — writes chronicle_bundle.json for the viewer."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chronicler.chronicle import ChronicleEntry
from chronicler.models import TurnSnapshot, WorldState


def assemble_bundle(
    world: WorldState,
    history: list[TurnSnapshot],
    chronicle_entries: list[ChronicleEntry],
    era_reflections: dict[int, str],
    sim_model: str,
    narrative_model: str,
    interestingness_score: float | None,
) -> dict[str, Any]:
    """Assemble all run data into a single dict for the viewer bundle."""
    return {
        "world_state": json.loads(world.model_dump_json()),
        "history": [json.loads(s.model_dump_json()) for s in history],
        "events_timeline": [
            json.loads(e.model_dump_json()) for e in world.events_timeline
        ],
        "named_events": [
            json.loads(ne.model_dump_json()) for ne in world.named_events
        ],
        "chronicle_entries": {
            str(entry.turn): entry.text for entry in chronicle_entries
        },
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
        },
    }


def write_bundle(bundle: dict[str, Any], path: Path) -> None:
    """Write assembled bundle to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2))
