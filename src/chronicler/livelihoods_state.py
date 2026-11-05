"""Persisted container for the livelihoods/commons sprint (default off).

``WorldState.livelihoods`` is None (and omitted) unless one of the
independent switches was enabled: ``workshops`` (L1), ``food_allocation``
(L2), ``timber_stock`` (L3), ``grain_convoys`` (L4), ``commons_rules`` (L8),
``learning_cohorts`` (L5), ``workshop_payroll`` (L6a), ``relocation_costs``
(L7), ``local_budgets`` (L9) and the recovery-skills phase's
``apprenticeship`` (RS1), ``repair_projects`` (RS2),
``veteran_reintegration`` (RS3), ``remittances`` (RS4) and
``clearing_protection`` (RS5), and the productive-recovery phase's
``recovery_crews`` and ``maintenance_obligation`` (PL3). Each sub-state is
owned by its own module and is None while that switch has never been enabled.
Pure data, importable by :mod:`chronicler.models`.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.apprenticeship_state import ApprenticeshipState
from chronicler.clearing_protection_state import ClearingProtectionState
from chronicler.commons_rules_state import CommonsRulesState
from chronicler.food_allocation_state import FoodAllocationState
from chronicler.grain_convoys_state import GrainConvoyState
from chronicler.learning_cohorts_state import LearningCohortState
from chronicler.local_budgets_state import LocalBudgetState
from chronicler.maintenance_obligation_state import MaintenanceObligationState
from chronicler.recovery_crews_state import RecoveryCrewsState
from chronicler.relocation_costs_state import RelocationCostsState
from chronicler.remittances_state import RemittancesState
from chronicler.repair_projects_state import RepairProjectsState
from chronicler.timber_stock_state import TimberStockState
from chronicler.veteran_reintegration_state import VeteranReintegrationState
from chronicler.workshop_payroll_state import WorkshopPayrollState
from chronicler.workshops_state import WorkshopState

#: Switch names, in declaration order (CLI ``--<name>``; module ``chronicler.<name>``).
LIVELIHOODS_SWITCHES: tuple[str, ...] = ("workshops", "food_allocation", "timber_stock", "grain_convoys",
                                         "commons_rules", "learning_cohorts", "workshop_payroll",
                                         "relocation_costs", "local_budgets",
                                         "apprenticeship", "repair_projects", "veteran_reintegration",
                                         "remittances", "clearing_protection",
                                         "recovery_crews", "maintenance_obligation")


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
    apprenticeship: ApprenticeshipState | None = Field(default=None, exclude_if=_is_none)
    repair_projects: RepairProjectsState | None = Field(default=None, exclude_if=_is_none)
    veteran_reintegration: VeteranReintegrationState | None = Field(default=None, exclude_if=_is_none)
    remittances: RemittancesState | None = Field(default=None, exclude_if=_is_none)
    clearing_protection: ClearingProtectionState | None = Field(default=None, exclude_if=_is_none)
    recovery_crews: RecoveryCrewsState | None = Field(default=None, exclude_if=_is_none)
    maintenance_obligation: MaintenanceObligationState | None = Field(default=None, exclude_if=_is_none)

    # Transient: ``id()`` of the native simulator whose pool the saved stable
    # ids belong to (``livelihoods.bind_native_pool``). Never serialized; an
    # exact checkpoint load re-binds it (``run_checkpoint._rebind_markers``).
    _pool_sim: int | None = PrivateAttr(default=None)
    # Transient, within one turn: the native paid-work receipt, taken once
    # and shared by every package that installed paid work
    # (``livelihoods.paid_work_receipt``). Never serialized.
    _paid_receipt: tuple | None = PrivateAttr(default=None)

    def __getstate__(self):
        state = super().__getstate__()
        private = state.get("__pydantic_private__")
        if private and (private.get("_pool_sim") is not None or private.get("_paid_receipt") is not None):
            state = {**state, "__pydantic_private__": {**private, "_pool_sim": None, "_paid_receipt": None}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        # Exact pickle restoration bypasses Pydantic defaults.
        for name in LIVELIHOODS_SWITCHES:
            self.__dict__.setdefault(name, None)
        private = getattr(self, "__pydantic_private__", None)
        if private is None:
            object.__setattr__(self, "__pydantic_private__", {"_pool_sim": None, "_paid_receipt": None})
        else:
            private.setdefault("_pool_sim", None)
            private.setdefault("_paid_receipt", None)
