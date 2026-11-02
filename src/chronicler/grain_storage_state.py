"""Optional persisted public-granary buildings and last completed work receipt.

Indices are world region indices; owners are civilization indices. Work is an
aggregate farmer-equivalent quantity, not an employee or a person identifier.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, PrivateAttr


class StoragePolicy(BaseModel):
    policy: Literal["neglect", "maintain", "expand"] = "neglect"
    work_budget: float = Field(default=0.0, ge=0, le=4, allow_inf_nan=False)


class StorageAsset(BaseModel):
    capacity: float = Field(ge=0, allow_inf_nan=False)
    condition: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)
    repair_progress: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    expansion_progress: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    owner: int = -1


class StorageReceipt(BaseModel):
    turn: int
    region: int
    owner: int
    policy: Literal["neglect", "maintain", "expand"]
    requested: float
    delivered: float
    timber_reserved: float
    timber_used: float
    timber_returned: float
    treasury_paid: int
    condition_before: float
    condition_after: float
    capacity_before: float
    capacity_after: float
    repair_progress: float
    expansion_progress: float


class GrainStorageState(BaseModel):
    # None entries are initialized with the first successful economy tick.
    assets: list[StorageAsset | None] = Field(default_factory=list)
    policies: list[StoragePolicy] = Field(default_factory=list)
    receipts: list[StorageReceipt] = Field(default_factory=list)
    receipt_turn: int | None = None
    _active_plan: object | None = PrivateAttr(default=None)
