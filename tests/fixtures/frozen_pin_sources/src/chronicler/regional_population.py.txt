"""Read-only regional observations with explicit model/pool/food epochs.

Every array is indexed by the immutable position in ``world.regions``. Model
population and native alive agents are distinct quantities in shadow and
clamped-demographics modes. Food weights belong to the Phase 2 input pool and
its controllers, never to the completed-turn population or ownership.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from numbers import Integral

from chronicler.columnar import pylist

MODES = frozenset(("off", "hybrid", "shadow", "demographics-only"))


def _mode(world) -> str | None:
    mode = world.agent_mode or "off"
    return mode if mode in MODES else None


def _counts(values, size: int) -> tuple[int, ...] | None:
    if len(values) != size or any(isinstance(v, bool) or not isinstance(v, Integral) or v < 0
                                  for v in values):
        return None
    return tuple(int(v) for v in values)


@dataclass(frozen=True, slots=True)
class FoodWeights:
    """Detached counts and controller identities from the same Phase 2 input."""

    source_turn: int
    counts: tuple[int, ...]
    controller_ids: tuple[int | None, ...]

    def as_dict(self) -> dict:
        return {"source": "phase2_agent_pool", "source_turn": self.source_turn,
                "timing": "phase2_entry", "counts": list(self.counts),
                "controller_ids": list(self.controller_ids)}


def capture_food_weights(world, snapshot) -> FoodWeights | None:
    """Copy the existing pre-economy alive rows; never fetch or mutate a pool.

    A missing/malformed region column makes the entire observation unavailable.
    In particular, out-of-universe rows must not silently turn into zero people.
    """
    if snapshot is None or _mode(world) not in MODES - {"off"}:
        return None
    size = len(world.regions)
    try:
        regions = pylist(snapshot.column("region"))
    except (AttributeError, KeyError, TypeError, ValueError, IndexError):
        return None
    if any(isinstance(v, bool) or not isinstance(v, Integral) or not 0 <= v < size
           for v in regions):
        return None
    counts = Counter(int(v) for v in regions)
    names = Counter(c.name for c in world.civilizations)
    civ_ids = {c.name: i for i, c in enumerate(world.civilizations) if names[c.name] == 1}
    return FoodWeights(world.turn, tuple(counts[i] for i in range(size)),
                       tuple(civ_ids.get(r.controller) for r in world.regions))


def capture_population_sources(world) -> tuple[str, ...] | None:
    """Record mode lineage after the bridge writeback, before Phase 10 politics.

    Demographics-only writes only controlled regions. Capturing that fact here
    avoids relabelling a region after Phase 10 transfers its ownership. These
    labels identify model lineage, not the cause of each completed-turn delta.
    """
    mode = _mode(world)
    if mode is None:
        return None
    if mode == "demographics-only":
        return tuple("demographics_clamped_region_state" if r.controller is not None
                     else "uncontrolled_region_state" for r in world.regions)
    source = "hybrid_region_state" if mode == "hybrid" else "python_region_state"
    return (source,) * len(world.regions)


def _native_counts(bridge, size: int) -> tuple[int, ...] | None:
    if bridge is None:
        return None
    try:
        batch = bridge._sim.get_region_populations()
        ids = pylist(batch.column("region_id"))
        counts = _counts(pylist(batch.column("alive_count")), size)
    except (AttributeError, KeyError, TypeError, ValueError, IndexError):
        return None
    if (_counts(ids, size) != tuple(range(size)) or counts is None):
        return None
    return counts


def snapshot_fields(world, bridge, observation) -> dict:
    """Export completed model state and an independent pure native pool read.

    ``get_region_populations`` is the native ``&self`` dense alive-count reader;
    it neither ticks agents nor updates bridge caches. Missing pool observations
    stay null. No civilization total is allocated across regions.
    """
    mode = _mode(world)
    counts = _counts([r.population for r in world.regions], len(world.regions))
    if mode is None or counts is None:
        return {}
    sources = getattr(observation, "population_sources", None)
    # Legacy/standalone off/shadow/hybrid TurnObservation constructors remain
    # readable. Only demographics-only needs the captured writeback ownership.
    if sources is None and mode != "demographics-only":
        sources = capture_population_sources(world)
    if sources is None or len(sources) != len(counts):
        return {}
    native = _native_counts(bridge, len(counts)) if mode != "off" else None
    weights = getattr(observation, "food_weights", None)
    if (weights is not None and (weights.source_turn != observation.source_turn
            or len(weights.counts) != len(counts) or len(weights.controller_ids) != len(counts))):
        weights = None
    return {"regional_population": {
        "schema_version": 1, "mode": mode,
        "source_turn": observation.source_turn,
        "completed_turn": observation.completed_turn, "timing": "completed_turn",
        "counts": list(counts), "sources": list(sources),
        "agent_counts": list(native) if native is not None else None,
        "agent_source": "native_region_alive_count" if native is not None else None,
        "food_weights": weights.as_dict() if weights is not None else None,
    }}
