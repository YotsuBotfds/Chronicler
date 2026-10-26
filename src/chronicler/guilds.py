"""Guilds and burghers (``--guilds``).

On by default for new worlds behind ``WorldState.guilds`` (CLI ``--guilds`` /
``--no-guilds``, persisted on the world so a resumed run keeps its setting). With the switch
off nothing in this module runs, no civ has a burgher faction, the bridge
sends no movement news, and every output is identical to the simulation
without it. See ``docs/integration/guilds.md``.

Guilds
    A guild forms in a city that makes wares (a craft guild), or whose
    merchants and craftworkers reach GUILD_MASTERS at the reference scale (a
    merchant guild). Craftworkers are the town's share of its farmers' labour
    (``cities.URBAN_FARM_LABOR``): there is no artisan occupation. Charters
    grant privileges: market rights a monopoly on the city's wares (their
    commerce term x MONOPOLY_ACCESS), self-government a say in civic dues
    (dues x SAY_DUES). The guild takes part of the city's commerce into its
    own purse and pays toward the city's walls.

Threats and guild movements
    A levy (the lord raising the city's dues), a revoked charter, a sack, an
    occupation or the repeal of its guild charter threatens the privileges.
    With movements on, a guild may then become a movement of the ``guild``
    creed (``agent_movements``): the city's civilian residents, its demand
    the confirmation of its privileges, its reform a guild charter (a lasting
    reform, repealed and restored like the others), upheld by Merchant
    Courts when governance has room.

Burghers
    A fifth faction (``FactionType.BURGHER``) in realms with chartered
    cities, free cities or guilds: it takes the patricians' voice and the
    charters' influence from the merchant faction and presses for trade, low
    tolls, charters and order (action weights, charter grants, crackdowns).

Movement news
    Movement foundings, risings, reforms and crackdowns become information
    packets (``knowledge.rs`` type 4) in their region. Agents who hold news
    of a like movement elsewhere join more readily (a crackdown deters), and
    regions where the aggrieved hold it found movements more readily.

Identity: region = index in ``world.regions``, civ = index in
``world.civilizations``, city = ``settlement_id``, guild = index in
``GuildState.guilds``. All randomness comes from
``random.Random(stable_hash_int("guilds", <namespace>, seed, turn, id))``.
Stat changes use the existing accumulator categories.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, Iterable

from chronicler.guilds_state import (
    CHARTER_REVOKED, COUNTER_KEYS, CRAFT, KIND_NAMES, LEVY, MERCHANT, OCCUPATION, REPEAL, SACK,
    THREAT_NAMES, Guild, GuildState, guilds_on,
)
from chronicler.utils import stable_hash_int

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Event, WorldState


# ---------------------------------------------------------------------------
# Parameters ([CALIBRATE]; documented in docs/integration/guilds.md)
# ---------------------------------------------------------------------------

#: Default for worlds created by the CLI/batch/live entry points (on since
#: the 2026-10 guilds full gate, docs/integration/guilds.md; ``--no-guilds``
#: opts out; loaded worlds keep their saved setting).
DEFAULT_ENABLED_FOR_NEW_WORLDS = True

# Formation and dissolution.
GUILD_WARES = 0.05            # wares made last turn that found a craft guild
GUILD_MASTERS = 4.0           # merchants and craftworkers (reference scale) that found one
DISSOLVE_MASTERS = 1.0        # a guild with fewer ...
DISSOLVE_TURNS = 20           # ... for this many turns dissolves
CRAFT_NAMES = ("Weavers'", "Smiths'", "Potters'", "Masons'", "Dyers'", "Coopers'")

# Privileges and money.
GUILD_TAKE = 0.05             # share of the city's commerce the guild takes
MONOPOLY_TAKE = 0.10          # ... with the wares monopoly
MONOPOLY_ACCESS = 1.5         # the wares' commerce term and its cap, with the monopoly
SAY_DUES = 0.8                # dues share with a say in civic dues
CHARTER_DUES = 0.75           # dues share under a guild charter
WEALTH_DECAY = 0.02           # the guild's purse, per turn

# Levies: the lord raises a city's dues.
LEVY_SHARE = 0.10             # added to the dues share ...
LEVY_TURNS = 20               # ... for this many turns
LEVY_CHANCE = 0.04            # per turn, a lord short of money (or at war)
LEVY_SAY = 0.5                # chance factor where the guild has a say
LEVY_TREASURY = 30
LEVY_GRIEVANCE = 0.1          # the city's grievance (unrest)

# Guild movements (agent_movements, creed "guild").
MOVEMENT_MASTERS = 3.0        # a guild this strong (reference scale) can rise
MOVEMENT_CHANCE = 0.5         # per threat
MOVEMENT_SATISFACTION = 0.65  # residents' mean satisfaction below which a guild rises
RESTORE_CHANCE = 0.8          # after a repeal of its guild charter
MAX_GUILD_MOVEMENTS = 4       # living guild movements in the world
WEALTH_APPEAL = 60.0          # guild purse that adds half to the movement's appeal
APPEAL_CAP = 0.5
RISING_UNREST = 0.3           # a guild rising stirs its city

# Burghers.
CHARTER_WEIGHT = (0.0, 1.0, 2.0, 3.0)   # by city charter (none .. free city), x rank
GUILD_WEIGHT = 1.0                      # a city with a guild, x rank
BURGHER_PER_WEIGHT = 0.002
BURGHER_CAP = 0.015
BURGHER_IDLE_DECAY = 0.01
BURGHER_IDLE_TURNS = 20       # turns without a base before the faction dissolves
BURGHER_ORDER = 0.3           # suppression chance (commons, liberty) per unit of influence

# Movement news (knowledge.rs InfoType::MovementNews).
NEWS_KINDS: tuple[str, ...] = ("founding", "rising", "reform", "crackdown")   # = knowledge.rs
FOUNDING_NEWS, RISING_NEWS, REFORM_NEWS, CRACKDOWN_NEWS = range(len(NEWS_KINDS))
NEWS_INTENSITY = (120, 180, 220, 160)
NO_NEWS = 255
#: Founding chance of a movement x (1 + NEWS_FOUND x min(1, share /
#: NEWS_FULL_SHARE)), share: the region's aggrieved who hold inspiring news of
#: a like movement elsewhere (half of them give the full factor, x2).
NEWS_FOUND = 1.0
NEWS_FULL_SHARE = 0.5

QUANTUM_DIGITS = 4
HISTORY_CAP = 60


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def guilds_enabled(world) -> bool:
    """True only for a real guild state (mocks and ``None`` read as off)."""
    return guilds_on(world)


def set_guilds_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (an empty state; guilds form in cities as they grow) or
    disable (dropping every guild record and the burgher factions)."""
    if enabled:
        if world.guilds is None:
            world.guilds = GuildState()
        return
    if world.guilds is not None:
        from chronicler.factions import normalize_influence
        from chronicler.models import FactionType
        for civ in world.civilizations:
            if civ.factions.influence.pop(FactionType.BURGHER, None) is not None:
                normalize_influence(civ.factions)
    world.guilds = None


def news_enabled(world) -> bool:
    """Movement news runs with guilds and movements (tuning
    ``guilds.movement_news`` 0 turns it off)."""
    from chronicler.agent_movements_state import agent_movements_on
    if not guilds_on(world) or not agent_movements_on(world):
        return False
    from chronicler.tuning import K_GUILD_NEWS, get_override
    return bool(get_override(world, K_GUILD_NEWS, 1.0))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _q(x: float) -> float:
    return round(x, QUANTUM_DIGITS)


def _rng(world, namespace: str, *parts) -> random.Random:
    return random.Random(stable_hash_int("guilds", namespace, world.seed, world.turn, *parts))


def _bump(state: GuildState, key: str, n: float = 1) -> None:
    state.counters[key] = round(state.counters.get(key, 0) + n, 4)


def _note(guild: Guild, turn: int, kind: str, event_id: str = "") -> None:
    guild.history.append((turn, kind, event_id))
    if len(guild.history) > HISTORY_CAP:
        del guild.history[1]   # keep the founding


def living_guilds(world) -> list[tuple[int, Guild]]:
    if not guilds_on(world):
        return []
    return [(i, g) for i, g in enumerate(world.guilds.guilds) if g.dissolved_turn is None]


def guild_index(world) -> dict[int, Guild] | None:
    """Living guilds by city settlement id; None with the switch off."""
    if not guilds_on(world):
        return None
    return {g.city: g for _i, g in living_guilds(world)}


def guild_of_movement(world, movement: int) -> Guild | None:
    """The guild whose movement is ``movement`` (an index in the movement list)."""
    if not guilds_on(world) or movement < 0:
        return None
    return next((g for g in world.guilds.guilds if g.movement == movement), None)


def has_burghers(civ) -> bool:
    from chronicler.models import FactionType
    return FactionType.BURGHER in civ.factions.influence


def urban_influence(civ, default: float = 0.25) -> float:
    """Merchant influence, plus the burghers' where the civ has them: the
    weight of the towns' interest at court."""
    from chronicler.models import FactionType
    inf = civ.factions.influence
    value = float(inf.get(FactionType.MERCHANT, default))
    if FactionType.BURGHER in inf:
        value += float(inf[FactionType.BURGHER])
    return value


def shift_urban(civ, amount: float) -> None:
    """The towns' voice: the burghers where the civ has them, else the
    merchant faction (as cities do without guilds)."""
    from chronicler.factions import normalize_influence
    from chronicler.models import FactionType
    ft = FactionType.BURGHER if has_burghers(civ) else FactionType.MERCHANT
    civ.factions.influence[ft] = civ.factions.influence.get(ft, 0.0) + amount
    normalize_influence(civ.factions)


def burgher_order(civ) -> float:
    """Added to the chance that a ruler crushes a commons or liberty movement."""
    from chronicler.models import FactionType
    return BURGHER_ORDER * float(civ.factions.influence.get(FactionType.BURGHER, 0.0))


def masters(city, k: float) -> float:
    """A city's merchants and craftworkers at the reference scale: its
    merchants and the town's share of its farmers' labour."""
    from chronicler.cities import URBAN_FARM_LABOR
    size = city.size / k if k > 0 else city.size
    farm, merchant = city.mix[0], city.mix[2]
    return size * (merchant + farm * (1.0 - URBAN_FARM_LABOR[city.rank]))


def _charter_reform(world, guild: Guild):
    state = getattr(world, "agent_movements", None)
    if state is None or not 0 <= guild.charter_reform < len(state.reforms):
        return None
    return state.reforms[guild.charter_reform]


def _charter_in_force(world, guild: Guild) -> bool:
    from chronicler.agent_movements_state import IN_FORCE
    r = _charter_reform(world, guild)
    return r is not None and r.repeal == IN_FORCE


def _levied(world, guild: Guild) -> bool:
    return guild.levy_turn is not None and world.turn - guild.levy_turn < LEVY_TURNS


# ---------------------------------------------------------------------------
# Hooks read by cities (guilds on only)
# ---------------------------------------------------------------------------

def craft_access(guild: Guild | None, cap: float, rate: float) -> tuple[float, float]:
    """(cap, rate) of the wares' commerce term; raised by the monopoly."""
    if guild is not None and guild.monopoly:
        return cap * MONOPOLY_ACCESS, rate * MONOPOLY_ACCESS
    return cap, rate


def dues_share(world, guild: Guild, share: float) -> float:
    """The city's dues share with its guild's say, charter and any levy."""
    if guild.say:
        share *= SAY_DUES
    if _charter_in_force(world, guild):
        share *= CHARTER_DUES
    if _levied(world, guild):
        share += LEVY_SHARE
    return share


def take(state: GuildState, guild: Guild, commerce: float) -> float:
    """The guild's take of the city's commerce this turn, paid into its purse."""
    amount = commerce * (MONOPOLY_TAKE if guild.monopoly else GUILD_TAKE)
    guild.wealth = _q(guild.wealth * (1.0 - WEALTH_DECAY) + amount)
    _bump(state, "take", round(amount, 4))
    return amount


def wall_help(guild: Guild | None, purse: float, cost: float) -> float:
    """What the guild pays toward walls the city cannot pay alone (0: none)."""
    if guild is None or purse >= cost or purse + guild.wealth < cost:
        return 0.0
    return cost - purse


def pay_walls(state: GuildState, guild: Guild, amount: float, turn: int, event_id: str) -> None:
    guild.wealth = _q(guild.wealth - amount)
    _bump(state, "walls")
    _note(guild, turn, "walls", event_id)


# ---------------------------------------------------------------------------
# The tick (Phase 10, after movements)
# ---------------------------------------------------------------------------

class _Tick:
    def __init__(self, world, acc, agent_bridge, phase10) -> None:
        from chronicler.cities import scale
        self.world = world
        self.acc = acc
        self.bridge = agent_bridge
        self.phase10 = phase10
        self.state: GuildState = world.guilds
        self.events: list = []
        self.k = scale(world)
        cities = getattr(world, "cities", None)
        self.cities = {c.settlement_id: c for c in cities.cities} if cities is not None else {}

    def civ(self, idx: int):
        civs = self.world.civilizations
        return civs[idx] if 0 <= idx < len(civs) else None

    @property
    def agent_rows(self) -> bool:
        rows = getattr(self.phase10, "agents", None) if self.phase10 is not None else None
        return rows is not None


def _emit(t: _Tick, event_type: str, actors: Iterable[str], description: str, *,
          importance: int = 4, region: str | None = None,
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


def tick_guilds(world: "WorldState", events: Iterable["Event"] = (), acc=None, *,
                phase10=None, agent_bridge=None) -> list["Event"]:
    """Phase 10, after cities and movements: dissolutions, then per guild its
    masters, lord, privileges and guild charter, the threats to them (and a
    guild movement); levies; foundings; the burgher factions."""
    if not guilds_on(world):
        return []
    t = _Tick(world, acc, agent_bridge, phase10)
    for gi, guild in living_guilds(world):
        city = t.cities.get(guild.city)
        if city is None:
            _dissolve(t, gi, guild, "its city has fallen")
            continue
        _update(t, gi, guild, city)
    _levies(t)
    _found_guilds(t)
    _burghers(t)
    t.state.last_tick_turn = world.turn
    return t.events


def _guild_name(world, city, kind: int) -> str:
    if kind == MERCHANT:
        return f"the Merchant Guild of {city.name}"
    rng = random.Random(stable_hash_int("guilds", "name", world.seed, city.settlement_id))
    return f"the {rng.choice(CRAFT_NAMES)} Guild of {city.name}"


def _found_guilds(t: _Tick) -> None:
    world, state = t.world, t.state
    have = {g.city for _i, g in living_guilds(world)}
    for sid in sorted(t.cities):
        if sid in have:
            continue
        city = t.cities[sid]
        crafts = city.crafts >= GUILD_WARES
        strength = masters(city, t.k)
        if not crafts and strength < GUILD_MASTERS:
            continue
        kind = CRAFT if crafts else MERCHANT
        region = world.regions[city.region]
        guild = Guild(city=sid, region=city.region, name=_guild_name(world, city, kind), kind=kind,
                      founded_turn=world.turn, masters=_q(strength), peak_masters=_q(strength),
                      last_charter=city.charter, lord=city.lord,
                      occupied=_occupied(region))
        what = "its crafts" if kind == CRAFT else "its trade"
        ev = _emit(t, "guild_founded", [region.controller or ""],
                   f"The masters of {city.name} in {region.name} form {guild.name} to govern {what}",
                   importance=4, region=region.name)
        _note(guild, world.turn, "founded", ev.event_id)
        state.guilds.append(guild)
        _bump(state, "founded")
        _sync_privileges(t, len(state.guilds) - 1, guild, city)


def _occupied(region) -> bool:
    return region.occupied_by is not None and region.occupied_by != region.controller


def _dissolve(t: _Tick, gi: int, guild: Guild, why: str) -> None:
    world = t.world
    region = world.regions[guild.region]
    guild.dissolved_turn = world.turn
    ev = _emit(t, "guild_dissolved", [region.controller or ""],
               f"{guild.name[0].upper()}{guild.name[1:]} is dissolved: {why}",
               importance=3, region=region.name)
    _note(guild, world.turn, "dissolved", ev.event_id)
    _bump(t.state, "dissolved")


def _update(t: _Tick, gi: int, guild: Guild, city) -> None:
    world = t.world
    region = world.regions[city.region]
    strength = masters(city, t.k)
    guild.masters = _q(strength)
    guild.peak_masters = max(guild.peak_masters, guild.masters)
    guild.low_turns = guild.low_turns + 1 if strength < DISSOLVE_MASTERS else 0
    if guild.low_turns >= DISSOLVE_TURNS:
        _dissolve(t, gi, guild, "too few masters remain")
        return
    threats: list[tuple[int, list[str | None]]] = []
    today = [eid for turn, _kind, eid in city.history if turn == world.turn and eid]
    if city.charter < guild.last_charter:
        threats.append((CHARTER_REVOKED, today))
    if city.last_sack == world.turn:
        threats.append((SACK, today))
    occupied = _occupied(region)
    if occupied and not guild.occupied:
        from chronicler import provenance as prov
        threats.append((OCCUPATION, [prov.recall(world, prov.key("occupation", region.name), within=1)]))
    guild.occupied = occupied
    if city.lord != guild.lord:
        guild.lord = city.lord
        guild.levy_turn = None   # a new lord's dues are his own
    if guild.levy_turn is not None and not _levied(world, guild):
        guild.levy_turn = None
    restores = _charter_lapse_or_repeal(t, guild)
    if restores >= 0:
        r = world.agent_movements.reforms[restores]
        threats.append((REPEAL, [r.repeal_event_id]))
    _adopt_charter(t, guild)
    _sync_privileges(t, gi, guild, city)
    guild.last_charter = city.charter
    for threat, causes in threats:
        _threatened(t, gi, guild, city, threat, causes, restores if threat == REPEAL else -1)


def _charter_lapse_or_repeal(t: _Tick, guild: Guild) -> int:
    """Forget a guild charter that ended; returns its index when a ruler or
    faction repealed it this turn (a threat: its restoration), else -1."""
    from chronicler.agent_movements_state import IN_FORCE, LAPSED
    r = _charter_reform(t.world, guild)
    if r is None or r.repeal == IN_FORCE:
        return -1
    k = guild.charter_reform
    guild.charter_reform = -1
    if r.repeal == LAPSED or r.repealed_turn != t.world.turn:
        return -1
    _note(guild, t.world.turn, "repealed", r.repeal_event_id)
    return k


def _adopt_charter(t: _Tick, guild: Guild) -> None:
    """A guild charter in force for the guild's city (won by its movement)."""
    from chronicler.agent_movements_state import GUILD_CHARTER, IN_FORCE
    state = getattr(t.world, "agent_movements", None)
    if state is None or guild.charter_reform >= 0:
        return
    for k, r in enumerate(state.reforms):
        if r.kind == GUILD_CHARTER and r.repeal == IN_FORCE and guild.city in r.cities:
            guild.charter_reform = k
            guild.levy_turn = None
            _bump(t.state, "charters")
            _note(guild, t.world.turn, "charter", r.event_id)
            return


def _sync_privileges(t: _Tick, gi: int, guild: Guild, city) -> None:
    """Privileges follow the city's charter (market rights: the monopoly;
    self-government: a say in dues) and the guild charter (both)."""
    from chronicler.cities_state import MARKET_RIGHTS, SELF_GOVERNMENT
    world = t.world
    chartered = _charter_in_force(world, guild)
    monopoly = chartered or city.charter >= MARKET_RIGHTS
    say = chartered or city.charter >= SELF_GOVERNMENT
    region = world.regions[city.region]
    lord = t.civ(city.lord)
    for name, have, now in (("monopoly", guild.monopoly, monopoly), ("say", guild.say, say)):
        if have == now:
            continue
        setattr(guild, name, now)
        what = "the monopoly of its wares" if name == "monopoly" else "a say in the city's dues"
        if now:
            _bump(t.state, "privileges")
            ev = _emit(t, "guild_privilege", [lord.name if lord is not None else ""],
                       f"{guild.name[0].upper()}{guild.name[1:]} wins {what}",
                       importance=3, region=region.name)
            _note(guild, world.turn, "privilege", ev.event_id)
        else:
            _bump(t.state, "privileges_lost")
            ev = _emit(t, "guild_privilege_lost", [lord.name if lord is not None else ""],
                       f"{guild.name[0].upper()}{guild.name[1:]} loses {what}",
                       importance=3, region=region.name)
            _note(guild, world.turn, "lost", ev.event_id)


def _levies(t: _Tick) -> None:
    """A lord short of money, or at war, raises a city's dues (not under a
    guild charter, not a free city's own)."""
    from chronicler.cities_state import FREE_CITY
    world = t.world
    for gi, guild in living_guilds(world):
        city = t.cities.get(guild.city)
        lord = t.civ(city.lord) if city is not None else None
        if (city is None or lord is None or not lord.regions or city.charter == FREE_CITY
                or _levied(world, guild) or _charter_in_force(world, guild)):
            continue
        at_war = any(lord.name in pair for pair in world.active_wars)
        if lord.treasury >= LEVY_TREASURY and not at_war:
            continue
        chance = LEVY_CHANCE * (LEVY_SAY if guild.say else 1.0)
        if _rng(world, "levy", guild.city).random() >= chance:
            continue
        guild.levy_turn = world.turn
        city.grievance = _q(min(1.0, city.grievance + LEVY_GRIEVANCE))
        _bump(t.state, "levies")
        region = world.regions[city.region]
        why = "for the war" if at_war else "to fill the treasury"
        ev = _emit(t, "guild_levy", [lord.name],
                   f"{lord.name} raises the dues of {city.name} {why}", importance=4,
                   region=region.name)
        from chronicler.cities import _note as city_note
        city_note(city, world.turn, "levy", ev.event_id)
        _note(guild, world.turn, "levy", ev.event_id)
        _threatened(t, gi, guild, city, LEVY, [ev.event_id], -1)


def _threatened(t: _Tick, gi: int, guild: Guild, city, threat: int, causes, restores: int) -> None:
    """Record a threat to the guild's privileges; a strong guild may rise as a
    movement of the guild creed against the city's lord."""
    from chronicler.agent_movements_state import ENDED, GUILD, agent_movements_on
    world = t.world
    _bump(t.state, "threats")
    first = next((c for c in causes if c), "")
    if threat != LEVY:   # a levy has its own entry
        _note(guild, world.turn, "threat", first)
    guild.last_threat = world.turn
    if not agent_movements_on(world) or not t.agent_rows:
        return
    if city.satisfaction is not None and city.satisfaction >= MOVEMENT_SATISFACTION:
        return   # content townsmen do not rise (= movements.rs GUILD_SAT)
    movements = world.agent_movements.movements
    if 0 <= guild.movement < len(movements) and movements[guild.movement].stage != ENDED:
        return
    living = sum(1 for m in movements if m.creed == GUILD and m.stage != ENDED)
    lord = t.civ(city.lord)
    region = world.regions[city.region]
    if (living >= MAX_GUILD_MOVEMENTS or lord is None or not lord.regions
            or region.controller != lord.name or guild.masters < MOVEMENT_MASTERS):
        return
    chance = RESTORE_CHANCE if threat == REPEAL else MOVEMENT_CHANCE
    if _rng(world, "movement", guild.city, threat).random() >= chance:
        return
    from chronicler.agent_movements import found_guild_movement
    i, events = found_guild_movement(world, guild, city, THREAT_NAMES[threat], restores=restores,
                                     causes=causes, agent_bridge=t.bridge, phase10=t.phase10)
    if i < 0:
        return   # no aggrieved resident free to join
    t.events.extend(events)
    guild.movement = i
    _bump(t.state, "movements")
    _note(guild, world.turn, "movement", events[-1].event_id if events else "")


def on_guild_rising(world, movement: int) -> None:
    """A guild movement rose: its city's unrest rises (the cities' revolt may
    follow, and with it a free city)."""
    guild = guild_of_movement(world, movement)
    cities = getattr(world, "cities", None)
    if guild is None or cities is None:
        return
    for city in cities.cities:
        if city.settlement_id == guild.city:
            city.unrest = _q(min(1.0, city.unrest + RISING_UNREST))
            return


def movement_appeal(world, movement: int) -> float:
    """A guild movement's appeal factor from its guild's purse (1 otherwise)."""
    guild = guild_of_movement(world, movement)
    if guild is None:
        return 1.0
    return 1.0 + min(APPEAL_CAP, APPEAL_CAP * guild.wealth / WEALTH_APPEAL)


# ---------------------------------------------------------------------------
# Burghers
# ---------------------------------------------------------------------------

def burgher_weights(world) -> dict[int, float]:
    """Per lord's civ index: rank x (charter weight + guild weight) over its
    cities (chartered and free cities, and cities with a guild)."""
    cities = getattr(world, "cities", None)
    if cities is None:
        return {}
    guilds = guild_index(world) or {}
    weight: dict[int, float] = {}
    for city in cities.cities:
        if city.lord < 0:
            continue
        w = CHARTER_WEIGHT[city.charter] + (GUILD_WEIGHT if city.settlement_id in guilds else 0.0)
        if w > 0:
            weight[city.lord] = weight.get(city.lord, 0.0) + city.rank * w
    return weight


def _burghers(t: _Tick) -> None:
    from chronicler.factions import FACTION_FLOOR, normalize_influence
    from chronicler.models import FactionType
    world, state = t.world, t.state
    weight = burgher_weights(world)
    while len(state.burgher_idle) < len(world.civilizations):
        state.burgher_idle.append(0)
    for idx, civ in enumerate(world.civilizations):
        inf = civ.factions.influence
        if not civ.regions:
            continue
        w = weight.get(idx, 0.0)
        if w > 0:
            state.burgher_idle[idx] = 0
            if FactionType.BURGHER not in inf:
                inf[FactionType.BURGHER] = FACTION_FLOOR
                normalize_influence(civ.factions)
                _bump(state, "burghers_formed")
            inf[FactionType.BURGHER] += min(BURGHER_CAP, BURGHER_PER_WEIGHT * w)
            normalize_influence(civ.factions)
            continue
        if FactionType.BURGHER not in inf:
            continue
        state.burgher_idle[idx] += 1
        if state.burgher_idle[idx] >= BURGHER_IDLE_TURNS:
            del inf[FactionType.BURGHER]
            state.burgher_idle[idx] = 0
            _bump(state, "burghers_dissolved")
        else:
            inf[FactionType.BURGHER] = max(0.0, inf[FactionType.BURGHER] - BURGHER_IDLE_DECAY)
        normalize_influence(civ.factions)


# ---------------------------------------------------------------------------
# Movement news (the region batch)
# ---------------------------------------------------------------------------

def movement_news_columns(world) -> tuple[list[int], list[int]] | None:
    """Per region index, the news code (creed x 4 + kind) and intensity of
    last turn's strongest movement event there, from the persisted movement
    records (founding, rising, reform, crackdown at ``turn - 1``); None when
    news is off. Nothing transient is kept on the world."""
    if not news_enabled(world):
        return None
    n = len(world.regions)
    codes = [NO_NEWS] * n
    strength = [0] * n
    last = world.turn - 1
    for m in world.agent_movements.movements:
        happened = (
            (m.founded_turn == last, m.home_region, FOUNDING_NEWS),
            (m.rising_turn == last, m.rising_region, RISING_NEWS),
            (m.reform_turn == last, m.home_region, REFORM_NEWS),
            (m.crackdown_turn == last, m.crackdown_region, CRACKDOWN_NEWS),
        )
        for yes, region, kind in happened:
            if not yes or not 0 <= region < n:
                continue
            intensity = NEWS_INTENSITY[kind]
            if intensity > strength[region]:
                codes[region] = m.creed * len(NEWS_KINDS) + kind
                strength[region] = intensity
    return codes, strength


def news_founding_factor(aggrieved: int, informed: int) -> float:
    """Founding chance factor of a candidate region and creed."""
    if aggrieved <= 0 or informed <= 0:
        return 1.0
    return 1.0 + NEWS_FOUND * min(1.0, informed / aggrieved / NEWS_FULL_SHARE)


# ---------------------------------------------------------------------------
# Snapshot, history and metrics
# ---------------------------------------------------------------------------

def snapshot_summary(world: "WorldState") -> dict:
    """Per-turn summary for ``TurnSnapshot.guilds``."""
    from chronicler.agent_movements_state import ENDED
    state = world.guilds
    regions = world.regions
    guilds = []
    for gi, g in living_guilds(world):
        row = {"id": gi, "name": g.name, "city": g.city,
               "region": regions[g.region].name if g.region < len(regions) else None,
               "kind": KIND_NAMES[g.kind], "masters": round(g.masters, 1),
               "wealth": round(g.wealth, 1), "monopoly": g.monopoly, "say": g.say}
        if _levied(world, g):
            row["levy"] = True
        if _charter_in_force(world, g):
            row["charter"] = g.charter_reform
        movements = getattr(getattr(world, "agent_movements", None), "movements", None) or []
        if 0 <= g.movement < len(movements) and movements[g.movement].stage != ENDED:
            row["movement"] = g.movement
        guilds.append(row)
    from chronicler.models import FactionType
    burghers = {civ.name: round(float(civ.factions.influence[FactionType.BURGHER]), 4)
                for civ in world.civilizations
                if civ.regions and FactionType.BURGHER in civ.factions.influence}
    return {
        "guilds": guilds,
        "dissolved": sum(1 for g in state.guilds if g.dissolved_turn is not None),
        "burghers": burghers,
        "counters": {k: state.counters.get(k, 0) for k in COUNTER_KEYS},
    }


def guild_history(world: "WorldState", index: int) -> list[str]:
    """One guild's record as text lines, with the event text the simulation
    wrote, then its last movement's record."""
    g = world.guilds.guilds[index]
    by_id = {e.event_id: e for e in world.events_timeline if e.event_id}
    region = world.regions[g.region].name
    status = (f"dissolved turn {g.dissolved_turn}" if g.dissolved_turn is not None
              else f"standing: {g.masters:.1f} masters, purse {g.wealth:.1f}"
                   + (", monopoly" if g.monopoly else "") + (", say in dues" if g.say else ""))
    lines = [f"{g.name} ({KIND_NAMES[g.kind]}), {region}; founded turn {g.founded_turn}; "
             f"peak {g.peak_masters:.1f} masters; {status}"]
    for turn, kind, eid in g.history:
        ev = by_id.get(eid)
        lines.append(f"  {turn:>4}: {kind}: {ev.description if ev is not None else ''}")
    state = getattr(world, "agent_movements", None)
    if state is not None:
        from chronicler.agent_movements import movement_history
        from chronicler.agent_movements_state import GUILD
        for i, m in enumerate(state.movements):
            if guild_of_movement(world, i) is g or (m.creed == GUILD and m.name.startswith(g.name)):
                lines.extend(f"  {line}" for line in movement_history(world, i))
    return lines


def extract_guild_metrics(bundles: list[dict]) -> dict:
    """Analytics: per run, the final counters and the peak living guilds."""
    runs = 0
    totals: dict[str, float] = {k: 0 for k in COUNTER_KEYS}
    peak = []
    for bundle in bundles:
        rows = [h.get("guilds") for h in bundle.get("history") or []
                if isinstance(h, dict) and h.get("guilds")]
        if not rows:
            continue
        runs += 1
        last = rows[-1].get("counters", {})
        for k in COUNTER_KEYS:
            totals[k] += float(last.get(k, 0))
        peak.append(max(len(r.get("guilds", [])) for r in rows))
    if not runs:
        return {"runs": 0}
    return {
        "runs": runs,
        "per_run": {k: round(v / runs, 3) for k, v in totals.items()},
        "peak_guilds_mean": round(sum(peak) / runs, 3),
    }
