"""D1c's bounded, dated local branches. Movement ids are native index + 1.

There is no branch cash account. Named resident members pay an explicit host
license/service contribution through the one wealth balance and money seam.
"""
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from chronicler.money import MoneyBook
from chronicler.switch_state import SwitchStateMixin

MODES = ("funded", "record_only", "cost_only")
MAX_BRANCHES = 256                 # lifetime identities; never pruned or reused
MAX_PAYERS = 32                    # per branch and completed turn
MAX_PAYERS_TOTAL = 512             # keeps every money flow in the bounded book
MIN_PAYERS = 3
DUES_MILLI = 10
BRANCH_BATCH = 0xD1C000
COUNTERS = ("turns", "branches", "identity_capacity_refused", "member_turns", "paid_members",
            "dues_milli", "funded_branch_turns", "boundary_refused", "pool_resets")
Status = Literal["record_only", "funded", "cost_only", "too_few", "poor", "capacity",
                 "hostile", "quarantined", "ended", "empty", "payment_refused"]


class Branch(BaseModel):
    branch: int
    movement: int                    # native movement_id, Python index + 1
    host: int                        # civilization index, never a display name
    first_turn: int


class BranchRow(BaseModel):
    branch: int
    movement: int
    host: int
    target: int
    host_name: str = ""               # display names observed at this frame, never decision inputs
    target_name: str = ""
    regions: list[int] = Field(default_factory=list)
    members: int = 0                 # living local adults, excluding trips
    payers: list[int] = Field(default_factory=list)  # actual stable native ids
    dues_milli: int = 0
    status: Status
    active_from: int | None = None


class BranchFrame(BaseModel):
    turn: int
    rows: list[BranchRow] = Field(default_factory=list)
    new_identities_refused: int = 0


class MovementBranchesState(SwitchStateMixin, BaseModel):
    enabled: bool = True
    mode: Literal["funded", "record_only", "cost_only"] = "funded"
    next_branch: int = 1
    branches: list[Branch] = Field(default_factory=list)
    book: MoneyBook = Field(default_factory=MoneyBook)
    frame: BranchFrame | None = None
    frame_turn: int | None = None
    counters: dict[str, int] = Field(default_factory=dict)
    _BUMP: ClassVar[dict] = {"allowed": COUNTERS}
