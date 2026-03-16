"""DemandSignalManager — 3-turn linear decay for action-derived demand shifts.

Manages active demand signals from guard-action stat mutations. Each signal
decays linearly over 3 turns. Python-side decay produces already-decayed
effective values passed to Rust via civ_signals RecordBatch columns.
"""
from __future__ import annotations
from chronicler.models import DemandSignal


class DemandSignalManager:
    __slots__ = ("active",)

    def __init__(self) -> None:
        self.active: list[DemandSignal] = []

    def add(self, signal: DemandSignal) -> None:
        self.active.append(signal)

    def tick(self) -> dict[int, list[float]]:
        """Decay, aggregate per-civ, return {civ_id: [5 demand shifts]}."""
        per_civ: dict[int, list[float]] = {}
        surviving = []
        for s in self.active:
            effective = s.magnitude * (s.turns_remaining / 3)
            shifts = per_civ.setdefault(s.civ_id, [0.0] * 5)
            shifts[s.occupation] += effective
            s.turns_remaining -= 1
            if s.turns_remaining > 0:
                surviving.append(s)
        self.active = surviving
        return per_civ

    def reset(self) -> None:
        self.active.clear()
