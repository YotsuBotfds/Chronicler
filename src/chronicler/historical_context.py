"""What a run's record says as of a turn: one convention for every reader.

Nothing here is read by the simulation and nothing here changes a run's
outputs. Narration, curation and other readers of a finished (or running)
record use it so that a moment told at turn T never shows a person, deed,
bond or value that the record dates after T.

Turn and phase convention
-------------------------
Turn ``T`` runs while ``world.turn == T``. Everything it records carries
``T``: ``Event.turn``, ``NamedEvent.turn``, ``GreatPerson.born_turn`` and
``death_turn``, ``GreatPersonDeed.turn``, a memory's ``turn``, a bond's
``formed_turn``, an artifact's ``origin_turn``. When the turn ends,
``world.turn`` becomes ``T + 1`` and the snapshot taken then is labelled
``TurnSnapshot.turn == T + 1``. So snapshot ``S`` holds the state after turn
``S - 1``, which is the state at the start of turn ``S``.

:class:`AsOf` names a point in that sequence:

* ``AsOf(T, Phase.END)`` (:meth:`AsOf.after`) is after turn ``T`` ran: it
  knows what turns ``<= T`` recorded; its snapshot is ``T + 1``.
* ``AsOf(T, Phase.START)`` (:meth:`AsOf.before`) is before turn ``T`` ran:
  it knows what turns ``<= T - 1`` recorded; its snapshot is ``T``.

Both reduce to :attr:`AsOf.completed`, the last completed turn. A record
dated ``d`` is known when ``d <= completed``; the snapshot used is the latest
one labelled ``<= completed + 1``, never a later one.

Readers and the point they use:

* curated narration of a moment covering turns ``a..b``: ``AsOf.after(b)``;
* a curator gap covering turns ``a..b``: from ``AsOf.before(a)`` to
  ``AsOf.after(b)``;
* the viewer at scrubber turn ``T`` shows snapshot ``T``, i.e.
  ``AsOf.before(T)`` (``AsOf.at_snapshot(T)``);
* a live turn message after turn ``T`` carries snapshot ``T + 1``,
  ``AsOf.after(T)``.

Observations
------------
Some inputs are not dated records but observations taken when the record
was read, normally after the run's last turn: a great person's needs, arc
phase and summary, memory intensities and bond sentiments; the agent
bridge's Gini, displacement and trade dependency; an artifact's holder; the
registry's dynasty flags; the role and civilization a person ends with.
``observed_through`` is the completed turn they describe (by default the
world's last completed turn). A view uses them only when its completed turn
is at or after that turn; before it, it keeps what the dated record and the
observation still imply (a memory recorded before the moment, as strong as
it is now or stronger, since memories only fade) and leaves the rest out.

Future information belongs only in sections a prompt labels as such (the
narrator's "AFTER this moment" and "LATER CONSEQUENCES"); views never carry
it.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import (
        Event, GreatPerson, GreatPersonDeed, SettlementSummary, TurnSnapshot, WorldState,
    )


class Phase(str, Enum):
    """Where in a turn a view stands."""

    START = "start"  # before the turn ran: its own records are not yet known
    END = "end"      # after the turn ran: its records are known


@dataclass(frozen=True, order=True)
class AsOf:
    """A point in the run: turn ``turn`` at ``phase`` (see the module doc)."""

    turn: int
    phase: Phase = Phase.END

    @classmethod
    def after(cls, turn: int) -> "AsOf":
        """After turn ``turn`` completed."""
        return cls(turn, Phase.END)

    @classmethod
    def before(cls, turn: int) -> "AsOf":
        """Before turn ``turn`` ran (after turn ``turn - 1``)."""
        return cls(turn, Phase.START)

    @classmethod
    def at_snapshot(cls, snapshot_turn: int) -> "AsOf":
        """The point a snapshot labelled ``snapshot_turn`` describes."""
        return cls.before(snapshot_turn)

    @property
    def completed(self) -> int:
        """The last completed turn."""
        return self.turn if self.phase is Phase.END else self.turn - 1

    @property
    def snapshot_turn(self) -> int:
        """The label of the snapshot that holds this point's state."""
        return self.completed + 1

    def knows(self, turn: int | None) -> bool:
        """Whether a record dated ``turn`` is known here (undated: no)."""
        return turn is not None and turn <= self.completed


def snapshot_as_of(history: Sequence["TurnSnapshot"], as_of: AsOf) -> "TurnSnapshot | None":
    """The latest snapshot labelled at or before ``as_of.snapshot_turn``.

    Never a later snapshot; None when the history starts after the point.
    ``history`` may be in any order.
    """
    best = None
    for snap in history:
        if snap.turn <= as_of.snapshot_turn and (best is None or snap.turn > best.turn):
            best = snap
    return best


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------

# Narration renders a memory as "fading" at this |intensity| and "vivid" at
# the second (narrative.MEMORY_NARRATION_FADING / _VIVID).
MEMORY_FADING = 30
MEMORY_VIVID = 60

_HOSTAGE_TAKEN = re.compile(r" takes (?P<name>.+) hostage from ")


def _terminal_status(gp: "GreatPerson") -> str:
    """A person's lifecycle label from their final record."""
    if gp.fate == "exile":
        return "exiled"
    if gp.fate == "retired":
        return "retired"
    if gp.fate in {"ascended", "ascended_to_leadership"}:
        return "ascended"
    if gp.fate == "dead" or not gp.alive:
        return "dead"
    return "active"


def _end_turn(gp: "GreatPerson") -> int | None:
    """The turn a person left active life, when the record dates it.

    ``death_turn`` (deaths and retirements); for a person inactive at the end
    without one (exile, ascension), the turn of their last dated deed, which
    those changes append. A person who ascended and died later left active
    life at the ascension: their last dated deed up to the death. None for a
    person still active, or undated.
    """
    ascended = gp.fate in {"ascended", "ascended_to_leadership"}
    if gp.death_turn is not None and not ascended:
        return gp.death_turn
    if gp.active:
        return None
    dated = [d.turn for d in gp.deeds
             if d.turn is not None and (gp.death_turn is None or d.turn <= gp.death_turn)]
    return max(dated) if dated else gp.death_turn


@dataclass(frozen=True)
class CharacterAsOf:
    """A great person as the record knows them at a point.

    ``memories`` keep their recorded fields; when ``memory_strength_observed``
    is False their intensities are later observations, lower bounds of the
    intensity at this point. ``needs`` and ``arc_phase``/``arc_summary`` are
    None unless observed here; bonds carry ``sentiment`` only when observed.
    """

    name: str
    role: str
    trait: str
    civilization: str
    origin_civilization: str
    source: str
    agent_id: int | None
    born_turn: int
    status: str
    active: bool
    deeds: tuple["GreatPersonDeed", ...]
    memories: tuple[Mapping[str, Any], ...]
    memory_strength_observed: bool
    needs: Mapping[str, float] | None
    bonds: tuple[Mapping[str, Any], ...]
    arc_type: str | None
    arc_phase: str | None
    arc_summary: str | None
    mule: bool
    utility_overrides: Mapping[str, float]
    dynasty_id: int | None
    lineage_house: int
    is_hostage: bool
    captured_by: str | None
    alive: bool


def _civ_as_of(gp: "GreatPerson", completed: int, hostage: bool) -> str:
    if hostage:
        return gp.civilization
    dated = [d for d in gp.deeds if d.turn is not None and d.turn <= completed and d.civ]
    if dated:
        return max(dated, key=lambda d: d.turn).civ
    return gp.origin_civilization or gp.civilization


def character_as_of(gp: "GreatPerson", as_of: AsOf, observed: bool,
                    capture_turn: int | None = None,
                    bond_extra: Sequence[Mapping[str, Any]] = ()) -> CharacterAsOf | None:
    """``gp`` as known at ``as_of``; None before their birth or when the
    record cannot place them there.

    ``capture_turn`` dates the hostage-taking that holds them at the end;
    ``bond_extra`` are bonds live at the point but dissolved later.
    """
    c = as_of.completed
    if gp.born_turn > c:
        return None
    if observed:
        status = _terminal_status(gp)
        active = gp.active
        alive = gp.alive
    else:
        end = _end_turn(gp)
        if end is None and not gp.active:
            return None  # left active life at an undated turn
        ended = end is not None and end <= c
        status = _terminal_status(gp) if ended else "active"
        active = not ended
        alive = gp.alive or (gp.death_turn is not None and gp.death_turn > c)
    hostage = gp.is_hostage and (observed or (capture_turn is not None and capture_turn <= c))
    role = gp.role
    if not observed and gp.role == "hostage" and not hostage:
        role = gp.pre_hostage_role or gp.role
    deeds = tuple(d for d in gp.deeds if (d.turn is None and observed) or as_of.knows(d.turn))
    memories = tuple(
        MappingProxyType(dict(m)) for m in (gp.memories or [])
        if as_of.knows(m.get("turn")) and (observed or abs(m.get("intensity", 0)) >= MEMORY_FADING)
    )
    bonds = []
    for bond in list(gp.agent_bonds or []) + list(bond_extra):
        if not as_of.knows(bond.get("formed_turn")):
            continue
        b = dict(bond)
        if not observed:
            b.pop("sentiment", None)
        bonds.append(MappingProxyType(b))
    arc_type = gp.arc_type if (observed or as_of.knows(gp.arc_type_turn)) else None
    return CharacterAsOf(
        name=gp.name, role=role, trait=gp.trait,
        civilization=gp.civilization if observed else _civ_as_of(gp, c, hostage),
        origin_civilization=gp.origin_civilization, source=gp.source, agent_id=gp.agent_id,
        born_turn=gp.born_turn, status=status, active=active, deeds=deeds, memories=memories,
        memory_strength_observed=observed,
        needs=MappingProxyType(dict(gp.needs)) if (observed and gp.needs) else None,
        bonds=tuple(bonds), arc_type=arc_type,
        arc_phase=gp.arc_phase if observed else None,
        arc_summary=gp.arc_summary if observed else None,
        mule=bool(getattr(gp, "mule", False)),
        utility_overrides=MappingProxyType(dict(getattr(gp, "utility_overrides", {}) or {})),
        dynasty_id=gp.dynasty_id, lineage_house=gp.lineage_house,
        is_hostage=hostage, captured_by=gp.captured_by if hostage else None, alive=alive,
    )


# ---------------------------------------------------------------------------
# The record and its views
# ---------------------------------------------------------------------------

_REL_TYPES = {
    0: "mentor", 1: "rival", 2: "marriage", 3: "exile_bond", 4: "co_religionist",
    5: "kin", 6: "friend", 7: "grudge",
}


class HistoricalRecord:
    """A run's record, indexed once; :meth:`view` gives what it says as of a point.

    ``history`` (snapshots), ``events`` (default: the world's timeline) and
    ``great_persons`` are dated records. ``world`` supplies names, the belief
    registry and artifacts. The remaining arguments are observations taken at
    ``observed_through``: by default (``"auto"``) the world's last completed
    turn, else the history's; ``None`` means the caller vouches that they
    describe every view (a per-turn caller with current values):
    ``gini_by_civ`` and ``displacement_by_region`` (by index),
    ``economy_result`` (its ``trade_dependent``), ``social_edges`` (live bonds
    without a per-character store), ``dissolved_edges_by_turn`` (dissolution
    turn -> ``(a, b, type, formed_turn)``), ``agent_name_map`` and
    ``dynasty_registry``. The record does not change its inputs; treat them as
    read-only while it is in use.
    """

    def __init__(
        self,
        *,
        history: Sequence["TurnSnapshot"] = (),
        events: Sequence["Event"] | None = None,
        great_persons: Iterable["GreatPerson"] = (),
        world: "WorldState | None" = None,
        observed_through: int | None | str = "auto",
        gini_by_civ: Mapping[int, float] | None = None,
        displacement_by_region: Mapping[int, float] | None = None,
        economy_result: Any = None,
        social_edges: Sequence[tuple] | None = None,
        dissolved_edges_by_turn: Mapping[int, Sequence[tuple]] | None = None,
        agent_name_map: Mapping[int, str] | None = None,
        dynasty_registry: Any = None,
    ) -> None:
        self.history = tuple(sorted(history, key=lambda s: s.turn))
        self._snap_turns = [s.turn for s in self.history]
        if events is None:
            events = list(getattr(world, "events_timeline", None) or [])
        self.events = tuple(events)
        self.great_persons = tuple(great_persons)
        self.world = world
        if observed_through == "auto":
            if world is not None:
                observed_through = world.turn - 1
            elif self.history:
                observed_through = self.history[-1].turn - 1
            else:
                observed_through = None
        self.observed_through: int | None = observed_through
        self.gini_by_civ = MappingProxyType(dict(gini_by_civ)) if gini_by_civ is not None else None
        self.displacement_by_region = (MappingProxyType(dict(displacement_by_region))
                                       if displacement_by_region is not None else None)
        self.economy_result = economy_result
        self.social_edges = tuple(social_edges) if social_edges is not None else None
        self.dissolved_edges_by_turn = MappingProxyType(
            {int(t): tuple(edges) for t, edges in (dissolved_edges_by_turn or {}).items()})
        self.agent_name_map = MappingProxyType(dict(agent_name_map or {}))
        self.dynasty_registry = dynasty_registry
        # Hostage-takings by name (the latest), dynasty splits by founder (the earliest).
        captures: dict[str, int] = {}
        splits: dict[str, int] = {}
        for ev in self.events:
            if ev.event_type == "hostage_taken":
                m = _HOSTAGE_TAKEN.search(ev.description or "")
                if m:
                    captures[m.group("name")] = max(ev.turn, captures.get(m.group("name"), ev.turn))
            elif ev.event_type == "dynasty_split" and ev.actors:
                splits[ev.actors[0]] = min(ev.turn, splits.get(ev.actors[0], ev.turn))
        self._captures = MappingProxyType(captures)
        self._splits = MappingProxyType(splits)
        self._views: dict[AsOf, HistoricalView] = {}

    def observed_at(self, as_of: AsOf) -> bool:
        """Whether the record's observations describe ``as_of``."""
        return self.observed_through is None or as_of.completed >= self.observed_through

    def snapshot(self, as_of: AsOf) -> "TurnSnapshot | None":
        i = bisect.bisect_right(self._snap_turns, as_of.snapshot_turn)
        return self.history[i - 1] if i else None

    def view(self, as_of: AsOf) -> "HistoricalView":
        cached = self._views.get(as_of)
        if cached is None:
            cached = self._views[as_of] = self._build_view(as_of)
        return cached

    def _bonds_dissolved_after(self, as_of: AsOf) -> dict[int, list[dict]]:
        """Per agent id: bonds formed by ``as_of`` and dissolved after it."""
        out: dict[int, list[dict]] = {}
        for turn in sorted(self.dissolved_edges_by_turn):
            if turn <= as_of.completed:
                continue
            for a, b, rel_type, formed in self.dissolved_edges_by_turn[turn]:
                if formed <= as_of.completed:
                    out.setdefault(a, []).append(
                        {"target_id": b, "bond_type": rel_type, "formed_turn": formed})
        return out

    def _build_view(self, as_of: AsOf) -> "HistoricalView":
        observed = self.observed_at(as_of)
        extra = {} if observed else self._bonds_dissolved_after(as_of)
        chars = []
        for gp in self.great_persons:
            ch = character_as_of(gp, as_of, observed, capture_turn=self._captures.get(gp.name),
                                 bond_extra=extra.get(gp.agent_id, ()) if gp.agent_id is not None else ())
            if ch is not None:
                chars.append(ch)
        return HistoricalView(record=self, as_of=as_of, snapshot=self.snapshot(as_of),
                              observed=observed, characters=tuple(chars))


@dataclass(frozen=True)
class HistoricalView:
    """What the record says as of ``as_of`` (build with :meth:`HistoricalRecord.view`).

    ``snapshot`` is the snapshot of that point (or the latest earlier one);
    ``characters`` are the great persons born by then, in the record's order;
    ``observed`` tells whether the record's observations describe this point.
    """

    record: HistoricalRecord = field(repr=False, compare=False)
    as_of: AsOf
    snapshot: "TurnSnapshot | None"
    observed: bool
    characters: tuple[CharacterAsOf, ...]

    def character(self, name: str) -> CharacterAsOf | None:
        return next((c for c in self.characters if c.name == name), None)

    def by_agent_id(self) -> dict[int, CharacterAsOf]:
        return {c.agent_id: c for c in self.characters if c.agent_id is not None}

    def events(self) -> list["Event"]:
        """The recorded events known here, in record order."""
        return [ev for ev in self.record.events if self.as_of.knows(ev.turn)]

    def moment_characters(self, actors: set[str], civs: set[str],
                          source: str | None = "agent") -> list[CharacterAsOf]:
        """The characters a moment's events name, and the active characters
        of the civs they involve (record order)."""
        return [c for c in self.characters
                if (source is None or c.source == source)
                and (c.name in actors or (c.active and c.civilization in civs))]

    # --- observations and snapshot values ---------------------------------

    def gini(self, civ_idx: int | None, civ_name: str | None) -> float:
        """The bridge's Gini when observed here, else the snapshot's, else 0."""
        bridge = self.record.gini_by_civ
        if self.observed and bridge is not None and civ_idx is not None:
            value = bridge.get(civ_idx)
            if value is not None:
                return value
        if self.snapshot is not None and civ_name is not None:
            row = self.snapshot.civ_stats.get(civ_name)
            if row is not None and row.gini is not None:
                return row.gini
        return 0.0

    def displacement(self) -> float | None:
        """Mean displaced fraction over tracked regions, when observed here."""
        values = self.record.displacement_by_region
        if not self.observed or values is None:
            return None
        values = list(values.values())
        return sum(values) / len(values) if values else 0.0

    def trade_dependent_regions(self) -> list[str] | None:
        """Regions the economy found trade-dependent, when observed here."""
        er = self.record.economy_result
        if not self.observed or er is None:
            return None
        return [name for name, dep in getattr(er, "trade_dependent", {}).items() if dep]

    def settlements(self, civ_name: str | None, limit: int = 3) -> list["SettlementSummary"]:
        """The largest active settlements of ``civ_name``'s regions in the snapshot."""
        snap = self.snapshot
        if snap is None or civ_name is None:
            return []
        rows = [s for s in snap.active_settlements
                if s.status in ("active", "dissolving") and snap.region_control.get(s.region_name) == civ_name]
        rows.sort(key=lambda s: (-s.population_estimate, s.settlement_id))
        return rows[:limit]

    # --- relationships and lineage -----------------------------------------

    def relationships(self, chars: Sequence[CharacterAsOf], turn_range: tuple[int, int],
                      per_character_bonds: bool) -> list[dict]:
        """Relationship lines of ``chars``: their bonds live here (from the
        per-character store, or the legacy edge list), the bonds dissolved
        during ``turn_range`` (up to this point), and hostages held here."""
        names = {c.name for c in chars}
        name_map = self.record.agent_name_map
        rels: list[dict] = []
        dissolved = [edge for t in range(turn_range[0], min(turn_range[1], self.as_of.completed) + 1)
                     for edge in self.record.dissolved_edges_by_turn.get(t, ())]
        if per_character_bonds:
            for c in chars:
                for bond in c.bonds:
                    target = name_map.get(bond["target_id"])
                    if target is None:
                        continue
                    rel = {"type": _REL_TYPES.get(bond["bond_type"], "unknown"),
                           "character_a": c.name, "character_b": target,
                           "since_turn": bond.get("formed_turn", 0)}
                    if "sentiment" in bond:
                        s = abs(bond.get("sentiment", 0))
                        rel["sentiment"] = ("deep" if s > 80 else "strong" if s > 40
                                            else "mild" if s > 0 else "fading")
                    rels.append(rel)
            for a, b, rel_type, formed in dissolved:
                name_a, name_b = name_map.get(a, ""), name_map.get(b, "")
                if name_a in names or name_b in names:
                    rels.append({"type": _REL_TYPES.get(rel_type, "unknown") + " (dissolved)",
                                 "character_a": name_a, "character_b": name_b, "since_turn": formed})
        else:
            edges = [e for e in (self.record.social_edges or ()) if self.as_of.knows(e[3])]
            if not self.observed:
                edges += [edge for t in sorted(self.record.dissolved_edges_by_turn)
                          if t > self.as_of.completed
                          for edge in self.record.dissolved_edges_by_turn[t]
                          if self.as_of.knows(edge[3])]
            for a, b, rel_type, formed in edges + dissolved:
                name_a, name_b = name_map.get(a, ""), name_map.get(b, "")
                if name_a not in names and name_b not in names:
                    continue
                rels.append({"type": _REL_TYPES.get(rel_type, "unknown"),
                             "character_a": name_a, "character_b": name_b,
                             "role_a": "mentor" if rel_type == 0 else None,
                             "role_b": "apprentice" if rel_type == 0 else None,
                             "since_turn": formed})
        for c in self.characters:
            if c.is_hostage and c.captured_by and (c.name in names or c.captured_by in names):
                rels.append({"type": "hostage", "character_a": c.captured_by, "character_b": c.name,
                             "role_a": "captor", "role_b": "captive", "since_turn": c.born_turn})
        return rels

    def dynasty(self, char: CharacterAsOf, gp_by_agent_id: Mapping[int, "GreatPerson"]) -> dict | None:
        """``dynasty``, ``dynasty_living``, ``dynasty_total`` (members known
        here), ``dynasty_split`` and ``lineage_house`` of a character."""
        registry = self.record.dynasty_registry
        if registry is None or not char.agent_id:
            return None
        out: dict[str, Any] = {}
        dynasty = registry.get_dynasty_for(char.agent_id, gp_by_agent_id)
        if dynasty is not None:
            out["dynasty"] = dynasty.founder_name
            if self.observed:
                out["dynasty_living"] = sum(1 for m in dynasty.members
                                            if m in gp_by_agent_id and gp_by_agent_id[m].alive)
                out["dynasty_total"] = len(dynasty.members)
                split = bool(dynasty.split_detected)
            else:
                known = self.by_agent_id()
                members = [known[m] for m in dynasty.members if m in known]
                out["dynasty_living"] = sum(1 for m in members if m.alive)
                out["dynasty_total"] = len(members)
                split = self.as_of.knows(self.record._splits.get(dynasty.founder_name))
            if split:
                out["dynasty_split"] = True
        if char.lineage_house and char.lineage_house != (char.dynasty_id or 0):
            try:
                out["lineage_house"] = registry._find(char.lineage_house).founder_name
            except ValueError:
                pass
        return out or None

    # --- artifacts -----------------------------------------------------------

    def artifacts(self, moment, max_count: int = 3) -> list[tuple[Any, str]]:
        """Artifacts relevant to a moment, each with its holder text.

        Observed here: as the world holds them (``artifacts._get_relevant_artifacts``).
        Before: artifacts made by then and still standing at the end, found
        and described by their making (the holder and owner are later
        observations).
        """
        world = self.record.world
        if world is None:
            return []
        from chronicler.artifacts import _get_relevant_artifacts, artifact_holder_text
        if self.observed:
            return [(a, artifact_holder_text(a)) for a in _get_relevant_artifacts(world, moment, max_count)]
        from chronicler.models import ArtifactStatus
        actors = {actor for ev in moment.events for actor in ev.actors}
        regions = {ne.region for ne in moment.named_events if getattr(ne, "region", None)}
        out = []
        for a in world.artifacts:
            if a.status != ArtifactStatus.ACTIVE or not self.as_of.knows(a.origin_turn):
                continue
            if ((a.creator_name and a.creator_name in actors)
                    or (a.anchored and a.origin_region in regions)
                    or (a.creator_civ in actors and (a.mule_origin or a.prestige_value >= 3))):
                where = f"made in {a.origin_region}" if a.origin_region else "made"
                out.append((a, f"{where} by {a.creator_name or a.creator_civ}"))
            if len(out) >= max_count:
                break
        return out
