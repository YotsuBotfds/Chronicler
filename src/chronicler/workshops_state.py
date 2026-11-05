"""Persisted state of the L1 staffed public workshops (default off).

Site and region indices: ``region`` is the index in ``world.regions``;
``settlement_id`` is the city's M56a settlement id; agent ids are native
stable ids. At most four sites are open at once, one per region, each with at
most eight named crew members. Receipts describe the last completed Phase 2
only (one frame), never a lifetime history. Pure data.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

MAX_SITES = 4
MAX_CREW = 8
MAX_CLOSED = 8
#: Site closure reasons, in declaration order (append only).
CLOSE_REASONS: tuple[str, ...] = ("city_fell", "city_missing", "region_changed")


class WorkshopSite(BaseModel):
    site: int
    region: int
    settlement_id: int
    city_name: str
    selected_turn: int
    status: Literal["open", "closed"] = "open"
    closed_turn: int | None = None
    closed_reason: str | None = None


class WorkshopReceipt(BaseModel):
    """One site's completed Phase 2, by stable identities and region totals.

    ``crew`` are the eligible identities the planner resolved; in observe
    mode they are available, not employed (``allocated`` is 0). Craft output
    and inputs are the region's actual native conversion, never a site share.
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


class WorkshopState(BaseModel):
    schema_version: Literal[1] = 1
    enabled: bool = True
    mode: Literal["operate", "observe"] = "observe"
    sites: list[WorkshopSite] = Field(default_factory=list)
    closed: list[WorkshopSite] = Field(default_factory=list)
    next_site: int = 0
    frame_turn: int | None = None
    frame: list[WorkshopReceipt] = Field(default_factory=list)
    counters: dict[str, float] = Field(default_factory=dict)
    _plan: object | None = PrivateAttr(default=None)
