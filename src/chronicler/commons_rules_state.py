"""Persisted state of the L8 commons rules (``--commons-rules``, default off).

Owned by its package lane (:mod:`chronicler.commons_rules`); pure data. One
rule per protected timber slot (region index, slot), owned by the civilization
(index in ``world.civilizations``) that adopted it, plus a bounded decision
log, repeal cooldowns, the last completed turn's receipts and cumulative
funnel counters. See docs/integration/commons-rules.md.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from chronicler.switch_state import SwitchStateMixin

#: Bounded logs.
MAX_DECISIONS = 64
#: Funnel counters, in report order (all start at zero).
COUNTER_KEYS: tuple[str, ...] = (
    "observed_turns", "eligible_slot_turns", "adoption_candidates", "adoption_unaffordable",
    "adopted", "rule_slot_turns", "quota_turns", "rest_turns", "required", "institution_cover",
    "billed", "paid", "coverage_sum", "full_coverage_turns", "partial_coverage_turns",
    "zero_coverage_turns", "tightened_turns", "binding_turns", "would_bind_turns", "excess",
    "extraction_under_rule", "grievance_added", "grievance_turns",
    "repealed_recovered", "repealed_unfunded", "repealed_idle", "repealed_unrest", "lapsed_owner_changed",
    "lapsed_slot_removed",
)


def _amount():
    return Field(ge=0.0, allow_inf_nan=False)


class StockObservation(BaseModel):
    """What the owner knows of a stand: the timber stock's account settled in
    ``turn`` (local and dated; never the current or a future stock)."""
    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=0)
    stock: float = _amount()
    capacity: float = _amount()
    extraction: float = _amount()
    water_gate_open: bool = False


class CommonsRule(BaseModel):
    """A harvest rule in force on one timber slot."""
    model_config = ConfigDict(extra="forbid")

    region_id: int = Field(ge=0)
    slot: int = Field(ge=0, le=2)
    owner: int = Field(ge=0)                  # civ index of the adopting controller
    adopted_turn: int = Field(ge=0)
    status: Literal["quota", "rest"] = "quota"
    unfunded_turns: int = Field(default=0, ge=0)   # consecutive turns with zero coverage
    idle_turns: int = Field(default=0, ge=0)       # consecutive turns no harvest was possible
    binding_turns: int = Field(default=0, ge=0)
    paid: int = Field(default=0, ge=0)
    grievance: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)  # city grievance it added, in total
    observation: StockObservation | None = None


class CommonsCooldown(BaseModel):
    """No new rule on this slot before ``until`` (after a repeal)."""
    model_config = ConfigDict(extra="forbid")

    region_id: int = Field(ge=0)
    slot: int = Field(ge=0, le=2)
    until: int = Field(ge=0)


class CommonsDecision(BaseModel):
    """An adoption, repeal or lapse, dated to the Phase 2 that committed it."""
    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=0)
    region_id: int = Field(ge=0)
    slot: int = Field(ge=0, le=2)
    civ: int = Field(ge=-1)
    kind: Literal["adopted", "repealed", "lapsed"]
    reason: str


class CommonsReceipt(BaseModel):
    """One protected slot's completed-turn account.

    ``limit = coverage x quota + (1 - coverage) x stock_cap`` (float32 floor):
    the covered share of the stand is held to the quota, the uncovered share
    is open access up to the standing stock. ``applied``: the limit was below
    the stock cap and (enforced mode) lowered the native harvest cap.
    ``binding`` (enforced): the harvest reached an applied limit (a zero limit
    binds where a harvest was possible); None in cost_only. ``excess``
    (cost_only): harvest above the limit the rule would have applied.
    """
    model_config = ConfigDict(extra="forbid")

    region_id: int = Field(ge=0)
    slot: int = Field(ge=0, le=2)
    owner: int = Field(ge=0)
    new: bool = False
    status: Literal["quota", "rest"]
    observation: StockObservation
    quota: float = _amount()
    stock_cap: float = _amount()
    required: int = Field(ge=0)
    institution_share: float = Field(ge=0.0, le=1.0)
    bill: int = Field(ge=0)
    paid: int = Field(ge=0)
    coverage: float = Field(ge=0.0, le=1.0)
    limit: float = _amount()
    applied: bool = False
    possible: bool | None = None
    extraction: float = _amount()
    binding: bool | None = None
    excess: float = _amount()
    city: int | None = None                    # settlement id of the grievance carrier
    grievance_added: float = _amount()
    neighbour_slots: int = Field(default=0, ge=0)
    neighbour_open_extraction: float = _amount()
    raw_imports: float | None = None
    craft_output: float | None = None
    farmer_income_modifier: float | None = None
    food_sufficiency: float | None = None


class CommonsRulesState(SwitchStateMixin, BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["enforced", "cost_only"] = "enforced"
    # Sorted by (region_id, slot); at most one rule per slot.
    rules: list[CommonsRule] = Field(default_factory=list)
    cooldowns: list[CommonsCooldown] = Field(default_factory=list)
    decisions: list[CommonsDecision] = Field(default_factory=list)
    # The turn whose Phase 2 the frame records (None before the first).
    frame_turn: int | None = None
    frame: list[CommonsReceipt] = Field(default_factory=list)
    counters: dict[str, int | float] = Field(default_factory=lambda: {key: 0 for key in COUNTER_KEYS})
    # Transient, within one Phase 2 only: the plan prepare made (decisions,
    # bills, limits); finish commits it and rollback drops it. Never
    # serialized; None between turns.
    _plan: object | None = PrivateAttr(default=None)
    _FILL_PRIVATE: ClassVar[tuple[str, ...]] = ("_plan",)
    _TRANSIENT: ClassVar[tuple[str, ...]] = ("_plan",)
