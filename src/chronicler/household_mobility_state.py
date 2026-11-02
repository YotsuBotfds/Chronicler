"""Detached observations of the optional native liquid eligibility proxy.

The gate does not spend wealth, create debt, track household food or prove a
move occurred. Native people counts are not model population estimates.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
import struct

MAX_SAMPLES = 128
_REASONS = ("sufficient", "insufficient", "no_local_distress", "unknown_destination", "on_trip")


def liquid_requirement(world) -> float:
    """Validate and return the exact Float32 value sent to the native tick."""
    value = getattr(world, "household_mobility_liquid_requirement", None)
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("household mobility liquid requirement must be a finite nonnegative number")
    try:
        value = float(value)
    except (OverflowError, ValueError):
        raise ValueError("household mobility liquid requirement must be a finite nonnegative number") from None
    if not math.isfinite(value) or value < 0:
        raise ValueError("household mobility liquid requirement must be a finite nonnegative number")
    try:
        converted = struct.unpack("f", struct.pack("f", value))[0]
    except (OverflowError, struct.error):
        raise ValueError("household mobility liquid requirement must fit Float32") from None
    if not math.isfinite(converted) or (value > 0 and converted == 0):
        raise ValueError("household mobility liquid requirement must fit Float32")
    return converted


def _count(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid mobility frame {name}")
    return value


def _finite(value, name, *, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"invalid mobility frame {name}")
    value = float(value)
    if nonnegative and value < 0:
        raise ValueError(f"invalid mobility frame {name}")
    return value


@dataclass(frozen=True, slots=True)
class MobilitySample:
    group_id: int
    origin_region_id: int
    destination_region_id: int
    native_persons: int
    local_food_sufficiency: float | None
    native_adult_liquid_wealth: float
    required_liquid: float
    reason: str


@dataclass(frozen=True, slots=True)
class HouseholdMobilityObservation:
    source_turn: int
    mode: str
    requirement_per_native_person: float
    proposed_groups: int
    proposed_native_persons: int
    passed_groups: int
    passed_native_persons: int
    blocked_groups: int
    blocked_native_persons: int
    dropped_samples: int
    samples: tuple[MobilitySample, ...]

    def as_dict(self, completed_turn: int) -> dict:
        if completed_turn != self.source_turn + 1:
            raise ValueError("household mobility completed turn does not match its source")
        from dataclasses import asdict
        return {"schema_version": 1, "source_turn": self.source_turn,
                "completed_turn": completed_turn, "timing": "agent_decision_post_consolidation",
                "mode": self.mode, "wealth_units": "native_agent_wealth",
                "person_units": "native_agents", "passed_means": "gate_passed_not_observed_move",
                "requirement_per_native_person": self.requirement_per_native_person,
                "proposed_groups": self.proposed_groups, "proposed_native_persons": self.proposed_native_persons,
                "passed_groups": self.passed_groups, "passed_native_persons": self.passed_native_persons,
                "blocked_groups": self.blocked_groups, "blocked_native_persons": self.blocked_native_persons,
                "dropped_samples": self.dropped_samples, "samples": [asdict(row) for row in self.samples]}


def capture_mobility_frame(frame, *, source_turn: int, mode: str, requirement: float) -> HouseholdMobilityObservation:
    """Validate and detach the successful native tick's bounded gate frame."""
    if not isinstance(frame, (tuple, list)) or len(frame) != 2:
        raise ValueError("invalid mobility frame")
    header, rows = frame
    if not isinstance(header, (tuple, list)) or len(header) != 8:
        raise ValueError("invalid mobility frame header")
    source, groups, persons, passed_g, passed_p, blocked_g, blocked_p, dropped = (
        _count(value, "header") for value in header)
    if source != source_turn:
        raise ValueError("mobility frame belongs to another source turn")
    if groups != passed_g + blocked_g or persons != passed_p + blocked_p:
        raise ValueError("invalid mobility frame counts")
    if not isinstance(rows, (tuple, list)) or len(rows) > MAX_SAMPLES or len(rows) + dropped != groups:
        raise ValueError("invalid mobility frame sample count")
    samples = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != 8:
            raise ValueError("invalid mobility frame sample")
        group, origin, dest, size, food, wealth, required, reason = row
        group, origin, dest, size, reason = (_count(v, "sample") for v in (group, origin, dest, size, reason))
        if not size or reason >= len(_REASONS):
            raise ValueError("invalid mobility frame sample")
        if food is not None:
            food = _finite(food, "food")
        samples.append(MobilitySample(group, origin, dest, size, food,
            _finite(wealth, "wealth", nonnegative=True), _finite(required, "required", nonnegative=True), _REASONS[reason]))
    return HouseholdMobilityObservation(source, str(mode), requirement, groups, persons, passed_g,
        passed_p, blocked_g, blocked_p, dropped, tuple(samples))


def snapshot_fields(observation: HouseholdMobilityObservation | None, completed_turn: int) -> dict:
    """Create a detached historical field for a completed turn."""
    return {} if observation is None else {"household_mobility": observation.as_dict(completed_turn)}
