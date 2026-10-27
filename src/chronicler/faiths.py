"""Permanent faith identity (docs/integration/permanent-faiths.md).

A faith's native id (``Belief.faith_id``; the agents' ``belief`` byte; the
regions' ``majority_belief``, ``conversion_target_signal`` and
``persecuting_faith``; the civs' ``civ_majority_faith``; a temple's
``faith_id``) is a *slot*. At most ``religion.MAX_FAITHS`` slots exist, and
when the registry is full a sect takes the slot of a faith no one holds any
more (``agent_movements._schism``), so one slot can name two unrelated
churches over a run.

A faith's *permanent id* is its index in ``WorldState.faiths``
(:class:`~chronicler.models.FaithRecord`): assigned at its founding, never
reused, with its name, founding turn, founding civilization (and, for a
sect, its movement and leader), the faith it broke from and the slot it
holds or held. The slot -> permanent mapping changes only when a slot is
recycled (:func:`release` then :func:`found`).

Faiths are founded in slot order until the registry first fills, so every
faith founded before the first recycle has permanent id == slot, and a run
without a recycle writes the same faith numbers as before. Records that
outlive a turn and name a particular faith carry the permanent id:
movements (``faith``, ``schism_from``, ``schism_to``, a schism's
``successor``), lasting reforms (``faith``), great-person and ruler
conversion objectives (``conversion_faith_id``), seats of learning
(``faith``), temple chroniclers (``temple:<id>``), the languages' faith
words, and the ``Temple of faith <id>`` event descriptions. Per-turn live
fields and the native runtime keep slots; :func:`uid_of` and
:func:`slot_of` convert at the boundary.

Older runs (saves, checkpoints and bundles written before this table) are
read through :func:`ensure` / :func:`upgrade_bundle`: the table is rebuilt
from the final registry and the run's ``Schism`` events, live faiths keep
permanent id == slot (so every live reference stays exact and a resumed run
behaves as before), faiths whose slot was taken get new ids after them, and
dated historical references to a recycled slot are mapped to the faith
holding it then. A slot whose earlier holders cannot be determined marks its
faith ``legacy="unresolved"``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Belief, FaithRecord, WorldState

#: The "no faith" sentinel shared with the native runtime and the records.
NO_FAITH = 0xFF

#: ``FaithRecord.origin`` values.
FOUNDING, SCHISM, SECT, UNRECORDED, RESERVED = "founding", "schism", "sect", "unrecorded", "reserved"
#: ``FaithRecord.legacy`` values.
RECONSTRUCTED, UNRESOLVED = "reconstructed", "unresolved"


# ---------------------------------------------------------------------------
# The table and the slot <-> permanent mapping
# ---------------------------------------------------------------------------

def table(world) -> list | None:
    """``world.faiths`` when the world carries a table (None for mocks and
    worlds without one, whose faith numbers are slots)."""
    faiths = getattr(world, "faiths", None)
    return faiths if isinstance(faiths, list) and faiths else None


def _holds(rec) -> bool:
    return rec.released_turn is None and rec.origin != RESERVED


def uid_of(world, slot: Any) -> int | None:
    """Permanent id of the faith holding ``slot`` now (None for the no-faith
    sentinel or an empty slot). Without a table the slot is returned."""
    if slot is None or not isinstance(slot, int) or slot < 0 or slot == NO_FAITH:
        return None
    faiths = table(world)
    if faiths is None:
        return slot
    for k in range(len(faiths) - 1, -1, -1):
        rec = faiths[k]
        if rec.slot == slot and _holds(rec):
            return k
    return None


def slot_of(world, uid: Any) -> int | None:
    """The slot faith ``uid`` holds now, or None (no faith, an unknown id, or
    a faith whose slot passed to another). Without a table the id is
    returned."""
    if uid is None or not isinstance(uid, int) or uid < 0 or uid == NO_FAITH:
        return None
    faiths = table(world)
    if faiths is None:
        return uid
    if uid >= len(faiths):
        return None
    rec = faiths[uid]
    return rec.slot if _holds(rec) else None


def same_faith(world, uid: Any, slot: Any) -> bool:
    """Whether permanent id ``uid`` is the faith now holding ``slot``."""
    return uid is not None and uid != NO_FAITH and uid_of(world, slot) == uid


def record(world, uid: Any):
    """The faith's record, or None."""
    faiths = table(world)
    if faiths is None or not isinstance(uid, int) or not 0 <= uid < len(faiths):
        return None
    return faiths[uid]


def name_of(world, uid: Any) -> str | None:
    """The faith's name, whether or not it still holds a slot. Without a
    table the registry's faith of that slot."""
    faiths = table(world)
    if faiths is None:
        for b in getattr(world, "belief_registry", None) or []:
            if b.faith_id == uid:
                return b.name
        return None
    rec = record(world, uid)
    return rec.name if rec is not None and rec.origin != RESERVED else None


def names(world) -> dict[int, str]:
    """Permanent id -> name of every faith the run founded (without a table:
    slot -> name of the registry)."""
    faiths = table(world)
    if faiths is None:
        return {b.faith_id: b.name for b in getattr(world, "belief_registry", None) or []}
    return {k: rec.name for k, rec in enumerate(faiths) if rec.origin != RESERVED}


def label(rec) -> str:
    """How a faith is shown where two may share a name: its name and
    founding turn (``Faith of X (Reformed), founded turn 120``)."""
    if rec.founded_turn is None:
        return rec.name
    return f"{rec.name}, founded turn {rec.founded_turn}"


# ---------------------------------------------------------------------------
# Founding and release
# ---------------------------------------------------------------------------

def _new_record(belief: "Belief", **fields):
    from chronicler.models import FaithRecord
    return FaithRecord(name=belief.name, civ=belief.civ_origin, slot=belief.faith_id,
                       doctrines=list(belief.doctrines), **fields)


def _append(world, rec) -> int:
    faiths = world.faiths
    if len(faiths) == NO_FAITH:
        # Keep the sentinel out of the id space: id 255 is a reserved,
        # empty record (reached only after ~240 recycles in one world).
        from chronicler.models import FaithRecord
        faiths.append(FaithRecord(name="", founded_turn=None, origin=RESERVED, slot=NO_FAITH,
                                  released_turn=getattr(world, "turn", 0)))
    faiths.append(rec)
    return len(faiths) - 1


def found_initial(world) -> None:
    """World generation: one record per founding faith, in registry order
    (permanent id == slot == the founding civ's index)."""
    world.faiths = [_new_record(b, founded_turn=world.turn, origin=FOUNDING)
                    for b in world.belief_registry]


def found(world, belief: "Belief", *, origin: str, parent: int | None = None,
          region: int | None = None, movement: int | None = None,
          leader: str | None = None) -> int:
    """Record a faith just added to the registry (``religion.fire_schism``);
    returns its permanent id. ``parent`` is the permanent id it broke from."""
    faiths = getattr(world, "faiths", None)
    if not isinstance(faiths, list):
        return belief.faith_id  # a stand-in world without a table
    fields = dict(founded_turn=world.turn, origin=origin, parent=parent, region=region,
                  movement=movement, leader=leader or None)
    if not faiths:
        # A world built without a table: record the registry as it stands
        # (this faith included), then date this one.
        ensure(world)
        uid = uid_of(world, belief.faith_id)
        rec = record(world, uid)
        if rec is not None:
            for key, value in fields.items():
                setattr(rec, key, value)
            rec.legacy = None
            return uid
    return _append(world, _new_record(belief, **fields))


def release(world, slot: int) -> int | None:
    """The faith holding ``slot`` gives it up this turn (its place is taken
    by a new faith). Returns its permanent id."""
    uid = uid_of(world, slot)
    rec = record(world, uid)
    if rec is not None:
        rec.released_turn = world.turn
    return uid


# ---------------------------------------------------------------------------
# Historical resolution (a slot named at a turn)
# ---------------------------------------------------------------------------

def holder_at(faiths: list, slot: Any, turn: Any) -> int | None:
    """Permanent id of the faith holding ``slot`` at the end of ``turn``
    (founded by then, not yet released); None when no recorded faith did.

    A record written in turn T (Phase 10 or later) or a history snapshot of
    turn T + 1 reads the end of T. An agent event of turn T (the agent tick
    runs before Phase 10) reads the end of T - 1.
    """
    if slot is None or not isinstance(slot, int) or slot < 0 or slot == NO_FAITH:
        return None
    found_id = None
    for k, rec in enumerate(faiths):
        rec_slot = rec["slot"] if isinstance(rec, dict) else rec.slot
        if rec_slot != slot:
            continue
        founded = rec.get("founded_turn") if isinstance(rec, dict) else rec.founded_turn
        released = rec.get("released_turn") if isinstance(rec, dict) else rec.released_turn
        if turn is not None and founded is not None and founded > turn:
            continue
        if released is not None and (turn is None or released <= turn):
            continue
        found_id = k
    return found_id


# ---------------------------------------------------------------------------
# Older runs: rebuilding the table
# ---------------------------------------------------------------------------

_SECT_FOUNDED = "' is founded"
_SECT_IN_PLACE = "' is founded in place of the vanished '"
_SECT_BREAKS = " breaks away from the "
_RELIGION_SPLITS = "' splits from the majority faith in "
_RELIGION_FRACTURES = "A schism fractures "


def parse_schism(description: str) -> dict | None:
    """The faiths a ``Schism`` event names: ``new``, ``parent`` (name or
    None), ``vanished`` (the faith whose slot it took, or None), ``region``
    (name), ``movement`` (a sect's movement name, or None) and ``kind``
    (``schism`` or ``sect``); None if unrecognised. The two wordings are
    ``religion.detect_schisms``'s and ``agent_movements._schism``'s."""
    desc = description or ""
    if desc.startswith(_RELIGION_FRACTURES) and _RELIGION_SPLITS in desc and ": '" in desc:
        new, rest = desc.split(": '", 1)[1].split(_RELIGION_SPLITS, 1)
        region = rest.rsplit(" (minority_ratio=", 1)[0]
        return {"new": new, "parent": None, "vanished": None, "region": region, "movement": None,
                "kind": SCHISM}
    if _SECT_BREAKS not in desc or ": '" not in desc:
        return None
    vanished = None
    if desc.endswith("'") and _SECT_IN_PLACE in desc:
        head, vanished = desc[:-1].rsplit(_SECT_IN_PLACE, 1)
    elif desc.endswith(_SECT_FOUNDED):
        head = desc[:-len(_SECT_FOUNDED)]
    else:
        return None
    pre, new = head.rsplit(": '", 1)
    movement, after = pre.split(_SECT_BREAKS, 1)
    parent, _, region = after.rpartition(" in ")
    return {"new": new, "parent": parent or None, "vanished": vanished, "region": region or None,
            "movement": movement or None, "kind": SECT}


def _founding_name(name: str | None, slot: int, civ_names: list[str] | None) -> bool:
    """Whether a faith reads as a founding faith of world generation."""
    if not name:
        return False
    if civ_names:
        return 0 <= slot < len(civ_names) and name == f"Faith of {civ_names[slot]}"
    return " (Reformed" not in name


def reconstruct(registry: Iterable, events: Iterable, civ_names: list[str] | None = None,
                region_names: list[str] | None = None,
                movement_names: list[str] | None = None) -> list[dict]:
    """Rebuild a run's faith table from its final registry and ``Schism``
    events (the records of a run written before the table existed).

    ``registry``: dicts or ``Belief``s (``faith_id``, ``name``,
    ``civ_origin``, ``doctrines``). ``events``: dicts or ``Event``s (``turn``,
    ``event_type``, ``description``), in timeline order. Returns record
    dicts (``FaithRecord`` fields), index = permanent id: the live faiths
    first with id == slot, then the faiths whose slot was taken, in the
    order they gave it up. A faith the events do not account for, or a slot
    whose history is inconsistent, is ``legacy="unresolved"``.
    """
    def get(obj, key, default=None):
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

    civ_index = {n: i for i, n in enumerate(civ_names or [])}
    region_index = {n: i for i, n in enumerate(region_names or [])}
    movement_index: dict[str, int] = {}
    for i, n in enumerate(movement_names or []):
        movement_index[n] = -1 if n in movement_index else i  # a repeated name is not resolved
    live: list[dict] = []
    for b in registry:
        live.append({"name": get(b, "name"), "founded_turn": None, "civ": get(b, "civ_origin", -1),
                     "origin": FOUNDING, "slot": get(b, "faith_id"),
                     "doctrines": list(get(b, "doctrines") or []), "legacy": RECONSTRUCTED})
    live.sort(key=lambda r: r["slot"])
    by_slot = {r["slot"]: r for r in live}
    if len(by_slot) != len(live):  # two registry entries in one slot: nothing can be trusted
        for r in live:
            r["legacy"] = UNRESOLVED
        return live
    # Backward over the schisms: who held each slot just after the event.
    holder: dict[int, dict] = dict(by_slot)
    released: list[dict] = []
    all_unresolved = False
    schisms = [e for e in events if get(e, "event_type") == "Schism"]
    for ev in reversed(schisms):
        parsed = parse_schism(get(ev, "description", ""))
        turn = get(ev, "turn")
        if parsed is None:
            all_unresolved = True
            continue
        slots = [s for s, r in holder.items() if r["name"] == parsed["new"] and r["founded_turn"] is None
                 and r["origin"] == FOUNDING]
        if len(slots) != 1:
            all_unresolved = True
            continue
        s = slots[0]
        rec = holder[s]
        rec["founded_turn"] = turn
        rec["origin"] = parsed["kind"]
        rec["_parent_name"] = parsed["parent"]
        if parsed["region"] in region_index:
            rec["region"] = region_index[parsed["region"]]
        if parsed["kind"] == SCHISM:
            fractures = get(ev, "description", "")[len(_RELIGION_FRACTURES):].split(": '", 1)[0]
            if fractures in civ_index:
                rec["civ"] = civ_index[fractures]
        elif movement_index.get(parsed["movement"], -1) >= 0:
            rec["movement"] = movement_index[parsed["movement"]]
        if parsed["vanished"] is not None:
            old = {"name": parsed["vanished"], "founded_turn": None, "civ": -1, "origin": FOUNDING,
                   "slot": s, "released_turn": turn, "legacy": RECONSTRUCTED}
            released.append(old)
            holder[s] = old
        else:
            del holder[s]
    # What remains held each slot from the start: the founding faiths
    # (``religion.generate_faiths``: slot = civ index, "Faith of <civ>"). A
    # remaining faith that is not one was founded by an event the record
    # does not hold (a trimmed timeline): its founding and the earlier
    # holders of its slot are not determined.
    for s, rec in holder.items():
        if rec["founded_turn"] is None and rec["origin"] == FOUNDING:
            if _founding_name(rec["name"], s, civ_names):
                rec["founded_turn"] = 0
                if rec["civ"] is None or rec["civ"] < 0:
                    rec["civ"] = s  # world generation: one founding faith per civ, in civ order
            else:
                rec["origin"] = UNRECORDED
                rec["legacy"] = UNRESOLVED
    released.reverse()  # in the order the slots were given up
    out = live + released
    # Parents by name among the faiths holding a slot when the child was founded.
    for rec in out:
        name = rec.pop("_parent_name", None)
        if rec["origin"] == SCHISM and name is None and rec["name"].endswith(")") and " (Reformed" in rec["name"]:
            name = rec["name"].rsplit(" (Reformed", 1)[0]
        if name is None:
            continue
        t = rec["founded_turn"]
        cands = [k for k, other in enumerate(out) if other["name"] == name and other is not rec
                 and (other["founded_turn"] is None or t is None or other["founded_turn"] <= t)
                 and (other.get("released_turn") is None or t is None or other["released_turn"] > t)]
        if len(cands) == 1:
            rec["parent"] = cands[0]
    if all_unresolved:
        for rec in out:
            if rec in live and rec.get("released_turn") is None:
                rec["legacy"] = UNRESOLVED
    return out


def _records_from_dicts(rows: list[dict]):
    from chronicler.models import FaithRecord
    return [FaithRecord(**{k: v for k, v in row.items() if v is not None and v != []}) for row in rows]


def resolver(faiths: list) -> "callable":
    """``resolve(slot, turn) -> permanent id`` over a reconstructed table: the
    faith holding the slot at the end of ``turn``; for a slot without such a
    record (an unresolved slot), the faith holding it at the end of the
    run, whose record says the reference may be older."""
    def resolve(slot, turn):
        if slot is None or not isinstance(slot, int) or slot < 0 or slot == NO_FAITH:
            return slot
        k = holder_at(faiths, slot, turn)
        if k is None:
            k = holder_at(faiths, slot, None)
        return slot if k is None else k
    return resolve


def needs_mapping(faiths: list) -> bool:
    """Whether a reconstructed table maps any slot reference to another id
    (some slot was recycled): otherwise every reference keeps its value."""
    for k, rec in enumerate(faiths):
        slot = rec["slot"] if isinstance(rec, dict) else rec.slot
        if slot != k:
            return True
    return False


# ---------------------------------------------------------------------------
# Older runs: worlds (saves and checkpoints)
# ---------------------------------------------------------------------------

def ensure(world) -> None:
    """Give ``world`` its faith table, keeping it in step with the registry.

    A world without one (saved before the table existed, or built by hand)
    gets one rebuilt from its record (:func:`reconstruct`) and its dated
    references to recycled slots mapped (:func:`upgrade_world`). A world with
    one gets a record for any registry faith founded outside
    :func:`found` (origin ``unrecorded``). A no-op in a run that records its
    faiths, as every simulated run does.
    """
    registry = getattr(world, "belief_registry", None)
    if not isinstance(registry, list) or not registry:
        return
    if not isinstance(getattr(world, "faiths", None), list):
        # A pickled world from before the field existed.
        world.__dict__["faiths"] = []
    if not world.faiths:
        am = getattr(world, "agent_movements", None)
        rows = reconstruct(registry, world.events_timeline,
                           [c.name for c in world.civilizations], [r.name for r in world.regions],
                           [m.name for m in (am.movements if hasattr(am, "movements") else ())])
        world.faiths = _records_from_dicts(rows)
        if needs_mapping(rows):
            upgrade_world(world, resolver(rows))
        return
    for b in registry:
        uid = uid_of(world, b.faith_id)
        rec = record(world, uid)
        if rec is not None and rec.name == b.name:
            continue
        if rec is not None:
            rec.released_turn = world.turn
        _append(world, _new_record(b, founded_turn=world.turn, origin=UNRECORDED))


def upgrade_world(world, resolve) -> int:
    """Map an older world's dated slot references to permanent ids (only
    references to a slot that was recycled change). Returns the number of
    values changed."""
    changed = 0

    def put(obj, attr, slot, turn):
        nonlocal changed
        new = resolve(slot, turn)
        if new != slot:
            setattr(obj, attr, new)
            changed += 1

    state = getattr(world, "agent_movements", None)
    if state is not None and hasattr(state, "movements"):
        from chronicler.agent_movements_state import SCHISM as END_SCHISM, TOLERATION
        for m in state.movements:
            put(m, "faith", m.faith, m.ended_turn if m.ended_turn is not None else world.turn)
            if m.schism_turn is not None:
                put(m, "schism_from", m.schism_from, m.schism_turn)
                put(m, "schism_to", m.schism_to, m.schism_turn)
                if m.end == END_SCHISM:
                    put(m, "successor", m.successor, m.schism_turn)
        for r in state.reforms:
            if r.kind == TOLERATION:
                put(r, "faith", r.faith, r.enacted_turn)
    gpa = getattr(world, "gp_agendas", None)
    for rec in (gpa.records.values() if gpa is not None and hasattr(gpa, "records") else ()):
        a = rec.agenda
        if a is not None and a.conversion_faith_id is not None:
            put(a, "conversion_faith_id", a.conversion_faith_id, a.generated_turn)
    for civ in world.civilizations:
        gov = getattr(civ, "governance", None)
        for a in (gov.ambitions if gov is not None else ()):
            if a.conversion_faith_id is not None:
                put(a, "conversion_faith_id", a.conversion_faith_id, a.generated_turn)
    sch = getattr(world, "scholarship", None)
    for seat in (sch.seats if sch is not None and hasattr(sch, "seats") else ()):
        put(seat, "faith", seat.faith, seat.founded_turn)
    hist = getattr(getattr(world, "_historiography", None), "state", None)
    for c in (hist.chroniclers if hist is not None else ()):
        if c.kind == "temple" and c.faith is not None:
            put(c, "faith", c.faith, c.founded_turn)
    langs = getattr(getattr(world, "_languages", None), "state", None)
    if langs is not None:
        changed += _upgrade_language_state(langs, resolve, world)
    return changed


def upgrade_snapshots(history: Iterable, resolve) -> int:
    """Map an older run's history snapshots (``TurnSnapshot`` or dicts): the
    reform rows' ``faith`` (snapshot T holds the state after turn T - 1).
    Returns the number of values changed."""
    changed = 0
    for snap in history:
        am = snap.get("agent_movements") if isinstance(snap, dict) else getattr(snap, "agent_movements", None)
        turn = snap.get("turn", 1) if isinstance(snap, dict) else getattr(snap, "turn", 1)
        for row in ((am or {}).get("reforms") or []) if isinstance(am, dict) else []:
            if isinstance(row, dict) and isinstance(row.get("faith"), int):
                new = resolve(row["faith"], turn - 1)
                if new != row["faith"]:
                    row["faith"] = new
                    changed += 1
    return changed


def _upgrade_language_state(st, resolve, world) -> int:
    changed = 0
    for w in st.words:
        if w.kind == "faith" and isinstance(w.ref, int):
            new = resolve(w.ref, w.turn)
            if new != w.ref:
                w.ref = new
                changed += 1
    named = {}
    for fid, name in st.faiths.items():
        hit = [k for k, rec in enumerate(world.faiths) if rec.slot == fid and rec.name == name]
        named[hit[-1] if hit else fid] = name
    for w in st.words:
        if w.kind == "faith" and isinstance(w.ref, int) and w.ref not in named:
            rec = record(world, w.ref)
            if rec is not None:
                named[w.ref] = rec.name
    if named != st.faiths:
        st.faiths = dict(sorted(named.items()))
        changed += 1
    return changed


# ---------------------------------------------------------------------------
# Older runs: bundles
# ---------------------------------------------------------------------------

_TEMPLE_PREFIX = "Temple of faith "
_END_SCHISM = 4   # agent_movements_state.SCHISM (a movement's end)
_TOLERATION = 2   # agent_movements_state.TOLERATION (a reform's kind)


def upgrade_bundle(bundle: dict) -> bool:
    """Give a bundle written before the faith table one (in place): the table
    in ``world_state.faiths`` (rebuilt, :func:`reconstruct`) and every dated
    slot reference to a recycled slot mapped to the faith holding it then:
    movements and reforms, the history snapshots' reform rows, ``Temple of
    faith`` event descriptions, temple chroniclers' ``faith``, faith words,
    seats and conversion objectives (chronicler ids such as ``temple:4`` are
    left as written: accounts and narration provenance cite them). Returns
    True when it added a table."""
    ws = bundle.get("world_state")
    if not isinstance(ws, dict) or ws.get("faiths") or not ws.get("belief_registry"):
        return False
    events = bundle.get("events_timeline") or ws.get("events_timeline") or []
    movements = (ws.get("agent_movements") or {}).get("movements") or []
    rows = reconstruct(ws["belief_registry"], events,
                       [c.get("name") for c in ws.get("civilizations", [])],
                       [r.get("name") for r in ws.get("regions", [])],
                       [m.get("name") for m in movements])
    ws["faiths"] = [{k: v for k, v in row.items() if v is not None and v != []} for row in rows]
    if not needs_mapping(rows):
        return True
    resolve = resolver(rows)
    final_turn = (bundle.get("metadata") or {}).get("total_turns")

    def put(obj, key, turn):
        if isinstance(obj, dict) and isinstance(obj.get(key), int):
            obj[key] = resolve(obj[key], turn)

    am = ws.get("agent_movements")
    if isinstance(am, dict):
        for m in am.get("movements") or []:
            put(m, "faith", m.get("ended_turn") if m.get("ended_turn") is not None else final_turn)
            if m.get("schism_turn") is not None:
                for key in ("schism_from", "schism_to"):
                    put(m, key, m["schism_turn"])
                if m.get("end") == _END_SCHISM:
                    put(m, "successor", m["schism_turn"])
        for r in am.get("reforms") or []:
            if r.get("kind") == _TOLERATION:
                put(r, "faith", r.get("enacted_turn"))
    upgrade_snapshots(bundle.get("history") or [], resolve)
    for ev in events:
        if ev.get("event_type") == "temple_destroyed":
            ev["description"] = _upgrade_temple_text(ev.get("description") or "", resolve, ev.get("turn"))
    for seat in ((ws.get("scholarship") or {}).get("seats") or []):
        put(seat, "faith", seat.get("founded_turn"))
    for rec in ((ws.get("gp_agendas") or {}).get("records") or {}).values():
        agenda = rec.get("agenda") or {}
        put(agenda, "conversion_faith_id", agenda.get("generated_turn"))
    for civ in ws.get("civilizations") or []:
        for a in ((civ.get("governance") or {}).get("ambitions") or []):
            put(a, "conversion_faith_id", a.get("generated_turn"))
    hist = bundle.get("historiography")
    if isinstance(hist, dict):
        for c in hist.get("chroniclers") or []:
            if c.get("kind") == "temple":
                put(c, "faith", c.get("founded_turn"))
    langs = bundle.get("languages")
    columns = list((langs or {}).get("word_columns") or []) if isinstance(langs, dict) else []
    if isinstance(langs, dict) and all(c in columns for c in ("kind", "ref", "turn")):
        ki, ri, ti = columns.index("kind"), columns.index("ref"), columns.index("turn")
        refs = set()
        for row in langs.get("words") or []:
            if row[ki] == "faith" and isinstance(row[ri], int):
                row[ri] = resolve(row[ri], row[ti])
                refs.add(row[ri])
        # A slot reused in the older run listed only its last faith: list
        # every faith a word names, by its rebuilt record.
        listed = [f for f in langs.get("faiths") or [] if f.get("faith") in refs]
        have = {f.get("faith") for f in listed}
        table = ws["faiths"]
        for uid in sorted(refs - have):
            if 0 <= uid < len(table):
                listed.append({"faith": uid, "name": table[uid]["name"], "civ": table[uid].get("civ", -1)})
        langs["faiths"] = sorted(listed, key=lambda f: f.get("faith"))
    return True


def _upgrade_temple_text(desc: str, resolve, turn) -> str:
    if not desc.startswith(_TEMPLE_PREFIX):
        return desc
    head = desc[len(_TEMPLE_PREFIX):]
    num, sep, rest = head.partition(" ")
    if not num.isdigit():
        return desc
    return f"{_TEMPLE_PREFIX}{resolve(int(num), turn)}{sep}{rest}"


def uid_or_slot(world, slot: Any) -> Any:
    """Permanent id of the faith holding ``slot``; the value itself when no
    faith does (the no-faith sentinel, a temple without a faith)."""
    uid = uid_of(world, slot)
    return slot if uid is None else uid


def temple_text(world, slot: Any) -> Any:
    """The faith number a ``Temple of faith`` description carries: the
    permanent id of the temple's faith (the slot itself if none holds it)."""
    return uid_or_slot(world, slot)
