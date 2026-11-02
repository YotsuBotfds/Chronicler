"""Closed pause command for one opt-in regional transport interruption."""
from chronicler.lab_transport import (
    TransportDisruptionRequest, apply_transport_disruptions, preview_transport_disruptions,
)

CONTROL = "regional_transport_disruption"
TARGET = "@transport"
STAT = "lab.transport_disruption"


def encode(region_id: int, duration: int) -> int:
    if type(region_id) is not int or region_id < 0 or type(duration) is not int or not 1 <= duration <= 6:
        raise ValueError("Invalid regional transport disruption")
    return region_id * 10 + duration


def decode(target: str, stat: str, value: int) -> TransportDisruptionRequest:
    if target != TARGET or stat != STAT or type(value) is not int or value < 0:
        raise ValueError("Invalid regional transport command")
    region_id, duration = divmod(value, 10)
    if not 1 <= duration <= 6:
        raise ValueError("Transport duration must be from 1 to 6")
    return TransportDisruptionRequest(region_id, duration)


def preview(world, target: str, stat: str, value: int):
    return preview_transport_disruptions(world, (decode(target, stat, value),))[0]


def apply(world, target: str, stat: str, value: int):
    receipt = apply_transport_disruptions(world, (decode(target, stat, value),))[0]
    if receipt.event is not None:
        event = receipt.event
        event.source = "lab"
        # Reconstruct the namespace from persistent timeline, including after resume.
        used = {e.event_id for e in world.events_timeline if e.event_id}
        prefix = f"{world.turn}:{event.event_type}:"
        index = 0
        while f"{prefix}{index}" in used:
            index += 1
        event.event_id = f"{prefix}{index}"
        world.events_timeline.append(event)
    return receipt
