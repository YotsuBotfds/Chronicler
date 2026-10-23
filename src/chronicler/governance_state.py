"""Persistent Phase 8 governance state for the live runtime (M63-M66 + PSI).

These Pydantic records are the save-file representation of the detached
governance kernels (``institutions``, ``elite_metrics``, ``governance_capital``
and ``ruler_ambitions``) once they run inside the real turn loop. The runtime
adapter in ``governance_runtime`` converts them to the kernels' frozen
dataclasses every turn and back again.

Every field has a default so worlds saved before governance existed load
unchanged. A world or civilization whose ``governance`` field is ``None`` is
dormant: the field is omitted from serialized output entirely, so feature-off
saves, bundles and snapshots stay byte-identical to the pre-governance format.

This module intentionally imports nothing from ``chronicler`` so that
``models`` can import it without a cycle.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

GOVERNANCE_STATE_VERSION = 1


class GovernanceSettings(BaseModel):
    """World-level switch and global counters. Presence means enabled."""

    enabled: bool = True
    version: int = GOVERNANCE_STATE_VERSION
    policy_id: str = "chronicler-governance-runtime-v1"


class GovernanceInstitution(BaseModel):
    """Persisted ``institutions.InstitutionState`` (M63a)."""

    institution_type: str
    enacted_turn: int
    legitimacy: float = 1.0
    enforcement_cost: float = 0.0
    opposing_faction: str


class GovernanceAmbition(BaseModel):
    """Persisted ``ruler_ambitions.Ambition`` (M66b)."""

    ambition_type: str
    target: str | None = None
    generated_turn: int
    deadline_turn: int
    generated_event_cursor: int
    conversion_faith_id: int | None = None
    conversion_minimum_share: float | None = None
    completed: bool = False
    failed: bool = False


class GovernanceReignRecord(BaseModel):
    """An archived reign, used for 1/n dynasty prestige and narration."""

    reign_id: str
    ruler_name: str
    start_turn: int
    end_turn: int
    succession_type: str = "founder"
    cognomen: str | None = None
    cognomen_bonus: float = 0.0
    ambitions_completed: int = 0
    ambitions_failed: int = 0
    victories: int = 0
    final_legitimacy: float = 0.5


class CivGovernance(BaseModel):
    """Per-civilization governance carry. Mutated only in Phase 2 / late Phase 10."""

    initialized_turn: int = 0

    # --- M63a institutions -------------------------------------------------
    institutions: list[GovernanceInstitution] = Field(default_factory=list)
    institutions_effective_turn: int = 0
    # Phase 2 funding record for ``funding_turn`` (consumed by late Phase 10).
    funding_turn: int = -1
    funding_treasury_before: float = 0.0
    funding_treasury_after: float = 0.0
    last_base_governing_cost: float = 0.0
    last_institution_enforcement_cost: float = 0.0
    last_institution_funding_ratio: float = 1.0
    last_enforcement_paid: int = 0
    # [turn, institution_type, kind] with kind in enacted/repealed/collapsed.
    institution_log: list[list] = Field(default_factory=list)
    institutions_enacted_total: int = 0
    institutions_repealed_total: int = 0
    institutions_collapsed_total: int = 0

    # --- M66a legitimacy and political capital ----------------------------
    governance_effective_turn: int = 0
    ruler_legitimacy: float = 0.5
    political_capital: float = 0.0
    legitimacy_sources: dict[str, float] = Field(default_factory=dict)
    reign_id: str | None = None
    reign_serial: int = 0
    ruler_name: str | None = None
    ruler_reign_start: int | None = None
    reign_start_turn: int = 0
    succession_kind: str | None = None
    victory_turns: list[int] = Field(default_factory=list)
    defeat_turns: list[int] = Field(default_factory=list)
    reign_archive: list[GovernanceReignRecord] = Field(default_factory=list)
    capital_spent_total: float = 0.0
    secession_suppressions: int = 0
    last_suppression_turn: int = -1000

    # --- M66b ambitions and event-chain tags ------------------------------
    ambitions: list[GovernanceAmbition] = Field(default_factory=list)
    ambition_contributions: dict[str, float] = Field(default_factory=dict)
    accession_turn: int = 0
    accession_event_cursor: int = 0
    last_evaluated_turn: int | None = None
    last_event_cursor: int | None = None
    evidence_cursor: int = 0
    ruler_event_tags: list[str] = Field(default_factory=list)
    # [turn, tag] recent window for curator / event-chain prerequisites.
    recent_tags: list[list] = Field(default_factory=list)
    ambitions_completed_total: int = 0
    ambitions_failed_total: int = 0

    # --- M65a elite metrics -----------------------------------------------
    ratchet_turn: int = -1
    conspicuous_consumption_index: float = 0.0
    elite_positions: int = 0
    elite_qualifier_count: int = 0
    elite_office_holder_count: int = 0
    frustrated_aspirant_count: int = 0
    emp: float = 0.0

    # --- M65b political stress index --------------------------------------
    mmp_raw: float = 0.0
    sfd_raw: float = 0.0
    mmp: float = 0.0  # smoothed normalized sub-indices
    emp_index: float = 0.0
    sfd: float = 0.0
    psi: float = 0.0
    psi_crisis: bool = False
    psi_crisis_since: int | None = None
    psi_crisis_count: int = 0
    last_psi_crisis_end: int | None = None
    psi_peak: float = 0.0
    psi_history: list[float] = Field(default_factory=list)
    revolts_total: int = 0
    civil_wars_total: int = 0

    # --- regime classification --------------------------------------------
    institutional_regime: str = "nascent"
    cycle_phase: str = "integrative"

    # --- guards -----------------------------------------------------------
    stability_carry: float = 0.0
    dominant_faction: str | None = None
    dominant_faction_turns: int = 0
    legitimacy_crisis: bool = False
    fiscal_crisis: bool = False
    elite_overproduction: bool = False
