"""Persisted great-person agenda state (see :mod:`chronicler.gp_agendas`).

Pure data with no simulation imports, so :mod:`chronicler.models` can import
it. ``WorldState.gp_agendas`` is ``None`` while the switch is off and is then
omitted from serialized output, so flag-off saves, bundles and fixtures keep
their bytes and worlds saved before this module existed load unchanged.

Identity: a great person has no index of its own; records are keyed by
``"<name>|<born_turn>"``, the pair the artifact holder lifecycle already uses
to find a person (``artifacts._find_gp``), plus ``"|a<agent_id>"`` for an
agent-backed person (promotion can name two agents alike in one turn; agent
ids are unique). Civilizations are stored as their
index in ``world.civilizations``; region targets are region names (as in
``civ.regions`` and the ruler-ambition targets) and trade-route targets are
civ indices written as strings (as the ruler-ambition kernel takes them).
The objective itself is a :class:`~chronicler.governance_state.GovernanceAmbition`,
the persisted form of ``ruler_ambitions.Ambition``.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from chronicler.governance_state import GovernanceAmbition

GP_AGENDA_STATE_VERSION = 1

#: Bond kinds. Alliances: ``loyalty`` (a person backs the ruler),
#: ``conspiracy`` (backs a plotting general), ``partnership`` (two merchants
#: courting each other's civ). Rivalries: ``opposition`` (a person against the
#: ruler) and ``feud`` (two persons whose agendas collide).
ALLIANCE_KINDS = ("loyalty", "conspiracy", "partnership")
RIVALRY_KINDS = ("opposition", "feud")
BOND_KINDS = ALLIANCE_KINDS + RIVALRY_KINDS


class AgendaRecord(BaseModel):
    """One great person's agenda career while the person is active."""

    gp_name: str
    born_turn: int
    role: str
    civ: int                                  # civ index holding the current agenda
    agent_id: int | None = None               # agent-backed persons (part of the key)
    serial: int = 0                           # agendas declared so far
    agenda: GovernanceAmbition | None = None  # the open objective (None between agendas)
    last_evaluated_turn: int | None = None
    last_event_cursor: int | None = None
    renown: int = 0
    next_turn: int = 0                        # earliest turn of the next declaration
    declared_event: str | None = None         # provenance id of the open agenda's declaration
    motive_events: list[str] = Field(default_factory=list)  # grievance / ambition it answers
    completed: int = 0
    failed: int = 0
    # Deed bookkeeping for the open agenda (reset at each declaration).
    deed_turn: int | None = None              # turn of the last deed (one per turn)
    commissioned: bool = False                # shrine commissioned / preaching begun


class AgendaBond(BaseModel):
    """An alliance or rivalry: person ``a`` with person ``b`` or a ruler."""

    kind: str
    a: str                                    # record key
    b: str                                    # record key, or "ruler:<civ index>"
    civ: int                                  # civ index of ``a`` when formed
    ruler: str | None = None                  # the ruler's name for ruler bonds
    formed_turn: int
    event_id: str | None = None


class AgendaLogEntry(BaseModel):
    """A resolved agenda (bounded archive for reports and narration)."""

    gp: str
    role: str
    civ: int
    kind: str
    target: str | None = None
    start: int
    end: int
    outcome: str                              # "fulfilled" | "failed"
    reason: str | None = None


class GPAgendaState(BaseModel):
    version: int = GP_AGENDA_STATE_VERSION
    records: dict[str, AgendaRecord] = Field(default_factory=dict)
    bonds: list[AgendaBond] = Field(default_factory=list)
    evidence_cursor: int = 0
    counts: dict[str, int] = Field(default_factory=dict)
    log: list[AgendaLogEntry] = Field(default_factory=list)
    # Trading houses founded: region name -> founding turn (one per region).
    houses: dict[str, int] = Field(default_factory=dict)


def gp_agendas_on(world) -> bool:
    """True only for a real agenda state (``None`` and mocks read as off)."""
    return isinstance(getattr(world, "gp_agendas", None), GPAgendaState)
