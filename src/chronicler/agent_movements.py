"""Movements grounded in people (``--agent-movements``).

Default off behind ``WorldState.agent_movements`` (CLI ``--agent-movements``
/ ``--no-agent-movements``, persisted on the world so a resumed run keeps its
setting). With the switch off nothing in this module runs, the bridge sends
no movement table, and every output is identical to the simulation without
it. See ``docs/integration/agent-movements.md``.

A movement is a set of agents (per-agent ``movement_id`` in the native pool)
sharing a grievance (its creed: ``commons`` for material, ``liberty`` for
autonomy, ``sect`` for spiritual needs) and a target: the ruler of the region
where it was founded. The native movement pass (``movements.rs``) moves
people: founding seeds, recruitment through bonds, co-residence and towns,
spread with migrants and merchants, lapse. This module decides, in Phase 10:

Emergence
    Where the aggrieved cluster (the native census) and a carrier exists: a
    great person, a city, or the boldest aggrieved agents.

Pressure and demands
    Strength (members' share of the target realm's adults) raises the
    creed's ally faction; at 10% the movement presents its demand and the
    ruler grants, refuses or suppresses.

Outcomes
    A reform satisfies the movement (relief of its members on the next
    ticks). A crackdown reuses the persecution memory and martyrdom. A
    refused or suppressed movement with a stronghold rises: a sect of the
    ruler's faith breaks with the church through ``religion.fire_schism``;
    others rise in revolt (members' rebel utility on the next tick), resolved
    as secession (liberty, a weak ruler, through the free-city transfer
    helper), concession or a crushing.

Decay
    Movements fade below three members, end as won after a reform, crushed
    after crackdowns, dissolved when their target is gone.

Identity: region = index in ``world.regions``, civ = index in
``world.civilizations``, movement = index in ``MovementState.movements``
(agents carry index + 1). All randomness comes from
``random.Random(stable_hash_int("agent_movements", <namespace>, seed, turn,
...))``. Stat changes use the existing accumulator categories.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Iterable

from chronicler.agent_movements_state import (
    COMMONS, COUNTER_KEYS, CREED_NAMES, CRUSHED, DISSOLVED, ENDED, END_NAMES, FADED, FISCAL,
    GATHERING, HOME_RULE, IN_FORCE, INQUISITION, LAPSED, LIBERTY, LIVING, NEGLECT, OPPOSITION,
    PRESSING, REFORM_NAMES, RELIEF, REPEAL_NAMES, RISING, RULER, SATISFIED, SCHISM, SECEDED,
    SECT, STAGE_NAMES, SUPPRESSED, TOLERATION, WON, Movement, MovementState, Reform,
    agent_movements_on,
)
from chronicler.utils import stable_hash_int

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Civilization, Event, WorldState


# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE]; documented in docs/integration/agent-movements.md)
# ---------------------------------------------------------------------------

#: Default for worlds created by the CLI/batch/live entry points.
DEFAULT_ENABLED_FOR_NEW_WORLDS = False

# Emergence (from the native grievance census).
EMERGE_FROM_TURN = 10           # no founding in the start-up turns
EMERGE_MIN_AGGRIEVED = 5
EMERGE_SHARE = 0.20
EMERGE_CHANCE = 0.03            # per candidate at EMERGE_SHARE, scaled by share
EMERGE_CHANCE_CAP = 0.25
CARRIER_PROPHET = 2.0           # a prophet founding a sect
CARRIER_GREAT_PERSON = 1.5
MAX_PER_CIV = 2                 # living movements opposing one ruler
EMERGE_COOLDOWN = 20            # turns after a movement of the creed against the ruler
MAX_LIVING = 8                  # living movements in the world
#: M16b idea values that fit each creed (commons, liberty, sect).
IDEA_VALUES = (
    frozenset({"wealth", "progress", "unity"}),
    frozenset({"freedom", "independence", "honor"}),
    frozenset({"faith", "tradition", "knowledge"}),
)
IDEA_APPEAL = 1.25

# Life cycle.
FOUNDING_GRACE = 2              # turns before a movement can fade
FADE_MEMBERS = 3
FADE_TURNS = 5
SPREAD_MIN = 2                  # members that make a region "reached"
GRIEVANCE_CAP = 1.5
ADULT_AGE = 16

# Pressure on factions while strength is at least PRESSURE_SHARE.
PRESSURE_SHARE = 0.05
VOICE_PER_STRENGTH = 0.05
VOICE_CAP = 0.01

# Demands and the ruler's response.
DEMAND_SHARE = 0.10
DEMAND_MIN = 5
DEMAND_INTERVAL = 12
DEMAND_MIN_AGE = 5              # turns of gathering before the first demand
GRANT_BASE = 0.35
GRANT_TRAIT = 0.2
GRANT_WEAK = 0.15               # ruler stability below GRANT_WEAK_STABILITY
GRANT_WEAK_STABILITY = 30
GRANT_STRENGTH = 0.5            # x (strength - DEMAND_SHARE)
GRANT_FACTION = 0.5             # x (ally faction influence - 0.25)
GRANT_LEGITIMACY = 0.3          # x (0.5 - legitimacy), with governance
GRANT_MIN, GRANT_MAX = 0.05, 0.9
SUPPRESS_BASE = 0.35
SUPPRESS_TRAIT = 0.2
SUPPRESS_FACTION = 0.5          # x (military - 0.25); sects also x (clergy - 0.25)
CONCILIATORY_TRAITS = frozenset({"cautious", "calculating", "shrewd", "opportunistic"})
HARSH_TRAITS = frozenset({"aggressive", "zealous", "stubborn", "bold"})

# Reforms (relief of the members happens natively, RELIEF_TURNS after the grant).
REFORM_TREASURY = 8
REFORM_TREASURY_PER_STRENGTH = 40
REFORM_STABILITY = 3            # liberty: concessions weaken central authority
REFORM_CLERGY = 0.03            # sect: toleration costs the clergy
RELIEF_TURNS = 20               # = movements.rs RELIEF_TURNS

# Refusals and crackdowns.
REFUSAL_GRIEVANCE = 0.25
REFUSAL_STABILITY = 1
CRACKDOWN_GRIEVANCE = 0.35
CRACKDOWN_STABILITY = 1
CRACKDOWN_MILITARY = 0.02
SUPPRESS_TURNS = 10
MARTYR_SHARE = 0.1
MARTYR_CAP = 5
MARTYR_APPEAL = 0.1
MARTYR_APPEAL_CAP = 2.0

# Risings (commons, liberty) and schisms (sects): grievance, stronghold
# share and members in the stronghold, by creed.
RISE_GRIEVANCE = (0.5, 0.5, 0.25)
RISE_SHARE = (0.25, 0.25, 0.20)
RISE_MIN = (5, 5, 4)
RISE_COOLDOWN = 20
RISING_STABILITY = 5
SECEDE_STABILITY = 30            # = cities' free-city threshold
SECEDE_TURNOUT = 0.3
SECEDE_LORD_LOSS = 10
CONCESSION_STABILITY = 30
CONCESSION_CHANCE = 0.35
OFF_MODE_TURNOUT = 0.5          # turnout of a rising without agents
NEW_CIV_STABILITY = 45
NEW_CIV_ASABIYA = 0.7
NEW_CIV_TRAITS = ("bold", "visionary", "zealous")
NEW_CIV_VALUE = "independence"
CIV_HEADROOM = 4                # no new polity this close to the native civ limit

# Appeal (native recruitment multiplier).
APPEAL_LEADER = 1.5
APPEAL_GRIEVANCE = 0.5

# Lasting reforms (a grant enacts one; the agents it covers read their creed
# need with movements.rs REFORM_NEED_CREDIT). Governance institutions they
# enact or uphold (relief, home rule; toleration has none).
REFORM_INSTITUTIONS = ("commons_management", "written_law", "")
#: Faction that opposes a reform without an institution (relief, home rule,
#: toleration); with an institution the governance opposition applies.
REFORM_OPPONENTS = ("merchant", "military", "clergy")
RELIEF_UPKEEP = 0.75             # treasury per realm region a turn (= the institution's rate)
ARREARS_TURNS = 3                # unpaid turns that end a relief without an institution
REPEAL_FACTION_SHARE = 0.40      # = institutions.FACTION_REPEAL_THRESHOLD
REPEAL_FACTION = 0.03            # chance a turn while the opponent is above the share
REPEAL_RULER = 0.03              # chance a new ruler repeals it ...
REPEAL_RULER_HARSH = 0.25        # ... a harsh one
REPEAL_MEMORY = 60               # turns a repeal is remembered against its ruler
REPEAL_EMERGE = 2.0              # founding chance of a restoration movement

# Leaders: a movement that presses its demand or rises without a living
# leader raises one from its boldest member in the stronghold (a native
# promotion; the person appears on the next turn).
LEADER_MIN_MEMBERS = 8
LEADER_RETRY = 3                 # turns before another candidate is queued
LEADER_ROLE_GENERAL, LEADER_ROLE_PROPHET = 0, 3   # native CharacterRole ids
SOLDIER = 1                      # occupation id

HISTORY_CAP = 60
QUANTUM_DIGITS = 4

#: Counters of the ends not counted by their own outcome (secessions and
#: schisms are).
_END_COUNTERS = {FADED: "faded", WON: "won", CRUSHED: "broken", DISSOLVED: "dissolved"}

# Native table sentinels (movements.rs).
NO_REGION = 0xFFFF
NO_FAITH = 0xFF
NO_RELIEF = 0xFFFF

_NAMES = (
    ("the {region} Bread League", "the Commons of {region}", "the Ploughmen's League of {region}",
     "the Levellers of {region}"),
    ("the Sons of {region}", "the {region} Covenant", "the Free {region} Movement",
     "the {region} Brotherhood"),
    ("the Penitents of {region}", "the Brethren of the Last Days", "the Reformers of {region}",
     "the Seekers of {region}"),
)
_DEMANDS = (
    "relief from hunger and dues",
    "that {region} keep its own customs and officers",
    "freedom to worship in the {faith}",
)
_REFORMS = (
    "{ruler} grants {name} relief: remitted dues and grain from the stores{cost}",
    "{ruler} grants {region} its own customs and officers at {name}'s demand",
    "{ruler} tolerates {name} and its worship",
)


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def agent_movements_enabled(world) -> bool:
    """True only for a real movement state (mocks and ``None`` read as off)."""
    return agent_movements_on(world)


def set_agent_movements_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (an empty state; movements are founded as grievances cluster)
    or disable (dropping every movement record)."""
    if enabled:
        if world.agent_movements is None:
            world.agent_movements = MovementState()
        return
    world.agent_movements = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(x: float) -> float:
    return round(x, QUANTUM_DIGITS)


def _rng(world, namespace: str, *parts) -> random.Random:
    return random.Random(stable_hash_int("agent_movements", namespace, world.seed, world.turn, *parts))


def _bump(state: MovementState, key: str, n: float = 1) -> None:
    state.counters[key] = round(state.counters.get(key, 0) + n, 4)


def _living(state: MovementState) -> list[tuple[int, Movement]]:
    return [(i, m) for i, m in enumerate(state.movements) if m.stage != ENDED]


def _faith_name(world, faith_id: int) -> str | None:
    belief = next((b for b in world.belief_registry if b.faith_id == faith_id), None)
    return belief.name if belief is not None else None


class _Observation:
    """Phase 10 rows: adults per region and, per movement id, its members."""

    def __init__(self, nreg: int, mid, region, age, ids, bold, belief, civ=None, occupation=None) -> None:
        import numpy as np
        self.nreg = nreg
        self.mid, self.region, self.ids, self.bold, self.belief = mid, region, ids, bold, belief
        # Optional (leaders only): civ affinity and occupation.
        self.civ, self.occupation = civ, occupation
        adult = age >= ADULT_AGE
        self.adults = np.bincount(region[adult], minlength=nreg)[:nreg]

    def counts(self, movement_id: int):
        import numpy as np
        mask = self.mid == movement_id
        return np.bincount(self.region[mask], minlength=self.nreg)[:self.nreg], mask


def _observe(phase10, nreg: int) -> _Observation | None:
    rows = getattr(phase10, "agents", None) if phase10 is not None else None
    if rows is None:
        return None
    import numpy as np
    names = ("movement_id", "region", "age", "id", "boldness", "belief")
    arrays = rows.arrays(*names)
    if arrays is None:
        # Row path (the columnar shortcut unavailable): the same values.
        if not all(rows.has(name) for name in names):
            return None
        cols = [rows.ints(n) for n in ("movement_id", "region", "age", "id", "belief")]
        bold = rows.floats("boldness")
        if any(v is None for col in (*cols, bold) for v in col):
            return None
        mid, region, age, ids, belief = (np.asarray(c, dtype=np.int64) for c in cols)
        arrays = (mid, region, age, ids, np.asarray(bold, dtype=np.float64), belief)
    mid, region, age, ids, bold, belief = arrays
    extra = rows.arrays("civ_affinity", "occupation") if hasattr(rows, "arrays") else None
    civ = occupation = None
    if extra is not None:
        civ, occupation = (np.asarray(a, dtype=np.int64) for a in extra)
    return _Observation(
        nreg, np.asarray(mid, dtype=np.int64), np.asarray(region, dtype=np.int64),
        np.asarray(age, dtype=np.int64), np.asarray(ids, dtype=np.int64),
        np.asarray(bold, dtype=np.float64), np.asarray(belief, dtype=np.int64),
        civ, occupation,
    )


def _grievance_census(agent_bridge, nreg: int):
    """Native census of the last tick: per region (adults, aggrieved per
    creed), or None without an agent pool."""
    sim = getattr(agent_bridge, "_sim", None) if agent_bridge is not None else None
    if sim is None or not hasattr(sim, "get_movement_stats"):
        return None
    import pyarrow as pa
    regions, _movements = sim.get_movement_stats()
    batch = pa.record_batch(regions)
    if batch.num_rows == 0:
        return None
    adults = [0] * nreg
    aggrieved = [[0, 0, 0] for _ in range(nreg)]
    cols = [batch.column(n).to_pylist() for n in (
        "region_id", "adults", "aggrieved_commons", "aggrieved_liberty", "aggrieved_sect")]
    for r, n, c, l, s in zip(*cols):
        if r < nreg:
            adults[r] = n
            aggrieved[r] = [c, l, s]
    return adults, aggrieved


class _Tick:
    def __init__(self, world, acc, agent_bridge, phase10) -> None:
        self.world = world
        self.acc = acc
        self.bridge = agent_bridge
        self.state: MovementState = world.agent_movements
        self.events: list = []
        nreg = len(world.regions)
        self.obs = _observe(phase10, nreg)
        rebels = None
        if agent_bridge is not None and hasattr(agent_bridge, "last_tick_unrest_by_region"):
            rebels = agent_bridge.last_tick_unrest_by_region()[0]
        self.rebels: dict[int, int] | None = rebels
        self.region_index = {r.name: i for i, r in enumerate(world.regions)}

    def civ(self, idx: int):
        civs = self.world.civilizations
        return civs[idx] if 0 <= idx < len(civs) else None

    def civ_index(self, name: str) -> int:
        from chronicler.utils import civ_index
        return civ_index(self.world, name)


def _emit(t: _Tick, event_type: str, actors: Iterable[str], description: str, *,
          importance: int = 5, region: str | None = None,
          causes: Iterable[str | None] = ()) -> "Event":
    from chronicler import provenance
    from chronicler.models import Event
    ev = Event(turn=t.world.turn, event_type=event_type,
               actors=[a for a in actors if a], description=description,
               importance=importance, region=region)
    provenance.cite(ev, *causes)
    provenance.observe_now(t.world, ev)
    t.events.append(ev)
    return ev


def _note(m: Movement, turn: int, kind: str, event_id: str = "") -> None:
    m.history.append((turn, kind, event_id))
    if len(m.history) > HISTORY_CAP:
        del m.history[1]   # keep the founding


def _key(i: int, what: str) -> str:
    from chronicler import provenance as prov
    return prov.key("agent_movement", f"{i}:{what}")


def _remember(t: _Tick, i: int, what: str, ev) -> None:
    from chronicler import provenance as prov
    prov.remember(t.world, _key(i, what), ev)


def _recall(t: _Tick, i: int, what: str, within: int | None = None):
    from chronicler import provenance as prov
    return prov.recall(t.world, _key(i, what), within=within)


def _region_causes(t: _Tick, region_name: str) -> list[str | None]:
    """The region's latest grievances: famine, epidemic, occupation, conquest, persecution."""
    from chronicler import provenance as prov
    w = t.world
    return [
        prov.open_episode(w, "famine", region_name),
        prov.recall(w, prov.key("pandemic", region_name), within=10),
        prov.recall(w, prov.key("occupation", region_name), within=20),
        prov.recall(w, prov.key("conquest", region_name), within=20),
        prov.recall(w, prov.key("persecution", region_name), within=10),
    ]


def _add_stat(t: _Tick, civ, stat: str, delta: float, category: str) -> None:
    from chronicler.war.common import add_stat
    add_stat(t, civ, stat, delta, category)


def _shift_faction(civ, faction, amount: float) -> None:
    from chronicler.factions import normalize_influence
    civ.factions.influence[faction] = civ.factions.influence.get(faction, 0.0) + amount
    normalize_influence(civ.factions)


def _ally_faction(creed: int):
    from chronicler.models import FactionType
    return (FactionType.CULTURAL, FactionType.MILITARY, FactionType.CLERGY)[creed]


def _influence(civ, faction) -> float:
    return float(civ.factions.influence.get(faction, 0.25))


def appeal(m: Movement, leader_alive: bool) -> float:
    """Native recruitment multiplier of a movement."""
    a = APPEAL_LEADER if leader_alive else 1.0
    a *= min(MARTYR_APPEAL_CAP, 1.0 + MARTYR_APPEAL * m.martyrs)
    a *= 1.0 + APPEAL_GRIEVANCE * min(1.0, m.grievance)
    if m.idea:
        a *= IDEA_APPEAL
    return a


def _find_great_person(world, name: str):
    if not name:
        return None
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if gp.name == name:
                return gp
    for gp in world.retired_persons:
        if gp.name == name:
            return gp
    return None


def _leader_alive(world, m: Movement) -> bool:
    gp = _find_great_person(world, m.leader)
    return gp is not None and gp.alive


# ---------------------------------------------------------------------------
# The tick (Phase 10, after cities)
# ---------------------------------------------------------------------------

def tick_agent_movements(world: "WorldState", events: Iterable["Event"] = (), acc=None, *,
                         phase10=None, agent_bridge=None) -> list["Event"]:
    """Phase 10: lasting reforms (upkeep, lapse, repeal), then each
    movement: observe members, its leader, fade, pressure, demands and
    responses, risings and their resolution, schisms and secessions; then
    emergence. Returns the turn's movement events."""
    if not agent_movements_on(world):
        return []
    t = _Tick(world, acc, agent_bridge, phase10)
    _tick_reforms(t)
    for i, m in _living(t.state):
        _update(t, i, m)
    census = _grievance_census(agent_bridge, len(world.regions))
    if census is not None and world.turn >= EMERGE_FROM_TURN:
        _emerge(t, census)
    t.state.last_tick_turn = world.turn
    return t.events


def _observe_movement(t: _Tick, i: int, m: Movement, civ) -> None:
    """Members, their regions, strength and stronghold from the Phase 10 rows
    (kept from the last observation without agent rows)."""
    obs = t.obs
    if obs is None:
        # No agent rows: the saved members stand; members in regions the
        # target no longer holds stop counting.
        held = {ri for ri, r in enumerate(t.world.regions) if r.controller == civ.name}
        in_realm = sum(c for r, c in m.member_regions if r in held)
        if m.members and in_realm < m.members:
            m.strength = _q(m.strength * in_realm / m.members)
        if m.stronghold >= 0 and m.stronghold not in held:
            m.stronghold, m.stronghold_share = -1, 0.0
        return
    import numpy as np
    counts, mask = obs.counts(i + 1)
    m.members = int(counts.sum())
    m.peak_members = max(m.peak_members, m.members)
    m.member_regions = [[int(r), int(c)] for r, c in enumerate(counts.tolist()) if c > 0]
    if m.members:
        beliefs = obs.belief[mask]
        beliefs = beliefs[(beliefs >= 0) & (beliefs < NO_FAITH)]
        if beliefs.size:
            m.faith = int(np.argmax(np.bincount(beliefs)))
    realm = [ri for ri, r in enumerate(t.world.regions) if r.controller == civ.name]
    realm_adults = int(sum(int(obs.adults[ri]) for ri in realm))
    realm_members = int(sum(int(counts[ri]) for ri in realm))
    m.strength = _q(realm_members / realm_adults) if realm_adults else 0.0
    best, best_share = -1, 0.0
    for ri in realm:
        n = int(obs.adults[ri])
        if n <= 0 or counts[ri] <= 0:
            continue
        share = int(counts[ri]) / n
        if share > best_share:
            best, best_share = ri, share
    m.stronghold, m.stronghold_share = best, _q(best_share)


def _members_in(m: Movement, region: int) -> int:
    for r, c in m.member_regions:
        if r == region:
            return c
    return 0


def _update(t: _Tick, i: int, m: Movement) -> None:
    world = t.world
    turn = world.turn
    civ = t.civ(m.target)
    if civ is None or not civ.regions:
        _end(t, i, m, DISSOLVED, f"{m.name} dissolves: the realm it opposed is gone")
        return
    _observe_movement(t, i, m, civ)
    _record_spread(t, i, m)
    _mourn_leader(t, i, m, civ)
    _lead(t, i, m, civ)
    if turn - m.founded_turn > FOUNDING_GRACE:
        m.low_turns = m.low_turns + 1 if m.members < FADE_MEMBERS else 0
        if m.low_turns >= FADE_TURNS:
            if m.stage == SATISFIED:
                _end(t, i, m, WON, f"{m.name} disbands, its demand met")
            elif m.stage == SUPPRESSED:
                _end(t, i, m, CRUSHED, f"{m.name} is broken by {civ.name}")
            else:
                _end(t, i, m, FADED, f"{m.name} fades away")
            return
    if m.stage in (GATHERING, PRESSING, SUPPRESSED, RISING):
        _pressure(t, m, civ)
    if m.stage == RISING:
        if m.rising_turn is not None and turn > m.rising_turn:
            _resolve_rising(t, i, m, civ)
        return
    if m.stage == SATISFIED:
        return
    if m.stage == SUPPRESSED:
        if turn - m.stage_turn < SUPPRESS_TURNS:
            return
        m.stage = PRESSING if m.demands else GATHERING
        m.stage_turn = turn
    if _can_rise(t, m):
        if m.creed == SECT and _schism(t, i, m, civ):
            return
        _rise(t, i, m, civ)
        return
    if (m.strength >= DEMAND_SHARE and m.members >= DEMAND_MIN
            and turn - m.founded_turn >= DEMAND_MIN_AGE
            and turn - m.last_demand >= DEMAND_INTERVAL):
        _demand(t, i, m, civ)


def _record_spread(t: _Tick, i: int, m: Movement) -> None:
    for r, c in m.member_regions:
        if c >= SPREAD_MIN and r not in m.regions_reached:
            m.regions_reached.append(r)
            region = t.world.regions[r].name
            ev = _emit(t, "movement_spread", [t.civ(m.target).name],
                       f"{m.name} spreads to {region} ({c} members)",
                       importance=3, region=region, causes=(_recall(t, i, "founded"),))
            _note(m, t.world.turn, "spread", ev.event_id)


def _mourn_leader(t: _Tick, i: int, m: Movement, civ) -> None:
    if not m.leader or m.leader_mourned:
        return
    gp = _find_great_person(t.world, m.leader)
    if gp is None or gp.alive:
        return
    m.leader_mourned = True
    m.martyrs += 1
    _bump(t.state, "martyrs")
    region = t.world.regions[m.home_region].name
    ev = _emit(t, "movement_martyr", [civ.name, m.leader],
               f"The death of {m.leader} makes a martyr for {m.name}",
               importance=5, region=region, causes=(_recall(t, i, "founded"),))
    _note(m, t.world.turn, "martyr", ev.event_id)


def _gp_by_agent(world, agent_id: int):
    """The living great person who is agent ``agent_id``, or None."""
    for civ in world.civilizations:
        for gp in civ.great_persons:
            if gp.agent_id == agent_id and gp.alive and gp.active:
                return gp
    return None


def _lead(t: _Tick, i: int, m: Movement, civ) -> None:
    """A movement that has pressed its demand or risen, with no living
    leader, raises one: its boldest member in the stronghold (a member of a
    living civ). A great person already is one; anyone else is promoted
    natively (a prophet for a sect or a civilian, a general for a soldier)
    and leads from the next turn."""
    world = t.world
    if m.leader_candidate:
        gp = _gp_by_agent(world, m.leader_candidate)
        if gp is not None:
            _install_leader(t, i, m, civ, gp)
            return
        if m.leader_turn is not None and world.turn - m.leader_turn < LEADER_RETRY:
            return
        m.leader_candidate, m.leader_turn = 0, None
    if m.leader and _leader_alive(world, m):
        return
    if (m.demands < 1 and m.stage != RISING) or m.members < LEADER_MIN_MEMBERS or m.stage == SATISFIED:
        return
    obs = t.obs
    sim = getattr(t.bridge, "_sim", None) if t.bridge is not None else None
    if obs is None or obs.civ is None or sim is None or not hasattr(sim, "queue_movement_leaders"):
        return
    import numpy as np
    mask = obs.mid == i + 1
    if m.stronghold >= 0:
        mask &= obs.region == m.stronghold
    living = {ci for ci, c in enumerate(world.civilizations) if c.regions}
    leading = {mm.leader_agent for mm in t.state.movements if mm.stage != ENDED and mm.leader}
    sel = [j for j in np.flatnonzero(mask).tolist()
           if int(obs.civ[j]) in living and int(obs.ids[j]) not in leading]
    if not sel:
        return
    j = min(sel, key=lambda j: (-float(obs.bold[j]), int(obs.ids[j])))
    agent_id = int(obs.ids[j])
    gp = _gp_by_agent(world, agent_id)
    if gp is not None:
        _install_leader(t, i, m, civ, gp)
        return
    soldier = m.creed != SECT and int(obs.occupation[j]) == SOLDIER
    sim.queue_movement_leaders([agent_id], [LEADER_ROLE_GENERAL if soldier else LEADER_ROLE_PROPHET])
    m.leader_candidate, m.leader_turn = agent_id, world.turn


def _install_leader(t: _Tick, i: int, m: Movement, civ, gp) -> None:
    from chronicler.great_persons import _append_deed
    world = t.world
    region = world.regions[m.stronghold if m.stronghold >= 0 else m.home_region].name
    m.leader, m.leader_agent = gp.name, int(gp.agent_id or 0)
    m.leader_candidate, m.leader_turn = 0, None
    m.leader_mourned = False
    gp.region = region
    _append_deed(gp, f"Rose to lead {m.name}", region=region, turn=world.turn, civ=gp.civilization)
    _bump(t.state, "leaders")
    ev = _emit(t, "movement_leader", [civ.name, gp.name],
               f"{gp.name} rises to lead {m.name} in {region}", importance=5, region=region,
               causes=(_recall(t, i, "rising", within=10), _recall(t, i, "demand", within=40),
                       _recall(t, i, "founded")))
    from chronicler import provenance as prov
    prov.remember(world, prov.key("gp", gp.name), ev)
    _note(m, world.turn, "leader", ev.event_id)


def _end(t: _Tick, i: int, m: Movement, kind: int, text: str, *, causes=()) -> None:
    m.stage = ENDED
    m.stage_turn = t.world.turn
    m.end = kind
    m.ended_turn = t.world.turn
    counter = _END_COUNTERS.get(kind)
    if counter is not None:
        _bump(t.state, counter)
    civ = t.civ(m.target)
    ev = _emit(t, "movement_end", [civ.name if civ is not None else ""], text,
               importance=5 if kind == WON else 4,
               region=t.world.regions[m.home_region].name, causes=causes)
    _note(m, t.world.turn, "ended", ev.event_id)


def _pressure(t: _Tick, m: Movement, civ) -> None:
    if m.strength < PRESSURE_SHARE:
        return
    _shift_faction(civ, _ally_faction(m.creed), min(VOICE_CAP, VOICE_PER_STRENGTH * m.strength))


def _can_rise(t: _Tick, m: Movement) -> bool:
    c = m.creed
    if m.grievance < RISE_GRIEVANCE[c] or m.stronghold < 0:
        return False
    if m.stronghold_share < RISE_SHARE[c] or _members_in(m, m.stronghold) < RISE_MIN[c]:
        return False
    return t.world.turn - m.last_rising >= RISE_COOLDOWN


def grant_chance(t: _Tick, m: Movement, civ) -> float:
    """Chance that the ruler grants the movement's demand."""
    from chronicler.models import FactionType
    p = GRANT_BASE
    trait = getattr(civ.leader, "trait", "")
    if trait in CONCILIATORY_TRAITS:
        p += GRANT_TRAIT
    elif trait in HARSH_TRAITS:
        p -= GRANT_TRAIT
    if civ.stability < GRANT_WEAK_STABILITY:
        p += GRANT_WEAK
    p += GRANT_STRENGTH * (m.strength - DEMAND_SHARE)
    if m.creed == COMMONS:
        p += GRANT_FACTION * (_influence(civ, FactionType.CULTURAL) - 0.25)
    elif m.creed == LIBERTY:
        p -= GRANT_FACTION * (_influence(civ, FactionType.MILITARY) - 0.25)
    else:
        p -= GRANT_FACTION * (_influence(civ, FactionType.CLERGY) - 0.25)
    gov = getattr(civ, "governance", None)
    if gov is not None and getattr(t.world, "governance", None) is not None:
        p += GRANT_LEGITIMACY * (0.5 - float(gov.ruler_legitimacy))
    return min(GRANT_MAX, max(GRANT_MIN, p))


def suppress_chance(m: Movement, civ) -> float:
    """Chance that a ruler who does not grant suppresses (else refuses)."""
    from chronicler.models import FactionType
    p = SUPPRESS_BASE
    if getattr(civ.leader, "trait", "") in HARSH_TRAITS:
        p += SUPPRESS_TRAIT
    p += SUPPRESS_FACTION * (_influence(civ, FactionType.MILITARY) - 0.25)
    if m.creed == SECT:
        p += SUPPRESS_FACTION * (_influence(civ, FactionType.CLERGY) - 0.25)
    return min(GRANT_MAX, max(GRANT_MIN, p))


def _demand_text(world, m: Movement) -> str:
    region = world.regions[m.home_region].name
    state = world.agent_movements
    if state is not None and 0 <= m.restores < len(state.reforms):
        return f"the restoration of {reform_name(world, state.reforms[m.restores])}"
    faith = _faith_name(world, m.faith)
    if m.creed == SECT:
        if faith is None:
            return "freedom to worship as they believe"
        target = world.civilizations[m.target] if 0 <= m.target < len(world.civilizations) else None
        if target is not None and getattr(target, "civ_majority_faith", NO_FAITH) == m.faith:
            return f"the reform of the {faith}"
    return _DEMANDS[m.creed].format(region=region, faith=faith)


def _demand(t: _Tick, i: int, m: Movement, civ) -> None:
    world = t.world
    m.demands += 1
    m.last_demand = world.turn
    if m.stage != PRESSING:
        m.stage = PRESSING
        m.stage_turn = world.turn
    _bump(t.state, "demands")
    region = world.regions[m.stronghold if m.stronghold >= 0 else m.home_region].name
    ev = _emit(t, "movement_demand", [civ.name],
               f"{m.name}, {m.members} strong ({int(round(100 * m.strength))}% of the people of "
               f"{civ.name}), demands {_demand_text(world, m)}",
               importance=5, region=region,
               causes=(_recall(t, i, "founded"), _recall(t, i, "refused", within=40),
                       _recall(t, i, "crackdown", within=40)))
    _remember(t, i, "demand", ev)
    _note(m, world.turn, "demand", ev.event_id)
    rng = _rng(world, "response", i)
    if rng.random() < grant_chance(t, m, civ):
        _reform(t, i, m, civ, causes=(ev.event_id,))
    elif m.stronghold >= 0 and rng.random() < suppress_chance(m, civ):
        _crackdown(t, i, m, civ, causes=(ev.event_id,))
    else:
        _refuse(t, i, m, civ, ev)


def _reform(t: _Tick, i: int, m: Movement, civ, *, concession: bool = False, causes=()) -> None:
    world = t.world
    cost = 0
    if m.creed == COMMONS:
        cost = min(int(REFORM_TREASURY + REFORM_TREASURY_PER_STRENGTH * m.strength),
                   max(0, int(civ.treasury)))
        if cost > 0:
            _add_stat(t, civ, "treasury", -cost, "keep")
            _bump(t.state, "relief_cost", cost)
    elif m.creed == LIBERTY:
        _add_stat(t, civ, "stability", -REFORM_STABILITY, "guard-shock")
    else:
        from chronicler.models import FactionType
        _shift_faction(civ, FactionType.CLERGY, -REFORM_CLERGY)
    m.stage = SATISFIED
    m.stage_turn = world.turn
    m.reform_turn = world.turn
    m.grievance = 0.0
    _bump(t.state, "concessions" if concession else "reforms")
    region = world.regions[m.home_region].name
    text = _REFORMS[m.creed].format(ruler=civ.name, name=m.name, region=region,
                                    cost=f" ({cost} from the treasury)" if cost else "")
    lasting = _enact(t, i, m, civ)
    if lasting is not None:
        text += lasting[2]
    if concession:
        text = f"After the rising, {text}"
    restored = t.state.reforms[m.restores] if 0 <= m.restores < len(t.state.reforms) else None
    ev = _emit(t, "movement_concession" if concession else "movement_reform", [civ.name], text,
               importance=6, region=region,
               causes=(*causes, restored.repeal_event_id if restored is not None else None))
    _note(m, world.turn, "concession" if concession else "reform", ev.event_id)
    if lasting is not None:
        k, created, _suffix, charter_region = lasting
        r = t.state.reforms[k]
        if created:
            r.event_id = ev.event_id
            from chronicler import provenance as prov
            prov.remember(world, _reform_key(k), ev)
        if charter_region >= 0:
            _charter(t, k, r, charter_region, ev)


def _refuse(t: _Tick, i: int, m: Movement, civ, demand) -> None:
    world = t.world
    m.grievance = _q(min(GRIEVANCE_CAP, m.grievance + REFUSAL_GRIEVANCE))
    _add_stat(t, civ, "stability", -REFUSAL_STABILITY, "guard-shock")
    _bump(t.state, "refusals")
    ev = _emit(t, "movement_refused", [civ.name], f"{civ.name} refuses {m.name}",
               importance=4, region=demand.region, causes=(demand.event_id,))
    _remember(t, i, "refused", ev)
    _note(m, world.turn, "refused", ev.event_id)


# ---------------------------------------------------------------------------
# Lasting reforms
# ---------------------------------------------------------------------------

_PRETTY_INSTITUTION = {"commons_management": "Commons Management", "written_law": "Written Law"}


def _reform_key(k: int, what: str = "granted") -> str:
    from chronicler import provenance as prov
    return prov.key("agent_reform", f"{k}:{what}")


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def reform_name(world, r: Reform) -> str:
    """How the record and the narration name a reform."""
    if r.kind == RELIEF:
        return "the poor relief"
    if r.kind == HOME_RULE:
        names = [world.regions[ri].name for ri in r.regions if 0 <= ri < len(world.regions)]
        return f"the home rule of {_join(names)}" if names else "the home rule"
    faith = _faith_name(world, r.faith)
    if r.church:
        return f"the reform of the {faith}" if faith else "the reform of the church"
    return f"the toleration of the {faith}" if faith else "the toleration"


def _in_force(state: MovementState, civ: int, kind: int, faith: int) -> int | None:
    """Index of the reform of ``kind`` in force in ``civ`` (toleration: of ``faith``)."""
    for k, r in enumerate(state.reforms):
        if r.repeal == IN_FORCE and r.civ == civ and r.kind == kind and (kind != TOLERATION or r.faith == faith):
            return k
    return None


def _governance(world, civ):
    """The civ's governance carry, or None with governance off."""
    if getattr(world, "governance", None) is None:
        return None
    return getattr(civ, "governance", None)


def _active_institutions(gov) -> set[str]:
    return {inst.institution_type for inst in gov.institutions} if gov is not None else set()


def _institutionalize(t: _Tick, civ, kind: int) -> tuple[str, bool]:
    """Enact the reform's governance institution, or uphold it when active:
    (institution, enacted here). ("", False) without one: toleration, no
    governance, or no free place (three institutions, or a conflict).
    Effective N+1, funded and resolved by the governance runtime."""
    name = REFORM_INSTITUTIONS[kind]
    gov = _governance(t.world, civ)
    if not name or gov is None:
        return "", False
    if name in _active_institutions(gov):
        return name, False
    from chronicler import institutions as g01
    from chronicler.governance_runtime import INSTITUTION_COEFFICIENTS, _log_institution
    from chronicler.governance_state import GovernanceInstitution
    itype = g01.InstitutionType(name)
    active = {g01.InstitutionType(x) for x in _active_institutions(gov)}
    if len(active) >= g01.MAX_ACTIVE_INSTITUTIONS or g01.INSTITUTION_CONFLICTS[itype] & active:
        return "", False
    cost = g01.enforcement_cost(institution_type=itype, coefficients=INSTITUTION_COEFFICIENTS,
                                region_count=len(civ.regions), trade_route_count=0)
    gov.institutions.append(GovernanceInstitution(
        institution_type=name, enacted_turn=t.world.turn, legitimacy=1.0, enforcement_cost=cost,
        opposing_faction=INSTITUTION_COEFFICIENTS.rule(itype).opposing_faction.value))
    order = list(g01.InstitutionType)
    gov.institutions.sort(key=lambda x: order.index(g01.InstitutionType(x.institution_type)))
    gov.institutions_enacted_total += 1
    _log_institution(gov, t.world.turn, itype, "enacted")
    return name, True


def _abolish_institution(t: _Tick, civ, name: str) -> None:
    """A ruler's repeal takes the institution the reform enacted with it."""
    gov = _governance(t.world, civ)
    if gov is None or name not in _active_institutions(gov):
        return
    from chronicler import institutions as g01
    from chronicler.governance_runtime import _log_institution
    gov.institutions = [x for x in gov.institutions if x.institution_type != name]
    gov.institutions_repealed_total += 1
    _log_institution(gov, t.world.turn, g01.InstitutionType(name), "repealed")


def _last_institution_kind(gov, name: str) -> str:
    for entry in reversed(gov.institution_log if gov is not None else []):
        if len(entry) >= 3 and entry[1] == name:
            return str(entry[2])
    return ""


def _enact(t: _Tick, i: int, m: Movement, civ):
    """Make a grant a lasting reform: a new one, or one in force extended.
    Returns (reform index, created, text for the grant, region whose city
    gains a charter or -1), or None when nothing lasting can be granted."""
    world, state = t.world, t.state
    kind = m.creed
    region = m.stronghold if m.stronghold >= 0 else m.home_region
    if kind == HOME_RULE and world.regions[region].controller != civ.name:
        return None
    if kind == TOLERATION and m.faith == NO_FAITH:
        return None
    k = _in_force(state, m.target, kind, m.faith)
    if k is not None:
        r = state.reforms[k]
        m.reform = k
        _bump(state, "extended")
        if kind == HOME_RULE and region not in r.regions:
            r.regions = sorted(r.regions + [region])
            return k, False, f"; home rule extends to {world.regions[region].name}", region
        return k, False, f"; {reform_name(world, r)} stands", -1
    r = Reform(kind=kind, civ=m.target, movement=i, enacted_turn=world.turn,
               regions=[region] if kind == HOME_RULE else [],
               faith=m.faith if kind == TOLERATION else NO_FAITH,
               ruler=civ.leader.name, ruler_start=civ.leader.reign_start, restores=m.restores)
    r.church = kind == TOLERATION and getattr(civ, "civ_majority_faith", NO_FAITH) == m.faith
    r.institution, r.founded_institution = _institutionalize(t, civ, kind)
    state.reforms.append(r)
    k = len(state.reforms) - 1
    m.reform = k
    _bump(state, "enacted")
    law = _PRETTY_INSTITUTION.get(r.institution)
    under = f" under {law}" if law else ""
    if m.restores >= 0:
        _bump(state, "restored")
        suffix = f"; {reform_name(world, r)} is restored{under}"
    elif kind == RELIEF:
        suffix = f"; poor relief becomes law{under}"
    elif kind == HOME_RULE:
        suffix = f"; {law} guarantees it" if law else "; a charter guarantees it"
    elif r.church:
        suffix = f"; the {_faith_name(world, r.faith)} is reformed"
    else:
        suffix = f"; the {_faith_name(world, r.faith)} is tolerated in the realm"
    if kind == TOLERATION and "holy_inquisition" in _active_institutions(_governance(world, civ)):
        # Toleration ends the Inquisition (enacting it again ends the toleration).
        _abolish_institution(t, civ, "holy_inquisition")
        suffix += " and the Holy Inquisition is abolished"
    return k, True, suffix, region if kind == HOME_RULE else -1


def _charter(t: _Tick, k: int, r: Reform, region: int, grant) -> None:
    """Home rule raises the realm's city in the region one charter level
    (self-government at most, at the cities' rank floors)."""
    from chronicler.cities_state import CHARTER_NAMES, SELF_GOVERNMENT, cities_on
    world = t.world
    if not cities_on(world):
        return
    from chronicler.cities import CHARTER_MIN_RANK, _note as city_note
    city = next((c for c in world.cities.cities if c.region == region and c.lord == r.civ
                 and c.charter < SELF_GOVERNMENT and c.rank >= CHARTER_MIN_RANK[c.charter + 1]), None)
    if city is None:
        return
    city.charter += 1
    r.cities.append(city.settlement_id)
    _bump(t.state, "charters")
    civ = t.civ(r.civ)
    ev = _emit(t, "city_charter", [civ.name],
               f"{civ.name} grants {city.name} {CHARTER_NAMES[city.charter]} with "
               f"{reform_name(world, r)}", importance=4, region=world.regions[region].name,
               causes=(grant.event_id,))
    city_note(city, world.turn, "charter", ev.event_id)


def _revoke_charters(t: _Tick, r: Reform, repeal) -> None:
    from chronicler.cities_state import MARKET_RIGHTS, SELF_GOVERNMENT, cities_on
    world = t.world
    if not cities_on(world) or not r.cities:
        return
    from chronicler.cities import _note as city_note
    for city in world.cities.cities:
        if (city.settlement_id in r.cities and city.lord == r.civ
                and MARKET_RIGHTS <= city.charter <= SELF_GOVERNMENT):
            city.charter -= 1
            city_note(city, world.turn, "charter", repeal.event_id)


def _treasury(t: _Tick, civ) -> int:
    from chronicler.war.common import projected_treasury
    return projected_treasury(t, civ)


def _tick_reforms(t: _Tick) -> None:
    """Upkeep, lapse and repeal of the lasting reforms in force (before the
    movements, so a repeal this turn is a cause for this turn's foundings)."""
    from chronicler.models import FactionType
    world, state = t.world, t.state
    for k, r in enumerate(state.reforms):
        if r.repeal != IN_FORCE:
            continue
        civ = t.civ(r.civ)
        if civ is None or not civ.regions:
            _repeal(t, k, r, LAPSED)
            continue
        if r.kind == HOME_RULE:
            held = [ri for ri in r.regions if world.regions[ri].controller == civ.name]
            if not held:
                _repeal(t, k, r, LAPSED)
                continue
            if held != r.regions:
                r.regions = held
        gov = _governance(world, civ)
        if r.institution and gov is None:
            r.institution, r.founded_institution = "", False   # governance off: it stands alone
        if r.institution and r.institution not in _active_institutions(gov):
            kind = _last_institution_kind(gov, r.institution)
            _repeal(t, k, r, NEGLECT if kind == "collapsed" else OPPOSITION)
            continue
        if r.kind == TOLERATION and "holy_inquisition" in _active_institutions(gov):
            _repeal(t, k, r, INQUISITION)
            continue
        leader = civ.leader
        if (leader.name, leader.reign_start) != (r.ruler, r.ruler_start):
            r.ruler, r.ruler_start = leader.name, leader.reign_start
            p = REPEAL_RULER_HARSH if leader.trait in HARSH_TRAITS else REPEAL_RULER
            if _rng(world, "repeal_ruler", k).random() < p:
                _repeal(t, k, r, RULER)
                continue
        if r.institution:
            continue
        opponent = FactionType(REFORM_OPPONENTS[r.kind])
        if (_influence(civ, opponent) > REPEAL_FACTION_SHARE
                and _rng(world, "repeal_faction", k).random() < REPEAL_FACTION):
            _repeal(t, k, r, OPPOSITION)
            continue
        if r.kind == RELIEF:
            due = math.ceil(RELIEF_UPKEEP * len(civ.regions))
            if _treasury(t, civ) >= due:
                _add_stat(t, civ, "treasury", -due, "keep")
                _bump(state, "upkeep", due)
                r.arrears = 0
            else:
                r.arrears += 1
                if r.arrears >= ARREARS_TURNS:
                    _repeal(t, k, r, FISCAL)


def _repeal(t: _Tick, k: int, r: Reform, why: int) -> None:
    world, state = t.world, t.state
    civ = t.civ(r.civ)
    civ_name = civ.name if civ is not None else "the fallen realm"
    name = reform_name(world, r)
    law = _PRETTY_INSTITUTION.get(r.institution, "")
    r.repeal, r.repealed_turn = why, world.turn
    if why == RULER and r.founded_institution and civ is not None:
        _abolish_institution(t, civ, r.institution)
    if why == LAPSED:
        _bump(state, "lapsed")
        text = f"{name[0].upper()}{name[1:]} of {civ_name} lapses"
    else:
        _bump(state, "repealed")
        if why == NEGLECT:
            text = f"{law} lapses in {civ_name} for want of pay, and with it {name}"
        elif why == OPPOSITION and law:
            from chronicler.governance_runtime import _OPPOSITION_AND_COST
            from chronicler import institutions as g01
            opp = _OPPOSITION_AND_COST[g01.InstitutionType(r.institution)][0].value
            text = f"The {opp} faction of {civ_name} forces the repeal of {law}, and with it {name}"
        elif why == OPPOSITION:
            text = f"The {REFORM_OPPONENTS[r.kind]} faction of {civ_name} has {name} repealed"
        elif why == RULER:
            text = f"{civ.leader.name} of {civ_name} repeals {name}"
        elif why == FISCAL:
            text = f"{civ_name} can no longer pay for {name}; it is abandoned"
        else:
            text = f"The Holy Inquisition of {civ_name} ends {name}"
    if r.kind == HOME_RULE and r.regions:
        region = world.regions[r.regions[0]].name
    else:
        region = civ.capital_region if civ is not None and civ.capital_region else None
    ev = _emit(t, "reform_lapsed" if why == LAPSED else "reform_repealed", [civ_name], text,
               importance=3 if why == LAPSED else 6, region=region, causes=(r.event_id,))
    r.repeal_event_id = ev.event_id
    if why != LAPSED:
        from chronicler import provenance as prov
        prov.remember(world, _reform_key(k, "repealed"), ev)
        if r.kind == HOME_RULE:
            _revoke_charters(t, r, ev)


def _restoration(world, state: MovementState, cidx: int, creed: int, ri: int, region) -> int:
    """The repealed reform of the creed a founding in region ``ri`` would
    seek to restore (repealed by ``cidx`` within REPEAL_MEMORY, covering the
    region, not yet restored or sought), else -1."""
    sought = {m.restores for m in state.movements if m.stage != ENDED and m.restores >= 0}
    sought.update(r.restores for r in state.reforms if r.restores >= 0)
    best = -1
    for k, r in enumerate(state.reforms):
        if (r.civ != cidx or r.kind != creed or r.repeal in (IN_FORCE, LAPSED) or k in sought
                or r.repealed_turn is None or world.turn - r.repealed_turn > REPEAL_MEMORY):
            continue
        if r.kind == HOME_RULE and ri not in r.regions:
            continue
        if r.kind == TOLERATION and region.majority_belief != r.faith:
            continue
        best = k
    return best


def _martyrs(t: _Tick, i: int, m: Movement, region: int, cap: int) -> int:
    """Kill the boldest members of ``region`` (queued native deaths); with no
    agent rows count them from the saved members. Returns the number."""
    obs = t.obs
    if obs is None:
        n = _members_in(m, region)
        return min(cap, max(1, math.ceil(MARTYR_SHARE * n))) if n else 0
    import numpy as np
    sel = np.flatnonzero((obs.mid == i + 1) & (obs.region == region))
    if sel.size == 0:
        return 0
    k = min(cap, max(1, math.ceil(MARTYR_SHARE * sel.size)))
    order = sorted(sel.tolist(), key=lambda j: (-float(obs.bold[j]), int(obs.ids[j])))
    ids = sorted(int(obs.ids[j]) for j in order[:k])
    sim = getattr(t.bridge, "_sim", None) if t.bridge is not None else None
    if sim is not None and hasattr(sim, "queue_targeted_deaths"):
        sim.queue_targeted_deaths(ids)
    return k


def _crackdown(t: _Tick, i: int, m: Movement, civ, *, crushed: bool = False,
               region: int | None = None, causes=()) -> None:
    world = t.world
    r = region if region is not None else m.stronghold
    k = _martyrs(t, i, m, r, MARTYR_CAP * (2 if crushed else 1))
    m.martyrs += k
    _bump(t.state, "martyrs", k)
    if m.creed == SECT and k:
        from chronicler.religion import MARTYRDOM_BOOST_CAP, MARTYRDOM_BOOST_PER_EVENT
        reg = world.regions[r]
        reg.martyrdom_boost = min(MARTYRDOM_BOOST_CAP, reg.martyrdom_boost + MARTYRDOM_BOOST_PER_EVENT * k)
    from chronicler.models import FactionType
    _shift_faction(civ, FactionType.MILITARY, CRACKDOWN_MILITARY)
    _add_stat(t, civ, "stability", -CRACKDOWN_STABILITY, "guard-shock")
    m.grievance = _q(min(GRIEVANCE_CAP, m.grievance + CRACKDOWN_GRIEVANCE))
    m.stage = SUPPRESSED
    m.stage_turn = world.turn
    m.crackdown_turn = world.turn
    m.crackdown_region = r
    _bump(t.state, "crushed" if crushed else "crackdowns")
    region_name = world.regions[r].name
    if crushed:
        text = (f"{civ.name} crushes the rising of {m.name} in {region_name}; "
                f"{k} {'is' if k == 1 else 'are'} put to death")
    else:
        text = (f"{civ.name} suppresses {m.name} in {region_name}; "
                f"{k} {'dies' if k == 1 else 'die'} a martyr's death")
    ev = _emit(t, "movement_crushed" if crushed else "movement_crackdown", [civ.name], text,
               importance=6, region=region_name, causes=causes)
    _remember(t, i, "crackdown", ev)
    _note(m, world.turn, "crushed" if crushed else "crackdown", ev.event_id)


def _rise(t: _Tick, i: int, m: Movement, civ) -> None:
    world = t.world
    r = m.stronghold
    m.stage = RISING
    m.stage_turn = world.turn
    m.rising_turn = world.turn
    m.rising_region = r
    m.rising_members = _members_in(m, r)
    m.last_rising = world.turn
    _add_stat(t, civ, "stability", -RISING_STABILITY, "guard-shock")
    gov = getattr(civ, "governance", None)
    if gov is not None and getattr(world, "governance", None) is not None:
        # A failed outcome (loss of control) for M66a legitimacy, as revolts are.
        gov.defeat_turns.append(world.turn)
    _bump(t.state, "risings")
    region_name = world.regions[r].name
    ev = _emit(t, "movement_rising", [civ.name],
               f"{m.name} rises against {civ.name} in {region_name} ({m.rising_members} members)",
               importance=7, region=region_name,
               causes=(_recall(t, i, "refused", within=40), _recall(t, i, "crackdown", within=40),
                       *_region_causes(t, region_name)))
    _remember(t, i, "rising", ev)
    _note(m, world.turn, "rising", ev.event_id)


def _extinct_faith_slot(t: _Tick) -> int | None:
    """Registry position of a faith no agent holds and nothing references
    (regions, rulers, temples and builds, the one-turn signals), lowest faith
    id first; None without agent rows or when every faith is alive."""
    obs = t.obs
    if obs is None:
        return None
    world = t.world
    used = set(int(b) for b in set(obs.belief.tolist()))
    for r in world.regions:
        used.update((r.majority_belief, r.conversion_target_signal, r.schism_convert_from,
                     r.schism_convert_to))
        if r.persecuting_faith is not None:
            used.add(r.persecuting_faith)
        used.update(inf.faith_id for inf in r.infrastructure)
        if r.pending_build is not None:
            used.add(r.pending_build.faith_id)
    for c in world.civilizations:
        used.update((c.civ_majority_faith, c.previous_majority_faith))
    free = [(b.faith_id, k) for k, b in enumerate(world.belief_registry) if b.faith_id not in used]
    return min(free)[1] if free else None


def _schism(t: _Tick, i: int, m: Movement, civ) -> bool:
    """A sect of the ruler's or the stronghold's faith breaks with that church
    through the religion path (``religion.fire_schism``). When the 16-faith
    registry is full, the sect takes the place of a faith no one holds any
    more (same id and registry position). Returns False when it cannot (a
    minority's sect, or no free place)."""
    from chronicler.religion import MAX_FAITHS, fire_schism
    world = t.world
    region = world.regions[m.stronghold]
    churches = {getattr(civ, "civ_majority_faith", NO_FAITH), region.majority_belief}
    if m.faith == NO_FAITH or m.faith not in churches:
        return False
    if not any(b.faith_id == m.faith for b in world.belief_registry):
        return False
    registry = world.belief_registry
    slot = retired = None
    if len(registry) >= MAX_FAITHS:
        slot = _extinct_faith_slot(t)
        if slot is None:
            return False
        retired = registry.pop(slot)
    old_name = _faith_name(world, m.faith)
    new = fire_schism(region, m.faith, registry, civ, world.turn, civ_origin=m.target)
    if new is None:
        if slot is not None:
            registry.insert(slot, retired)
        return False
    if slot is not None:
        # fire_schism appended the sect with the freed id; keep the position.
        registry.insert(slot, registry.pop())
    m.schism_turn = world.turn
    m.schism_from = m.faith
    m.schism_to = new.faith_id
    m.successor = new.faith_id
    _bump(t.state, "schisms")
    replaced = f" in place of the vanished '{retired.name}'" if retired is not None else ""
    ev = _emit(t, "Schism", [civ.name],
               f"{m.name} breaks away from the {old_name} in {region.name}: "
               f"'{new.name}' is founded{replaced}",
               importance=7, region=region.name,
               causes=(_recall(t, i, "refused", within=40), _recall(t, i, "crackdown", within=40)))
    _note(m, world.turn, "schism", ev.event_id)
    m.faith = new.faith_id
    _end(t, i, m, SCHISM, f"{m.name} becomes the church of '{new.name}'", causes=(ev.event_id,))
    return True


def _resolve_rising(t: _Tick, i: int, m: Movement, civ) -> None:
    world = t.world
    r = m.rising_region
    region = world.regions[r]
    rising = _recall(t, i, "rising")
    m.rising_turn = None
    if region.controller != civ.name:
        m.stage = PRESSING
        m.stage_turn = world.turn
        ev = _emit(t, "movement_dispersed", [civ.name, region.controller or ""],
                   f"The rising of {m.name} in {region.name} breaks up as the region passes "
                   f"from {civ.name}" + (f" to {region.controller}" if region.controller else ""),
                   importance=4, region=region.name, causes=(rising,))
        _note(m, world.turn, "dispersed", ev.event_id)
        return
    if t.rebels is not None:
        turnout = min(1.0, t.rebels.get(r, 0) / max(1, m.rising_members))
    else:
        turnout = OFF_MODE_TURNOUT
    occupied = region.occupied_by is not None and region.occupied_by != region.controller
    if (m.creed == LIBERTY and civ.stability < SECEDE_STABILITY and turnout >= SECEDE_TURNOUT
            and civ.capital_region != region.name and not occupied and len(civ.regions) >= 2
            and len(world.civilizations) + CIV_HEADROOM <= _max_civs()):
        _secede(t, i, m, civ, rising)
        return
    rng = _rng(world, "rising", i)
    if civ.stability < CONCESSION_STABILITY or rng.random() < CONCESSION_CHANCE:
        _reform(t, i, m, civ, concession=True, causes=(rising,))
        return
    _crackdown(t, i, m, civ, crushed=True, region=r, causes=(rising,))


def _max_civs() -> int:
    from chronicler.ffi_constants import MAX_CIV_RECORDS
    return MAX_CIV_RECORDS


def _secession_regions(t: _Tick, m: Movement, civ) -> list[str]:
    """The stronghold and the adjacent realm regions where the movement
    holds RISE_SHARE of the adults; never the capital, and the ruler keeps
    at least one region."""
    world = t.world
    home = world.regions[m.rising_region]
    leaving = [home.name]
    obs = t.obs
    for name in sorted(home.adjacencies):
        ri = t.region_index.get(name)
        if ri is None or world.regions[ri].controller != civ.name or name == civ.capital_region:
            continue
        n = int(obs.adults[ri]) if obs is not None else 0
        if n and _members_in(m, ri) / n >= RISE_SHARE[m.creed]:
            leaving.append(name)
    while len(leaving) >= len(civ.regions):
        leaving.pop()
    return leaving


def _secede(t: _Tick, i: int, m: Movement, civ, rising) -> None:
    from chronicler.leaders import _compose_regnal_name, _pick_regnal_name
    from chronicler.models import Civilization, Leader
    from chronicler.politics import transfer_regions_to_new_civ
    world = t.world
    home = world.regions[m.rising_region]
    leaving = _secession_regions(t, m, civ)
    existing = {c.name for c in world.civilizations}
    name = f"Free {home.name}"
    if name in existing:
        name = f"Free {home.name} {world.turn}"
    region_map = world.region_map
    population = sum(region_map[n].population for n in leaving)
    share = population / max(1, civ.population)
    split_mil = math.floor(civ.military * share)
    split_eco = math.floor(civ.economy * share)
    split_tre = max(0, math.floor(civ.treasury * len(leaving) / max(1, len(civ.regions))))
    rng = _rng(world, "secession", i)
    values = list(civ.values)
    if values and NEW_CIV_VALUE not in values:
        values[-1] = NEW_CIV_VALUE
    leader = Leader(name="Placeholder", trait=rng.choice(NEW_CIV_TRAITS),
                    reign_start=world.turn, succession_type="secession")
    new = Civilization(
        name=name, population=max(population, 1), military=max(split_mil, 0),
        economy=max(split_eco, 0), culture=civ.culture, stability=NEW_CIV_STABILITY,
        treasury=split_tre, tech_era=civ.tech_era, leader=leader, regions=list(leaving),
        capital_region=home.name, domains=list(civ.domains), values=values,
        asabiya=NEW_CIV_ASABIYA, leader_name_pool=list(civ.leader_name_pool or []),
    )
    for n in leaving:
        region_map[n].asabiya_state.asabiya = NEW_CIV_ASABIYA
    regnal = random.Random(stable_hash_int("agent_movements", "regnal", world.seed, world.turn, name))
    title, throne, ordinal = _pick_regnal_name(new, world, regnal)
    founder = _find_great_person(world, m.leader) if m.leader else None
    if founder is not None and founder.alive and founder.active:
        # The movement's leader takes the throne of the state it founded.
        from chronicler.leaders import strip_title
        new.regnal_name_counts.pop(throne, None)
        throne = getattr(founder, "base_name", None) or strip_title(founder.name)
        ordinal = 0
        new.regnal_name_counts[throne] = 1
        new.leader.trait = founder.trait
    else:
        founder = None
    new.leader.name = _compose_regnal_name(title, throne, ordinal)
    new.leader.throne_name = throne
    new.leader.regnal_ordinal = ordinal
    new.founded_turn = world.turn
    new.traditions = list(civ.traditions)
    new_idx = len(world.civilizations)
    if split_tre:
        _add_stat(t, civ, "treasury", -split_tre, "keep")
    transitions = transfer_regions_to_new_civ(
        world, civ, new, leaving,
        add_stat=lambda c, stat, delta, category: _add_stat(t, c, stat, delta, category),
        split_military=split_mil, split_economy=split_eco,
        lord_stability_loss=SECEDE_LORD_LOSS, bridge=t.bridge,
    )
    civ.event_counts["secession_occurred"] = civ.event_counts.get("secession_occurred", 0) + 1
    m.successor = new_idx
    _bump(t.state, "secessions")
    ruled = ""
    if founder is not None:
        from chronicler.great_persons import _append_deed
        _append_deed(founder, f"Took the throne of the {name}", region=home.name, turn=world.turn,
                     civ=name)
        founder.active = False
        founder.fate = "ascended"
        for owner in world.civilizations:
            if founder in owner.great_persons:
                owner.great_persons.remove(founder)
        world.retired_persons.append(founder)
        ruled = f", and {founder.name} takes its throne as {new.leader.name}"
    ev = _emit(t, "secession", [civ.name, name],
               f"{m.name} carries {', '.join(leaving)} out of {civ.name}: the {name}{ruled}",
               importance=9, region=home.name, causes=(rising,))
    _note(m, world.turn, "seceded", ev.event_id)
    t.events.extend(transitions)
    _end(t, i, m, SECEDED, f"{m.name} has its state: the {name}", causes=(ev.event_id,))


# ---------------------------------------------------------------------------
# Emergence
# ---------------------------------------------------------------------------

def _carrier(world, civ, region_name: str, creed: int, leaders: set[str]):
    """(great person, chance multiplier) of the best carrier in the region:
    an active great person of the ruler there (a prophet for a sect counts
    double), else a city (x(1 + unrest)), else (None, 1)."""
    best = None
    for gp in civ.great_persons:
        if not gp.alive or not gp.active or gp.region != region_name or gp.name in leaders:
            continue
        mult = CARRIER_PROPHET if (creed == SECT and gp.role == "prophet") else CARRIER_GREAT_PERSON
        if best is None or mult > best[1]:
            best = (gp, mult)
    if best is not None:
        return best
    cities = getattr(world, "cities", None)
    if cities is not None and getattr(cities, "cities", None):
        ri = next(i for i, r in enumerate(world.regions) if r.name == region_name)
        unrest = max((c.unrest for c in cities.cities if c.region == ri), default=None)
        if unrest is not None:
            return None, 1.0 + unrest
    return None, 1.0


def _idea_for(world, civ, creed: int) -> str:
    """The first M16b idea adopted by the civ whose value fits the creed."""
    for idea in world.movements:
        if civ.name in idea.adherents and idea.value_affinity in IDEA_VALUES[creed]:
            return idea.id
    return ""


def _emerge(t: _Tick, census) -> None:
    world = t.world
    state = t.state
    living = _living(state)
    if len(living) >= MAX_LIVING:
        return
    adults, aggrieved = census
    per_civ: dict[int, int] = {}
    alive: dict[int, set[int]] = {}
    cooling: dict[int, set[int]] = {}
    for _i, m in living:
        per_civ[m.target] = per_civ.get(m.target, 0) + 1
        alive.setdefault(m.target, set()).add(m.creed)
    leaders = {m.leader for _i, m in living if m.leader}
    for m in state.movements:
        # A ruler who just faced a movement of a creed does not face another
        # at once (the end, or the founding while it lives, starts the clock);
        # a repealed reform's restoration is not held back.
        if world.turn - (m.ended_turn if m.ended_turn is not None else m.founded_turn) < EMERGE_COOLDOWN:
            cooling.setdefault(m.target, set()).add(m.creed)
    index = {c.name: i for i, c in enumerate(world.civilizations)}
    repeals = any(r.repeal not in (IN_FORCE, LAPSED) for r in state.reforms)
    candidates = []
    for ri, region in enumerate(world.regions):
        cidx = index.get(region.controller) if region.controller else None
        if cidx is None:
            continue
        civ = world.civilizations[cidx]
        if not civ.regions or per_civ.get(cidx, 0) >= MAX_PER_CIV:
            continue
        n = adults[ri]
        for creed in range(len(CREED_NAMES)):
            a = aggrieved[ri][creed]
            if n <= 0 or a < EMERGE_MIN_AGGRIEVED or a / n < EMERGE_SHARE:
                continue
            if creed in alive.get(cidx, ()):
                continue
            restores = _restoration(world, state, cidx, creed, ri, region) if repeals else -1
            if restores < 0 and creed in cooling.get(cidx, ()):
                continue
            gp, mult = _carrier(world, civ, region.name, creed, leaders)
            if restores >= 0:
                mult *= REPEAL_EMERGE
            share = a / n
            chance = min(EMERGE_CHANCE_CAP, EMERGE_CHANCE * share / EMERGE_SHARE * mult)
            candidates.append((-share * mult, ri, creed, chance, gp, a, n, restores))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    for _score, ri, creed, chance, gp, a, n, restores in candidates:
        if _rng(world, "emerge", ri, creed).random() < chance:
            _found(t, ri, creed, gp, a, n, restores=restores)
            return


def _movement_name(world, creed: int, region: str, faith: str, i: int) -> str:
    templates = _NAMES[creed]
    rng = random.Random(stable_hash_int("agent_movements", "name", world.seed, world.turn, i))
    name = rng.choice(templates).format(region=region, faith=faith)
    taken = {m.name for m in world.agent_movements.movements}
    if name in taken:
        name = f"{name} ({world.turn})"
    return name


def _found(t: _Tick, ri: int, creed: int, gp, aggrieved: int, adults: int, *,
           restores: int = -1) -> None:
    world = t.world
    state = t.state
    region = world.regions[ri]
    cidx = t.civ_index(region.controller)
    civ = world.civilizations[cidx]
    i = len(state.movements)
    faith = region.majority_belief if region.majority_belief is not None else NO_FAITH
    name = _movement_name(world, creed, region.name, _faith_name(world, faith) or "", i)
    m = Movement(
        name=name, creed=creed, founded_turn=world.turn, home_region=ri, target=cidx,
        leader=gp.name if gp is not None else "",
        leader_agent=int(gp.agent_id) if gp is not None and gp.agent_id is not None else 0,
        idea=_idea_for(world, civ, creed), faith=faith if 0 <= faith < NO_FAITH else NO_FAITH,
        stage=GATHERING, stage_turn=world.turn, regions_reached=[ri], restores=restores,
    )
    state.movements.append(m)
    _bump(state, "founded")
    founder = f"{gp.name} founds" if gp is not None else "the discontented found"
    idea = f", carrying the idea of {next(x.value_affinity for x in world.movements if x.id == m.idea)}" if m.idea else ""
    repeal = state.reforms[restores].repeal_event_id if restores >= 0 else None
    ev = _emit(t, "movement_founded", [civ.name] + ([gp.name] if gp is not None else []),
               f"In {region.name}, {founder} {name}{idea}: {aggrieved} of {adults} "
               f"people there want {_demand_text(world, m)}",
               importance=5, region=region.name, causes=(repeal, *_region_causes(t, region.name)))
    _remember(t, i, "founded", ev)
    _note(m, world.turn, "founded", ev.event_id)


# ---------------------------------------------------------------------------
# Native table (built from persisted state for every tick)
# ---------------------------------------------------------------------------

def movement_table(world: "WorldState"):
    """The native movement table for this turn's tick: one row per living
    movement, plus a schism's movement for the tick after its schism (so its
    members convert). One-shots are derived from turns stored on the
    movement (``turn - 1``)."""
    import pyarrow as pa
    turn = world.turn
    cols: dict[str, list] = {k: [] for k in (
        "movement_id", "creed", "stage", "target_civ", "appeal", "found_region", "founder_id",
        "relief_age", "crackdown_region", "rising_region", "convert_from", "convert_to")}
    state = world.agent_movements
    for i, m in enumerate(state.movements if state is not None else ()):
        schism_tick = m.end == SCHISM and m.schism_turn == turn - 1
        if m.stage == ENDED and not schism_tick:
            continue
        cols["movement_id"].append(i + 1)
        cols["creed"].append(m.creed)
        cols["stage"].append(SATISFIED if schism_tick else m.stage)
        cols["target_civ"].append(m.target if 0 <= m.target < 255 else 255)
        cols["appeal"].append(appeal(m, _leader_alive(world, m)))
        founding = m.founded_turn == turn - 1
        cols["found_region"].append(m.home_region if founding else NO_REGION)
        cols["founder_id"].append(m.leader_agent if founding else 0)
        age = turn - m.reform_turn if m.reform_turn is not None else None
        cols["relief_age"].append(age if age is not None and 1 <= age <= RELIEF_TURNS else NO_RELIEF)
        cols["crackdown_region"].append(
            m.crackdown_region if m.crackdown_turn == turn - 1 and m.crackdown_region >= 0 else NO_REGION)
        cols["rising_region"].append(
            m.rising_region if m.stage == RISING and m.rising_turn == turn - 1 else NO_REGION)
        cols["convert_from"].append(m.schism_from if schism_tick else NO_FAITH)
        cols["convert_to"].append(m.schism_to if schism_tick else NO_FAITH)
    types = {
        "movement_id": pa.uint16(), "creed": pa.uint8(), "stage": pa.uint8(),
        "target_civ": pa.uint8(), "appeal": pa.float32(), "found_region": pa.uint16(),
        "founder_id": pa.uint32(), "relief_age": pa.uint16(), "crackdown_region": pa.uint16(),
        "rising_region": pa.uint16(), "convert_from": pa.uint8(), "convert_to": pa.uint8(),
    }
    return pa.record_batch({k: pa.array(v, type=types[k]) for k, v in cols.items()})


def reform_table(world: "WorldState"):
    """The lasting reforms in force for this turn's tick: one row per
    chartered region of a home rule, one per realm for relief (every
    believer) and toleration (its faith)."""
    import pyarrow as pa
    cols: dict[str, list] = {k: [] for k in ("creed", "civ", "region", "faith")}
    state = world.agent_movements
    for r in (state.reforms if state is not None else ()):
        if r.repeal != IN_FORCE or not 0 <= r.civ < 255:
            continue
        rows = ([(ri, NO_FAITH) for ri in r.regions] if r.kind == HOME_RULE
                else [(NO_REGION, r.faith if r.kind == TOLERATION else NO_FAITH)])
        for region, faith in rows:
            cols["creed"].append(r.kind)
            cols["civ"].append(r.civ)
            cols["region"].append(region)
            cols["faith"].append(faith)
    types = {"creed": pa.uint8(), "civ": pa.uint8(), "region": pa.uint16(), "faith": pa.uint8()}
    return pa.record_batch({k: pa.array(v, type=types[k]) for k, v in cols.items()})


def movement_seeds(world: "WorldState"):
    """Members to re-seed per region for a native pool built fresh (a
    resumed world): the saved members of every living movement."""
    import pyarrow as pa
    ids, regions, counts = [], [], []
    state = world.agent_movements
    for i, m in enumerate(state.movements if state is not None else ()):
        if m.stage == ENDED or m.founded_turn >= world.turn - 1:
            continue
        for r, c in m.member_regions:
            ids.append(i + 1)
            regions.append(r)
            counts.append(c)
    return pa.record_batch({
        "movement_id": pa.array(ids, type=pa.uint16()),
        "region": pa.array(regions, type=pa.uint16()),
        "count": pa.array(counts, type=pa.uint32()),
    })


def send_to_native(world: "WorldState", agent_bridge) -> None:
    """Before an agent tick (switch on): re-seed a fresh pool once, then send
    this tick's table. Nothing is sent with the switch off."""
    if not agent_movements_on(world):
        return
    sim = agent_bridge._sim
    if not hasattr(sim, "set_movement_table") or not hasattr(sim, "set_movement_reforms"):
        raise RuntimeError(
            "the installed chronicler_agents extension predates agent movements (or their "
            "lasting reforms); rebuild it to use --agent-movements"
        )
    if not getattr(agent_bridge, "_movements_seeded", False):
        seeds = movement_seeds(world)
        if seeds.num_rows:
            sim.seed_movement_members(seeds)
        agent_bridge._movements_seeded = True
    sim.set_movement_table(movement_table(world))
    sim.set_movement_reforms(reform_table(world))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def snapshot_summary(world: "WorldState") -> dict:
    """Per-turn bundle summary: living movements, ended count, counters."""
    state = world.agent_movements
    living = []
    for i, m in _living(state):
        row = {
            "id": i, "name": m.name, "creed": CREED_NAMES[m.creed], "target": m.target,
            "stage": STAGE_NAMES[m.stage], "members": m.members, "strength": m.strength,
            "stronghold": m.stronghold, "martyrs": m.martyrs,
        }
        if m.leader:
            row["leader"] = m.leader
        if m.restores >= 0:
            row["restores"] = m.restores
        living.append(row)
    summary = {
        "living": living,
        "ended": sum(1 for m in state.movements if m.stage == ENDED),
        "counters": {k: state.counters.get(k, 0) for k in COUNTER_KEYS},
    }
    reforms = []
    for k, r in enumerate(state.reforms):
        if r.repeal != IN_FORCE:
            continue
        row = {"id": k, "kind": REFORM_NAMES[r.kind], "civ": r.civ, "since": r.enacted_turn,
               "movement": r.movement}
        if r.regions:
            row["regions"] = list(r.regions)
        if r.kind == TOLERATION:
            row["faith"] = r.faith
            if r.church:
                row["church"] = True
        if r.institution:
            row["institution"] = r.institution
        reforms.append(row)
    if reforms or state.reforms:
        summary["reforms"] = reforms
    return summary


def movement_history(world: "WorldState", index: int) -> list[str]:
    """One movement's record as text lines: the header and each history
    entry with the event text the simulation wrote."""
    m = world.agent_movements.movements[index]
    by_id = {e.event_id: e for e in world.events_timeline if e.event_id}
    civ = world.civilizations[m.target].name if 0 <= m.target < len(world.civilizations) else "?"
    lines = [
        f"{m.name} ({CREED_NAMES[m.creed]}), founded turn {m.founded_turn} in "
        f"{world.regions[m.home_region].name} against {civ}"
        + (f", led by {m.leader}" if m.leader else "")
        + (f", carrying {m.idea}" if m.idea else "")
        + f"; peak {m.peak_members} members, {m.demands} demands, {m.martyrs} martyrs; "
        + (f"ended {END_NAMES[m.end]} turn {m.ended_turn}" if m.stage == ENDED
           else f"standing: {STAGE_NAMES[m.stage]}, {m.members} members")
    ]
    for turn, kind, eid in m.history:
        ev = by_id.get(eid)
        lines.append(f"  {turn:>4}: {kind}: {ev.description if ev is not None else ''}")
    state = world.agent_movements
    if 0 <= m.reform < len(state.reforms):
        lines.extend(f"  {line}" for line in reform_history(world, m.reform, by_id))
    return lines


def reform_history(world: "WorldState", index: int, by_id: dict | None = None) -> list[str]:
    """One lasting reform's record: what it is, its grant and its end."""
    r = world.agent_movements.reforms[index]
    if by_id is None:
        by_id = {e.event_id: e for e in world.events_timeline if e.event_id}
    civ = world.civilizations[r.civ].name if 0 <= r.civ < len(world.civilizations) else "?"
    law = f", {_PRETTY_INSTITUTION[r.institution]}" if r.institution in _PRETTY_INSTITUTION else ""
    status = (f"repealed ({REPEAL_NAMES[r.repeal]}) turn {r.repealed_turn}" if r.repeal
              else "in force")
    lines = [f"reform {index}: {reform_name(world, r)} in {civ}{law}, enacted turn "
             f"{r.enacted_turn}; {status}"]
    for eid in (r.event_id, r.repeal_event_id):
        ev = by_id.get(eid) if eid else None
        if ev is not None:
            lines.append(f"  {ev.turn:>4}: {ev.event_type}: {ev.description}")
    return lines


def extract_movement_metrics(bundles: list[dict]) -> dict:
    """Analytics: per run, the final counters and the peak living count."""
    runs = 0
    totals: dict[str, float] = {k: 0 for k in COUNTER_KEYS}
    peak_living = []
    for bundle in bundles:
        history = bundle.get("history") or []
        rows = [h.get("agent_movements") for h in history if isinstance(h, dict) and h.get("agent_movements")]
        if not rows:
            continue
        runs += 1
        last = rows[-1].get("counters", {})
        for k in COUNTER_KEYS:
            totals[k] += float(last.get(k, 0))
        peak_living.append(max(len(r.get("living", [])) for r in rows))
    if not runs:
        return {"runs": 0}
    return {
        "runs": runs,
        "per_run": {k: round(v / runs, 3) for k, v in totals.items()},
        "peak_living_mean": round(sum(peak_living) / runs, 3),
    }
