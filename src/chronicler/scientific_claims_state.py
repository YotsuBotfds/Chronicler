"""Bounded institutional claims/evidence state; no simulation imports.

IDs are cohort-local monotonically allocated integers. Seat IDs are indexes
in ScholarshipState.seats; regions/civilizations keep their existing indexes.
No per-agent beliefs or random technique-validity flags are introduced.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from chronicler.scientific_research_state import LazyResearchModel, ResearchAgendas


MAX_SEATS = 20
MAX_CLAIMS = 20
MAX_TRIALS = 40
MAX_MESSAGES = (MAX_CLAIMS + MAX_TRIALS) * MAX_SEATS
LEGACY_PUBLICATION = "current-context-v1"
FUNDED_CONTEXT_PUBLICATION = "funded-context-v2"


def _is_legacy_publication(value):
    return value == LEGACY_PUBLICATION


class ClaimContext(BaseModel):
    crop: Literal["grain"] = "grain"
    soil_band: int = Field(ge=0, le=3)
    water_band: int = Field(ge=0, le=3)
    season: int = Field(ge=0, le=3)
    climate_phase: str
    crew: int = 4
    protocol: Literal["fixed-crew-grain-v1"] = "fixed-crew-grain-v1"


class ScientificClaim(BaseModel):
    id: int
    recipe: str
    origin_seat: int
    proposed_turn: int
    context: ClaimContext
    metric: Literal["grain_output"] = "grain_output"
    intervention: float = 1.0
    comparator: float = 0.0
    threshold: float = 0.02
    horizon: int = 1
    event_id: str = ""


class ScientificTrial(BaseModel):
    id: int
    claim: int
    seat: int
    payer: int
    funded_turn: int
    completion_turn: int
    resolved_turn: int | None = None
    cost: int
    parent: int = -1
    method: str = "fixed-crew-grain-v1"
    source_data: str = ""
    environment_block: str = ""
    dependence_group: str = ""
    inputs: dict = Field(default_factory=dict)
    control_output: float = 0.0
    treatment_output: float = 0.0
    observed_control: float | None = None
    observed_treatment: float | None = None
    informative: bool = False
    supports: bool | None = None
    status: Literal["running", "completed", "cancelled", "failed"] = "running"
    reason: str = ""
    funded_event_id: str = ""
    event_id: str = ""


class ProposalReceipt(LazyResearchModel):
    lazy_name = "agenda_id"
    lazy_backing = "_agenda_id"
    lazy_payload = int

    seat: int
    claim: int
    received_turn: int
    hops: int = 0

    @property
    def agenda_id(self):
        value = self._research_value()
        return 0 if value is None else value


class EvidenceReceipt(BaseModel):
    seat: int
    trial: int
    received_turn: int
    sender: int
    hops: int = 0
    event_id: str = ""


class ScienceMessage(LazyResearchModel):
    lazy_name = "agenda_id"
    lazy_backing = "_agenda_id"
    lazy_payload = int

    kind: Literal["proposal", "evidence"]
    record: int
    sender: int
    recipient: int
    sent_turn: int
    delivery_turn: int
    expires_turn: int
    hops: int

    @property
    def agenda_id(self):
        value = self._research_value()
        return 0 if value is None else value


class AdoptionEffort(BaseModel):
    seat: int
    region: int
    recipe: str
    share: float
    confidence: float
    paid: int  # whole seat payment on its first allocation row; zero on others
    event_id: str = ""  # present only for a first/materially changed allocation


class ScientificClaimsState(LazyResearchModel):
    lazy_name = "research_agendas"
    lazy_backing = "_research_agendas"
    lazy_payload = ResearchAgendas

    cohort: int = 0
    started_turn: int | None = None
    seat_ids: list[int] = Field(default_factory=list, max_length=MAX_SEATS)
    claims: list[ScientificClaim] = Field(default_factory=list, max_length=MAX_CLAIMS)
    trials: list[ScientificTrial] = Field(default_factory=list, max_length=MAX_TRIALS)
    proposals: list[ProposalReceipt] = Field(default_factory=list, max_length=MAX_SEATS * MAX_CLAIMS)
    receipts: list[EvidenceReceipt] = Field(default_factory=list, max_length=MAX_SEATS * MAX_TRIALS)
    messages: list[ScienceMessage] = Field(default_factory=list, max_length=MAX_MESSAGES)
    last_effort: list[AdoptionEffort] = Field(default_factory=list, max_length=MAX_SEATS * 2)
    reported_allocations: dict[int, dict[str, float]] = Field(default_factory=dict, max_length=MAX_SEATS)
    withhold_information: bool = False
    transmission_enabled: bool = True
    uninformative_tests: bool = False
    publication_rule: Literal["current-context-v1", "funded-context-v2"] = Field(
        default=LEGACY_PUBLICATION, exclude_if=_is_legacy_publication)
    trial_spent: int = 0
    effort_spent: int = 0
    cancelled: int = 0
    failed: int = 0
    expired_messages: int = 0
    withheld_results: int = 0
    unfunded_trials: int = 0
    unfunded_effort: int = 0
    last_tick_turn: int = -1
    last_effort_turn: int = -1

    @property
    def research_agendas(self):
        return self._research_value()


def scientific_claims_on(world) -> bool:
    return isinstance(getattr(world, "scientific_claims", None), ScientificClaimsState)
