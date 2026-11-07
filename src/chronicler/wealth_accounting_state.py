"""Persisted state of the observation-only wealth ledger (A1, ``--wealth-accounting``, default off).

Owned by :mod:`chronicler.wealth_accounting`. Pure data with no simulation
imports, so :mod:`chronicler.livelihoods_state` can import it. A world that
never enabled the switch has no sub-state, so feature-off output is unchanged.

Identities: regions are indices in ``world.regions``; civilizations are
indices in ``world.civilizations``; people are native stable ids, but no id is
persisted here (the closing balance is kept as a digest and per-region sums).
Units: native wealth units (f32 balances summed in f64) for balances and the
native model residual; whole milli-units (1000 = one wealth unit = one
treasury unit) for typed flows, as the native wealth transfer counts them
(domestic credit, applied as an f32 change, is rounded to the nearest milli;
the sub-milli rest stays in the residual);
whole treasury units for treasury charges and created treasury income.

Everything is bounded: one completed-turn frame (one row per region, one per
typed channel, one per paid-work package, one treasury row per civilization),
the last closing (a digest and one sum per region), a rolling dated log
(``MAX_LOG``), lifetime totals with the fixed key set ``LIFETIME`` and scalar
counters with the fixed key set ``COUNTERS``. Tuple orders below are
declaration orders: append new values at the end, never reorder.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr

#: Typed channels: ``(channel, package switch, payer -> payee)``. A typed flow
#: moves native wealth between a named payer and payee through a keyed native
#: transfer (``wealth_transfer.rs``, ``credit.rs``); the household sector's
#: side is recorded here. ``package`` None: not a livelihoods switch.
CHANNELS: tuple[tuple[str, str | None, str], ...] = (
    ("workshop_wage", "workshop_payroll", "firm cash -> workshop crew (L6a)"),
    ("apprentice_stipend", "apprenticeship", "firm cash -> apprentice (RS1)"),
    ("repair_wage", "repair_projects", "treasury -> workshop repair crew (RS2)"),
    ("granary_crew_wage", "recovery_crews", "treasury granary coins -> granary crew (PL3)"),
    ("woodcut_wage", "timber_supply", "treasury -> woodcutting crew (PL1)"),
    ("food_procurement", "household_retail", "treasury -> owners of procured grain (L6b)"),
    ("food_purchase", "household_retail", "buyers -> sellers in the tick (L6b)"),
    ("remittance", "remittances", "sender -> recipient, fee to the courier sink (RS4)"),
    ("relocation_fare", "relocation_costs", "movers -> travel sink (L7)"),
    ("domestic_credit", None, "treasury <-> merchants, net applied (domestic credit)"),
    ("wares_purchase", "workshop_economics", "households -> workshop firm cash, wares bought by id (A3)"),
    # C2 (epidemic care): registered for the payment seam; the ledger does not
    # itemize it (``--epidemic-care`` and ``--wealth-accounting`` exclude each other).
    ("care_wage", "epidemic_care", "treasury -> epidemic carers by id (C2; not itemized: excluded with A1)"),
)
CHANNEL_NAMES: tuple[str, ...] = tuple(c[0] for c in CHANNELS)

#: Packages that withhold a paid share of ordinary income through the shared
#: native paid-work receipt (``livelihoods.paid_work_receipt``), in the order
#: a receipt row is matched. PL3's granary and workshop crews are separate
#: (the recorded limit RL7); RS2's workshop crews are PL3's workshop crews
#: while PL3 is active (PL3 widens RS2's pool; RS2 installs the share).
WITHHELD_PACKAGES: tuple[str, ...] = (
    "workshop_payroll", "apprenticeship", "recovery_crews_granary", "recovery_crews_workshop",
    "repair_projects", "timber_supply",
)

#: Withheld channels that are not paid work (no money moves). ``withheld_retail``:
#: L6b replaces a pilot farmer's farm income by sales (recorded in the frame).
#: ``withheld_learning`` (L5 attendance), ``withheld_teaching`` (academy
#: services) and ``withheld_health`` (rural health work): registered, NOT
#: itemized in slice 1 - their withheld shares stay in the native-model residual.
WITHHELD_OTHER: tuple[str, ...] = ("withheld_retail", "withheld_learning", "withheld_teaching", "withheld_health",
                                   # C2 carers' withheld income (appended; excluded with A1).
                                   "withheld_care")

#: Native methods that move agent wealth or withhold ordinary income.
WEALTH_WRITER_METHODS: tuple[str, ...] = (
    "transfer_wealth", "remit_wealth", "apply_merchant_transfers", "set_household_retail",
    "install_paid_work", "extend_paid_work", "install_retail_income",
    "reserve_learning_attendance", "prepare_teaching_work", "prepare_health_work",
)
#: Python helpers that route a payment to a writer for a caller-chosen purpose,
#: with the channels they may carry. Every call of a router is a payer path of
#: its own (registered below with its purpose); a writer call that takes a
#: purpose or batch from a parameter of a function that is not a router fails
#: the guard. A new helper (A3's ``money.py``) is declared here.
WEALTH_ROUTERS: dict[str, tuple[str, ...]] = {
    "pay_from_firm": ("apprentice_stipend",),
    # The shared payment seam (connected-world A3): ``money.pay`` routes every
    # agent-wealth line of a bill through ``money._native_transfer``; the
    # purposes it may carry are ``MONEY_PURPOSE_CHANNELS``.
    "_native_transfer": ("wares_purchase", "care_wage"),
}
#: The arguments that identify a payer path, ``(position, keyword)``.
WEALTH_PATH_ARGS: dict[str, tuple[tuple[int | None, str], ...]] = {
    "transfer_wealth": ((1, "purpose"), (2, "batch")),
    "remit_wealth": ((1, "batch"),),
    "pay_from_firm": ((None, "purpose"),),
    "_native_transfer": ((2, "purpose"),),
}
#: The one registry of payer paths: ``(module under chronicler, enclosing
#: function, writer or router, identifying arguments as written) -> (call
#: sites, channels the ledger reads it as)``. ``tests/test_wealth_accounting.py``
#: walks ``src/`` and fails on a path that is not here, a different number of
#: call sites, or a stale row, so a payer cannot vanish into the native-model
#: residual. A new payer path adds one row (and its channel). Append only.
WEALTH_WRITERS: dict[tuple[str, str, str, str], tuple[int, tuple[str, ...]]] = {
    ("workshop_payroll", "finish_phase2", "install_paid_work", ""): (1, ("workshop_payroll",)),
    ("workshop_payroll", "_pay", "transfer_wealth", "purpose=PURPOSE_WORKSHOP_WAGE,batch=firm.site"):
        (1, ("workshop_wage",)),
    ("workshop_payroll", "pay_from_firm", "transfer_wealth", "purpose=purpose,batch=site"):
        (1, ("apprentice_stipend",)),
    ("apprenticeship", "finish_phase2", "extend_paid_work", ""): (1, ("apprenticeship",)),
    ("apprenticeship", "phase10", "pay_from_firm", "purpose=PURPOSE_APPRENTICE_STIPEND"):
        (1, ("apprentice_stipend",)),
    ("repair_projects", "finish_phase2", "extend_paid_work", ""):
        (1, ("repair_projects", "recovery_crews_granary", "recovery_crews_workshop")),
    ("repair_projects", "finish_phase2", "transfer_wealth", "purpose=PURPOSE_REPAIR_WAGE,batch=0"):
        (1, ("repair_wage",)),
    ("recovery_crews", "pay_granary_crews", "transfer_wealth",
     "purpose=PURPOSE_REPAIR_WAGE,batch=GRANARY_WAGE_BATCH"): (1, ("granary_crew_wage",)),
    ("timber_supply", "finish_phase2", "extend_paid_work", ""): (1, ("timber_supply",)),
    ("timber_supply", "finish_phase2", "transfer_wealth", "purpose=PURPOSE_REPAIR_WAGE,batch=WAGE_BATCH"):
        (1, ("woodcut_wage",)),
    ("household_retail", "before_agent_tick", "set_household_retail", ""): (1, ("food_purchase",)),
    ("household_retail", "before_agent_tick", "install_retail_income", ""): (1, ("withheld_retail",)),
    ("household_retail", "_credit_procurement", "transfer_wealth",
     "purpose=PURPOSE_FOOD_PROCUREMENT,batch=PROCUREMENT_BATCH"): (1, ("food_procurement",)),
    ("remittances", "after_agent_tick", "remit_wealth", "batch=REMIT_BATCH"): (1, ("remittance",)),
    ("relocation_costs", "after_agent_tick", "transfer_wealth", "purpose=PURPOSE_RELOCATION_FARE,batch=FARE_BATCH"):
        (1, ("relocation_fare",)),
    ("domestic_credit", "Tick.finish", "apply_merchant_transfers", ""): (1, ("domestic_credit",)),
    ("learning_cohorts", "before_agent_tick", "reserve_learning_attendance", ""): (1, ("withheld_learning",)),
    ("simulation", "run_turn_result.tick_agents", "prepare_teaching_work", ""): (1, ("withheld_teaching",)),
    ("health_care", "prepare_health_care", "prepare_health_work", ""): (2, ("withheld_health",)),
    # A3 (the payment seam): the router's one native call, and its two callers in
    # ``money.pay`` (a payment's agent credits, a collection's agent debits).
    ("money", "_native_transfer", "transfer_wealth", "purpose=code,batch=batch"): (1, ("wares_purchase", "care_wage")),
    ("money", "pay", "_native_transfer", "purpose=bill.purpose"): (2, ("wares_purchase", "care_wage")),
    # C2 (epidemic care): carers' ordinary income withheld for their care time.
    ("epidemic_care", "finish_phase2", "extend_paid_work", ""): (1, ("withheld_care",)),
}
#: Purposes ``money.pay`` may move agent wealth for, with the ledger channel
#: each is read as (``money.flows_for_turn``); ``money`` refuses any other
#: agent-wealth purpose at run time, so a new payer through the seam must add
#: its row here (and its channel). Append only.
MONEY_PURPOSE_CHANNELS: dict[str, str] = {
    "wares_purchase": "wares_purchase",
    "care_wage": "care_wage",
}
#: Every bill built for the payment seam outside ``money`` itself:
#: ``(module under chronicler, enclosing function) -> purposes`` (a literal
#: ``purpose=`` at each ``Bill(...)``). ``tests/test_money.py`` walks ``src/``
#: and fails on an unregistered or stale caller, a non-literal purpose, or an
#: agent-wealth purpose without a ledger channel. Append only.
MONEY_BILLS: dict[tuple[str, str], tuple[str, ...]] = {
    ("workshop_economics", "charge_inputs"): ("firm_input_purchase",),
    ("workshop_economics", "sell_to_households"): ("wares_purchase",),
    ("workshop_economics", "open_firms"): ("firm_capital",),
    # C2: carers' wages, treasury to agents (prepaid carry rule).
    ("epidemic_care", "_quote_bills"): ("care_wage",),
}
#: Every reference to a writer or router name that is not a call: the name
#: strings packages use to check the extension has a method
#: (``callable(getattr(sim, name, None))``). ``(module, enclosing function,
#: name) -> occurrences``. Any other reference - an alias, a ``getattr`` that
#: could call a writer, a name in a string - fails the guard (fail closed).
WEALTH_WRITER_REFERENCES: dict[tuple[str, str, str], int] = {
    ("workshop_payroll", "_native", "transfer_wealth"): 1,
    ("workshop_payroll", "_native", "install_paid_work"): 1,
    ("apprenticeship", "<module>", "extend_paid_work"): 1,
    ("repair_projects", "<module>", "extend_paid_work"): 1,
    ("repair_projects", "<module>", "transfer_wealth"): 1,
    ("timber_supply", "<module>", "extend_paid_work"): 1,
    ("timber_supply", "<module>", "transfer_wealth"): 1,
    ("household_retail", "<module>", "set_household_retail"): 1,
    ("household_retail", "<module>", "install_retail_income"): 1,
    ("remittances", "<module>", "remit_wealth"): 1,
    ("relocation_costs", "<module>", "transfer_wealth"): 1,
    ("learning_cohorts", "<module>", "reserve_learning_attendance"): 1,
    ("simulation", "run_turn_result", "prepare_teaching_work"): 1,
    ("health_care", "prepare_health_care", "prepare_health_work"): 1,
    ("epidemic_care", "<module>", "extend_paid_work"): 1,
}
#: Native ``AgentSimulator.wealth_transfer_purposes()`` this ledger knows
#: (append only; a native test fails when the extension grows past it).
KNOWN_PURPOSES: tuple[str, ...] = (
    "workshop_wage", "relocation_fare", "apprentice_stipend", "repair_wage", "remittance", "food_purchase",
    "food_procurement", "wares_purchase",
)

#: Continuity of an opening with the previous closing.
CONTINUITY: tuple[str, ...] = ("exact", "broken", "unchecked")
#: Why a continuity check could not run.
UNCHECKED_REASONS: tuple[str, ...] = ("first_turn", "pool_reset", "gap", "no_closing", "no_opening")

#: Dated log kinds.
LOG_KINDS: tuple[str, ...] = (
    "switched_on", "switched_off", "pool_reset", "continuity_broken", "attribution", "unobserved",
)
MAX_LOG = 64
#: At most this many regions are named in a broken continuity record.
MAX_CONTINUITY_REGIONS = 16

#: Lifetime totals (declaration order; append only). ``*_milli`` are typed
#: flows in milli-units, ``native_model``/``delta``/``discontinuity`` wealth
#: units, ``withheld_*`` ordinary income withheld (wealth units),
#: ``treasury_*``/``tithe_*`` treasury units.
LIFETIME: tuple[str, ...] = (
    *(f"{name}_{side}_milli" for name in CHANNEL_NAMES[:10] for side in ("in", "out")),
    "delta", "native_model", "discontinuity",
    *(f"withheld_{name}" for name in WITHHELD_PACKAGES), "withheld_unattributed",
    # tithe_potential replaced tithe_offered in place once, before the first
    # landing (no saved state carried it); append only from here.
    "treasury_tax_created", "tithe_potential", "treasury_to_households_milli",
    "treasury_to_firm_cash_milli", "firm_cash_to_treasury_milli", "treasury_charged",
    "tithe_at_threshold_after_tick", "withheld_retail",
    # A3 (workshop economics), appended: its typed channel, then its treasury side.
    "wares_purchase_in_milli", "wares_purchase_out_milli", "treasury_to_firm_capital_milli",
    "firm_inputs_to_treasury_milli", "asset_subsidy_units",
)

#: Lifetime counters (declaration order; append only).
COUNTERS: tuple[str, ...] = (
    "turns_observed", "turns_unobserved", "continuity_exact", "continuity_broken", "continuity_unchecked",
    "pool_resets", "switched_on", "switched_off", "withheld_rows", "unattributed_rows",
    "attribution_conflicts", "typed_incomplete_turns", "closures_failed", "unattributed_pl3_dropped_rows",
)


def _is_none(value) -> bool:
    return value is None


class Closing(BaseModel):
    """The balance at the last observed closing (after every payer of a
    completed turn's Phase 10): a SHA-256 of ``(id, f32 wealth bits)`` and of
    ``(id, region)`` in ascending id order, the world total and agent count,
    and one sum and count per region index (``-1`` rows are not kept)."""

    turn: int
    digest: str
    region_digest: str
    total: float
    agents: int
    regions: list[float] = Field(default_factory=list)
    counts: list[int] = Field(default_factory=list)


class LedgerRecord(BaseModel):
    """A dated record: switches, pool resets, broken continuity, attribution."""

    turn: int
    kind: str                                   # LOG_KINDS
    detail: dict[str, Any] = Field(default_factory=dict)


class WealthAccountingState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    #: The last observed closing (None: none yet, or dropped by a pool reset
    #: or a switch-off: the next opening is then unchecked).
    closing: Closing | None = Field(default=None, exclude_if=_is_none)
    #: The turn a pool reset was seen (the next opening's reason).
    reset_turn: int | None = Field(default=None, exclude_if=_is_none)
    #: The completed-turn frame (JSON-ready; shape in
    #: ``docs/integration/wealth-accounting.md``). None: not observed.
    frame_turn: int | None = None
    frame: dict[str, Any] | None = None
    #: Lifetime totals (the fixed key set ``LIFETIME``).
    lifetime: dict[str, int | float] = Field(default_factory=dict)
    #: Rolling dated log (the last ``MAX_LOG`` records).
    log: list[LedgerRecord] = Field(default_factory=list)
    log_dropped: int = 0
    #: Scalar lifetime counters (the fixed key set ``COUNTERS``).
    counters: dict[str, int] = Field(default_factory=dict)
    # Transient, within one turn (Phase 2 opening -> Phase 10 closing): the
    # opening arrays and the counter baselines. Never serialized.
    _turn: object | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and private.get("_turn") is not None:
            state = {**state, "__pydantic_private__": {**private, "_turn": None}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name not in self.__dict__:
                self.__dict__[name] = field.get_default(call_default_factory=True)
        if getattr(self, "__pydantic_private__", None) is None:
            object.__setattr__(self, "__pydantic_private__", {"_turn": None})
        else:
            self.__pydantic_private__.setdefault("_turn", None)
