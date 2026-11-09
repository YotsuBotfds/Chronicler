"""Persisted state of A3 workshop economics (``--workshop-economics``, default off).

Owned by :mod:`chronicler.workshop_economics`. Pure data with no simulation
imports, so :mod:`chronicler.livelihoods_state` can import it. A world that
never enabled the switch has no sub-state, so feature-off output is
unchanged.

Identities: a firm is the L6a firm of an L1 workshop site and is named by
the site id (monotone, persisted, never reused); regions are indices in
``world.regions``; civilizations are indices in ``world.civilizations``;
buyers are native stable ids (never persisted here: households pay at once).
Units: money in whole milli-units (1000 = one treasury unit = one native
wealth unit), wares and raw inputs in milli-loads, prices in milli-units per
load. The firm's cash, inventory, wages owed and books stay in the L6a firm
(``workshop_payroll_state.WorkshopFirm``); this state holds what A3 adds:
capital, the input-price observations, the idle run, the completed-turn
frame, the payment book and bounded counters and log.

Tuple orders below are declaration orders: append new values at the end,
never reorder.
"""
from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.money import MoneyBook
from chronicler.switch_state import SwitchStateMixin

#: Modes (``--workshop-economics-mode``), in declaration order (append only).
#: ``market``: inputs are bought from the commons owner, households buy;
#: ``free_inputs`` (cost control): inputs are planned and recorded but not
#: charged; ``academy_only`` (demand control): no household customers.
MODES: tuple[str, ...] = ("market", "free_inputs", "academy_only")
#: Rules versions (``--workshop-economics-rules`` choices are their strings;
#: the first is the default of a new state). 1: A3-1 (the tick's output
#: enters the commons before title); 2: A3-2 (a native column keeps each
#: firm's output out of the commons: it reaches users only by sale).
RULES_VERSIONS: tuple[int, ...] = (1, 2)
#: Why a firm-turn bought no inputs (append only).
NO_INPUT_REASONS: tuple[str, ...] = (
    "price_unknown", "budget_exhausted", "not_funded", "no_crew", "not_built", "worn", "no_firm",
    "price_discovery", "not_operating",
    # Rules version 2 (A3-2): no room left in the firm's inventory for output.
    "inventory_full",
)
#: Why a firm-turn sold to nobody (append only): ``no_inventory``,
#: ``no_controller``; academies: ``no_academy`` (no fully informed purchaser of
#: the region's ruler), ``academy_full`` (no remaining need or budget);
#: households: ``commons_covers`` (the free commons covers the demand),
#: ``households_cannot_pay``, ``depopulated`` (residents fell by at least a
#: quarter over ``DEPOPULATION_WINDOW`` turns), ``price_unknown``, and the
#: controls ``academy_only_mode`` and ``no_customer_mode``.
ABSENCE_REASONS: tuple[str, ...] = (
    "no_inventory", "no_controller", "no_academy", "academy_full", "commons_covers",
    "households_cannot_pay", "depopulated", "price_unknown", "academy_only_mode", "no_customer_mode",
)
#: Why an operating site without a firm did not open one (append only).
OPENING_REFUSALS: tuple[str, ...] = ("treasury_short", "price_unknown", "no_controller", "no_crew",
                                     "no_input_price", "closed_city")
#: Dated log kinds (append only).
LOG_KINDS: tuple[str, ...] = ("switched_on", "switched_off", "opened", "opening_refused", "closed")
MAX_LOG = 64
MAX_FRAME = 12
MAX_POPULATION_HISTORY = 11

#: Scalar lifetime counters (append only). Money in milli-units, wares in milli-loads.
COUNTERS: tuple[str, ...] = (
    "firms_opened", "opening_refused_treasury_short", "opening_refused_price_unknown",
    "opening_refused_no_controller", "opening_refused_no_crew", "capital_paid",
    "firm_turns", "operating_firm_turns", "input_capacity_zero_turns", "price_unknown_turns",
    "inputs_used", "inputs_charged", "inputs_not_charged", "input_treasury_units",
    "academy_sales", "household_sale_turns", "household_sales", "household_delivered",
    "buying_households", "priced_out_households", "household_gap", "household_offered",
    "free_use_upper_bound", "idle_firm_turns", "closed_idle", "closed_insolvent", "closed_other",
    "sites_without_firm_turns", "asset_subsidy_firm_units", "asset_subsidy_idle_units",
    "demand_absent_firm_turns", "unpaid_conversion",
    "unbought_need", "plan_price_realm_turns", "opening_refused_no_input_price", "opening_refused_closed_city",
    "idle_no_conversion_turns",
    # Rules version 2 (A3-2): output the firm took straight into its inventory
    # (never in the commons) and the operating firm-turns that produced it.
    "owned_output", "owned_output_turns",
    # Rules version 2: unsold wares a closing firm handed to the region's ruler
    # (owner of the commons) at liquidation, milli-loads.
    "liquidation_to_owner",
)


class PriceObservation(BaseModel):
    """The economy's post-trade prices of one region in one turn (as computed
    by the native economy; ``None`` when absent or not positive). ``*_milli``
    is the price rounded **up** to whole milli-units per load (a buyer never
    pays less than the economy's price). ``plan_raw_milli``/``plan_turn``: the
    last positive raw price computed for the region and its turn (what the
    next turn's input plan uses; a turn without raw demand prices raw at 0)."""

    region: int
    turn: int
    raw: float | None = None
    raw_milli: int | None = None
    craft: float | None = None
    craft_milli: int | None = None
    plan_raw_milli: int | None = None
    plan_turn: int | None = None


class FirmTerms(BaseModel):
    """What A3 adds to one L6a firm (named by its site id)."""

    firm: int
    region: int
    opened_turn: int
    settlement_id: int | None = None
    capital: int = 0                    # milli-units received once at opening
    capital_payer: int | None = None    # civ index
    status: Literal["open", "closed"] = "open"
    closed_turn: int | None = None
    closed_reason: str | None = None
    idle_run: int = 0
    turns: int = 0
    operating_turns: int = 0
    last_operating_turn: int | None = None
    totals: dict[str, int] = Field(default_factory=dict)


class EconomicsReceipt(BaseModel):
    """One firm's completed turn under A3 (money in milli-units, wares and
    inputs in milli-loads, prices in milli-units per load). ``inputs`` is None
    when the firm was not planned this turn (opened this Phase 10)."""

    turn: int
    firm: int
    region: int
    owner: int | None = None
    status: str = "open"
    operating: bool = False
    inputs: dict[str, Any] | None = None
    produced: int = 0
    titled: int = 0
    free_use_upper_bound: int = 0
    academy_sales: int = 0
    academy_sold: int = 0
    households: dict[str, Any] | None = None
    customer_absent: list[str] = Field(default_factory=list)
    capital_in: int = 0
    wages_due: int = 0
    wages_paid: int = 0
    owed_after: int = 0
    worn: int = 0
    returned: int = 0
    distributed: int = 0
    written_off: int = 0
    #: Cash and inventory after the payroll pass (before any RS1 apprentice
    #: stipend, which the L6a receipt records): exact closures
    #: ``cash_close = cash_open + capital_in + academy_sales + households.paid
    #: - inputs.charged - wages_paid - distributed - written_off`` and
    #: ``inventory_close = inventory_open + titled - academy_sold -
    #: households.bought - worn - returned``.
    cash_open: int = 0
    cash_close: int = 0
    inventory_open: int = 0
    inventory_close: int = 0
    unsold_inventory: int = 0
    owner_asset_spend: int = 0          # treasury units the owner paid for the asset this turn (subsidy)
    idle_run: int = 0
    insolvent_run: int = 0
    event: str | None = None


class EconomicsRecord(BaseModel):
    """A dated log record."""

    turn: int
    kind: str
    firm: int | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


def _is_one(value) -> bool:
    return value == 1


class WorkshopEconomicsState(SwitchStateMixin, BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["market", "free_inputs", "academy_only"] = "market"
    #: Rules version (RULES_VERSIONS); 1 when absent (an A3-1 state) and
    #: omitted while 1, so A3-1 dumps keep their bytes; a saved state keeps it.
    rules_version: Literal[1, 2] = Field(default=1, exclude_if=_is_one)
    firms: list[FirmTerms] = Field(default_factory=list)
    closed: list[FirmTerms] = Field(default_factory=list)
    prices: list[PriceObservation] = Field(default_factory=list)
    #: Settlement ids of every city whose A3 firm closed (sorted, never pruned):
    #: L1 never readmits them while A3 is active and no opening happens there.
    closed_settlements: list[int] = Field(default_factory=list)
    #: Residents of each firm region over the last turns: ``[turn, region, residents]``.
    population: list[tuple[int, int, int]] = Field(default_factory=list)
    frame_turn: int | None = None
    frame: list[EconomicsReceipt] = Field(default_factory=list)
    book: MoneyBook = Field(default_factory=MoneyBook)
    counters: dict[str, int] = Field(default_factory=dict)
    log: list[EconomicsRecord] = Field(default_factory=list)
    log_dropped: int = 0
    # Transient, within one turn (Phase 2 plan -> Phase 10 frame). Never serialized.
    _turn: object | None = PrivateAttr(default=None)

    _FILL_DEFAULTS: ClassVar[bool] = True
    _FILL_PRIVATE: ClassVar[tuple[str, ...]] = ("_turn",)
    _TRANSIENT: ClassVar[tuple[str, ...]] = ("_turn",)
    _BUMP: ClassVar[dict] = {"allowed": COUNTERS, "message": "undeclared workshop economics counter {key!r}", "coerce": int}

    @property
    def rules(self) -> str:
        """The rules version as the ``--workshop-economics-rules`` choice."""
        return str(self.rules_version)
