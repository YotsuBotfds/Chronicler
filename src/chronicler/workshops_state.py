"""Persisted state of the L1 staffed public workshops (default off).

Site and region indices: ``region`` is the index in ``world.regions``;
``settlement_id`` is the city's M56a settlement id; ``payer`` is a civilization
index in ``world.civilizations``; agent ids are native stable ids. At most four
sites are open at once, one per region, each with at most eight named crew
members. Receipts describe the last completed Phase 2 only (one frame), and
each site keeps a bounded dated history, never a lifetime copy. Pure data.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from chronicler.switch_state import SwitchStateMixin

MAX_SITES = 4
MAX_CREW = 8
MAX_CLOSED = 8
MAX_HISTORY = 16
#: Site closure reasons, in declaration order (append only).
CLOSE_REASONS: tuple[str, ...] = ("city_fell", "city_missing", "region_changed", "insolvent")
#: Asset statuses (L1B). ``building``: construction installments outstanding;
#: ``open``: built and in condition; ``idle``: built but unfunded or in need of
#: repair this turn; ``closed``: the city is gone.
ASSET_STATUSES: tuple[str, ...] = ("building", "open", "idle", "closed")
#: Payment kinds, in declaration order (append only). All are a disclosed
#: public expenditure sink of the payer's treasury, never a wage.
PAYMENT_KINDS: tuple[str, ...] = ("construction", "upkeep", "arrears", "repair")


class WorkshopSite(BaseModel):
    site: int
    region: int
    settlement_id: int
    city_name: str
    selected_turn: int
    status: Literal["open", "closed"] = "open"
    closed_turn: int | None = None
    closed_reason: str | None = None
    # L1B asset lifecycle (absent in L1A observe mode: defaults below).
    asset: Literal["building", "open", "idle", "closed"] = "building"
    construction_paid: int = 0
    condition: float = 1.0
    arrears: int = 0
    last_payer: int = -1
    history: list[tuple[int, str, int, int]] = Field(default_factory=list)   # (turn, event, civ, amount)


class WorkshopReceipt(BaseModel):
    """One site's completed Phase 2, by stable identities and region totals.

    ``crew`` are the eligible identities the planner resolved. In observe and
    cost-only modes they are available, not employed (``allocated`` is 0).
    In operate mode a funded open site allocates each member's diverted
    fraction; ``realized`` is the work the region's actual craft output used
    (output / conversion), never more than allocated. Craft output and inputs
    are the region's actual native conversion, never a site share.
    """

    turn: int
    site: int
    region: int
    settlement_id: int
    rank: int
    diverted_fraction: float
    resident_adult_farmers: int
    excluded_trip: int
    excluded_army: int
    excluded_assigned: int
    eligible: int
    crew: list[int] = Field(default_factory=list)
    crew_ages: list[int] = Field(default_factory=list)
    work_available: float
    allocated: float = 0.0
    realized: float = 0.0
    legacy_craft_ceiling: float | None = None
    region_craft_output: float | None = None
    region_craft_input: dict[str, float] | None = None
    # L1B (None in observe mode).
    asset: str | None = None
    payer: int | None = None
    funded: bool | None = None
    craft_ceiling: float | None = None
    paid: dict[str, int] | None = None
    arrears_after: int | None = None
    condition_after: float | None = None
    affected_ordinary_income_share: float = 0.0


class WorkshopState(SwitchStateMixin, BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["operate", "observe", "cost_only"] = "observe"
    sites: list[WorkshopSite] = Field(default_factory=list)
    closed: list[WorkshopSite] = Field(default_factory=list)
    next_site: int = 0
    frame_turn: int | None = None
    frame: list[WorkshopReceipt] = Field(default_factory=list)
    counters: dict[str, float] = Field(default_factory=dict)
    _plan: object | None = PrivateAttr(default=None)
