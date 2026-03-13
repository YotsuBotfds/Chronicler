"""Shared utilities used across chronicler modules."""

from __future__ import annotations


def clamp(value: int, low: int, high: int) -> int:
    """Clamp an integer value to [low, high]."""
    return max(low, min(high, value))
