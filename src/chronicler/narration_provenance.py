"""Claim provenance for narration: stable fact ids, what each passage was
given, and the facts each of its sentences cites.

Nothing here is read by the simulation, and nothing here changes a run's
outputs other than the narration's own record (``ChronicleEntry.provenance``).
Every function is a deterministic function of its inputs.

Fact ids
--------
Every fact line a narrator receives carries an id. Ids are scoped to one
bundle and name a record it holds (or a value read from one); none is
invented beside the records' own identities:

======================  ==================================================
``e<i>``                ``events_timeline[i]`` (the run's event timeline;
                        the event's own ``event_id`` is
                        ``events_timeline[i].event_id``)
``n<i>``                ``named_events[i]``
``<chronicler>/e<i>``   the in-world account of event ``e<i>`` by a
                        chronicler (``court:<civ>``, ``temple:<faith>``,
                        ``seat:<n>``); the historiography account id is
                        ``<chronicler>/<event_id>``
``p<agent id>``         a named character (great person) by agent id;
                        ``p:<name>|<born turn>`` (spaces as ``_``) for one
                        without an agent id, the languages layer's key
``art<id>``             ``world_state.artifacts`` by ``artifact_id``
``s<S>.<what>.<key>``   a value of history snapshot ``S`` (the state after
                        turn ``S - 1``): ``ruler.c<i>``, ``war.c<i>-c<j>``,
                        ``movement.<id>``, ``reform.<id>``, ``city.<id>``,
                        ``guild.<id>``, ``burghers.c<i>``, ``seat.<id>``,
                        ``food.r<i>``, ``urban.c<i>``, ``settlement.<id>``
                        (ids are the snapshot rows' own)
``d<S1>-<S2>.<key>``    a change between snapshots ``S1`` and ``S2``:
                        ``c<i>.<stat>`` (a civ's stat) or ``r<i>`` (a
                        region's controller)
``w<a>-<b>``            the events recorded in turns ``a..b`` as counted
                        (a moment's unlisted events); ``w<a>-<b>.mood`` the
                        population mood its agent events give
``o<T>.<what>``         an observation describing completed turn ``T``
                        (``displacement``, ``trade_dependency``; the
                        per-turn narrator's ``civ.c<i>``, ``rival.c<i>``,
                        ``governance``)
``L.<k><ref>``          in-world names of a languages entity: ``c`` civ,
                        ``r`` region, ``s`` settlement, ``f`` faith (their
                        indices / ids), ``p`` person (index in
                        ``languages.persons``)
``k<j>``                the entry's ``causal_links[j]`` (type-pair links of
                        bundles without recorded provenance)
======================  ==================================================

``c<i>`` and ``r<i>`` are indices in ``world.civilizations`` and
``world.regions``; a name the world does not hold is written ``c:<name>``
or ``r:<name>`` (spaces as ``_``, direct callers without a world only).

Provenance of a passage
-----------------------
:class:`FactSheet` collects the facts a narrator was given: an LLM
narrator's prompt lines (tagged ``[id, id]`` at the end), or the records the
mechanical narrator built its sentences from. Each fact keeps its date (the
turn of the record) and whether it was given as retrospective (the prompt's
"AFTER this moment" and "LATER CONSEQUENCES" sections). The sheet also
keeps the names of the characters, civilizations, regions and faiths
(:class:`EntityUniverse`) its facts mention. :func:`parse_citations` reads
an LLM's bracketed citations and removes them from the prose; the
mechanical narrator records each sentence's facts exactly (:class:`Composer`).
The result is :meth:`FactSheet.export`, stored as
``ChronicleEntry.provenance``::

    {"v": 1, "narrator": "mechanical" | "llm", "as_of": T,
     "facts": [id, [id, turn], [id, turn, "r"], ...],  # a bare id is dated T; "r": retrospective
     "names": [...],                                    # entities the facts name
     "spans": [[start, end, [id, ...]], ...]}           # over the entry's narrative

In a bundle file the names are indices into one table, the top-level
``narration_provenance.names`` (:func:`compact_entries`; most passages of a
run name the same peoples and places); :func:`expand_entries` reads them
back. :func:`fact_rows` reads the facts in either form.
``chronicler.narration_audit`` checks it against the bundle.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Iterable, Sequence

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Event, NamedEvent, TurnSnapshot, WorldState

VERSION = 1
RETRO = "r"
#: The bundle's top-level field holding the names table of the entries' provenance.
BUNDLE_FIELD = "narration_provenance"

# ---------------------------------------------------------------------------
# Citation grammar
# ---------------------------------------------------------------------------

#: One fact id (see the module doc).
ID_PATTERN = (
    r"(?:e\d+|e:[\w.:|\-]+|n\d+|k\d+|art\d+|p\d+|p:[\w.:|\-]+"
    r"|w\d+-\d+(?:\.\w+)?|[sd]\d+(?:-\d+)?(?:\.[\w:\-]+)+|o\d+\.[\w.:\-]+|L\.[crsfp]\d+"
    r"|(?:court|temple|seat):\d+/e(?:\d+|:[\w.:|\-]+))"
)
_ID = re.compile(rf"^{ID_PATTERN}$")
_GROUP = rf"\[\s*{ID_PATTERN}(?:\s*[,;]\s*{ID_PATTERN})*\s*\]"
#: A bracketed group of one or more ids: "[e12]", "[e12, n3]", "[e12; s84.ruler.c2]".
CITATION = re.compile(rf"\[\s*({ID_PATTERN}(?:\s*[,;]\s*{ID_PATTERN})*)\s*\]")
#: Adjacent groups ("[e12][n3]", "[e12] [n3]") read as one citation.
CITATION_RUN = re.compile(rf"{_GROUP}(?:[ \t]*{_GROUP})*")
#: An id left in prose outside brackets (a citation the narrator wrote another way).
STRAY_ID = re.compile(r"(?<![\w\[/.:])(?:e\d+|n\d+|art\d+|[sd]\d+(?:-\d+)?\.[a-z]+[\w.:\-]*|L\.[crsfp]\d+)(?![\w])")

#: What the curated prompt asks of an LLM narrator when citations are on.
CITE_INSTRUCTION = (
    "SOURCES: every fact above ends with its id in square brackets, e.g. [e12] or [e12, n3]. "
    "After each sentence, write the ids of the facts it draws on in square brackets, e.g. "
    "\"The walls of the city fell [e12].\" Cite only ids listed above, and name only people, "
    "peoples, places and faiths the facts name. The brackets are removed before the chronicle is shown."
)


def is_fact_id(token: str) -> bool:
    return bool(_ID.match(token))


def split_ids(group: str) -> list[str]:
    return [t for t in re.split(r"\s*[,;]\s*", group.strip()) if t]


def slug(name: str) -> str:
    """A name as an id key (direct callers without a world only)."""
    return re.sub(r"\s+", "_", str(name).strip())


_BOUNDARY = re.compile(r"(?<=[.!?])[\"'”’)]*\s+|\n+")


def _sentence_start(text: str, pos: int, floor: int) -> int:
    """Start of the sentence that ends at (or contains) ``pos``, not before ``floor``."""
    i = pos
    while i > floor and text[i - 1] in ".!?\"'”’) ":
        i -= 1
    start = floor
    for m in _BOUNDARY.finditer(text, floor, i):
        start = m.end()
    return start


def parse_citations(text: str) -> tuple[str, list[list]]:
    """``text`` without its bracketed citations, and one span per citation.

    A span is ``[start, end, [ids]]`` over the returned text: the sentence
    (or the part of it after the previous citation) that the bracket
    follows, with the full stop right after it. Adjacent brackets
    ("[e1][e2]") are one citation. Ids are kept as written, valid or not; the
    audit judges them. Brackets that hold anything but ids ("[turn 4]")
    are left in place.
    """
    out: list[str] = []
    spans: list[list] = []
    last = 0
    length = 0
    floor = 0
    for m in CITATION_RUN.finditer(text):
        chunk = text[last:m.start()]
        after = text[m.end():m.end() + 1]
        # Drop the space before the bracket ("fell [e12]." -> "fell.").
        if chunk.endswith(" ") and (not after or after in ".,;:!?)\"'”’ \n"):
            chunk = chunk.rstrip(" ")
        ids: list[str] = []
        for group in CITATION.finditer(m.group(0)):
            ids.extend(i for i in split_ids(group.group(1)) if i not in ids)
        last = m.end()
        out.append(chunk)
        length += len(chunk)
        start = _sentence_start("".join(out), length, floor)
        while start < length and out and "".join(out)[start] in " \t":
            start += 1
        end = length
        j = m.end()
        while j < len(text) and text[j] in ".!?":  # the full stop after the bracket
            end += 1
            j += 1
        spans.append([start, end, ids])
        floor = end
    out.append(text[last:])
    return "".join(out), spans


# ---------------------------------------------------------------------------
# Fact ids
# ---------------------------------------------------------------------------


def _event_key(ev: Any) -> tuple:
    return (ev.turn, ev.event_type, ev.description, tuple(ev.actors))


def _named_key(ne: Any) -> tuple:
    return (ne.turn, ne.name, ne.event_type, ne.description)


class FactIds:
    """Maps records to their fact ids (see the module doc).

    ``timeline`` is the run's event timeline (the bundle's
    ``events_timeline``), ``named_events`` its ``named_events``; ``world``
    names the civilizations and regions by index; ``names`` (a
    ``languages.NameIndex``) orders the in-world persons.
    """

    def __init__(self, timeline: Sequence["Event"] = (), named_events: Sequence["NamedEvent"] = (),
                 world: "WorldState | None" = None, names: Any = None) -> None:
        self.timeline: list = []
        self.named_events: list = []
        self._ev_obj: dict[int, int] = {}
        self._ev_id: dict[str, int] = {}
        self._ev_key: dict[tuple, int] | None = None
        self._ne_obj: dict[int, int] = {}
        self._ne_key: dict[tuple, int] | None = None
        self.sync(timeline, named_events)
        self._civ: dict[str, int] = {}
        self._region: dict[str, int] = {}
        self.sync_world(world)
        self._person: dict[Any, int] = {}
        if names:
            for k, key in enumerate(getattr(names, "persons", {}) or {}):
                self._person[key] = k

    def sync(self, timeline: Sequence["Event"], named_events: Sequence["NamedEvent"] = ()) -> None:
        """Index what was appended to the (append-only) timeline and named
        events since the last call (the per-turn narrator's running record)."""
        for i in range(len(self.timeline), len(timeline)):
            ev = timeline[i]
            self.timeline.append(ev)
            self._ev_obj[id(ev)] = i
            if ev.event_id and ev.event_id not in self._ev_id:
                self._ev_id[ev.event_id] = i
            if self._ev_key is not None:
                self._ev_key.setdefault(_event_key(ev), i)
        for i in range(len(self.named_events), len(named_events)):
            ne = named_events[i]
            self.named_events.append(ne)
            self._ne_obj[id(ne)] = i
            if self._ne_key is not None:
                self._ne_key.setdefault(_named_key(ne), i)

    def sync_world(self, world: "WorldState | None") -> None:
        """Civilization and region indices (civs founded later are added)."""
        if world is None:
            return
        for i, civ in enumerate(world.civilizations):
            self._civ.setdefault(civ.name, i)
        for i, region in enumerate(world.regions):
            self._region.setdefault(region.name, i)

    # --- records -------------------------------------------------------------

    def event_index(self, ev: "Event") -> int | None:
        i = self._ev_obj.get(id(ev))
        if i is not None and self.timeline[i] is ev:
            return i
        if ev.event_id:
            i = self._ev_id.get(ev.event_id)
            if i is not None:
                return i
        if self._ev_key is None:
            self._ev_key = {}
            for j, other in enumerate(self.timeline):
                self._ev_key.setdefault(_event_key(other), j)
        return self._ev_key.get(_event_key(ev))

    def event(self, ev: "Event") -> str:
        i = self.event_index(ev)
        if i is not None:
            return f"e{i}"
        return f"e:{slug(ev.event_id or f'{ev.turn}:{ev.event_type}')}"

    def event_by_id(self, event_id: str | None) -> str | None:
        if not event_id:
            return None
        i = self._ev_id.get(event_id)
        return f"e{i}" if i is not None else f"e:{slug(event_id)}"

    def timeline_event(self, event_id: str | None) -> "Event | None":
        i = self._ev_id.get(event_id) if event_id else None
        return self.timeline[i] if i is not None else None

    def named(self, ne: "NamedEvent") -> str | None:
        i = self._ne_obj.get(id(ne))
        if i is None or self.named_events[i] is not ne:
            if self._ne_key is None:
                self._ne_key = {}
                for j, other in enumerate(self.named_events):
                    self._ne_key.setdefault(_named_key(other), j)
            i = self._ne_key.get(_named_key(ne))
        return f"n{i}" if i is not None else None

    def account(self, row: dict) -> str:
        eid = self.event_by_id(row.get("event_id")) or "e:?"
        return f"{row.get('chronicler')}/{eid}"

    def character(self, agent_id: int | None, name: str, born_turn: int | None = None) -> str:
        if agent_id is not None:
            return f"p{agent_id}"
        return f"p:{slug(name)}|{born_turn if born_turn is not None else '?'}"

    def artifact(self, artifact_id: int) -> str:
        return f"art{artifact_id}"

    def link(self, j: int) -> str:
        return f"k{j}"

    # --- entities ------------------------------------------------------------

    def civ(self, name: str) -> str:
        i = self._civ.get(name)
        return f"c{i}" if i is not None else f"c:{slug(name)}"

    def region(self, name: str) -> str:
        i = self._region.get(name)
        return f"r{i}" if i is not None else f"r:{slug(name)}"

    def snapshot(self, snapshot_turn: int, kind: str, key: Any = None) -> str:
        """``s<S>.<kind>[.<key>]``; a civ or region key is ``("civ", name)`` / ``("region", name)``."""
        return f"s{snapshot_turn}.{kind}" + (f".{self._key(key)}" if key is not None else "")

    def change(self, from_turn: int, to_turn: int, key: Any, attr: str | None = None) -> str:
        """``d<S1>-<S2>.<key>[.<attr>]``: a civ's stat (``("civ", name)``, the
        stat) or a region's controller (``("region", name)``)."""
        return f"d{from_turn}-{to_turn}.{self._key(key)}" + (f".{attr}" if attr else "")

    def window(self, start: int, end: int, what: str | None = None) -> str:
        return f"w{start}-{end}" + (f".{what}" if what else "")

    def observation(self, turn: int, what: str, key: Any = None) -> str:
        return f"o{turn}.{what}" + (f".{self._key(key)}" if key is not None else "")

    def names_entity(self, kind: str, ref: Any) -> str | None:
        code = {"civ": "c", "region": "r", "settlement": "s", "faith": "f"}.get(kind)
        if code is not None and isinstance(ref, int):
            return f"L.{code}{ref}"
        if kind == "person":
            k = self._person.get(ref)
            return f"L.p{k}" if k is not None else None
        return None

    def _key(self, key: Any) -> str:
        """A civ (``("civ", name)``) or region (``("region", name)``) as its
        index, a tuple of keys joined by ``-`` (a pair of civs), else the
        row's own id."""
        if isinstance(key, tuple) and len(key) == 2 and key[0] in ("civ", "region"):
            return self.civ(key[1]) if key[0] == "civ" else self.region(key[1])
        if isinstance(key, tuple):
            return "-".join(self._key(k) for k in key)
        return slug(str(key))


# ---------------------------------------------------------------------------
# Named entities
# ---------------------------------------------------------------------------

#: Leading titles of rulers and great persons ("Consul Ulveth" -> "Ulveth").
_MIN_FORM = 4


def _stem(name: str) -> str | None:
    try:
        from chronicler.languages import _title_and_stem
    except Exception:  # pragma: no cover
        return None
    title, stem, _tail = _title_and_stem(name)
    if title is None or len(stem) < _MIN_FORM or not stem[:1].isupper():
        return None
    return stem


def _civ_forms(name: str) -> list[str]:
    from chronicler.historiography import short_name
    forms = [name]
    short = short_name(name)
    if short != name and len(short) >= _MIN_FORM:
        forms.append(short)
    return forms


def _faith_forms(name: str) -> list[str]:
    from chronicler.historiography import faith_display
    forms = [name]
    shown = faith_display(name)
    if shown.startswith("the "):
        shown = shown[4:]
    if shown != name:
        forms.append(shown)
    return forms


def _person_forms(name: str) -> list[str]:
    forms = [name]
    stem = _stem(name)
    if stem and stem != name:
        forms.append(stem)
    return forms


_WORD = re.compile(r"\w+")
_WORD_CHAR = re.compile(r"\w")


class EntityUniverse:
    """The characters, civilizations, regions and faiths a run names.

    ``find`` gives the canonical names of the entities a text mentions,
    ``mentions`` where. A form ("Kethani", "Ulveth") may stand for more than
    one entity; matching is case-sensitive and scans left to right: at each
    word start the longest form that ends on a word boundary wins (as a
    ``(?<!\\w)(?:longest|...|shortest)(?!\\w)`` alternation would, without
    compiling one per world). Forms begin with a word character.
    """

    def __init__(self, entries: Iterable[tuple[str, str, Sequence[str]]] = ()) -> None:
        self.kind: dict[str, str] = {}
        self.forms: dict[str, list[str]] = {}
        for kind, canonical, forms in entries:
            if not canonical or len(canonical) < 3:
                continue
            self.kind.setdefault(canonical, kind)
            for form in forms:
                if form and len(form) >= 3:
                    owners = self.forms.setdefault(form, [])
                    if canonical not in owners:
                        owners.append(canonical)
        # Forms by their first word, longest first.
        self._by_first: dict[str, list[str]] = {}
        for form in sorted(self.forms, key=lambda s: (-len(s), s)):
            m = _WORD.match(form)
            if m is not None:
                self._by_first.setdefault(m.group(0), []).append(form)

    def __bool__(self) -> bool:
        return bool(self._by_first)

    def mentions(self, text: str) -> list[tuple[int, int, list[str]]]:
        """``(start, end, canonical names)`` of each form in ``text``."""
        if not self._by_first or not text:
            return []
        out: list[tuple[int, int, list[str]]] = []
        pos = 0
        for m in _WORD.finditer(text):
            start = m.start()
            if start < pos:
                continue
            for form in self._by_first.get(m.group(0), ()):
                end = start + len(form)
                if text.startswith(form, start) and not _WORD_CHAR.match(text, end):
                    out.append((start, end, self.forms[form]))
                    pos = end
                    break
        return out

    def find(self, text: str) -> set[str]:
        return {name for _s, _e, names in self.mentions(text) for name in names}

    # --- builders --------------------------------------------------------------

    @classmethod
    def from_parts(cls, civs: Iterable[str] = (), regions: Iterable[str] = (), faiths: Iterable[str] = (),
                   persons: Iterable[str] = ()) -> "EntityUniverse":
        entries: list[tuple[str, str, list[str]]] = []
        for name in _unique(civs):
            entries.append(("civ", name, _civ_forms(name)))
        for name in _unique(regions):
            entries.append(("region", name, [name]))
        for name in _unique(faiths):
            entries.append(("faith", name, _faith_forms(name)))
        for name in _unique(persons):
            entries.append(("character", name, _person_forms(name)))
        return cls(entries)

    @classmethod
    def from_world(cls, world: "WorldState | None",
                   history: Sequence["TurnSnapshot"] = ()) -> "EntityUniverse":
        """From a world (its civs, regions, faiths, great persons and rulers)
        and its history (every ruler and civ a snapshot names)."""
        civs: list[str] = []
        regions: list[str] = []
        faiths: list[str] = []
        persons: list[str] = []
        if world is not None:
            civs = [c.name for c in world.civilizations]
            regions = [r.name for r in world.regions]
            faiths = [b.name for b in (getattr(world, "belief_registry", None) or [])]
            for c in world.civilizations:
                persons.append(c.leader.name)
                persons.extend(gp.name for gp in c.great_persons)
            persons.extend(gp.name for gp in getattr(world, "retired_persons", None) or [])
        for snap in history:
            for name, cs in snap.civ_stats.items():
                civs.append(name)
                if cs.leader_name:
                    persons.append(cs.leader_name)
            regions.extend(snap.region_control.keys())
        return cls.from_parts(civs, regions, faiths, persons)

    @classmethod
    def from_bundle(cls, bundle: dict) -> "EntityUniverse":
        """The same universe from a (decoded, restored) bundle dict."""
        world = bundle.get("world_state") or {}
        civs = [c.get("name") for c in world.get("civilizations", [])]
        regions = [r.get("name") for r in world.get("regions", [])]
        faiths = [b.get("name") for b in world.get("belief_registry", []) or []]
        persons: list[str] = []
        for c in world.get("civilizations", []):
            leader = c.get("leader") or {}
            persons.append(leader.get("name"))
            persons.extend(gp.get("name") for gp in c.get("great_persons", []) or [])
        persons.extend(gp.get("name") for gp in world.get("retired_persons", []) or [])
        for snap in bundle.get("history", []) or []:
            for name, cs in (snap.get("civ_stats") or {}).items():
                civs.append(name)
                if cs.get("leader_name"):
                    persons.append(cs.get("leader_name"))
            regions.extend((snap.get("region_control") or {}).keys())
        return cls.from_parts(civs, regions, faiths, persons)


def _unique(names: Iterable[str | None]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


# ---------------------------------------------------------------------------
# Fact texts (what a record says, for the names it mentions)
# ---------------------------------------------------------------------------


def event_fact_text(ev: "Event", faiths: dict[int, str] | None = None) -> str:
    """The names-bearing text of an event's record: its narrator line,
    description, actors, civs and places."""
    from chronicler.narration_context import event_text
    parts = [event_text(ev, faiths), ev.description or "", *ev.actors, *ev.civs,
             ev.region or "", ev.shock_region or ""]
    return " | ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Fact sheets
# ---------------------------------------------------------------------------


class FactSheet:
    """The facts one passage's narrator was given (see the module doc).

    ``as_of`` is the last completed turn the passage narrates; ``tags``
    False registers facts without tagging prompt lines.
    """

    def __init__(self, ids: FactIds, universe: EntityUniverse | None, as_of: int,
                 tags: bool = True) -> None:
        self.ids = ids
        self.universe = universe
        self.as_of = as_of
        self.tags = tags
        self._facts: dict[str, list] = {}  # id -> [turn, retrospective]
        self._order: list[str] = []
        self._names: set[str] = set()

    def __contains__(self, fid: str) -> bool:
        return fid in self._facts

    @property
    def fact_ids(self) -> list[str]:
        return list(self._order)

    def fact(self, fid: str | None, turn: int | None, text: str = "", retro: bool = False) -> str | None:
        """Register a fact (dated ``turn``) and the names ``text`` mentions."""
        if not fid:
            return None
        row = self._facts.get(fid)
        if row is None:
            self._facts[fid] = [turn, retro]
            self._order.append(fid)
        else:
            if turn is not None and (row[0] is None or turn > row[0]):
                row[0] = turn
            row[1] = row[1] and retro
        if text and self.universe:
            self._names.update(self.universe.find(text))
        return fid

    def names_in(self, text: str) -> None:
        if text and self.universe:
            self._names.update(self.universe.find(text))

    def line(self, text: str, facts: Iterable[tuple[str | None, int | None] | None], retro: bool = False,
             shown: Sequence[str | None] | None = None) -> str:
        """A prompt line: its facts registered (the names from the line's
        text) and the line tagged with the ids in ``shown`` (default: all)."""
        ids = []
        for item in facts:
            if not item:
                continue
            fid, turn = item
            if self.fact(fid, turn, "", retro) is not None and fid not in ids:
                ids.append(fid)
        self.names_in(text)
        shown_ids = [f for f in (shown if shown is not None else ids) if f]
        if not self.tags or not shown_ids:
            return text
        return f"{text} [{', '.join(dict.fromkeys(shown_ids))}]"

    def export(self, narrator: str, spans: Sequence[Sequence] = ()) -> dict:
        facts: list = []
        for fid in self._order:
            turn, retro = self._facts[fid]
            if retro:
                facts.append([fid, turn, RETRO])
            elif turn == self.as_of:
                facts.append(fid)  # dated the passage's own turn
            else:
                facts.append([fid, turn])
        return {
            "v": VERSION,
            "narrator": narrator,
            "as_of": self.as_of,
            "facts": facts,
            "names": sorted(self._names),
            "spans": [[int(s), int(e), list(ids)] for s, e, ids in spans],
        }


class Composer:
    """Mechanical prose built from facts: each segment's facts are its span."""

    def __init__(self, sheet: FactSheet) -> None:
        self.sheet = sheet
        self._parts: list[str] = []
        self._length = 0
        self.spans: list[list] = []
        self.accounts: list[str] = []  # historiography account ids told (ChronicleEntry.accounts)

    def add(self, text: str, facts: Iterable[tuple[str | None, int | None, str]] = (),
            sep: str = " ") -> None:
        """Append ``text`` (after ``sep`` unless it is the first part) as one
        span citing ``facts`` (``(id, turn, record text)``)."""
        if self._parts and sep:
            self._parts.append(sep)
            self._length += len(sep)
        start = self._length
        self._parts.append(text)
        self._length += len(text)
        ids = []
        for fid, turn, record_text in facts:
            if self.sheet.fact(fid, turn, record_text) is not None and fid not in ids:
                ids.append(fid)
        self.spans.append([start, self._length, ids])

    @property
    def text(self) -> str:
        return "".join(self._parts)

    def export(self) -> dict:
        return self.sheet.export("mechanical", self.spans)


# ---------------------------------------------------------------------------
# Reading provenance; its bundle form
# ---------------------------------------------------------------------------


def fact_rows(provenance: dict) -> list[tuple[str, int | None, bool]]:
    """``(id, turn, retrospective)`` of each fact given (a bare id is dated ``as_of``)."""
    as_of = provenance.get("as_of")
    out = []
    for row in provenance.get("facts") or []:
        if isinstance(row, str):
            out.append((row, as_of, False))
        else:
            out.append((row[0], row[1] if len(row) > 1 else None, len(row) > 2 and row[2] == RETRO))
    return out


def compact_entries(entries: Sequence[Any]) -> dict | None:
    """The bundle form of the entries' provenance (in place): each entry's
    names become indices into one table, returned as the bundle's
    ``narration_provenance`` field (None when no entry has provenance)."""
    table: list[str] = []
    index: dict[str, int] = {}
    found = False
    for entry in entries:
        prov = entry.get("provenance") if isinstance(entry, dict) else None
        if not prov:
            continue
        found = True
        ids = []
        for name in prov.get("names") or []:
            if not isinstance(name, str):
                raise ValueError("provenance names are already compact")
            if name not in index:
                index[name] = len(table)
                table.append(name)
            ids.append(index[name])
        prov["names"] = ids
    return {"version": VERSION, "names": table} if found else None


def expand_entries(bundle: dict) -> list[dict]:
    """The bundle's chronicle entries with their provenance names read back
    from the table (the entries are copied where changed)."""
    entries = bundle.get("chronicle_entries") or []
    if isinstance(entries, dict):
        return []
    field = bundle.get(BUNDLE_FIELD)
    table = field.get("names") if isinstance(field, dict) else None
    out = []
    for entry in entries:
        prov = entry.get("provenance") if isinstance(entry, dict) else None
        names = (prov or {}).get("names") or []
        if prov and table is not None and any(isinstance(n, int) for n in names):
            prov = {**prov, "names": [table[n] if isinstance(n, int) and 0 <= n < len(table) else n
                                      for n in names]}
            entry = {**entry, "provenance": prov}
        out.append(entry)
    return out
