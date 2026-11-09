"""Explicit, opt-in regional transport interruptions at a paused turn boundary.

A counter covers incident trade routes, not a single edge or guaranteed cargo.
The next environment phase decrements it before the economy builds its graph.
Callers must record returned events; this module does not write turn history.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from chronicler.models import Event, WorldState


@dataclass(frozen=True)
class TransportDisruptionRequest:
    region_id: int
    duration: int  # future economy phases, 1..6


@dataclass(frozen=True)
class TransportDisruptionReceipt:
    source_turn: int
    region_id: int
    requested_duration: int
    prior_counter: int
    effective_counter: int
    effective_through_turn: int
    neighbor_ids: tuple[int, ...]
    changed: bool
    event: Event | None = None


def _require_physical_hybrid(world: WorldState) -> None:
    from chronicler.agent_bridge import AgentBridge
    try:
        from chronicler_agents import AgentSimulator
    except ImportError as exc:
        raise ValueError("transport disruption requires the native agent simulator") from exc

    bridge = world._agent_bridge
    if (world.agent_mode != "hybrid" or not isinstance(bridge, AgentBridge)
            or bridge._mode != "hybrid" or not isinstance(bridge._sim, AgentSimulator)):
        raise ValueError("transport disruption requires an attached physical hybrid agent bridge")


def preview_transport_disruptions(
    world: WorldState, requests: Iterable[TransportDisruptionRequest],
) -> tuple[TransportDisruptionReceipt, ...]:
    """Validate the entire batch and describe its effect without mutation or RNG."""
    _require_physical_hybrid(world)
    entries = tuple(requests)
    seen: set[int] = set()
    names = {region.name: i for i, region in enumerate(world.regions)}
    if len(names) != len(world.regions):
        raise ValueError("region names must be unique")
    result = []
    for request in entries:
        if not isinstance(request, TransportDisruptionRequest):
            raise ValueError("expected TransportDisruptionRequest")
        rid, duration = request.region_id, request.duration
        if type(rid) is not int or not 0 <= rid < len(world.regions):
            raise ValueError("region_id must be a valid region index")
        if type(duration) is not int or not 1 <= duration <= 6:
            raise ValueError("duration must be an integer from 1 to 6")
        if rid in seen:
            raise ValueError("duplicate region in disruption batch")
        seen.add(rid)
        region = world.regions[rid]
        prior = region.route_suspensions.get("trade_route", 0)
        if type(prior) is not int or prior < 0:
            raise ValueError("existing trade route counter must be a nonnegative integer")
        if any(name not in names for name in region.adjacencies):
            raise ValueError("unknown adjacent region")
        counter = max(prior, duration + 1)
        result.append(TransportDisruptionReceipt(
            source_turn=world.turn, region_id=rid, requested_duration=duration,
            prior_counter=prior, effective_counter=counter,
            effective_through_turn=world.turn + counter - 2,
            neighbor_ids=tuple(sorted({names[name] for name in region.adjacencies})),
            changed=counter != prior,
        ))
    return tuple(result)


def apply_transport_disruptions(
    world: WorldState, requests: Iterable[TransportDisruptionRequest],
) -> tuple[TransportDisruptionReceipt, ...]:
    """Apply a validated batch; return a lab event only for each actual change."""
    from dataclasses import replace

    planned = preview_transport_disruptions(world, requests)
    result = []
    for receipt in planned:
        if not receipt.changed:
            result.append(receipt)
            continue
        region = world.regions[receipt.region_id]
        region.route_suspensions["trade_route"] = receipt.effective_counter
        event = Event(
            turn=receipt.source_turn, event_type="lab_transport_disruption",
            actors=[region.controller] if region.controller else [],
            region=region.name, shock_region=region.name, shock_category="transport",
            duration=receipt.effective_counter - 1,
            description=(f"[Lab] Transport disruption in {region.name} through "
                         f"turn {receipt.effective_through_turn}"),
        )
        result.append(replace(receipt, event=event))
    return tuple(result)
