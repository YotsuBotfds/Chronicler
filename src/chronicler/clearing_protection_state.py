"""Persisted state of RS5 clearing protection (``--clearing-protection``, default off).

Owned by its package lane (:mod:`chronicler.clearing_protection`); pure data.
One protection per protected region (its index in ``world.regions``), paid by
the civilization (index in ``world.civilizations``) that adopted it, plus a
bounded decision log, the last completed turn's receipts and cumulative funnel
counters. See docs/integration/clearing-protection.md.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

#: Funnel counters, in report order (all start at zero).
COUNTER_KEYS: tuple[str, ...] = (
    "planned_turns", "settled_turns", "abandoned_plans",
    "eligible_region_turns", "adoption_candidates", "adoption_over_limit", "adoption_unaffordable",
    "adopted", "protected_region_turns", "pressure_planned_turns", "clearing_active_turns",
    "required", "paid_planned", "charged", "full_funded_turns", "partial_funded_turns",
    "zero_funded_turns", "cover_not_cleared", "cover_would_keep", "timber_capacity_kept",
    "ended_controller_changed", "ended_uncontrolled", "ended_cover_lost", "ended_idle",
    "ended_unfunded", "unprotected_clearing_turns", "cover_cleared_unprotected",
)
#: Why a protection ended (counted as ``ended_<reason>``).
END_REASONS: tuple[str, ...] = ("controller_changed", "uncontrolled", "cover_lost", "idle", "unfunded")
#: Why a controlled region under clearing pressure (or clearing) was not protected.
UNPROTECTED_REASONS: tuple[str, ...] = ("over_limit", "unaffordable", "not_forested", "not_planned")


def _amount():
    return Field(ge=0.0, allow_inf_nan=False)


class Protection(BaseModel):
    """A protection in force on one region."""
    model_config = ConfigDict(extra="forbid")

    region_id: int = Field(ge=0)
    payer: int = Field(ge=0)                       # civ index of the adopting controller
    adopted_turn: int = Field(ge=0)
    idle_turns: int = Field(default=0, ge=0)       # consecutive settled turns without clearing
    unfunded_turns: int = Field(default=0, ge=0)   # consecutive clearing turns with nothing paid
    active_turns: int = Field(default=0, ge=0)     # settled turns in which clearing fired
    charged: int = Field(default=0, ge=0)          # coins charged in total
    cover_not_cleared: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)  # cover kept, in total


class ProtectionDecision(BaseModel):
    """An adoption or an ending, dated to the planning that committed it."""
    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=0)
    region_id: int = Field(ge=0)
    civ: int = Field(ge=-1)
    kind: Literal["adopted", "ended"]
    reason: str


class ProtectionReceipt(BaseModel):
    """One protected region-turn's account.

    ``pressure_planned``: the planning saw the population above
    ``forest_pop_ratio`` of carrying capacity, so a warden bill ``required``
    was planned. ``p_planned = PROTECTION x paid_planned / WARDEN_COST``;
    ``p_applied`` is what the ecology tick received (0 in ``cost_only``).
    ``clearing_active`` and ``cover_not_cleared`` are the authoritative
    ecology receipts (native or Python fallback, ``source``);
    ``cover_would_keep`` is what ``p_planned`` keeps from an active clearing
    (equal to ``cover_not_cleared`` when enforced). ``charged`` is
    ``paid_planned`` when the clearing was active, otherwise 0.
    ``timber_capacity_kept``: the L3 effective capacity the kept cover holds
    on the region's timber slots (None without ``--timber-stock``).
    """
    model_config = ConfigDict(extra="forbid")

    region_id: int = Field(ge=0)
    payer: int = Field(ge=0)
    new: bool = False
    cover_before: float = _amount()
    cover_after: float = _amount()
    pressure_planned: bool
    required: int = Field(ge=0)
    envelope: int | None = None                    # the L9 cap, None without --local-budgets
    paid_planned: int = Field(ge=0)
    p_planned: float = Field(ge=0.0, le=1.0)
    p_applied: float = Field(ge=0.0, le=1.0)
    clearing_active: bool
    cover_not_cleared: float = _amount()
    cover_would_keep: float = _amount()
    charged: int = Field(ge=0)
    timber_capacity_kept: float | None = None
    source: Literal["native", "python"]


class UnprotectedRegion(BaseModel):
    """A controlled region under clearing pressure at planning, or whose
    clearing fired, without a protection this turn: the unmet need and the
    cover lost elsewhere.

    ``reason``: ``over_limit`` (its controller already held ``MAX_REGIONS``),
    ``unaffordable`` (the first bill could not be paid in full, or its L9
    envelope could not), ``not_forested`` (cover below ``MIN_COVER``) or
    ``not_planned`` (no pressure at planning, yet the tick's clearing fired).
    ``cleared`` is the nominal ``forest_clearing`` the tick removed (0 when
    the clearing did not fire)."""
    model_config = ConfigDict(extra="forbid")

    region_id: int = Field(ge=0)
    controller: int = Field(ge=0)
    reason: Literal["over_limit", "unaffordable", "not_forested", "not_planned"]
    pressure_planned: bool
    clearing_active: bool
    cover_before: float = _amount()
    cover_after: float = _amount()
    cleared: float = _amount()


class ClearingProtectionState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["enforced", "cost_only"] = "enforced"
    # Sorted by region_id; at most one protection per region.
    protections: list[Protection] = Field(default_factory=list)
    # The last settled turn's decisions, all of them (no cap: bounded by the
    # regions); earlier turns are not kept.
    decisions: list[ProtectionDecision] = Field(default_factory=list)
    # The turn whose Phase 9 the frame records (None before the first).
    frame_turn: int | None = None
    frame: list[ProtectionReceipt] = Field(default_factory=list)
    # The same turn's unprotected regions under pressure or clearing.
    unprotected: list[UnprotectedRegion] = Field(default_factory=list)
    counters: dict[str, int | float] = Field(default_factory=lambda: {key: 0 for key in COUNTER_KEYS})
    # Transient, within one Phase 9 only: the plan made before the ecology
    # tick and the tick's receipts; settlement after the tick commits it. A
    # plan left by a failed tick is dropped (nothing charged). Never
    # serialized; None between turns.
    _plan: object | None = PrivateAttr(default=None)
    # Whether the native ecology (f32) or the Python fallback (f64) decides
    # this run's clearing, as Phase 9 reports it to ``before_ecology``; kept
    # in exact checkpoints (the engine is fixed for a run), unknown (None)
    # before the first Phase 9 of a run or after a state-file load.
    _native_ecology: bool | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and private.get("_plan") is not None:
            state = {**state, "__pydantic_private__": {**private, "_plan": None}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        self.__dict__.setdefault("unprotected", [])
        private = getattr(self, "__pydantic_private__", None)
        if private is None:
            object.__setattr__(self, "__pydantic_private__", {"_plan": None, "_native_ecology": None})
        else:
            private.setdefault("_plan", None)
            private.setdefault("_native_ecology", None)
