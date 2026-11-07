"""Cross-border guild leagues (D1b, ``--guild-leagues``, default off).

Requires ``--agents hybrid``, cities and guilds (both on by default). Design:
AUDIT-D section 7.4(b) (``docs/superpowers/audits/connected-world/audit-d-institutions-war-owned-stock.md``);
integration page ``docs/integration/guild-leagues.md``.

Why. Guilds (``guilds.py``) stay inside their city's realm: a levy, a sack or
an occupation falls on one city's purse alone, and nothing institutional crosses
a border. This package lets guilds of cities in different realms, linked by
merchant flows they could know, pool part of their purses in a bounded mutual
fund that pays a member's recorded losses.

Links. Each Phase 10 the economy's recorded merchant deliveries of this turn
(``EconomyResult.inbound_sources``: the regions whose goods native merchant
agents delivered to each region, the delivery provenance of hybrid trade) mark
every pair of living guilds in different regions of different realms whose
regions traded either way. A pair seen on ``LINK_TURNS`` turns within
``LINK_WINDOW`` turns is a candidate. A guild knows the goods that reach its own
market and where its merchants go; it never reads another market, provenance or
attribution records.

Leagues (ids from ``next_league``, never reused). A candidate pair of free
guilds whose realms are not at war founds a league; a free guild linked to a
member joins that member's league when the league has fewer than
``MAX_MEMBERS`` members, none of them in the joiner's realm (one member per
realm: the league is a cross-border body) and no member's realm at war with
the joiner's. Leagues never merge.

Dues (``mutual`` and ``dues_only``). Once a turn per league, each member pays
``DUES_SHARE`` of its guild purse, at most ``DUES_CAP`` milli, into the league
fund while the fund is below ``FUND_CAP_PER_MEMBER`` per member: a real purse
transfer (the guild purse falls by exactly what the fund gains, to the purses'
1e-4 rounding).

Claims (``mutual`` only). The fund pays a member city's civic purse only for
that member's recorded loss of this turn, noted at the event and matched to the
city's history: the levy's share of this turn's dues (``cities._commerce``:
``commerce x guilds.LEVY_SHARE`` while a levy recorded in the city's history on
an earlier turn runs) and the plunder of a sack (``cities._sack``: the loot, an
occupation's sack included; city history ``sacked``). Each claim is paid at most
``min(loss, PAYOUT_CAP, fund)``, once. ``dues_only`` is the cost control: the
same links, leagues, dues and dissolutions, no claim paid.

What it does not touch. ``city.grievance`` and every proxy that feeds it (the
levy's and the sack's grievance) stay as they are: no recorded quantity replaces
a proxy here, so nothing stacks; the lord still receives the dues and the sacker
the plunder; guild wall help is unchanged (the fund restores the civic purse, it
does not pay walls). No event is emitted (records only).

Dissolution (declared rules, checked each Phase 10 in this order):

1. A member leaves when its guild dissolved, its city fell, or its city's lord is
   no longer the lord it joined under (a conquest or cession: it joined across
   that border); a member that leaves keeps no claim on the fund.
2. A league dissolves when two members' realms are at war, when fewer than two
   members remain, when all remaining members share one realm, or when no
   recorded delivery passed between two members' regions for ``DORMANT_TURNS``.

A dissolved league returns its fund to the remaining members' guild purses pro
rata to the dues each paid (largest remainder, ties by guild index; equally when
none paid); with no member left, the fund is recorded as unclaimed (lost).

Turn order: Phase 10 after the cities and guilds ticks (levies, sacks and
dissolutions of this turn are recorded), in the livelihoods hook order (before
the attribution records and the wealth ledger): departures, war/size
dissolutions, links, dormancy, claims, foundings and joins, dues.

Identity: region = index in ``world.regions``, civ = index in
``world.civilizations``, guild = index in ``GuildState.guilds``, city =
``settlement_id``, league = its id. No random draws; every order is by league
id, guild index or settlement id.
"""
from __future__ import annotations

import math

from chronicler.guild_leagues_state import (
    COUNTERS, LOG_KINDS, MAX_DISSOLVED, MAX_LINKS, MAX_LOG, MODES, Change, Dues, GuildLeagueState, League,
    LeagueFrame, LeagueRecord, LeagueRow, Link, Member, Payout,
)

STAGE = "D1b"
#: A pair is a candidate after recorded deliveries on this many turns ...
LINK_TURNS = 3
#: ... within this many turns.
LINK_WINDOW = 10
#: Members of one league at most (one per realm).
MAX_MEMBERS = 4
#: Share of a member's guild purse paid in dues each turn, and the most per turn (milli).
DUES_SHARE = 0.02
DUES_CAP = 250
#: The fund collects no dues while it holds this much per member (milli).
FUND_CAP_PER_MEMBER = 3000
#: The most one claim is paid (milli).
PAYOUT_CAP = 2000
#: A league with no recorded delivery between two members' regions for this many turns dissolves.
DORMANT_TURNS = 20
MILLI = 1000
#: A purse transfer must move exactly milli / 1000 within the purses' rounding.
PURSE_TOL = 1.5e-4


# ---------------------------------------------------------------------------
# State and switch
# ---------------------------------------------------------------------------

def _state(world) -> GuildLeagueState | None:
    container = getattr(world, "livelihoods", None)
    return getattr(container, "guild_leagues", None) if container is not None else None


def _bump(state: GuildLeagueState, key: str, amount: int = 1) -> None:
    if key not in COUNTERS:
        raise KeyError(key)
    state.counters[key] = state.counters.get(key, 0) + int(amount)


def _log(state: GuildLeagueState, record: LeagueRecord) -> None:
    if record.kind not in LOG_KINDS:
        raise KeyError(record.kind)
    state.log.append(record)
    if len(state.log) > MAX_LOG:
        state.log_dropped += len(state.log) - MAX_LOG
        del state.log[:len(state.log) - MAX_LOG]


class _Turn:
    def __init__(self, turn: int):
        self.turn = turn
        self.notes: dict[int, dict] = {}


def set_guild_leagues_enabled(world, value: bool, *, args=None, agent_mode=None) -> None:
    """Enable, or end: every living league dissolves (``switched_off``) and
    returns its fund to its members' guild purses, dated."""
    mode = getattr(args, "guild_league_mode", None) if args is not None else None
    if mode is not None and mode not in MODES:
        raise ValueError(f"guild_league_mode must be one of {MODES}")
    turn = int(getattr(world, "turn", 0))
    state = _state(world)
    if state is None:
        world.livelihoods.guild_leagues = state = GuildLeagueState(enabled=bool(value), mode=mode or MODES[0])
        if value:
            _log(state, LeagueRecord(turn=turn, kind="switched_on", note=state.mode))
        return
    t = state._turn
    if t is not None and t.turn == turn:
        raise RuntimeError("cannot change guild leagues while a turn is pending")
    if mode is not None:
        state.mode = mode
    if bool(value) == state.enabled:
        return
    state.enabled = bool(value)
    if value:
        _log(state, LeagueRecord(turn=turn, kind="switched_on", note=state.mode))
        return
    frame = LeagueFrame(turn=turn)
    for league in list(state.leagues):
        _dissolve(world, state, league, "switched_off", frame, {}, turn)
    state.frame, state.frame_turn, state._turn = None, None, None
    _log(state, LeagueRecord(turn=turn, kind="switched_off", note=state.mode))


def guild_leagues_active(world) -> bool:
    state = _state(world)
    if state is None or not state.enabled or getattr(world, "agent_mode", None) != "hybrid":
        return False
    from chronicler.cities_state import cities_on
    from chronicler.guilds_state import guilds_on
    return guilds_on(world) and cities_on(world)


def _turn(state: GuildLeagueState, world) -> _Turn:
    t = state._turn
    if t is None or t.turn != world.turn:
        t = state._turn = _Turn(int(world.turn))
    return t


def _member_cities(state: GuildLeagueState) -> set[int]:
    return {m.city for league in state.leagues for m in league.members}


# ---------------------------------------------------------------------------
# Event-time notes (cities.py, behind the livelihoods guard)
# ---------------------------------------------------------------------------

def note_city_dues(world, city, commerce: float, dues: float, guild) -> None:
    """``cities._commerce``: the levy's share of this turn's dues of a member
    city (``commerce x guilds.LEVY_SHARE`` while the lord's levy runs)."""
    if not guild_leagues_active(world):
        return
    state = _state(world)
    if city.settlement_id not in _member_cities(state) or guild is None or city.lord < 0 or dues <= 0:
        return
    from chronicler.guilds import LEVY_SHARE, _levied
    if not _levied(world, guild):
        return
    milli = math.floor(float(commerce) * LEVY_SHARE * MILLI)
    if milli > 0:
        _turn(state, world).notes.setdefault(city.settlement_id, {})["levy"] = milli


def note_city_sack(world, city, loot: float, event_id: str) -> None:
    """``cities._sack``: the plunder of a member city's purse (an occupation's sack included)."""
    if not guild_leagues_active(world):
        return
    state = _state(world)
    if city.settlement_id not in _member_cities(state):
        return
    milli = math.floor(float(loot) * MILLI)
    if milli > 0:
        _turn(state, world).notes.setdefault(city.settlement_id, {})["sack"] = (milli, str(event_id))


# ---------------------------------------------------------------------------
# Purses
# ---------------------------------------------------------------------------

def _q(x: float) -> float:
    return round(x, 4)


def _move_purse(holder, field: str, milli: int) -> None:
    """Change a float purse by exactly ``milli / 1000`` (to its 1e-4 rounding)."""
    before = float(getattr(holder, field))
    after = _q(before + milli / MILLI)
    if abs((after - before) - milli / MILLI) > PURSE_TOL or after < -PURSE_TOL:
        raise RuntimeError(f"guild league purse transfer of {milli} milli does not close")
    setattr(holder, field, after)


def _purse_milli(guild) -> int:
    return max(0, math.floor(float(guild.wealth) * MILLI + 1e-6))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _at_war(world, a: int, b: int) -> bool:
    civs = world.civilizations
    if not (0 <= a < len(civs) and 0 <= b < len(civs)):
        return False
    na, nb = civs[a].name, civs[b].name
    return any((x == na and y == nb) or (x == nb and y == na) for x, y in world.active_wars)


def _row(rows: dict[int, LeagueRow], league: League) -> LeagueRow:
    row = rows.get(league.league)
    if row is None:
        row = rows[league.league] = LeagueRow(league=league.league, founded_turn=league.founded_turn,
                                              fund_open_milli=league.fund_milli)
    return row


def _dissolve(world, state: GuildLeagueState, league: League, reason: str, frame: LeagueFrame,
              rows: dict[int, LeagueRow], turn: int) -> None:
    """Return the fund to the remaining members' guild purses pro rata to their
    dues (equally when none paid); with none left it is unclaimed."""
    from chronicler.household_retail import largest_remainder
    guilds = world.guilds.guilds if getattr(world, "guilds", None) is not None else []
    row = _row(rows, league)
    fund = league.fund_milli
    living = [m for m in league.members if 0 <= m.guild < len(guilds) and guilds[m.guild].dissolved_turn is None]
    returned = unclaimed = 0
    if fund > 0 and living:
        weights = [(m.guild, m.dues_milli) for m in living]
        if not any(w for _g, w in weights):
            weights = [(m.guild, 1) for m in living]
        for gi, milli in largest_remainder(fund, weights).items():
            _move_purse(guilds[gi], "wealth", milli)
            returned += milli
    elif fund > 0:
        unclaimed = fund
        _log(state, LeagueRecord(turn=turn, kind="fund_unclaimed", league=league.league, milli=fund,
                                 note="no member left to return the fund to"))
    if returned + unclaimed != fund:
        raise RuntimeError("a dissolved guild league's fund does not close")
    league.fund_milli = 0
    league.dissolved_turn, league.dissolved_reason = turn, reason
    row.returned_milli += returned
    row.unclaimed_milli += unclaimed
    row.dissolved = reason
    frame.changes.append(Change(league=league.league, kind="dissolved", reason=reason, returned_milli=returned,
                                unclaimed_milli=unclaimed))
    _bump(state, "dissolutions")
    _bump(state, "returned_milli", returned)
    _bump(state, "unclaimed_milli", unclaimed)
    state.leagues = [x for x in state.leagues if x is not league]
    state.dissolved.append(league)
    if len(state.dissolved) > MAX_DISSOLVED:
        state.dissolved_dropped += len(state.dissolved) - MAX_DISSOLVED
        del state.dissolved[:len(state.dissolved) - MAX_DISSOLVED]


# ---------------------------------------------------------------------------
# Phase 10
# ---------------------------------------------------------------------------

def _departures(world, state, frame, rows, cities, turn) -> None:
    guilds = world.guilds.guilds
    for league in list(state.leagues):
        for m in list(league.members):
            g = guilds[m.guild] if 0 <= m.guild < len(guilds) else None
            reason = None
            if g is None or g.dissolved_turn is not None or g.city != m.city:
                reason = "guild_dissolved"
            elif m.city not in cities:
                reason = "city_fallen"
            elif cities[m.city].lord != m.lord:
                reason = "lord_changed"
            if reason is None:
                continue
            _row(rows, league)
            league.members = [x for x in league.members if x is not m]
            frame.changes.append(Change(league=league.league, kind="left", guild=m.guild, city=m.city, reason=reason))
            _bump(state, "departures")


def _structure(world, state, frame, rows, turn) -> None:
    for league in list(state.leagues):
        lords = [m.lord for m in league.members]
        if any(_at_war(world, a, b) for i, a in enumerate(lords) for b in lords[i + 1:]):
            _dissolve(world, state, league, "war_between_members", frame, rows, turn)
        elif len(league.members) < 2:
            _dissolve(world, state, league, "too_few_members", frame, rows, turn)
        elif len(set(lords)) < 2:
            _dissolve(world, state, league, "one_realm", frame, rows, turn)


def _links(world, state, economy_result, cities, turn) -> set[tuple[int, int]]:
    """This turn's recorded deliveries between living guilds' regions of
    different realms; updates and prunes the link records. Returns the pairs seen."""
    from chronicler.guilds import living_guilds
    inbound = getattr(economy_result, "inbound_sources", None) or {}
    names = [r.name for r in world.regions]
    index = {n: i for i, n in enumerate(names)}
    sources = {i: {index[s] for s in inbound.get(n, ()) if s in index} for i, n in enumerate(names)}
    living = []
    for gi, g in living_guilds(world):
        city = cities.get(g.city)
        if city is not None and city.lord >= 0:
            living.append((gi, g.region, city.lord))
    seen: set[tuple[int, int]] = set()
    for i, (ga, ra, la) in enumerate(living):
        for gb, rb, lb in living[i + 1:]:
            if ra == rb or la == lb:
                continue
            if rb in sources.get(ra, ()) or ra in sources.get(rb, ()):
                seen.add((min(ga, gb), max(ga, gb)))
    by_pair = {(lk.a, lk.b): lk for lk in state.links}
    for pair in sorted(seen):
        lk = by_pair.get(pair)
        if lk is None:
            lk = by_pair[pair] = Link(a=pair[0], b=pair[1])
        if not lk.turns or lk.turns[-1] != turn:
            lk.turns = (lk.turns + [turn])[-LINK_TURNS:]
    alive = {gi for gi, _r, _l in living}
    kept = [lk for _p, lk in sorted(by_pair.items())
            if lk.turns and lk.turns[-1] > turn - LINK_WINDOW and lk.a in alive and lk.b in alive]
    if len(kept) > MAX_LINKS:
        kept = sorted(kept, key=lambda lk: (-lk.turns[-1], lk.a, lk.b))[:MAX_LINKS]
        kept.sort(key=lambda lk: (lk.a, lk.b))
    _bump(state, "links_pruned", len(by_pair) - len(kept))
    state.links = kept
    return seen


def _claims(world, state, frame, rows, notes, cities, turn) -> None:
    from chronicler.guilds import LEVY_TURNS
    for league in state.leagues:
        for m in league.members:
            note = notes.get(m.city)
            city = cities.get(m.city)
            if not note or city is None:
                continue
            claims = []
            if "levy" in note:
                levy = next((eid for t, kind, eid in reversed(city.history)
                             if kind == "levy" and t < turn and turn - t < LEVY_TURNS), None)
                if levy is None:
                    _log(state, LeagueRecord(turn=turn, kind="claim_unverified", league=league.league,
                                             milli=note["levy"], note=f"city {m.city}: no running levy recorded"))
                else:
                    claims.append(("levy", note["levy"], levy))
            if "sack" in note:
                loss, eid = note["sack"]
                if any(t == turn and kind == "sacked" and e == eid for t, kind, e in city.history):
                    claims.append(("sack", loss, eid))
                else:
                    _log(state, LeagueRecord(turn=turn, kind="claim_unverified", league=league.league, milli=loss,
                                             note=f"city {m.city}: the sack is not in its history"))
            for kind, loss, eid in claims:
                paid = min(loss, PAYOUT_CAP, league.fund_milli) if state.mode == "mutual" else 0
                if paid > 0:
                    league.fund_milli -= paid
                    _move_purse(city, "wealth", paid)
                    m.payouts_milli += paid
                    _row(rows, league).payouts_milli += paid
                    _bump(state, "payouts_milli", paid)
                    _bump(state, f"payouts_{kind}_milli", paid)
                    _bump(state, "payout_rows")
                _bump(state, "claims_unpaid_milli", loss - paid)
                frame.payouts.append(Payout(league=league.league, guild=m.guild, city=m.city, kind=kind,
                                            loss_milli=loss, paid_milli=paid, event_id=eid))


def _formation(world, state, frame, rows, cities, turn) -> None:
    guilds = world.guilds.guilds
    league_of = {m.guild: league for league in state.leagues for m in league.members}
    candidates = [lk for lk in state.links if len(lk.turns) >= LINK_TURNS and lk.turns[0] > turn - LINK_WINDOW]
    frame.candidates = len(candidates)

    def member(gi: int) -> Member | None:
        g = guilds[gi]
        city = cities.get(g.city)
        if g.dissolved_turn is not None or city is None or city.lord < 0:
            return None
        return Member(guild=gi, city=g.city, region=g.region, lord=city.lord, joined_turn=turn)

    for lk in candidates:
        a, b = member(lk.a), member(lk.b)
        if a is None or b is None or a.lord == b.lord or _at_war(world, a.lord, b.lord):
            continue
        la, lb = league_of.get(a.guild), league_of.get(b.guild)
        if la is None and lb is None:
            league = League(league=state.next_league, founded_turn=turn, members=[a, b], last_trade_turn=turn)
            state.next_league += 1
            state.leagues.append(league)
            league_of[a.guild] = league_of[b.guild] = league
            _row(rows, league).fund_open_milli = 0
            frame.changes.append(Change(league=league.league, kind="founded", guild=a.guild, city=a.city))
            frame.changes.append(Change(league=league.league, kind="joined", guild=b.guild, city=b.city))
            _bump(state, "leagues_founded")
            continue
        if (la is None) == (lb is None):
            continue                              # both members already: leagues never merge
        league, joiner = (la, b) if lb is None else (lb, a)
        lords = {m.lord for m in league.members}
        if (len(league.members) >= MAX_MEMBERS or joiner.lord in lords
                or any(_at_war(world, joiner.lord, lord) for lord in lords)):
            continue
        league.members.append(joiner)
        league_of[joiner.guild] = league
        _row(rows, league)
        frame.changes.append(Change(league=league.league, kind="joined", guild=joiner.guild, city=joiner.city))
        _bump(state, "joins")


def _dues(world, state, frame, rows, turn) -> None:
    guilds = world.guilds.guilds
    for league in state.leagues:
        if league.dues_turn == turn:
            raise RuntimeError("guild league dues settled twice in one turn")
        league.dues_turn = turn
        cap = FUND_CAP_PER_MEMBER * len(league.members)
        row = _row(rows, league)
        row.cap_milli = cap
        for m in sorted(league.members, key=lambda x: x.guild):
            room = cap - league.fund_milli
            if room <= 0:
                break
            g = guilds[m.guild]
            milli = min(math.floor(DUES_SHARE * _purse_milli(g)), DUES_CAP, room)
            if milli <= 0:
                continue
            _move_purse(g, "wealth", -milli)
            league.fund_milli += milli
            m.dues_milli += milli
            row.dues_milli += milli
            frame.dues.append(Dues(league=league.league, guild=m.guild, city=m.city, milli=milli))
            _bump(state, "dues_milli", milli)
            _bump(state, "dues_rows")


def phase10(world, acc, economy_result, agent_bridge):
    """After the cities and guilds ticks of this turn: departures, dissolutions,
    links, dormancy, claims, foundings and joins, dues."""
    state = _state(world)
    turn = int(world.turn)
    if state.frame_turn is not None and state.frame_turn >= turn:
        raise RuntimeError("guild leagues committed twice in one turn")
    t = state._turn
    notes = t.notes if t is not None and t.turn == turn else {}
    frame = LeagueFrame(turn=turn)
    rows: dict[int, LeagueRow] = {league.league: LeagueRow(league=league.league, founded_turn=league.founded_turn,
                                                             fund_open_milli=league.fund_milli)
                                  for league in state.leagues}
    cities = {c.settlement_id: c for c in world.cities.cities}
    _bump(state, "turns")
    _departures(world, state, frame, rows, cities, turn)
    _structure(world, state, frame, rows, turn)
    seen = _links(world, state, economy_result, cities, turn)
    for league in list(state.leagues):
        ids = sorted(m.guild for m in league.members)
        if any((a, b) in seen for i, a in enumerate(ids) for b in ids[i + 1:]):
            league.last_trade_turn = turn
        elif turn - league.last_trade_turn >= DORMANT_TURNS:
            _dissolve(world, state, league, "dormant", frame, rows, turn)
    _claims(world, state, frame, rows, notes, cities, turn)
    _formation(world, state, frame, rows, cities, turn)
    _dues(world, state, frame, rows, turn)
    living = {league.league: league for league in state.leagues}
    for lid in sorted(rows):
        row = rows[lid]
        league = living.get(lid)
        if league is not None:
            row.members = [m.model_copy() for m in league.members]
            row.fund_close_milli = league.fund_milli
            row.cap_milli = FUND_CAP_PER_MEMBER * len(league.members)
        if (row.fund_open_milli + row.dues_milli - row.payouts_milli - row.returned_milli - row.unclaimed_milli
                != row.fund_close_milli):
            raise RuntimeError(f"guild league {lid}'s fund does not close")
        frame.leagues.append(row)
    frame.links = len(state.links)
    state.frame, state.frame_turn = frame, turn
    state._turn = None
    return []


# ---------------------------------------------------------------------------
# Snapshot and reading
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """The completed turn's record, dated by ``source_turn``; ``frame`` is None
    when that turn was not observed (unknown, not zero)."""
    state = _state(world)
    source = world.turn - 1
    fresh = state.frame_turn == source and state.frame is not None
    return {
        "schema_version": 1, "stage": STAGE, "mode": state.mode, "source_turn": source,
        "frame": state.frame.model_dump() if fresh else None,
        "next_league": state.next_league,
        "dissolved": [{"league": x.league, "founded_turn": x.founded_turn, "dissolved_turn": x.dissolved_turn,
                       "reason": x.dissolved_reason} for x in state.dissolved],
        "dissolved_dropped": state.dissolved_dropped,
        "counters": {k: state.counters[k] for k in COUNTERS if k in state.counters},
        "log": [r.model_dump() for r in state.log], "log_dropped": state.log_dropped,
        "parameters": {"link_turns": LINK_TURNS, "link_window": LINK_WINDOW, "max_members": MAX_MEMBERS,
                       "dues_share": DUES_SHARE, "dues_cap_milli": DUES_CAP,
                       "fund_cap_per_member_milli": FUND_CAP_PER_MEMBER, "payout_cap_milli": PAYOUT_CAP,
                       "dormant_turns": DORMANT_TURNS, "units": "milli_purse"},
    }


FRAME_KEYS: tuple[str, ...] = ("turn", "leagues", "dues", "payouts", "changes", "links", "candidates")


def record_status(snapshot) -> tuple[str, dict | None]:
    """``absent``, ``malformed``, ``unobserved``, ``recorded_zero`` (observed; no
    league held money or changed, no dues or claims) or ``recorded``."""
    livelihoods = snapshot.get("livelihoods") if isinstance(snapshot, dict) else None
    if not isinstance(livelihoods, dict) or "guild_leagues" not in livelihoods:
        return "absent", None
    record = livelihoods["guild_leagues"]
    source = record.get("source_turn") if isinstance(record, dict) else None
    if (not isinstance(record, dict) or record.get("schema_version") != 1 or record.get("stage") != STAGE
            or record.get("mode") not in MODES or not isinstance(source, int) or isinstance(source, bool)
            or "frame" not in record):
        return "malformed", None
    frame = record["frame"]
    if frame is None:
        return "unobserved", None
    if (not isinstance(frame, dict) or any(k not in frame for k in FRAME_KEYS) or frame["turn"] != source
            or not all(isinstance(frame[k], list) for k in ("leagues", "dues", "payouts", "changes"))):
        return "malformed", None
    from pydantic import ValidationError
    try:
        LeagueFrame.model_validate(frame, strict=True)
    except ValidationError:
        return "malformed", None
    empty = not frame["leagues"] and not frame["dues"] and not frame["payouts"] and not frame["changes"]
    return ("recorded_zero" if empty else "recorded"), frame
