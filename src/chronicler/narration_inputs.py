"""Curation and narration inputs from a saved bundle, the same for every caller.

``--narrate BUNDLE`` (``main._run_narrate``) and the live server's range
narration (``live.LiveServer._narrate_range_sync``) read a bundle-shaped dict
the same way: events, named events, the restored history, the world, the
great persons (living characters with an agent id and the dead or retired
with a recorded end), the curator's named characters and arc map, the agent
name map, and the in-world accounts and names indexes. The narrator then
reads all of it as of each moment (``historical_context``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BundleNarrationInputs:
    events: list = field(default_factory=list)
    named_events: list = field(default_factory=list)
    history: list = field(default_factory=list)
    world: Any = None
    great_persons: list = field(default_factory=list)
    gp_by_name: dict = field(default_factory=dict)
    named_characters: set = field(default_factory=set)
    agent_name_map: dict = field(default_factory=dict)
    account_index: Any = None
    name_index: Any = None
    seed: int = 0

    def curate_kwargs(self) -> dict:
        """Keyword arguments ``curator.curate`` takes from these inputs."""
        return {
            "named_characters": self.named_characters or None,
            "gp_by_name": self.gp_by_name or None,
            "contested": self.account_index.contested_bonus() if self.account_index else None,
        }

    def narrate_kwargs(self) -> dict:
        """Keyword arguments ``NarrativeEngine.narrate_batch`` takes from these inputs.

        A saved bundle has no bridge values; the world's final fields are
        observations of its last turn (``observed_through`` "auto"). Fact ids
        (``narration_provenance``) index the bundle's own ``events_timeline``
        and ``named_events``, the lists curation read."""
        return {
            "great_persons": self.great_persons or None,
            "world": self.world,
            "timeline": self.events,
            "named_events": self.named_events,
            "historiography": self.account_index,
            "languages": self.name_index,
            "agent_name_map": self.agent_name_map or None,
            "social_edges": None,
            "dissolved_edges_by_turn": None,
            "displacement_by_region": None,
            "dynasty_registry": None,
            "economy_result": None,
            "gini_by_civ": None,
        }


def from_bundle(bundle: dict, *, default_seed: int = 0, historiography: bool = True,
                languages: bool = True, strict_world: bool = True) -> BundleNarrationInputs:
    """Read ``bundle`` (any version; decoded and restored here).

    ``strict_world`` False logs and skips a ``world_state`` that does not
    validate (a live session's minimal world) instead of raising.
    """
    from chronicler.historiography import AccountIndex
    from chronicler.languages import NameIndex
    from chronicler.models import Event, GreatPerson, NamedEvent, TurnSnapshot, WorldState
    from chronicler.snapshot_pruning import restore_bundle

    bundle = restore_bundle(bundle)
    out = BundleNarrationInputs()
    out.events = [Event.model_validate(e) for e in bundle.get("events_timeline", bundle.get("events", []))]
    out.named_events = [NamedEvent.model_validate(ne) for ne in bundle.get("named_events", [])]
    out.history = [TurnSnapshot.model_validate(s) for s in bundle.get("history", [])]
    world_state = bundle.get("world_state")
    if world_state is not None:
        try:
            out.world = WorldState.model_validate(world_state)
        except Exception as exc:  # pydantic.ValidationError
            if strict_world:
                raise
            logger.warning("Narrating without the world: its state does not validate (%s)", exc)
    seed = (bundle.get("metadata") or {}).get("seed")
    out.seed = seed if isinstance(seed, int) else default_seed

    world_dict = world_state or {}
    for civ_data in world_dict.get("civilizations", []):
        for gp_data in civ_data.get("great_persons", []):
            gp = GreatPerson(**gp_data)
            if gp.active and gp.agent_id is not None:
                out.named_characters.add(gp.name)
                out.gp_by_name[gp.name] = gp
    for gp_data in world_dict.get("retired_persons", []):
        gp = GreatPerson(**gp_data)
        if gp.death_turn is not None:
            out.gp_by_name[gp.name] = gp
    out.great_persons = list(out.gp_by_name.values())
    out.agent_name_map = {gp.agent_id: gp.name for gp in out.great_persons if gp.agent_id is not None}

    if languages:
        out.name_index = NameIndex.from_bundle(bundle)
    if historiography:
        out.account_index = AccountIndex.from_bundle(bundle)
        if out.account_index is not None and out.name_index:
            out.account_index = AccountIndex(bundle["historiography"], names=out.name_index)
    return out
