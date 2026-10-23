"""Incremental lookups over a world's append-only history lists.

Several per-turn checks used to rescan the whole ``events_timeline``,
``named_events`` or ``agent_events_raw`` list, so a turn's cost grew with run
length. ``HistoryIndex`` answers the same questions from derived buckets that
are extended with only the entries appended since the previous query.

The index is a cache, never state: it is not serialized, a copied world gets
an empty index, and every query first re-synchronizes against the live lists.
A list that was replaced, shortened or rewritten at its tail is detected and
the affected buckets are rebuilt from scratch, so a world loaded from
``state.json`` (or edited by tests) answers exactly as a full rescan would.
Buckets keep source-list order, so results iterate in the original order.
"""
from __future__ import annotations

from typing import Any

# Named-event types whose duplicate checks are served from the index.
_SCHISM = "movement_schism"
_HEGEMONY = "cultural_hegemony"
_ENLIGHTENMENT = "universal_enlightenment"


class _Cursor:
    """Tracks how much of one source list has been folded into buckets."""

    __slots__ = ("source", "seen", "last")

    def __init__(self) -> None:
        self.source: list | None = None
        self.seen = 0
        self.last: Any = None

    def new_items(self, source: list) -> tuple[bool, list]:
        """Return (reset, items appended since the last call).

        ``reset`` is True when the source no longer extends what was seen
        (a different list object, a shorter list, or a replaced tail item);
        the caller must then clear its buckets and fold every item again.
        """
        seen = self.seen
        reset = (
            source is not self.source
            or len(source) < seen
            or (seen and source[seen - 1] is not self.last)
        )
        if reset:
            seen = self.seen = 0
            self.last = None
        self.source = source
        if len(source) == seen:
            return reset, []
        items = source[seen:]
        self.seen = len(source)
        self.last = source[-1]
        return reset, items


class NameView:
    """Membership/length view equivalent to ``[ne.name for ne in named_events]``."""

    __slots__ = ("_names", "_count")

    def __init__(self, names: set[str], count: int) -> None:
        self._names = names
        self._count = count

    def __contains__(self, name: object) -> bool:
        return name in self._names

    def __len__(self) -> int:
        return self._count


class HistoryIndex:
    """Derived per-turn / per-actor / per-name buckets for one world."""

    def __init__(self) -> None:
        self._events = _Cursor()
        self._events_by_turn: dict[int, list] = {}
        self._events_by_actor: dict[str, list] = {}

        self._named = _Cursor()
        self._named_names: set[str] = set()
        self._schism_descriptions: dict[frozenset, list[str]] = {}
        self._hegemony_actors: set[str] = set()
        self._enlightenment_descriptions: list[str] = []

        self._agent = _Cursor()
        self._agent_migrations_by_turn: dict[int, list] = {}
        self._agent_migration_counts: dict[int, int] = {}
        self._agent_switch_counts: dict[int, int] = {}

    # A copied or pickled world must not share (or carry stale) buckets.
    def __copy__(self) -> "HistoryIndex":
        return HistoryIndex()

    def __deepcopy__(self, memo: dict) -> "HistoryIndex":
        return HistoryIndex()

    def __reduce__(self):
        return (HistoryIndex, ())

    # Pydantic compares private attributes in ``WorldState.__eq__``; a cache
    # (present, absent or at a different sync point) never makes worlds unequal.
    def __eq__(self, other: object) -> bool:
        return other is None or isinstance(other, HistoryIndex)

    __hash__ = None  # type: ignore[assignment]

    # --- events_timeline -------------------------------------------------

    def _sync_events(self, world: Any) -> None:
        reset, items = self._events.new_items(world.events_timeline)
        if reset:
            self._events_by_turn = {}
            self._events_by_actor = {}
        by_turn = self._events_by_turn
        by_actor = self._events_by_actor
        for event in items:
            bucket = by_turn.get(event.turn)
            if bucket is None:
                by_turn[event.turn] = [event]
            else:
                bucket.append(event)
            actors = event.actors
            if not actors:
                continue
            for actor in (actors if len(actors) == 1 else dict.fromkeys(actors)):
                bucket = by_actor.get(actor)
                if bucket is None:
                    by_actor[actor] = [event]
                else:
                    bucket.append(event)

    def events_for_turn(self, world: Any, turn: int) -> list:
        """``[e for e in world.events_timeline if e.turn == turn]``."""
        self._sync_events(world)
        return list(self._events_by_turn.get(turn, ()))

    def events_for_actor(self, world: Any, actor: str) -> list:
        """``[e for e in world.events_timeline if actor in e.actors]``."""
        self._sync_events(world)
        return list(self._events_by_actor.get(actor, ()))

    # --- named_events ----------------------------------------------------

    def _sync_named(self, world: Any) -> None:
        reset, items = self._named.new_items(world.named_events)
        if reset:
            self._named_names = set()
            self._schism_descriptions = {}
            self._hegemony_actors = set()
            self._enlightenment_descriptions = []
        for ne in items:
            self._named_names.add(ne.name)
            event_type = ne.event_type
            if event_type == _SCHISM:
                actors = list(dict.fromkeys(ne.actors))
                for i, a in enumerate(actors):
                    for b in actors[i + 1:]:
                        self._schism_descriptions.setdefault(frozenset((a, b)), []).append(ne.description)
            elif event_type == _HEGEMONY:
                self._hegemony_actors.update(ne.actors)
            elif event_type == _ENLIGHTENMENT:
                self._enlightenment_descriptions.append(ne.description)

    def named_event_names(self, world: Any) -> NameView:
        """View equal (for ``in``/``len``) to ``[ne.name for ne in named_events]``."""
        self._sync_named(world)
        return NameView(self._named_names, self._named.seen)

    def schism_fired(self, world: Any, movement_id: str, a: str, b: str) -> bool:
        """Any ``movement_schism`` naming both a and b whose description contains movement_id."""
        self._sync_named(world)
        if a == b:
            # Pairs are only indexed for distinct actors; keep exact semantics.
            return any(
                ne.event_type == _SCHISM and a in ne.actors and movement_id in ne.description
                for ne in world.named_events
            )
        descriptions = self._schism_descriptions.get(frozenset((a, b)))
        return bool(descriptions) and any(movement_id in d for d in descriptions)

    def hegemony_fired(self, world: Any, civ_name: str) -> bool:
        """Any ``cultural_hegemony`` named event listing civ_name as an actor."""
        self._sync_named(world)
        return civ_name in self._hegemony_actors

    def enlightenment_fired(self, world: Any, movement_id: str) -> bool:
        """Any ``universal_enlightenment`` named event whose description contains movement_id."""
        self._sync_named(world)
        return any(movement_id in d for d in self._enlightenment_descriptions)

    # --- agent_events_raw ------------------------------------------------

    def _sync_agent(self, world: Any) -> None:
        reset, items = self._agent.new_items(world.agent_events_raw)
        if reset:
            self._agent_migrations_by_turn = {}
            self._agent_migration_counts = {}
            self._agent_switch_counts = {}
        migrations = self._agent_migrations_by_turn
        migration_counts = self._agent_migration_counts
        switch_counts = self._agent_switch_counts
        for e in items:
            event_type = e.event_type
            if event_type == "migration":
                bucket = migrations.get(e.turn)
                if bucket is None:
                    migrations[e.turn] = [e]
                else:
                    bucket.append(e)
                migration_counts[e.agent_id] = migration_counts.get(e.agent_id, 0) + 1
            elif event_type == "occupation_switch":
                switch_counts[e.agent_id] = switch_counts.get(e.agent_id, 0) + 1

    def agent_migrations_for_turn(self, world: Any, turn: int) -> list:
        """``[e for e in agent_events_raw if e.event_type == "migration" and e.turn == turn]``."""
        self._sync_agent(world)
        return list(self._agent_migrations_by_turn.get(turn, ()))

    def agent_event_counts(self, world: Any, agent_id: int) -> tuple[int, int]:
        """(migration count, occupation_switch count) for agent_id over agent_events_raw."""
        self._sync_agent(world)
        return (
            self._agent_migration_counts.get(agent_id, 0),
            self._agent_switch_counts.get(agent_id, 0),
        )


def history_index(world: Any) -> HistoryIndex:
    """Return the world's cached index, attaching a fresh one when absent.

    Objects that cannot carry the cache (or carry something else under the
    name, such as a mock) get a throwaway index: still exact, just not reused.
    """
    index = getattr(world, "_history_index", None)
    if isinstance(index, HistoryIndex):
        return index
    index = HistoryIndex()
    try:
        world._history_index = index
    except (AttributeError, TypeError, ValueError):
        pass
    return index
