"""Persisted state of the L3 renewable timber stock (default off).

Owned by its package lane (:mod:`chronicler.timber_stock`); pure data. One
harvestable stock per region slot whose resource is timber, in the goods the
economy's ``slot_output`` counts, plus the last completed turn's ledger and
cumulative totals. See docs/integration/timber-stock.md.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


def _amount():
    return Field(ge=0.0, allow_inf_nan=False)


class TimberSlotStock(BaseModel):
    """The harvestable timber standing in one region slot (region index, slot)."""
    model_config = ConfigDict(extra="forbid")

    region_id: int = Field(ge=0)
    slot: int = Field(ge=0, le=2)
    stock: float = _amount()


class TimberLedgerRow(BaseModel):
    """One slot's completed-turn account.

    ``stock = opening - cleared - (extraction - overdraft) + regrowth - removed``.
    ``cleared``: stock above this turn's capacity (cover fell: clearing,
    cooling, wildfire, succession). ``overdraft``: extraction beyond the stock,
    possible only while the cap is not enforced (ablation). ``removed``: the
    slot is no longer timber. ``cap``: the harvest limit offered to the economy
    (None when not enforced). ``capped``: the realized output reached a
    positive cap (None when the cap was zero or not enforced: binding is not
    observable then).
    """
    model_config = ConfigDict(extra="forbid")

    region_id: int = Field(ge=0)
    slot: int = Field(ge=0, le=2)
    opening: float = _amount()
    cleared: float = _amount()
    extraction: float = _amount()
    overdraft: float = _amount()
    regrowth: float = _amount()
    removed: float = _amount()
    stock: float = _amount()
    capacity: float = _amount()
    cap: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    capped: bool | None = None
    water_gate_open: bool = False


class TimberTotals(BaseModel):
    """Cumulative flows over every observed turn since the stock was enabled."""
    model_config = ConfigDict(extra="forbid")

    observed_turns: int = Field(default=0, ge=0)
    extraction: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    overdraft: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    regrowth: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    cleared: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    removed: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    capped_slot_turns: int = Field(default=0, ge=0)


#: Fields added after the interface stub (schema 1 held ``enabled`` only),
#: with factories for the pickle backfill.
_BACKFILL = {
    "stocks": list,
    "ledger_turn": lambda: None,
    "ledger": list,
    "totals": TimberTotals,
}


class TimberStockState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    # Sorted by (region_id, slot); one entry per timber slot.
    stocks: list[TimberSlotStock] = Field(default_factory=list)
    # The turn whose Phase 2 the ledger records (None before the first).
    ledger_turn: int | None = None
    ledger: list[TimberLedgerRow] = Field(default_factory=list)
    totals: TimberTotals = Field(default_factory=TimberTotals)
    # Transient, within one Phase 2 only: what prepare offered the economy,
    # {(region, slot): (cap, harvest possible)}; finish and rollback clear it.
    # Never serialized; None between turns.
    _offered: dict | None = PrivateAttr(default=None)

    def __setstate__(self, state):
        super().__setstate__(state)
        # Exact pickle restoration bypasses Pydantic defaults (stub pickles).
        for name, factory in _BACKFILL.items():
            if name not in self.__dict__:
                self.__dict__[name] = factory()
        private = getattr(self, "__pydantic_private__", None)
        if private is None:
            object.__setattr__(self, "__pydantic_private__", {"_offered": None})
        else:
            private.setdefault("_offered", None)
