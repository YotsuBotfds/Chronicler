"""Persisted container for the livelihoods/commons sprint (default off).

``WorldState.livelihoods`` is None (and omitted) unless one of the
independent switches was enabled: ``workshops`` (L1), ``food_allocation``
(L2), ``timber_stock`` (L3), ``grain_convoys`` (L4), ``commons_rules`` (L8),
``learning_cohorts`` (L5), ``workshop_payroll`` (L6a), ``relocation_costs``
(L7) and ``local_budgets`` (L9). Each sub-state is owned by its own module and
is None while that switch has never been enabled.
Pure data, importable by :mod:`chronicler.models`.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from chronicler.clearing_protection_state import ClearingProtectionState
from chronicler.commons_rules_state import CommonsRulesState
from chronicler.food_allocation_state import FoodAllocationState
from chronicler.grain_convoys_state import GrainConvoyState
from chronicler.learning_cohorts_state import LearningCohortState
from chronicler.local_budgets_state import LocalBudgetState
from chronicler.relocation_costs_state import RelocationCostsState
from chronicler.timber_stock_state import TimberStockState
from chronicler.workshop_payroll_state import WorkshopPayrollState
from chronicler.workshops_state import WorkshopState

#: Switch names, in declaration order (CLI ``--<name>``; module ``chronicler.<name>``).
LIVELIHOODS_SWITCHES: tuple[str, ...] = ("workshops", "food_allocation", "timber_stock", "grain_convoys",
                                         "commons_rules", "learning_cohorts", "workshop_payroll",
                                         "relocation_costs", "local_budgets", "clearing_protection")


def _is_none(value) -> bool:
    return value is None


class LivelihoodsState(BaseModel):
    schema_version: Literal[1] = 1
    workshops: WorkshopState | None = Field(default=None, exclude_if=_is_none)
    food_allocation: FoodAllocationState | None = Field(default=None, exclude_if=_is_none)
    timber_stock: TimberStockState | None = Field(default=None, exclude_if=_is_none)
    grain_convoys: GrainConvoyState | None = Field(default=None, exclude_if=_is_none)
    commons_rules: CommonsRulesState | None = Field(default=None, exclude_if=_is_none)
    learning_cohorts: LearningCohortState | None = Field(default=None, exclude_if=_is_none)
    workshop_payroll: WorkshopPayrollState | None = Field(default=None, exclude_if=_is_none)
    relocation_costs: RelocationCostsState | None = Field(default=None, exclude_if=_is_none)
    local_budgets: LocalBudgetState | None = Field(default=None, exclude_if=_is_none)
    clearing_protection: ClearingProtectionState | None = Field(default=None, exclude_if=_is_none)

    def __setstate__(self, state):
        super().__setstate__(state)
        # Exact pickle restoration bypasses Pydantic defaults.
        for name in LIVELIHOODS_SWITCHES:
            self.__dict__.setdefault(name, None)
