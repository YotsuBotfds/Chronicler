"""Shared utilities used across chronicler modules."""

from __future__ import annotations


def clamp(value: int, low: int, high: int) -> int:
    """Clamp an integer value to [low, high]."""
    return max(low, min(high, value))


STAT_FLOOR: dict[str, int] = {
    "population": 1,
    "military": 0,
    "economy": 0,
    "culture": 0,
    "stability": 0,
}
