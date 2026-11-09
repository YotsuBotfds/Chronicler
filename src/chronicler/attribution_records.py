"""Attribution records (D2, ``--attribution-records``, default off): who did what to whom.

Requires ``--agents hybrid``. Design: AUDIT-D section 7.3 (on the lead's
branch as ``docs/superpowers/audits/connected-world/audit-d-institutions-war-owned-stock.md``);
integration page ``docs/integration/attribution-records.md``.

Why. Program D2 asks for an audit of attribution before foreign grievances
use it: the actual actor, victim and cause must survive conquest and state
changes. Today a granary seizure names only its victim (in a field called
``buyer``), natural deaths of soldiers are booked as army casualties
(``war.armies.reconcile_rosters``), a restored polity silently reuses the dead
polity's index and name, and the burdens one polity lays on another (dues,
levies, plunder, requisitions, seizures, war losses, closures) are recorded in
a dozen places with different identities, or not at all. This package records
them, at the event, in one dated record:

1. **Granary seizures**: each SEIZED flow (``grain_reserves.seize_granary``)
   with its actor (the besieger, occupier or conqueror), its victim (the
   region's ruler at the event) and the granary's books owner (the flow's
   ``buyer``, stale after a same-turn conquest), matched to the flow by index.
2. **Casualties** per war, turn, victim, actor and cause: campaign combat
   (``battle``, ``trapped`` after a lost battle, occupation ``revolt``),
   ``attrition``, and the deaths ``reconcile_rosters`` books as casualties,
   split into ``war_drain``/``possibly_enemy`` (the agent died in a region
   where a war drain staged deaths that turn) and ``natural`` (the rest:
   native mortality with its x2 for soldiers at war, plague and other non-war
   catastrophes). A per-army closure against the army's own casualty counter
   (kept outside ``models.Army``) shows that no note was dropped; a per-battle
   check bounds each side's recorded battle deaths by its battle record.
3. **Identity**: each reuse of a civilization index (a restoration resets the
   dead polity's founding turn under the same index and name; a "New"
   restoration appends a second index with an old name), dated, with the old
   polity's founding and last observed living turn.
4. **Burdens** per actor -> victim pair and turn, each labelled with the
   authority that decided it and its nature: a real ``transfer``, an amount
   ``minted`` for the actor and taken from nobody, an amount ``destroyed``, or
   a ``restriction`` (``attribution_records_state.BURDEN_KINDS``).

Seams. Event-time notes from the unpinned decision modules, each behind the
existing ``world.livelihoods`` guard and a no-op unless this switch is active
(``war.armies.apply_casualties``, ``reconcile_rosters`` and ``drain_population``,
``war.occupation._requisition``, ``start_occupation`` and
``tick_occupations``, ``action_engine.apply_region_conquest``,
``cities._commerce`` and ``cities._sack``), plus the Phase 10 commit (the last
livelihoods hooks but the wealth ledger's), which reads the turn's battle,
treaty, granary, retail and quarantine receipts and the civilization table.
Pinned ``grain_reserves.py`` is not edited: the seizure note reads the flow the
seizure just appended.

Contract. It never writes simulation state, draws no random number, builds no
world lookup cache (``civ_map``, ``region_map``, ``civ_index_map``: it scans
the lists, as provenance does) and has no consumer: no decision reads it, so
with the switch on every output except this record equals the switch off. A
later grievance (D1) may replace a proxy with a recorded burden behind its own
switch; it must not stack on the channels that already carry war harm
(AUDIT-D section 4.3), and it must restrict itself to what the grieving party
could know (the record itself is observer truth).
"""
from __future__ import annotations

import copy

from chronicler.attribution_records_state import (
    BURDEN_KINDS, BURDEN_NATURES, BURDEN_UNITS, CASUALTY_CAUSES, CASUALTY_CLASS, CASUALTY_CLASSES, COUNTERS,
    IDENTITY_KINDS, LIFETIME, MAX_ENTRIES, MAX_IDENTITY_LOG, MAX_LOG, AttributionRecordsState, CivIdentity,
    IdentityRecord, LogRecord,
)
from chronicler.switch_state import sub_state_getter

STAGE = "D2"

#: What each record means (copied into every snapshot record).
LABELS: dict[str, str] = {
    "casualties": ("enlisted soldiers who died this turn, per war (war key and start turn), victim (the army's "
                   "civilization), actor and cause; combat: battle (field, skirmish or assault; the actor is the "
                   "other side of the battle record), trapped (a beaten army with no retreat; the battle's "
                   "winner), revolt (an occupation uprising: the actor is the region's owner polity, whose "
                   "partisans are drawn from the population); attrition: terrain, hunger, supply and siege "
                   "disease (no actor; the war's other side is the opponent); war_drain: found dead after the "
                   "tick in a region where a war drain (siege civilians, a battle's garrison, occupation "
                   "depopulation, a crushed revolt) staged deaths that turn, at most as many per region and turn "
                   "as were staged there, with the drain's actor when the region's drains name one - possibly "
                   "killed by it, possibly natural; possibly_enemy: the same where the drains name several "
                   "actors or none (nomad raids and a roster-less army's own casualties drain without naming "
                   "one); natural: the other deaths found after the tick (beyond_staged counts those in a "
                   "drained region beyond its staged deaths), which reconcile_rosters books as army "
                   "casualties (no actor): native mortality including its x2 for soldiers at war, which cannot "
                   "be separated without a native change, plague and other non-war catastrophes. Militia, "
                   "mercenary and civilian deaths are not soldiers of a roster and are not here (battle records "
                   "count them)"),
    "army_closure": ("per live army: the deaths recorded this turn against the change of its casualty counter "
                     "since the last commit; unchecked (null) for an army without a baseline. Both writers of the "
                     "counter note the same number, so this proves only that no note was dropped, not the cause "
                     "split"),
    "battle_checks": ("per battle and side: the battle deaths recorded for that side's armies, at most the side's "
                      "losses in the battle record (which also count mercenaries and garrison), so a death "
                      "attributed to the wrong battle or side shows"),
    "granary": ("each SEIZED flow of the turn with its actor and victim at the event; books_owner is the flow's "
                "buyer (the granary owner on the books, set at the Phase 2 opening), stale after an earlier "
                "same-turn conquest; unattributed counts SEIZED flows no note saw (null: granaries inactive)"),
    "burdens": ("recorded burdens per actor -> victim pair: transfer (paid by the victim, received by the actor), "
                "minted (credited to the actor, taken from nobody), destroyed (lost by the victim, received by "
                "nobody), restriction (no amount moves); each entry names the authority that decided it. "
                "Dues and sacks are paid from the city purse, not the victim polity's treasury; dues are "
                "assessed (a dead lord's are dropped at payment). Internal pairs (actor == victim) are a "
                "polity's own dues. Events of amount zero (but restrictions) are counted in zero_events, not "
                "in pairs. Not recorded: diplomacy tribute installments, vassal tribute, siege and occupation "
                "civilian deaths"),
    "identity": ("a civilization index reused by another polity: restored (a new founding turn under the same "
                 "index and name), revived (alive again without a new founding), name_reused (a new index named "
                 "like an older one), renamed; records keyed by index or name before the event belong to the "
                 "old polity"),
}


class _Turn:
    """The notes of one turn, first note to the Phase 10 commit (never checkpointed)."""

    __slots__ = ("turn", "casualties", "entries", "seizures", "granary_flows", "retail_seqs", "drains",
                 "drain_used", "beyond_staged")

    def __init__(self, turn: int):
        self.turn = turn
        self.casualties: list[dict] = []
        self.entries: list[dict] = []
        self.seizures: list[dict] = []
        self.granary_flows: set[int] = set()
        self.retail_seqs: set[int] = set()
        self.drains: dict[int, list[tuple[int, int | None, str | None]]] = {}
        self.drain_used: dict[int, int] = {}       # region -> deaths labelled war_drain/possibly_enemy
        self.beyond_staged: dict[int, int] = {}    # region -> deaths beyond the staged count (natural)


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

_state = sub_state_getter("attribution_records")


def _bump(state: AttributionRecordsState, key: str, amount: int = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(f"undeclared attribution-records counter {key!r}")
    state.counters[key] = state.counters.get(key, 0) + amount


def _total(state: AttributionRecordsState, key: str, amount) -> None:
    if key not in LIFETIME:
        raise KeyError(f"undeclared attribution-records total {key!r}")
    state.lifetime[key] = state.lifetime.get(key, 0) + amount


def _log(state: AttributionRecordsState, turn: int, kind: str, **detail) -> None:
    state.log.append(LogRecord(turn=int(turn), kind=kind, detail=detail))
    if len(state.log) > MAX_LOG:
        state.log_dropped += len(state.log) - MAX_LOG
        del state.log[:-MAX_LOG]


def set_attribution_records_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable, or end with a dated record (the frame is dropped; lifetime
    totals, counters, the civilization table and the logs are kept)."""
    turn = int(getattr(world, "turn", 0))
    state = _state(world)
    if state is None:
        world.livelihoods.attribution_records = state = AttributionRecordsState(enabled=bool(value))
        if value:
            _bump(state, "switched_on")
            _log(state, turn, "switched_on")
        return
    t = state._turn
    if t is not None and t.turn == turn:
        raise RuntimeError("cannot change attribution records while a turn is pending")
    if bool(value) == state.enabled:
        return
    state.enabled = bool(value)
    if value:
        _bump(state, "switched_on")
        _log(state, turn, "switched_on")
        return
    _log(state, turn, "switched_off", frame_turn=state.frame_turn)
    _bump(state, "switched_off")
    state.frame, state.frame_turn = None, None
    state._turn = None


def attribution_records_active(world) -> bool:
    state = _state(world)
    return state is not None and state.enabled and getattr(world, "agent_mode", None) == "hybrid"


# ---------------------------------------------------------------------------
# Identity helpers (lists scanned directly: no world lookup cache is built)
# ---------------------------------------------------------------------------

def _civ(world, civ) -> tuple[int | None, str | None]:
    """A civilization (object, name or index) as (its index, its name). A name
    resolves as the simulation's own maps resolve it: the last index with it."""
    if civ is None:
        return None, None
    civs = world.civilizations
    if isinstance(civ, int) and not isinstance(civ, bool):
        return (civ, civs[civ].name) if 0 <= civ < len(civs) else (None, None)
    if isinstance(civ, str):
        for i in range(len(civs) - 1, -1, -1):
            if civs[i].name == civ:
                return i, civ
        return None, civ
    for i, c in enumerate(civs):
        if c is civ:
            return i, c.name
    return _civ(world, getattr(civ, "name", None))


def _region_index(world, region) -> int | None:
    for i, r in enumerate(world.regions):
        if r is region:
            return i
    name = getattr(region, "name", region)
    for i, r in enumerate(world.regions):
        if r.name == name:
            return i
    return None


def _war(world, key: str | None, turn: int):
    """The war record of ``key`` standing at ``turn`` (active first, then the
    latest ended one that started by then), or None."""
    if not key:
        return None
    state = world.war_state
    for war in state.wars:
        if war.war_key == key and war.start_turn <= turn:
            return war
    ended = [w for w in state.ended_wars if w.war_key == key and w.start_turn <= turn]
    return max(ended, key=lambda w: w.start_turn) if ended else None


# ---------------------------------------------------------------------------
# Notes at the events
# ---------------------------------------------------------------------------

def _pending(state: AttributionRecordsState, world, what: str) -> _Turn | None:
    turn = int(world.turn)
    if state.frame_turn is not None and state.frame_turn >= turn:
        # The turn was already committed: a note after the Phase 10 commit.
        _bump(state, "notes_after_close")
        _log(state, turn, "note_after_close", note=what)
        return None
    t = state._turn
    if t is None or t.turn != turn:
        if t is not None and (t.casualties or t.entries or t.seizures):
            # Notes of a turn whose commit never ran: that turn is unobserved.
            _bump(state, "turns_unobserved")
            _log(state, t.turn, "unobserved", reason="no commit", notes=len(t.casualties) + len(t.entries))
        t = state._turn = _Turn(turn)
    return t


def _active_turn(world, what: str) -> tuple[AttributionRecordsState, _Turn] | None:
    state = _state(world)
    if state is None or not attribution_records_active(world):
        return None
    t = _pending(state, world, what)
    return (state, t) if t is not None else None


def _entry(world, kind: str, actor, victim, amount, *, region: int | None = None, city: int | None = None,
           cause: str | None = None, receipt: dict | None = None, detail: dict | None = None) -> dict:
    authority, nature, unit = BURDEN_KINDS[kind]
    a_idx, a_name = _civ(world, actor)
    v_idx, v_name = _civ(world, victim)
    row = {"kind": kind, "nature": nature, "unit": unit, "actor": a_idx, "actor_name": a_name,
           "victim": v_idx, "victim_name": v_name, "amount": amount, "region": region, "city": city,
           "cause": cause}
    if receipt:
        row["receipt"] = receipt
    if detail:
        row["detail"] = detail
    return row


def note_casualties(world, army, count: int, cause: str, *, actor: tuple | None = None) -> None:
    """``war.armies.apply_casualties``: ``count`` soldiers of ``army`` killed by
    ``cause``. The actor of a battle is resolved at the commit from the battle
    record the engagement appends next (``trapped``: the one it just
    appended); a revolt's actor is the owner of the occupied region now."""
    if count <= 0:
        return
    found = _active_turn(world, "casualties")
    if found is None:
        return
    _state_, t = found
    v_idx, v_name = _civ(world, army.civ)
    row = {"army": army.army_id, "victim": v_idx, "victim_name": v_name, "war": army.war_key,
           "cause": cause, "count": int(count)}
    if actor is not None:
        row.update(actor=actor[0], actor_name=actor[1])
    battles = world.war_state.battles
    if cause == "battle":
        row["battle"] = len(battles)
    elif cause == "trapped":
        row["battle"] = len(battles) - 1
    elif cause == "revolt":
        occ = next((o for o in world.war_state.occupations
                    if o.region == army.region and o.occupier == army.civ), None)
        if occ is not None:
            a_idx, a_name = _civ(world, occ.owner)
            row.update(actor=a_idx, actor_name=a_name, war=occ.war_key)
    t.casualties.append(row)


def note_war_drain(world, regions, drains, actor) -> None:
    """``war.armies.drain_population`` (agent modes): deaths staged in each
    region by a war drain this turn, with the enemy whose action it is when the
    caller names one (siege, garrison, occupation, revolt)."""
    found = _active_turn(world, "war_drain")
    if found is None:
        return
    _s, t = found
    a_idx, a_name = _civ(world, actor)
    for region, staged in zip(regions, drains):
        if staged > 0:
            rid = _region_index(world, region)
            if rid is not None:
                t.drains.setdefault(rid, []).append((int(staged), a_idx, a_name))


def note_natural_deaths(world, army, entries) -> None:
    """``war.armies.reconcile_rosters``: the roster entries ``(agent id,
    region)`` of ``army`` found dead after the native tick, booked there as
    casualties. A death in a region where a war drain staged deaths this turn
    is ``war_drain`` (the drains name one actor) or ``possibly_enemy``, at most
    as many per region and turn (over all armies) as the drains staged there:
    the rest, and deaths elsewhere, are ``natural`` (``beyond_staged`` counts
    them per region)."""
    if not entries:
        return
    state = _state(world)
    if state is None or not attribution_records_active(world):
        return
    t = state._turn if state._turn is not None and state._turn.turn == int(world.turn) else None
    drains = t.drains if t is not None else {}
    groups: dict[tuple, int] = {}
    for _aid, region in entries:
        hit = drains.get(region)
        if not hit:
            key = ("natural", None)
        elif t.drain_used.get(region, 0) >= sum(n for n, _i, _a in hit):
            # More deaths here than the drains staged: these cannot be theirs.
            t.beyond_staged[region] = t.beyond_staged.get(region, 0) + 1
            key = ("natural", None)
        else:
            t.drain_used[region] = t.drain_used.get(region, 0) + 1
            actors = {(idx, name) for _n, idx, name in hit}
            key = ("war_drain", next(iter(actors))) if len(actors) == 1 and None not in next(iter(actors)) \
                else ("possibly_enemy", None)
        groups[key] = groups.get(key, 0) + 1
    for (cause, actor), n in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or (-1, ""))):
        note_casualties(world, army, n, cause, actor=actor)


def _seizure(world, t: _Turn, rid: int | None, cause: str, actor, victim, via: str | None) -> None:
    """Attribute the SEIZED flow a seizure just appended (the newest flow of
    the turn, of this region, not yet attributed); none when nothing was taken."""
    reserves = getattr(world, "grain_reserves", None)
    if reserves is None or rid is None or getattr(reserves, "flows_turn", None) != world.turn:
        return
    from chronicler.grain_reserves_state import SEIZED
    flows = reserves.flows
    i = len(flows) - 1
    if i < 0 or i in t.granary_flows:
        return
    flow = flows[i]
    if flow.kind != SEIZED or flow.region != rid:
        return
    t.granary_flows.add(i)
    a_idx, a_name = _civ(world, actor)
    v_idx, v_name = _civ(world, victim)
    b_idx, b_name = _civ(world, flow.buyer) if flow.buyer >= 0 else (None, None)
    t.seizures.append({"region": rid, "flow": i, "grain": float(flow.amount), "cause": cause, "via": via,
                       "actor": a_idx, "actor_name": a_name, "victim": v_idx, "victim_name": v_name,
                       "books_owner": b_idx, "books_owner_name": b_name,
                       "owner_stale": b_idx is not None and v_idx is not None and b_idx != v_idx})
    t.entries.append(_entry(world, "granary_seizure", actor, victim, float(flow.amount), region=rid, cause=cause,
                            receipt={"granary_flow": i}))


def _retail(world, t: _Turn, rid: int | None, cause: str) -> None:
    """Attribute the retail war-loss record the event just logged, if any (a
    pilot region under retail rules 2); retail names actor and victim itself."""
    container = getattr(world, "livelihoods", None)
    retail = getattr(container, "household_retail", None) if container is not None else None
    if retail is None or rid is None or not retail.log:
        return
    seq = retail.log_dropped + len(retail.log) - 1
    record = retail.log[-1]
    if (seq in t.retail_seqs or record.kind != "war_loss" or record.turn != world.turn
            or record.region != rid or record.cause != cause):
        return
    t.retail_seqs.add(seq)
    t.entries.append(_entry(world, "retail_war_loss", record.actor, record.victim, int(record.milli), region=rid,
                            cause=cause, receipt={"retail_record": seq}))


def note_requisition(world, region, factor: float, cause: str | None, actor) -> None:
    """``war.occupation._requisition`` (a siege turn or an occupation start),
    after the commons, the granary and owned stock were cut: the commons food
    destroyed (derived from the commons after the cut and the factor), the
    granary seizure and the retail war loss, actor and victim at the event."""
    found = _active_turn(world, "requisition")
    if found is None:
        return
    _s, t = found
    from chronicler.economy import FOOD_GOODS
    rid = _region_index(world, region)
    victim = region.controller
    goods = region.stockpile.goods
    after = sum(float(goods[g]) for g in sorted(FOOD_GOODS) if g in goods)
    destroyed = after * (1.0 - factor) / factor if 0.0 < factor else None
    t.entries.append(_entry(world, "food_requisition", actor, victim, destroyed, region=rid, cause=cause,
                            detail={"factor": factor, "commons_after": after}))
    _seizure(world, t, rid, cause or "requisition", actor, victim, None)
    _retail(world, t, rid, cause)


def note_conquest(world, region, attacker, defender, *, via: str = "war") -> None:
    """``action_engine.apply_region_conquest`` (each call: two conquests of one
    region in one turn are two events), after the stock, the granary and owned
    stock were cut: the goods destroyed, the granary seizure and the retail war
    loss, conqueror and previous ruler at the event."""
    found = _active_turn(world, "conquest")
    if found is None:
        return
    _s, t = found
    from chronicler.economy import CONQUEST_STOCKPILE_SURVIVAL as keep
    from chronicler.economy import FOOD_GOODS
    rid = _region_index(world, region)
    goods = region.stockpile.goods
    after = sum(float(v) for _g, v in sorted(goods.items()))
    food = sum(float(goods[g]) for g in sorted(FOOD_GOODS) if g in goods)
    scale = (1.0 - keep) / keep if keep > 0 else 0.0
    t.entries.append(_entry(world, "conquest_stock_loss", attacker, defender, after * scale, region=rid,
                            cause="conquest", detail={"via": via, "food": food * scale}))
    _seizure(world, t, rid, "conquest", attacker, defender, via)
    _retail(world, t, rid, "conquest")


def note_infrastructure_damage(world, damage, actor, victim) -> None:
    """Record accepted B3 war damage once, directly from its actual receipt.

    Condition points across assets have their own unit. A same-turn skipped
    sack/conquest, flood, wear, and repair bill are not foreign burdens here.
    Actor/victim are the event's parties, never the region's final controller.
    """
    if damage.event not in ("conquest", "sack") or damage.amount <= 0:
        return
    found = _active_turn(world, "infrastructure_damage")
    if found is None:
        return
    _s, t = found
    t.entries.append(_entry(world, "infrastructure_war_damage", actor, victim, float(damage.amount),
                            region=damage.region, cause=damage.event,
                            receipt={"damage": damage.did, "asset": damage.aid, "war": damage.war_key,
                                     "war_start_turn": damage.war_start_turn},
                            detail={"kind": damage.kind, "condition_before": damage.condition_before,
                                    "condition_after": damage.condition_after}))


def note_plunder(world, region, occupier, owner, plunder: int) -> None:
    """``war.occupation.start_occupation``: the occupier's plunder, credited to
    its treasury and taken from nobody (minted)."""
    found = _active_turn(world, "plunder")
    if found is None:
        return
    _s, t = found
    t.entries.append(_entry(world, "occupation_plunder", occupier, owner, int(plunder),
                            region=_region_index(world, region), cause="occupation"))


def note_occupation_turn(world, occ, owner, occupier, tax_lost: int, requisition: int) -> None:
    """``war.occupation.tick_occupations``: one occupied turn - the owner's lost
    taxes (spent into nothing) and the occupier's requisition (minted)."""
    found = _active_turn(world, "occupation")
    if found is None:
        return
    _s, t = found
    rid = _region_index(world, occ.region)
    receipt = {"war": occ.war_key, "since_turn": occ.since_turn}
    t.entries.append(_entry(world, "occupation_tax_loss", occupier, owner, int(tax_lost), region=rid,
                            cause="occupation", receipt=receipt))
    t.entries.append(_entry(world, "occupation_requisition", occupier, owner, int(requisition), region=rid,
                            cause="occupation", receipt=receipt))


def note_city_dues(world, city, commerce: float, share: float, dues: float, guild) -> None:
    """``cities._commerce``: the dues assessed on ``city`` for its lord this
    turn (debited from the civic purse now, paid to the lord's treasury at the
    next Phase 2), split into the ordinary dues and a guild levy's part."""
    if dues <= 0 or city.lord < 0:
        return
    found = _active_turn(world, "city_dues")
    if found is None:
        return
    _s, t = found
    levy = 0.0
    if guild is not None:
        from chronicler.guilds import LEVY_SHARE, _levied
        if _levied(world, guild):
            levy = min(dues, commerce * LEVY_SHARE)
    region = world.regions[city.region] if 0 <= city.region < len(world.regions) else None
    victim = region.controller if region is not None else None
    receipt = {"settlement": city.settlement_id}
    t.entries.append(_entry(world, "city_dues", city.lord, victim, dues - levy, region=city.region,
                            city=city.settlement_id, cause="dues", receipt=receipt,
                            detail={"commerce": commerce, "share": share}))
    if levy > 0:
        t.entries.append(_entry(world, "guild_levy", city.lord, victim, levy, region=city.region,
                                city=city.settlement_id, cause="levy", receipt=receipt))


def note_city_sack(world, city, sacker_idx: int, victim_idx: int, loot: float, paid: int) -> None:
    """``cities._sack``: the plunder paid to the sacker (a transfer from the
    civic purse) and the rest of the loot, which no one receives."""
    found = _active_turn(world, "city_sack")
    if found is None:
        return
    _s, t = found
    sacker = sacker_idx if sacker_idx >= 0 else None
    victim = victim_idx if victim_idx >= 0 else None
    receipt = {"settlement": city.settlement_id}
    # Without a sacker nothing is credited (cities._sack): the whole loot is lost.
    paid_to = int(paid) if sacker is not None else 0
    t.entries.append(_entry(world, "city_sack", sacker, victim, paid_to, region=city.region,
                            city=city.settlement_id, cause="sack", receipt=receipt))
    t.entries.append(_entry(world, "city_sack_loss", sacker, victim, float(loot) - paid_to, region=city.region,
                            city=city.settlement_id, cause="sack", receipt=receipt))


# ---------------------------------------------------------------------------
# Phase 10 commit
# ---------------------------------------------------------------------------

def _casualties(world, state: AttributionRecordsState, t: _Turn, turn: int) -> dict:
    battles = world.war_state.battles
    rows: dict[tuple, dict] = {}
    by_army: dict[str, int] = {}
    unresolved = 0
    for note in t.casualties:
        cause = note["cause"]
        war_key = note["war"]
        actor, actor_name, kind = note.get("actor"), note.get("actor_name"), None
        if cause in ("battle", "trapped"):
            i = note["battle"]
            b = battles[i] if 0 <= i < len(battles) else None
            name = note["victim_name"]
            if b is not None and b.turn == turn and name in (b.attacker, b.defender) and b.attacker != b.defender:
                actor, actor_name = _civ(world, b.defender if name == b.attacker else b.attacker)
                war_key, kind = b.war_key, b.kind
            else:
                unresolved += note["count"]
        elif cause == "revolt" and actor_name is None:
            unresolved += note["count"]
        war = _war(world, war_key, turn)
        opponent = None
        if war is not None and note["victim_name"] in (war.attacker, war.defender):
            opponent = war.defender if note["victim_name"] == war.attacker else war.attacker
        o_idx, o_name = _civ(world, opponent)
        key = (war_key or "", war.start_turn if war is not None else -1, note["victim"] if note["victim"] is not None else -1,
               note["victim_name"] or "", actor if actor is not None else -1, actor_name or "", cause, kind or "")
        row = rows.get(key)
        if row is None:
            row = rows[key] = {
                "war": war_key, "war_start": war.start_turn if war is not None else None,
                "victim": note["victim"], "victim_name": note["victim_name"], "actor": actor,
                "actor_name": actor_name, "opponent": o_idx, "opponent_name": o_name, "cause": cause,
                "class": CASUALTY_CLASS.get(cause, "unclassified"), "kind": kind, "deaths": 0,
            }
        row["deaths"] += note["count"]
        by_army[note["army"]] = by_army.get(note["army"], 0) + note["count"]
    ordered = [rows[k] for k in sorted(rows)]
    # Per battle and side: recorded battle deaths at most the battle record's losses.
    per_battle: dict[tuple[int, str], int] = {}
    for note in t.casualties:
        if note["cause"] == "battle":
            key = (note["battle"], note["victim_name"] or "")
            per_battle[key] = per_battle.get(key, 0) + note["count"]
    battle_checks = []
    for (i, name), recorded in sorted(per_battle.items()):
        b = battles[i] if 0 <= i < len(battles) else None
        if b is None or b.turn != turn or name not in (b.attacker, b.defender):
            losses = None
        else:
            losses = b.attacker_losses if name == b.attacker else b.defender_losses
        holds = losses is not None and recorded <= losses
        battle_checks.append({"battle": i, "side": name, "recorded": recorded, "battle_losses": losses,
                              "holds": holds})
        _bump(state, "battle_checks")
        if not holds:
            _bump(state, "battle_checks_failed")
    war_drains = [{"region": rid, "staged": sum(n for n, _i, _a in hits),
                   "actors": sorted({a for _n, _i, a in hits if a is not None}),
                   "unnamed": sum(1 for _n, i, _a in hits if i is None),
                   "labelled": t.drain_used.get(rid, 0), "beyond_staged": t.beyond_staged.get(rid, 0)}
                  for rid, hits in sorted(t.drains.items())]
    by_class = {c: 0 for c in CASUALTY_CLASSES}
    by_cause = {c: 0 for c in CASUALTY_CAUSES}
    for row in ordered:
        by_class[row["class"]] = by_class.get(row["class"], 0) + row["deaths"]
        by_cause[row["cause"]] = by_cause.get(row["cause"], 0) + row["deaths"]
    # Closure per army: recorded deaths against the change of its counter.
    continuous = state.baseline_turn == turn - 1
    armies = []
    live = set()
    for army in sorted(world.war_state.armies, key=lambda a: a.army_id):
        live.add(army.army_id)
        if army.army_id in state.army_casualties and continuous:
            change = army.casualties - state.army_casualties[army.army_id]
        elif army.raised_turn == turn and army.army_id not in state.army_casualties:
            change = army.casualties          # raised this turn: its counter started at 0
        else:
            change = None
        recorded = by_army.get(army.army_id, 0)
        if change is None and not recorded:
            continue
        a_idx, a_name = _civ(world, army.civ)
        armies.append({"army": army.army_id, "civ": a_idx, "civ_name": a_name, "recorded": recorded,
                       "counter_change": change, "closes": None if change is None else change == recorded})
    for army_id in sorted(set(by_army) - live):
        # Disbanded or destroyed this turn: its counter is gone.
        armies.append({"army": army_id, "civ": None, "civ_name": None, "recorded": by_army[army_id],
                       "counter_change": None, "closes": None})
    for row in armies:
        if row["closes"] is None:
            _bump(state, "army_closures_unchecked")
        else:
            _bump(state, "army_closures_checked")
            if not row["closes"]:
                _bump(state, "army_closures_failed")
    state.army_casualties = {a.army_id: int(a.casualties) for a in world.war_state.armies}
    for cause, n in by_cause.items():
        if n and f"deaths_{cause}" in LIFETIME:
            _total(state, f"deaths_{cause}", n)
    if unresolved:
        _bump(state, "combat_unresolved", unresolved)
    drained = by_class.get("war_drain", 0)
    if drained:
        _bump(state, "war_drain_deaths", drained)
    return {"rows": ordered, "by_class": by_class, "by_cause": by_cause, "unresolved": unresolved,
            "armies": armies, "battle_checks": battle_checks, "war_drains": war_drains}


def _treaties(world, t: _Turn, turn: int) -> None:
    for i, treaty in enumerate(world.war_state.treaties):
        if treaty.turn != turn or not treaty.treasury_paid or treaty.winner is None:
            continue
        loser = next((p for p in treaty.parties if p != treaty.winner), None)
        t.entries.append(_entry(world, "treaty_payment", treaty.winner, loser, int(treaty.treasury_paid),
                                cause=treaty.kind, receipt={"treaty": i, "war": treaty.war_key}))


def _quarantine(world, t: _Turn, turn: int) -> None:
    from chronicler.quarantine_rules import rules_of
    rules = rules_of(world)
    if rules is None or rules.mode != "closure" or rules.receipt is None or rules.receipt.turn != turn:
        return
    receipt = rules.receipt
    removed = {tuple(pair) for pair in receipt.routes_removed}
    for civ, target in receipt.decided:
        pair = (min(civ, target), max(civ, target))
        closure = next((c for c in rules.closures if c.civ == civ and c.target == target), None)
        t.entries.append(_entry(world, "quarantine_closure", civ, target, 1 if pair in removed else 0,
                                cause="closure",
                                receipt={"closure": closure.id if closure is not None else None}))


def _granary(world, state: AttributionRecordsState, t: _Turn, turn: int) -> dict:
    from chronicler.grain_reserves import grain_reserves_active
    if not grain_reserves_active(world):
        return {"active": False, "seizures": [], "unattributed": None}
    from chronicler.grain_reserves_state import SEIZED
    reserves = world.grain_reserves
    flows = reserves.flows if reserves.flows_turn == turn else []
    seized = [i for i, f in enumerate(flows) if f.kind == SEIZED]
    missing = len([i for i in seized if i not in t.granary_flows])
    _bump(state, "granary_seizures", len(t.seizures))
    if missing:
        _bump(state, "granary_unattributed", missing)
    return {"active": True, "seizures": sorted(t.seizures, key=lambda s: s["flow"]), "unattributed": missing}


def _retail_unattributed(world, state: AttributionRecordsState, t: _Turn, turn: int) -> int | None:
    container = getattr(world, "livelihoods", None)
    retail = getattr(container, "household_retail", None) if container is not None else None
    from importlib import import_module
    if retail is None or not import_module("chronicler.household_retail").household_retail_active(world):
        return None
    base = retail.log_dropped
    seen = [base + i for i, r in enumerate(retail.log) if r.kind == "war_loss" and r.turn == turn]
    _bump(state, "retail_war_losses", len(t.retail_seqs))
    missing = len([s for s in seen if s not in t.retail_seqs])
    if missing:
        _bump(state, "retail_unattributed", missing)
    return missing


def _burdens(state: AttributionRecordsState, entries: list[dict]) -> dict:
    pairs: dict[tuple, dict] = {}
    zero: dict[str, int] = {}
    kept_entries = []
    for e in entries:
        if e["amount"] == 0 and e["nature"] != "restriction":
            # A burden event that moved nothing (no plunder from an empty
            # region, nothing left to spend or seize): counted, not paired.
            zero[e["kind"]] = zero.get(e["kind"], 0) + 1
            _bump(state, "zero_amount_events")
            continue
        kept_entries.append(e)
        key = (e["kind"], e["nature"], e["unit"], e["actor"] if e["actor"] is not None else -1,
               e["victim"] if e["victim"] is not None else -1)
        row = pairs.get(key)
        if row is None:
            row = pairs[key] = {"kind": e["kind"], "nature": e["nature"], "unit": e["unit"],
                                "authority": BURDEN_KINDS[e["kind"]][0], "actor": e["actor"],
                                "actor_name": e["actor_name"], "victim": e["victim"],
                                "victim_name": e["victim_name"], "amount": 0, "unknown": 0, "events": 0,
                                "internal": e["actor"] is not None and e["actor"] == e["victim"]}
        if e["amount"] is None:
            row["unknown"] += 1
        else:
            row["amount"] += e["amount"]
        row["events"] += 1
        _total(state, f"burden_{e['kind']}", e["amount"] or 0)
        _total(state, f"burden_{e['kind']}_events", 1)
    kept = kept_entries[:MAX_ENTRIES]
    dropped = len(kept_entries) - len(kept)
    if dropped:
        _bump(state, "entries_dropped", dropped)
    return {"pairs": [pairs[k] for k in sorted(pairs)], "entries": kept, "entries_dropped": dropped,
            "zero_events": dict(sorted(zero.items()))}


def _identity(world, state: AttributionRecordsState, turn: int) -> list[dict]:
    """Compare the civilization table with the last observation: a new founding
    turn under an index is a restoration (index and name reused)."""
    events: list[IdentityRecord] = []
    first = not state.civs
    continuous = state.baseline_turn == turn - 1
    for idx, civ in enumerate(world.civilizations):
        alive = bool(civ.regions)
        founded = getattr(civ, "founded_turn", None)
        if idx >= len(state.civs):
            if not first:
                older = [j for j, seen in enumerate(state.civs) if seen.name == civ.name]
                if older:
                    events.append(IdentityRecord(turn=turn, kind="name_reused", civ=idx, name=civ.name,
                                                 detail={"older_indices": older, "founded_turn": founded}))
            state.civs.append(CivIdentity(name=civ.name, alive=alive, founded_turn=founded,
                                          last_alive_turn=turn if alive else None, since_turn=turn))
            continue
        seen = state.civs[idx]
        detail = {"observed_previous_turn": continuous}
        if civ.name != seen.name:
            events.append(IdentityRecord(turn=turn, kind="renamed", civ=idx, name=civ.name,
                                         detail={**detail, "old_name": seen.name}))
        if founded != seen.founded_turn:
            events.append(IdentityRecord(turn=turn, kind="restored", civ=idx, name=civ.name, detail={
                **detail, "old_founded_turn": seen.founded_turn, "new_founded_turn": founded,
                "old_last_alive_turn": seen.last_alive_turn, "old_alive_at_last_observation": seen.alive}))
        elif alive and not seen.alive:
            events.append(IdentityRecord(turn=turn, kind="revived", civ=idx, name=civ.name, detail={
                **detail, "founded_turn": founded, "old_last_alive_turn": seen.last_alive_turn}))
        seen.name, seen.alive, seen.founded_turn = civ.name, alive, founded
        if alive:
            seen.last_alive_turn = turn
    for record in events:
        if record.kind not in IDENTITY_KINDS:
            raise ValueError(f"undeclared identity kind {record.kind!r}")
        state.identity_log.append(record)
    if len(state.identity_log) > MAX_IDENTITY_LOG:
        state.identity_dropped += len(state.identity_log) - MAX_IDENTITY_LOG
        del state.identity_log[:-MAX_IDENTITY_LOG]
    if events:
        _bump(state, "identity_events", len(events))
    return [r.model_dump() for r in events]


def phase10(world, acc, economy_result, agent_bridge):
    """Commit the turn's notes with the Phase 10 receipts into the frame (after
    every package's Phase 10 but the wealth ledger's; changes nothing else)."""
    state = _state(world)
    turn = int(world.turn)
    t = state._turn
    if t is None or t.turn != turn:
        if t is not None and (t.casualties or t.entries or t.seizures):
            _bump(state, "turns_unobserved")
            _log(state, t.turn, "unobserved", reason="no commit", notes=len(t.casualties) + len(t.entries))
        t = _Turn(turn)
    if state.frame_turn is not None and state.frame_turn >= turn:
        raise RuntimeError("attribution records committed twice in one turn")
    _treaties(world, t, turn)
    _quarantine(world, t, turn)
    casualties = _casualties(world, state, t, turn)
    granary = _granary(world, state, t, turn)
    burdens = _burdens(state, t.entries)
    burdens["retail_unattributed"] = _retail_unattributed(world, state, t, turn)
    identity = _identity(world, state, turn)
    state.frame = {"turn": turn, "casualties": casualties, "granary": granary, "burdens": burdens,
                   "identity": identity}
    state.frame_turn = turn
    state.baseline_turn = turn
    state._turn = None
    _bump(state, "turns_observed")
    return []


def rollback_phase2(world) -> None:
    """A failed Phase 2 leaves no notes (none are taken there); nothing to release."""


# ---------------------------------------------------------------------------
# Snapshot and reading
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """The completed-turn record, dated by ``source_turn``; ``frame`` is None
    when that turn was not observed (unknown, not zero)."""
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source and state.frame is not None
    return {
        "schema_version": 1, "stage": STAGE, "source_turn": source,
        # A copy: the record never aliases the package's own state.
        "frame": copy.deepcopy(state.frame) if fresh else None,
        "lifetime": {k: state.lifetime[k] for k in LIFETIME if k in state.lifetime},
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "identity_log": [r.model_dump() for r in state.identity_log], "identity_dropped": state.identity_dropped,
        "log": [r.model_dump() for r in state.log], "log_dropped": state.log_dropped,
        "labels": dict(LABELS),
        "parameters": {"burden_kinds": {k: {"authority": a, "nature": n, "unit": u}
                                        for k, (a, n, u) in BURDEN_KINDS.items()},
                       "natures": list(BURDEN_NATURES), "units": list(BURDEN_UNITS),
                       "causes": list(CASUALTY_CAUSES), "classes": list(CASUALTY_CLASSES),
                       "identity_kinds": list(IDENTITY_KINDS), "max_entries": MAX_ENTRIES},
    }


#: Keys every observed frame carries (the record shape a reader may rely on).
FRAME_KEYS: tuple[str, ...] = ("turn", "casualties", "granary", "burdens", "identity")


def record_status(snapshot) -> tuple[str, dict | None]:
    """How a reader treats one history snapshot's record (the reference for
    viewer and analysis readers): ``("absent", None)`` - the switch was never
    on or is off in that turn; ``("malformed", None)`` - present but not this
    record's shape; ``("unobserved", None)`` - the source turn was not observed
    (unknown, not zero); ``("recorded_zero", frame)`` - observed, and nothing
    was attributed that turn; ``("recorded", frame)`` - observed with records."""
    livelihoods = snapshot.get("livelihoods") if isinstance(snapshot, dict) else None
    if not isinstance(livelihoods, dict) or "attribution_records" not in livelihoods:
        return "absent", None
    record = livelihoods["attribution_records"]
    source = record.get("source_turn") if isinstance(record, dict) else None
    if (not isinstance(record, dict) or record.get("schema_version") != 1 or record.get("stage") != STAGE
            or not isinstance(source, int) or isinstance(source, bool) or "frame" not in record):
        return "malformed", None
    frame = record["frame"]
    if frame is None:
        return "unobserved", None
    if (not isinstance(frame, dict) or any(key not in frame for key in FRAME_KEYS) or frame["turn"] != source
            or not isinstance(frame["casualties"], dict) or not isinstance(frame["burdens"], dict)
            or not isinstance(frame["casualties"].get("rows"), list)
            or not isinstance(frame["burdens"].get("pairs"), list) or not isinstance(frame["identity"], list)
            or not isinstance(frame["granary"], dict) or not isinstance(frame["granary"].get("seizures"), list)):
        return "malformed", None
    empty = (not frame["casualties"]["rows"] and not frame["burdens"]["pairs"] and not frame["identity"]
             and not frame["granary"]["seizures"])
    return ("recorded_zero" if empty else "recorded"), frame
