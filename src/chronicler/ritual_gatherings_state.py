"""Pure persisted data for default-off recurring harvest gatherings.

Region indices, agent IDs and permanent faith IDs retain their usual meanings.
Schedules belong to regions, never to their current ruler or a reusable faith slot.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

COUNTER_KEYS = ("scheduled", "held", "cancelled", "attendees", "food", "funds", "contact_units", "bond_ops")


class GatheringSchedule(BaseModel):
    region: int
    gathering_id: str
    created_turn: int
    next_turn: int
    last_turn: int | None = None
    last_status: Literal["held", "cancelled"] | None = None
    last_reason: str | None = None
    first_held_turn: int | None = None
    last_host: int = -1
    last_faith: int | None = None


class GatheringOutcome(BaseModel):
    gathering_id: str
    turn: int
    region: int
    region_name: str
    host: int = -1
    host_name: str | None = None
    faith: int | None = None
    faith_name: str | None = None
    purpose: Literal["harvest"] = "harvest"
    status: Literal["held", "cancelled"]
    reason: str | None = None
    attendee_ids: list[int] = Field(default_factory=list)
    food: float = 0.0
    funds: int = 0
    contact_units: float = 0.0
    # Attempts accepted by Python's eligibility checks, not an FFI success count.
    bond_ops: int = 0
    # Actual dated arrival receipts: [agent_id, source_region]. No birth origins.
    arrivals: list[tuple[int, int]] = Field(default_factory=list)
    grain_before: float | None = None
    grain_after: float | None = None
    funds_before: int | None = None
    funds_after: int | None = None


class RitualGatheringState(BaseModel):
    schedules: list[GatheringSchedule] = Field(default_factory=list)
    outcomes_turn: int | None = None
    outcomes: list[GatheringOutcome] = Field(default_factory=list)
    last_tick_turn: int = -1
    counters: dict[str, float] = Field(default_factory=lambda: {k: 0.0 for k in COUNTER_KEYS})
    # Persisted intervention controls: equal costs/attendance in every arm.
    contact_enabled: bool = True
    bonds_enabled: bool = True


def ritual_gatherings_on(world) -> bool:
    return isinstance(getattr(world, "ritual_gatherings", None), RitualGatheringState)
