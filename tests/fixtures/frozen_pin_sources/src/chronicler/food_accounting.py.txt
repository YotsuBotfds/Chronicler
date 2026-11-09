"""Detached Phase-2 food observations, never inputs to simulation decisions.

The native kernel consumes regional model goods before Python public relief.
The latter is modeled as directly eaten; it is not another native drawdown or
proof of household access. Public procurement is a later Phase-10 decision.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real

FOOD_LEDGER_FIELDS = (
    "opening", "produced", "transport_net", "craft_input", "clamp_correction",
    "pre_consumption", "consumed", "storage_loss", "cap_overflow", "closing",
)


def _number(value):
    return float(value) if isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value) else None


def public_opening(world) -> tuple[float, ...] | None:
    """Read existing custody without initializing, advancing or draining it."""
    from chronicler.grain_reserves import grain_reserves_active
    if not grain_reserves_active(world):
        return None
    state = world.grain_reserves
    if len(state.granaries) != len(world.regions):
        return None
    values = tuple(_number(g.grain) for g in state.granaries)
    return values if all(v is not None and v >= 0 for v in values) else None


@dataclass(frozen=True, slots=True)
class RegionFood:
    region_id: int
    model_population: int
    native_count: int | None
    native: tuple[float, ...] | None
    sufficiency_after_relief: float | None
    # owner, opening, released, spoiled, abandoned, captured, after_open
    public: tuple[int, float | None, float, float, float, float, float] | None

    def as_dict(self) -> dict:
        native = None
        if self.native is not None:
            native = dict(zip((*FOOD_LEDGER_FIELDS, "demand", "sufficiency"), self.native))
            terms = [native["opening"], native["produced"], native["transport_net"],
                     -native["craft_input"], native["clamp_correction"], -native["consumed"],
                     -native["storage_loss"], -native["cap_overflow"]]
            native["balance_residual"] = native["closing"] - math.fsum(terms)
            # f32 component operations were not reordered to manufacture equality.
            native["balance_tolerance"] = 1e-5 * max(1.0, math.fsum(abs(v) for v in terms))
        public = None
        if self.public is not None:
            public = dict(zip(("owner_id", "opening", "released", "spoiled", "abandoned", "captured", "after_open"), self.public))
            public["balance_residual"] = (None if public["opening"] is None else
                public["after_open"] - math.fsum((public["opening"], -public["released"],
                                                  -public["spoiled"], -public["abandoned"])))
        return {"region_id": self.region_id, "model_population": self.model_population,
                "native_count": self.native_count, "native": native,
                "sufficiency_after_relief": self.sufficiency_after_relief, "public": public}


@dataclass(frozen=True, slots=True)
class FoodAccounting:
    source_turn: int
    mode: str
    transport: str
    regions: tuple[RegionFood, ...]

    def as_dict(self, completed_turn: int, procurement=()) -> dict:
        if completed_turn != self.source_turn + 1:
            raise ValueError("Food accounting completed turn does not match its source")
        return {"schema_version": 1, "source_turn": self.source_turn,
                "completed_turn": completed_turn, "mode": self.mode, "timing": "phase2",
                "units": "model_food_goods", "transport": self.transport,
                "regions": [r.as_dict() for r in self.regions],
                "procurement": [{"civilization_id": ci, "budget_initial": initial,
                                 "budget_remaining": remaining, "spent": initial - remaining}
                                for ci, initial, remaining in procurement]}


def capture_food_accounting(world, economy_result, weights, opening) -> FoodAccounting:
    """Copy existing native output and public Phase-2 flows after public relief.

    No extra native calls, state initialization, inventory writes or RNG reads.
    Missing old native fields stay unknown. Phase-10 purchases are not included
    in the native stock-flow balance or retrospectively counted as meals.
    """
    from chronicler.grain_reserves import grain_reserves_active
    from chronicler.grain_reserves_state import RELEASED, SPOILED, ABANDONED, CAPTURED
    size = len(world.regions)
    active = grain_reserves_active(world)
    state = world.grain_reserves if active else None
    flows = state.flows if state is not None and state.flows_turn == world.turn else ()
    totals = {}
    for flow in flows:
        if flow.kind in (RELEASED, SPOILED, ABANDONED, CAPTURED):
            key = (flow.region, flow.kind)
            totals[key] = totals.get(key, 0.0) + flow.amount
    ledger = getattr(economy_result, "food_ledger", {}) if economy_result is not None else {}
    sufficiency = getattr(economy_result, "food_sufficiency", {}) if economy_result is not None else {}
    rows = []
    for rid, region in enumerate(world.regions):
        public = None
        if state is not None and len(state.granaries) == size:
            g = state.granaries[rid]
            public = (g.owner, opening[rid] if opening is not None else None,
                      *(totals.get((rid, kind), 0.0) for kind in (RELEASED, SPOILED, ABANDONED, CAPTURED)),
                      g.grain)
        count = weights.counts[rid] if weights is not None and weights.source_turn == world.turn and len(weights.counts) == size else None
        rows.append(RegionFood(rid, region.population, count, ledger.get(rid),
                               _number(sufficiency.get(region.name)), public))
    mode = world.agent_mode or "off"
    transport = "none" if economy_result is None else "physical_delivery" if mode == "hybrid" else "abstract_allocation"
    return FoodAccounting(world.turn, mode, transport, tuple(rows))


def snapshot_fields(world, observation) -> dict:
    captured = getattr(observation, "food_accounting", None)
    if captured is None:
        return {}
    if captured.source_turn != observation.source_turn:
        raise ValueError("Food accounting belongs to another source turn")
    return {"food_accounting": captured.as_dict(observation.completed_turn,
                                               getattr(observation, "food_procurement", ()))}
