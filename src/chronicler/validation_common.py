"""Constants and helpers shared by the validation loaders and oracles.

A leaf module: it imports no other validation module, so ``validation_io``
and the oracle modules split out of it can all import it. ``validation_io``
re-exports every name here (docs/integration/validation-split.md).
"""
from __future__ import annotations

from math import ceil


EVENT_NAME_TO_CODE = {
    "death": 0,
    "migration": 1,
    "rebellion": 2,
    "occupation_switch": 3,
    "loyalty_flip": 4,
    "birth": 5,
    "dissolution": 6,
}


def required_seed_count(total_seeds: int, fraction: float) -> int:
    """Return the minimum passing seed count for a fractional threshold."""
    if total_seeds <= 0:
        return 0
    return max(1, ceil(total_seeds * fraction))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
