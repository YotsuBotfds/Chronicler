"""Technology as diffusing techniques (``--techniques``, default off).

The monolithic tech era is replaced by a registry of techniques
(:data:`chronicler.techniques_state.TECHNIQUES`: agriculture, metallurgy,
construction, navigation, writing and administration, medicine, commerce and
banking, military), each with prerequisites and the terrain or resources it
needs. Every region keeps a practice level per technique: the share of its
people who practise it. Once per turn, in Phase 4 (where era advancement
used to run), :func:`tick_techniques`:

1. **Practice** (:func:`_update_practice`): within a region practice grows
   logistically toward 1 (toward :data:`UNSUITED_CAP` where the region lacks
   the technique's terrain or resources), once its prerequisites are
   practised. It spreads between regions along the contact ledger's flows,
   each channel carrying some domains more than others (merchants carry
   commerce and navigation, migrants husbandry and building, soldiers
   arms, pilgrims letters and medicine), plus the shared borders of regions
   under one ruler. It decays: a little always, and much faster when the
   practitioners who share the craft (the region's own plus those of the
   regions it is in close contact with) fall short of what the technique
   needs (:func:`sustain_need`, rising with the tier). A plague, famine or
   collapse that thins or isolates the practitioners therefore loses the
   most demanding techniques first: a real dark age, not a dice roll.
2. **Invention** (:func:`_invent`): a civ meeting the old era advance's
   research inputs (culture and economy thresholds, treasury, the tech
   diffusion rate multiplier, the scholarship focus) may invent one
   technique per turn whose prerequisites it knows; its tech focus and great
   scientists steer and speed the choice. The invention starts practice in
   one of its suitable regions.
3. **Gains and losses** per civ (hysteresis: taken up at :data:`GAIN_LEVEL`
   in any region, lost below :data:`LOSE_LEVEL` everywhere), attributed to
   the channel and source that carried them, or to land changing hands.
4. **Era** (:func:`_derive_eras`): a civ's ``tech_era`` is the highest era
   whose tier, and every tier below it, it practises to a quorum
   (:data:`ERA_QUORUM`), one step per turn, with hysteresis. Advances and
   regressions keep the old events, era bonuses, focus selection, named
   events and great-person bookkeeping, so every era consumer keeps working.
   The M18 random regression does not run while techniques are on.

Effects through existing modifiers (each hook is guarded by
:func:`techniques_on`): battle strength (:func:`military_factor`), build
costs (:func:`build_cost`), trade range (:func:`extend_trade_routes`),
epidemic fatality and quarantine (:func:`epidemic_cfr_factors`,
:func:`quarantine_efficacy`, with ``--epidemiology``), credit capacity
(:func:`credit_factor`, with ``--finance``) and crop yields
(:func:`yield_multiplier`, the one ecology hook).

Determinism: one namespaced ``stable_hash_int`` draw per civ per turn
(``technique_invent``); everything else is a deterministic function of saved
state, iterated in index order. Provenance: inventions, adoptions ("X learned
Y from Z's merchants"), losses, advances and regressions cite their causes.
See ``docs/integration/techniques.md``.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from chronicler.techniques_state import (
    CH_INVENTION, CH_NEIGHBOURS, CH_PEOPLE, CH_PILGRIMS, CH_SEEDED, CH_SOLDIERS, CH_TRADE,
    CHANNELS, CONQUEST, DOMAINS, MAX_TIER, TECHNIQUE_INDEX, TECHNIQUES, TechniqueState,
    techniques_on,
)

if TYPE_CHECKING:  # pragma: no cover
    from chronicler.models import Civilization, Event, Region, WorldState

#: Default for worlds newly created by the CLI/batch/live entry points.
DEFAULT_ENABLED_FOR_NEW_WORLDS = False

# ---------------------------------------------------------------------------
# Parameters (illustrative calibrations, documented in docs/integration/techniques.md)
# ---------------------------------------------------------------------------

QUANTUM_DIGITS = 6
DROP_LEVEL = 0.002        # rows below this are removed
GAIN_LEVEL = 0.10         # a civ takes up a technique when one of its regions practises this much
LOSE_LEVEL = 0.03         # ... and loses it once every region it holds is below this
PRACTISED = 0.25          # civ practice (over its suitable regions) that counts toward a new era
KEEP_PRACTISED = 0.10     # ... and that keeps an era already reached
PREREQ_LEVEL = 0.20       # a region takes a technique up only with its prerequisites practised this much
UNSUITED_CAP = 0.20       # practice ceiling without the technique's terrain or resources
INVENT_LEVEL = 0.20       # practice an invention starts with in its region
SEED_LEVEL = 0.60         # practice of the techniques a world already had when switched on
ADOPT_RATE = 0.15         # logistic adoption within a region per turn
BASE_FORGET = 0.01        # per-turn forgetting
EMPTY_FORGET = 0.05       # per-turn fading of the practice of a region nobody lives in
LEVEL_SMOOTHING = 0.25    # weight of this tick's measurement in a civ's practice levels
SHORTFALL_FORGET = 0.20   # extra forgetting at a complete practitioner shortfall
DIFFUSION_SCALE = 0.005   # adoption hazard per unit of channel-weighted contact x source practice
NEIGHBOUR_FLOW = 3.0      # contact of a shared border under one ruler (every border, ledger off)
CONTACT_FULL = 10.0       # weighted contact at which a partner's people fully share the craft
IMPORT_FLOW = 1.0         # trade flow at which a partner region's resources supply a civ
SUSTAIN_BASE = 12.0       # connected people a technique needs: SUSTAIN_BASE * tier ** SUSTAIN_EXP
SUSTAIN_EXP = 1.5
PRACTITIONER_SHARE = 0.5  # pool weight of people who do not practise (practitioners count 1)
OCCUPIED_GROWTH = 0.0     # growth multiplier in an occupied region
FAMINE_GROWTH = 0.5       # growth multiplier during a famine
INVENT_P = 0.10           # invention chance per turn at full research intensity, tier 1
TIER_DIFFICULTY = (1.0, 1.0, 1.5, 2.5, 4.0, 6.0, 9.0, 13.0)  # index = tier
INVENTIONS_PER_ERA = 2    # an invention costs the era advance's treasury cost / this
SCHOLARSHIP_COST = 0.8    # scholarship focus: cost multiplier (as for the old era advance)
SCHOLARSHIP_RESEARCH = 1.25
SCIENTIST_RESEARCH = 0.5  # research bonus per active great scientist (at most two count)
FOCUS_AFFINITY_BONUS = 1  # candidate score for the focus's domains
ERA_QUORUM = (0, 3, 3, 3, 3, 2, 2, 1)   # techniques of a tier to practise, index = tier
ERA_GRACE = 3             # consecutive ticks below the keep quorum before an era is lost
RANGE_PRACTICE = 0.30     # practice at which a region's navigation or roads extend trade

#: Channel x domain carrying weights (domains in ``DOMAINS`` order):
#: agriculture, metallurgy, construction, navigation, writing, medicine, commerce, military.
CHANNEL_DOMAIN_WEIGHTS: dict[int, tuple[float, ...]] = {
    CH_TRADE:      (0.6, 0.8, 0.3, 1.0, 0.4, 0.3, 1.0, 0.2),
    CH_PEOPLE:     (1.0, 0.5, 0.8, 0.4, 0.5, 0.6, 0.4, 0.3),
    CH_SOLDIERS:   (0.1, 0.6, 0.4, 0.1, 0.1, 0.2, 0.1, 1.0),
    CH_PILGRIMS:   (0.2, 0.1, 0.4, 0.2, 1.0, 1.0, 0.2, 0.0),
    CH_NEIGHBOURS: (0.5, 0.5, 0.5, 0.3, 0.5, 0.5, 0.5, 0.5),
}
#: Contact weight of each channel for the shared practitioner pool (the
#: ledger's own weights, then the shared border).
POOL_WEIGHTS = (1.0, 1.0, 0.25, 2.0, 1.0)

#: Tech focus -> domains its inventions favour.
FOCUS_DOMAINS: dict[str, tuple[int, ...]] = {
    "navigation": (3,), "metallurgy": (1,), "agriculture": (0,),
    "fortification": (2, 7), "commerce": (6,), "scholarship": (4, 5),
    "exploration": (3,), "banking": (6,), "printing": (4,),
    "mechanization": (1, 2), "railways": (2,), "naval_power": (3, 7),
    "networks": (4, 6), "surveillance": (4,), "media": (4,),
}

# Effects (practice-weighted; region practice for local effects, civ practice
# over suitable regions for civ-wide ones).
MILITARY_EFFECTS: dict[str, tuple[float, float]] = {   # (attack, defence)
    "bronze_working": (0.05, 0.05), "iron_working": (0.08, 0.08), "horsemanship": (0.04, 0.02),
    "siegecraft": (0.05, 0.0), "stirrup": (0.06, 0.03), "castles": (0.0, 0.08),
    "gunpowder": (0.12, 0.10),
}
MILITARY_CAP = 1.4
BUILD_DISCOUNT: dict[str, float] = {
    "masonry": 0.08, "roads": 0.04, "aqueducts": 0.04, "castles": 0.04,
    "steam_power": 0.06, "railways": 0.04,
}
FORTIFICATION_DISCOUNT: dict[str, float] = {"castles": 0.10}
BUILD_FLOOR = 0.6
CFR_REDUCTION: dict[str, float] = {
    "herbalism": 0.05, "physicians": 0.10, "lazarets": 0.05, "vaccination": 0.30,
}
CFR_FLOOR = 0.5
QUARANTINE_BONUS: dict[str, float] = {"law_codes": 0.05, "lazarets": 0.15}
QUARANTINE_CAP = 0.9
CREDIT_BONUS: dict[str, float] = {"coinage": 0.10, "banking": 0.30, "double_entry": 0.20}
RESEARCH_BONUS: dict[str, float] = {"writing": 0.10, "law_codes": 0.10, "printing": 0.30,
                                    "telegraph": 0.30}
GRAIN_YIELD: dict[str, float] = {"irrigation": 0.05, "ox_plough": 0.05, "heavy_plough": 0.08}
FISH_YIELD: dict[str, float] = {"sailing": 0.04}

_K = len(TECHNIQUES)
_PREREQS: tuple[tuple[int, ...], ...] = tuple(
    tuple(TECHNIQUE_INDEX[p] for p in t.prereqs) for t in TECHNIQUES)
_BY_TIER: dict[int, tuple[int, ...]] = {
    tier: tuple(k for k, t in enumerate(TECHNIQUES) if t.tier == tier) for tier in range(1, MAX_TIER + 1)}

def sustain_need(tier: int) -> float:
    """Connected people a technique of ``tier`` needs to hold its ground.

    The pool of a region is its own people plus those of the regions it is in
    close contact with (weighted by contact up to :data:`CONTACT_FULL`), each
    person counting fully when they practise the technique and
    :data:`PRACTITIONER_SHARE` when they do not.
    """
    return SUSTAIN_BASE * float(tier) ** SUSTAIN_EXP


# ---------------------------------------------------------------------------
# Switch
# ---------------------------------------------------------------------------

def techniques_enabled(world) -> bool:
    return techniques_on(world)


def set_techniques_enabled(world: "WorldState", enabled: bool) -> None:
    """Enable (an empty state, initialized on the first tick) or disable."""
    if enabled:
        if not techniques_on(world):
            world.techniques = TechniqueState()
    else:
        world.techniques = None


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _q(x: float) -> float:
    return round(x, QUANTUM_DIGITS)


def _draw(namespace: str, world, *parts: object) -> float:
    from chronicler.utils import stable_hash_int
    return random.Random(stable_hash_int(namespace, world.seed, world.turn, *parts)).random()


def _rate(world) -> float:
    from chronicler.tuning import K_TECH_DIFFUSION_RATE, get_multiplier
    return max(get_multiplier(world, K_TECH_DIFFUSION_RATE), 0.1)


def _civ_indices(world) -> dict[str, int]:
    return {c.name: i for i, c in enumerate(world.civilizations)}


def _controllers(world, civ_idx: dict[str, int]) -> list[int]:
    return [civ_idx.get(r.controller, -1) if r.controller else -1 for r in world.regions]


def _civ_index_of(world, civ) -> int:
    for i, c in enumerate(world.civilizations):
        if c is civ or c.name == civ.name:
            return i
    return -1


def label(k: int) -> str:
    return TECHNIQUES[k].label


def _era_order():
    from chronicler.models import TechEra
    return list(TechEra)


# ---------------------------------------------------------------------------
# Contacts, suitability and civ practice
# ---------------------------------------------------------------------------

def _contacts(world, ctrl: list[int]) -> dict[int, dict[int, list[float]]]:
    """Undirected per-channel contact between region pairs: the contact
    ledger's four channels (both directions summed) and the shared border of
    regions under one controller (every border while the ledger is off)."""
    from chronicler import contact_ledger as cl

    regions = world.regions
    n = len(regions)
    links: dict[int, dict[int, list[float]]] = {}

    def add(a: int, b: int, c: int, v: float) -> None:
        if v <= 0.0:
            return
        for x, y in ((a, b), (b, a)):
            row = links.setdefault(x, {})
            vals = row.get(y)
            if vals is None:
                vals = row[y] = [0.0, 0.0, 0.0, 0.0, 0.0]
            vals[c] += v

    ledger_on = cl.ledger_enabled(world)
    if ledger_on:
        for src, dst, t, p, s, g in world.contact_ledger.edges:
            if src == dst or src >= n or dst >= n:
                continue
            add(src, dst, CH_TRADE, t)
            add(src, dst, CH_PEOPLE, p)
            add(src, dst, CH_SOLDIERS, s)
            add(src, dst, CH_PILGRIMS, g)
    index = {r.name: i for i, r in enumerate(regions)}
    for i, region in enumerate(regions):
        for adj in region.adjacencies:
            j = index.get(adj)
            if j is None or j <= i:
                continue
            if (ledger_on and ctrl[i] >= 0 and ctrl[i] == ctrl[j]) or not ledger_on:
                add(i, j, CH_NEIGHBOURS, NEIGHBOUR_FLOW)
    return links


def _region_resources(region) -> set[int]:
    return {rt for rt in region.resource_types if rt != 255}


def _suitability(world, ctrl: list[int], links) -> list[list[bool]]:
    """suit[r][k]: region r has the terrain or resources technique k needs.

    Resources a technique may be supplied with (``supply``) count when any
    region of the controlling civ has them, or a region trading with one of
    its regions at :data:`IMPORT_FLOW` or more.
    """
    regions = world.regions
    own = [_region_resources(r) for r in regions]
    supply_by_civ: dict[int, set[int]] = {}
    for i, c in enumerate(ctrl):
        if c < 0:
            continue
        pool = supply_by_civ.setdefault(c, set())
        pool |= own[i]
        for j, vals in links.get(i, {}).items():
            if vals[CH_TRADE] >= IMPORT_FLOW:
                pool |= own[j]
    suit: list[list[bool]] = []
    for i, region in enumerate(regions):
        supply = supply_by_civ.get(ctrl[i])
        if supply is None:
            supply = set(own[i])
            for j, vals in links.get(i, {}).items():
                if vals[CH_TRADE] >= IMPORT_FLOW:
                    supply |= own[j]
        row = []
        for t in TECHNIQUES:
            if not t.terrains and not t.resources and not t.river:
                row.append(True)
                continue
            ok = region.terrain in t.terrains or (t.river and bool(region.river_mask))
            if not ok and t.resources:
                have = supply if t.supply else own[i]
                ok = any(res in have for res in t.resources)
            row.append(ok)
        suit.append(row)
    return suit


def _civ_practice(pm: dict, suit, regions, members: list[int], k: int) -> float:
    """Population-weighted practice of technique ``k`` over the suitable regions."""
    total = 0.0
    weighted = 0.0
    for r in members:
        if not suit[r][k]:
            continue
        pop = max(0, int(regions[r].population))
        total += pop
        weighted += pop * pm.get((r, k), 0.0)
    return weighted / total if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Practice dynamics
# ---------------------------------------------------------------------------

def _update_practice(world, st: TechniqueState, ctrl: list[int], links, suit) -> tuple[dict, dict]:
    """One turn of growth, diffusion and decay. Returns (practice, meta)."""
    regions = world.regions
    n = len(regions)
    old = {}
    meta: dict[tuple[int, int], tuple[int, int, int]] = {}
    for r, k, p, src, ch, sciv in st.rows:
        if r < n and k < _K:
            old[(r, k)] = p
            meta[(r, k)] = (src, ch, sciv)
    pops = [max(0, int(r.population)) for r in regions]
    rate = _rate(world)
    # Technique -> regions practising it (sources).
    by_tech: dict[int, list[int]] = {}
    for (r, k) in sorted(old):
        by_tech.setdefault(k, []).append(r)
    new: dict[tuple[int, int], float] = {}
    new_meta: dict[tuple[int, int], tuple[int, int, int]] = {}
    neighbours = {t: sorted(row) for t, row in links.items()}
    pool_link: dict[int, dict[int, float]] = {}
    for t, row in links.items():
        pool_link[t] = {j: min(1.0, sum(w * v for w, v in zip(POOL_WEIGHTS, vals)) / CONTACT_FULL)
                        for j, vals in row.items()}
    for k in range(_K):
        spec = TECHNIQUES[k]
        sources = by_tech.get(k, ())
        if not sources:
            continue
        need = sustain_need(spec.tier)
        weights = [CHANNEL_DOMAIN_WEIGHTS[c][spec.domain] for c in range(5)]
        targets = set(sources)
        for j in sources:
            targets.update(links.get(j, {}).keys())
        for t in sorted(targets):
            if t >= n:
                continue
            p = old.get((t, k), 0.0)
            if pops[t] <= 0:
                # Nobody lives here now: the people who left carry the craft
                # and settlers may return with it, so the practice fades
                # slowly instead of vanishing (it teaches no one meanwhile).
                if p > 0.0:
                    value = _q(p * (1.0 - EMPTY_FORGET))
                    if value >= DROP_LEVEL:
                        new[(t, k)] = value
                        new_meta[(t, k)] = meta[(t, k)]
                continue
            cap = 1.0 if suit[t][k] else UNSUITED_CAP
            prereq_ok = all(old.get((t, q), 0.0) >= PREREQ_LEVEL for q in _PREREQS[k])
            row = links.get(t, {})
            plink = pool_link.get(t, {})
            pool = pops[t] * (PRACTITIONER_SHARE + (1.0 - PRACTITIONER_SHARE) * p)
            hazard = 0.0
            best = (0.0, -1, -1)
            for j in neighbours.get(t, ()):
                pj = old.get((j, k), 0.0)
                pool += plink.get(j, 0.0) * pops[j] * (PRACTITIONER_SHARE + (1.0 - PRACTITIONER_SHARE) * pj)
                if pj <= 0.0 or pops[j] <= 0:
                    continue
                vals = row[j]
                for c in range(5):
                    contribution = weights[c] * vals[c] * pj
                    if contribution > 0.0:
                        hazard += contribution
                        if contribution > best[0]:
                            best = (contribution, j, c)
            shortfall = max(0.0, 1.0 - pool / need) if need > 0 else 0.0
            disruption = 1.0
            region = regions[t]
            if region.occupied_by:
                disruption = OCCUPIED_GROWTH
            elif region.famine_cooldown > 0:
                disruption = FAMINE_GROWTH
            growth = 0.0
            inflow = 0.0
            if prereq_ok:
                growth = ADOPT_RATE * p * (1.0 - p / cap) * (1.0 - shortfall) * disruption
                if p < cap and hazard > 0.0:
                    inflow = (cap - p) * -math.expm1(-DIFFUSION_SCALE * rate * hazard)
            forget = (BASE_FORGET + SHORTFALL_FORGET * shortfall) * p
            value = _q(min(1.0, max(0.0, p + growth - forget + inflow)))
            if value < DROP_LEVEL:
                continue
            new[(t, k)] = value
            m = meta.get((t, k))
            if m is None or (p < GAIN_LEVEL and inflow > growth and best[1] >= 0
                             and m[1] not in (CH_INVENTION, CH_SEEDED)):
                if best[1] >= 0:
                    m = (best[1], best[2], ctrl[best[1]])
                elif m is None:
                    m = (-1, CH_NEIGHBOURS, -1)
            new_meta[(t, k)] = m
    return new, new_meta


# ---------------------------------------------------------------------------
# Invention
# ---------------------------------------------------------------------------

def _research_multiplier(world, civ, civ_levels: dict[int, float]) -> float:
    mult = 1.0 + sum(bonus * civ_levels.get(TECHNIQUE_INDEX[key], 0.0)
                     for key, bonus in RESEARCH_BONUS.items())
    if civ.active_focus == "scholarship":
        mult *= SCHOLARSHIP_RESEARCH
    scientists = sum(1 for gp in civ.great_persons if gp.active and gp.role == "scientist")
    mult *= 1.0 + SCIENTIST_RESEARCH * min(2, scientists)
    return mult


def _invent(world, st: TechniqueState, civ_i: int, civ, members: list[int], known: set[int],
            practice: dict, meta: dict, suit, civ_levels: dict[int, float], acc,
            events: list) -> int | None:
    """At most one invention for ``civ`` this turn. Returns the technique index."""
    from chronicler import provenance as prov
    from chronicler.models import Event
    from chronicler.tech import TECH_REQUIREMENTS, _era_index
    from chronicler.utils import stable_hash_int

    era_idx = _era_index(civ.tech_era)
    regions = world.regions
    candidates: list[tuple[tuple, int, list[int]]] = []
    focus_domains = FOCUS_DOMAINS.get(civ.active_focus or "", ())
    for k, spec in enumerate(TECHNIQUES):
        if k in known or spec.tier > era_idx + 1:
            continue
        if any(q not in known for q in _PREREQS[k]):
            continue
        # Sites: inhabited regions that suit it and practise its prerequisites.
        sites = [r for r in members if suit[r][k] and regions[r].population > 0
                 and all(practice.get((r, q), 0.0) >= PREREQ_LEVEL for q in _PREREQS[k])]
        if not sites:
            continue
        score = (-spec.tier, FOCUS_AFFINITY_BONUS if spec.domain in focus_domains else 0,
                 len(sites), stable_hash_int("technique_choice", world.seed, civ_i, k))
        candidates.append((score, k, sites))
    if not candidates:
        return None
    _, k, sites = max(candidates, key=lambda c: c[0])
    spec = TECHNIQUES[k]
    reqs = TECH_REQUIREMENTS.get(_era_order()[spec.tier - 1])
    if reqs is None:
        return None
    min_culture, min_economy, era_cost = reqs
    rate = _rate(world)
    cost = era_cost / INVENTIONS_PER_ERA / rate
    scholarship = civ.active_focus == "scholarship"
    if scholarship:
        cost *= SCHOLARSHIP_COST
    cost = int(cost)
    if civ.culture < min_culture or civ.economy < min_economy or civ.treasury < cost:
        return None
    intensity = max(0.0, min(1.0, (civ.culture + civ.economy) / 200.0))
    chance = (INVENT_P * intensity * rate * _research_multiplier(world, civ, civ_levels)
              / TIER_DIFFICULTY[spec.tier])
    if _draw("technique_invent", world, civ_i) >= chance:
        return None
    # Where: the capital if it is a site, else the most populous site.
    site = max(sites, key=lambda r: (regions[r].name == civ.capital_region,
                                     int(regions[r].population), -r))
    if acc is not None:
        acc.add(civ_i, civ, "treasury", -cost, "keep")
    else:
        civ.treasury -= cost
    practice[(site, k)] = _q(max(practice.get((site, k), 0.0), INVENT_LEVEL))
    meta[(site, k)] = (site, CH_INVENTION, civ_i)
    if scholarship:
        world.events_timeline.append(Event(
            turn=world.turn, event_type="capability_scholarship",
            actors=[civ.name], description=f"{civ.name} scholarship reduces tech cost",
            importance=1,
        ))
    ev = Event(
        turn=world.turn, event_type="technique_invented", actors=[civ.name],
        description=f"{civ.name} develops {spec.label} in {regions[site].name}",
        importance=5 if spec.tier < 4 else 6, region=regions[site].name,
    )
    causes = [prov.recall(world, prov.key("technique", civ.name, TECHNIQUES[q].key)) for q in _PREREQS[k]]
    if any(gp.active and gp.role == "scientist" for gp in civ.great_persons):
        causes.append(prov.recall(world, prov.key("gp_role", civ.name, "scientist")))
    prov.cite(ev, *causes)
    prov.remember(world, prov.key("technique", civ.name, spec.key), ev)
    events.append(ev)
    st.counts["invented"] = st.counts.get("invented", 0) + 1
    return k


# ---------------------------------------------------------------------------
# Gains and losses
# ---------------------------------------------------------------------------

def _decay_causes(world, civ_name: str, region_names: list[str]) -> list[str | None]:
    from chronicler import provenance as prov
    out: list[str | None] = []
    for name in region_names:
        out += [prov.recall(world, prov.key("pandemic", name), within=30),
                prov.open_episode(world, "famine", name),
                prov.open_episode(world, "demographic_crisis", name),
                prov.recall(world, prov.key("occupation", name)),
                prov.recall(world, prov.key("disaster", name), within=10)]
    out += [prov.recall(world, prov.key("collapse", civ_name), within=50),
            prov.recall(world, prov.key("twilight", civ_name)),
            prov.recall(world, prov.key("secession", civ_name), within=30)]
    return out


def _land_causes(world, civ_name: str, region_names: list[str]) -> list[str | None]:
    from chronicler import provenance as prov
    out: list[str | None] = []
    for name in region_names:
        out += [prov.recall(world, prov.key("conquest", name), within=5),
                prov.recall(world, prov.key("occupation", name), within=5)]
    out += [prov.recall(world, prov.key("secession", civ_name), within=5),
            prov.recall(world, prov.key("conquered", civ_name), within=5)]
    return out


_TRANSFER_TYPES = frozenset({
    "twilight_absorption", "union_annexation", "civ_conquered", "annexation", "secession",
    "restoration", "liberation", "occupation_revolt",
})
TRANSFER_WINDOW = 5


def _transfer_causes(world, old_owner: str, new_owner: str, region: str) -> list[str | None]:
    """Recent committed events that moved land between the two civs (or this
    region): absorptions and annexations are not in the causal index, so the
    last few turns of the timeline are read (read-only, newest first)."""
    out: list[str | None] = []
    for ev in reversed(world.events_timeline):
        if ev.turn < world.turn - TRANSFER_WINDOW:
            break
        if ev.event_type not in _TRANSFER_TYPES or not ev.event_id:
            continue
        actors = set(ev.actors) | set(ev.civs)
        if ev.region == region or (old_owner in actors and new_owner in actors):
            out.append(ev.event_id)
            if len(out) >= 2:
                break
    return out


def _gains_and_losses(world, st: TechniqueState, ctrl: list[int], old_rows: dict,
                      practice: dict, meta: dict, invented: dict[int, int], events: list
                      ) -> list[set[int]]:
    """Update every civ's known set; emit adoption and loss events."""
    from chronicler import provenance as prov
    from chronicler.models import Event

    regions = world.regions
    civs = world.civilizations
    prev_ctrl = st.controllers
    held_before = {i for i in prev_ctrl if i >= 0}
    known_now: list[set[int]] = []
    for ci, civ in enumerate(civs):
        members = [r for r, c in enumerate(ctrl) if c == ci]
        if not members:
            known_now.append(set())
            continue
        maxp = [0.0] * _K
        best_region = [-1] * _K
        for r in members:
            for k in range(_K):
                p = practice.get((r, k), 0.0)
                if p > maxp[k]:
                    maxp[k] = p
                    best_region[k] = r
        fresh = ci >= len(st.known) or ci not in held_before
        if fresh:
            # A new polity (secession, restoration, first tick) starts with
            # what its land practises, silently.
            known_now.append({k for k in range(_K) if maxp[k] >= GAIN_LEVEL})
            continue
        before = set(st.known[ci])
        now = {k for k in before if maxp[k] >= LOSE_LEVEL}
        now |= {k for k in range(_K) if k not in before and maxp[k] >= GAIN_LEVEL}
        for k in sorted(now - before):
            if invented.get(ci) == k:
                continue
            r = best_region[k]
            spec = TECHNIQUES[k]
            src, ch, sciv = meta.get((r, k), (-1, CH_NEIGHBOURS, -1))
            region_name = regions[r].name
            causes: list[str | None] = []
            if r < len(prev_ctrl) and prev_ctrl[r] != ci:
                channel = CONQUEST
                old_owner = prev_ctrl[r]
                text = f"{civ.name} takes up {spec.label} in newly held {region_name}"
                old_name = civs[old_owner].name if 0 <= old_owner < len(civs) else ""
                causes += _land_causes(world, old_name, [region_name])
                causes += _transfer_causes(world, old_name, civ.name, region_name)
                if old_name:
                    causes.append(prov.recall(world, prov.key("technique", old_name, spec.key)))
                    causes.append(prov.recall(world, prov.key("secession", civ.name), within=5))
            else:
                channel = CHANNELS[ch] if 0 <= ch < len(CHANNELS) else "neighbours"
                if 0 <= sciv < len(civs) and sciv != ci:
                    source = civs[sciv].name
                    causes.append(prov.recall(world, prov.key("technique", source, spec.key)))
                else:
                    source = None
                place = regions[src].name if 0 <= src < len(regions) else "its neighbours"
                carriers = {CH_TRADE: "merchants", CH_SOLDIERS: "soldiers", CH_PILGRIMS: "pilgrims",
                            CH_PEOPLE: "migrants"}.get(ch)
                if sciv == ci and carriers is None:
                    text = f"{civ.name} revives {spec.label} in {region_name}"
                elif carriers is None:
                    text = f"{civ.name} learned {spec.label} from {source or place} across the border"
                elif ch == CH_PEOPLE:
                    text = f"{civ.name} learned {spec.label} from migrants out of {source or place}"
                elif source is not None:
                    text = f"{civ.name} learned {spec.label} from {_possessive(source)} {carriers}"
                else:
                    text = f"{civ.name} learned {spec.label} from the {carriers} of {place}"
            ev = Event(
                turn=world.turn, event_type="technique_adopted", actors=[civ.name],
                description=text, importance=3 if spec.tier < 4 else 4, region=region_name,
            )
            prov.cite(ev, *causes)
            prov.remember(world, prov.key("technique", civ.name, spec.key), ev)
            events.append(ev)
            st.counts[f"gained:{channel}"] = st.counts.get(f"gained:{channel}", 0) + 1
        for k in sorted(before - now):
            spec = TECHNIQUES[k]
            had = sorted(r for (r, kk) in old_rows if kk == k and r < len(prev_ctrl) and prev_ctrl[r] == ci)
            moved = [r for r in had if ctrl[r] != ci and old_rows.get((r, k), 0.0) >= LOSE_LEVEL]
            names = [regions[r].name for r in (moved or had or members)]
            if moved:
                cause = "land"
                text = f"{civ.name} loses {spec.label} with {names[0]}"
                causes = _land_causes(world, civ.name, names)
                new_owner = ctrl[moved[0]]
                causes += _transfer_causes(world, civ.name, civs[new_owner].name if new_owner >= 0 else "",
                                           names[0])
            else:
                cause = "decay"
                text = f"{civ.name} loses the art of {spec.label} as its practitioners dwindle"
                causes = _decay_causes(world, civ.name, names)
            ev = Event(
                turn=world.turn, event_type="technique_lost", actors=[civ.name],
                description=text, importance=4 if spec.tier < 3 else 5, region=names[0],
            )
            prov.cite(ev, *causes)
            prov.remember(world, prov.key("technique_lost", civ.name, spec.key), ev)
            events.append(ev)
            st.counts[f"lost:{cause}"] = st.counts.get(f"lost:{cause}", 0) + 1
        known_now.append(now)
    return known_now


def _possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


# ---------------------------------------------------------------------------
# Era derivation
# ---------------------------------------------------------------------------

def _tier_count(tier: int, known: set[int], levels: dict[int, float], threshold: float) -> int:
    return sum(1 for k in _BY_TIER.get(tier, ()) if k in known and levels.get(k, 0.0) >= threshold)


def derived_era_step(era_idx: int, known: set[int], levels: dict[int, float],
                     core: dict[int, float] | None = None) -> int:
    """-1, 0 or +1: the era change the technique mix calls for (one step per turn).

    A new era needs its tier practised broadly (``levels``: population-weighted
    over the civ's suitable regions). An era is kept while each tier up to it
    is still practised to the quorum either broadly or in the civ's core
    (``core``: its capital), so newly held, untaught land does not undo it;
    losing the capital's practitioners or a decline everywhere does.
    """
    keep = levels if core is None else {k: max(levels.get(k, 0.0), core.get(k, 0.0))
                                        for k in set(levels) | set(core)}
    for tier in range(1, era_idx + 1):
        if _tier_count(tier, known, keep, KEEP_PRACTISED) < ERA_QUORUM[tier]:
            return -1
    if era_idx < MAX_TIER and _tier_count(era_idx + 1, known, levels, PRACTISED) >= ERA_QUORUM[era_idx + 1]:
        return 1
    return 0


def _advance(world, civ_i: int, civ, known: set[int], acc, events: list) -> None:
    """The old Phase 4 advance, kept event for event (bonus, focus, named events)."""
    from chronicler import provenance as prov
    from chronicler.models import Event, NamedEvent
    from chronicler.named_events import generate_tech_breakthrough_name
    from chronicler.tech import ERA_BONUSES, _next_era, apply_era_bonus
    from chronicler.tech_focus import TechFocus, apply_focus_effects, remove_focus_effects, select_tech_focus

    new_era = _next_era(civ.tech_era)
    tier = _era_order().index(new_era)
    civ.tech_era = new_era
    apply_era_bonus(civ, new_era, acc=acc, civ_idx=civ_i)
    ev = Event(
        turn=world.turn, event_type="tech_advancement", actors=[civ.name],
        description=f"{civ.name} advances to the {new_era.value} era", importance=7,
    )
    prov.cite(ev, *[prov.recall(world, prov.key("technique", civ.name, TECHNIQUES[k].key))
                    for k in _BY_TIER[tier] if k in known])
    events.append(ev)
    if civ.active_focus:
        remove_focus_effects(civ, TechFocus(civ.active_focus))
    new_focus = select_tech_focus(civ, world)
    if new_focus:
        apply_focus_effects(civ, new_focus)
        events.append(Event(
            turn=world.turn, event_type="tech_focus_selected", actors=[civ.name],
            description=f"{civ.name} develops {new_focus.value} specialization", importance=6,
        ))
    from chronicler.great_persons import note_tech_era_reached
    note_tech_era_reached(civ)
    world.named_events.append(NamedEvent(
        name=generate_tech_breakthrough_name(civ.tech_era), event_type="tech_breakthrough",
        turn=world.turn, actors=[civ.name], description=ev.description, importance=7,
    ))
    era_bonuses = ERA_BONUSES.get(civ.tech_era, {})
    if any(k in era_bonuses and era_bonuses[k] != 1.0
           for k in ("military_multiplier", "fortification_multiplier", "culture_projection_range")):
        world.named_events.append(NamedEvent(
            name=f"Paradigm Shift: {civ.tech_era.value.title()} Era", event_type="paradigm_shift",
            turn=world.turn, actors=[civ.name],
            description=(f"{civ.name} enters the {civ.tech_era.value.title()} era, "
                         "fundamentally changing the rules of engagement."),
            importance=7,
        ))


def _regress(world, civ_i: int, civ, known: set[int], acc, events: list) -> None:
    """The old M18 regression's consequences, caused by lost practice."""
    from chronicler import provenance as prov
    from chronicler.models import Event
    from chronicler.tech import _prev_era, remove_era_bonus

    old_era = civ.tech_era
    new_era = _prev_era(old_era)
    from chronicler.great_persons import note_tech_era_lost
    note_tech_era_lost(civ)
    remove_era_bonus(civ, old_era, acc=acc, civ_idx=civ_i)
    if civ.active_focus:
        from chronicler.tech_focus import TechFocus, remove_focus_effects
        remove_focus_effects(civ, TechFocus(civ.active_focus))
        civ.active_focus = None
    civ.tech_era = new_era
    causes: list[str | None] = []
    for tier in range(1, _era_order().index(old_era) + 1):
        for k in _BY_TIER[tier]:
            if k not in known:
                causes.append(prov.recall(world, prov.key("technique_lost", civ.name, TECHNIQUES[k].key),
                                          within=60))
    # The conditions that thinned the practitioners: disease, hunger,
    # occupation and disaster in its regions, collapse, and a lost capital.
    causes += _decay_causes(world, civ.name, list(civ.regions))
    causes += [prov.recall(world, prov.key("capital_taken", civ.name), within=20),
               prov.recall(world, prov.key("capital_loss", civ.name), within=20)]
    events.append(Event(
        turn=world.turn, event_type="tech_regression", actors=[civ.name],
        description=f"{civ.name} loses the knowledge of the {old_era.value} era, falling back to {new_era.value}",
        importance=9, causes=[c for c in dict.fromkeys(causes) if c],
    ))


def _derive_eras(world, st: TechniqueState, ctrl: list[int], known_now: list[set[int]],
                 levels: list[dict[int, float]], practice: dict, suit, acc, events: list) -> None:
    from chronicler.tech import _era_index
    strain = list(st.era_strain) + [0] * max(0, len(world.civilizations) - len(st.era_strain))
    for ci, civ in enumerate(world.civilizations):
        if not civ.regions or ci >= len(known_now) or not any(c == ci for c in ctrl):
            strain[ci] = 0
            continue
        core: dict[int, float] = {}
        regions = world.regions
        for r, region in enumerate(regions):
            if region.name == civ.capital_region and ctrl[r] == ci and region.population > 0:
                core = {k: practice.get((r, k), 0.0) for k in range(_K) if suit[r][k]}
                break
        step = derived_era_step(_era_index(civ.tech_era), known_now[ci], levels[ci], core)
        if step > 0:
            strain[ci] = 0
            _advance(world, ci, civ, known_now[ci], acc, events)
            st.counts["era_up"] = st.counts.get("era_up", 0) + 1
        elif step < 0:
            strain[ci] += 1
            if strain[ci] >= ERA_GRACE:
                strain[ci] = 0
                _regress(world, ci, civ, known_now[ci], acc, events)
                st.counts["era_down"] = st.counts.get("era_down", 0) + 1
        else:
            strain[ci] = 0
    st.era_strain = strain


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def _initialize(world, st: TechniqueState, ctrl: list[int], suit) -> None:
    """A world switched on mid-history keeps what its eras imply: every civ
    practises the techniques of its era and below that its land can carry."""
    from chronicler.tech import _era_index
    st.initialized_turn = world.turn
    rows: dict[tuple[int, int], float] = {}
    meta: dict[tuple[int, int], tuple[int, int, int]] = {}
    for ci, civ in enumerate(world.civilizations):
        era_idx = _era_index(civ.tech_era)
        members = [r for r, c in enumerate(ctrl) if c == ci]
        if era_idx <= 0 or not members:
            continue
        chosen: set[int] = set()
        for k, spec in enumerate(TECHNIQUES):
            if spec.tier > era_idx or any(q not in chosen for q in _PREREQS[k]):
                continue
            chosen.add(k)
            for r in members:
                level = SEED_LEVEL if suit[r][k] else UNSUITED_CAP
                rows[(r, k)] = _q(level)
                meta[(r, k)] = (-1, CH_SEEDED, ci)
    st.rows = [(r, k, rows[(r, k)], *meta[(r, k)]) for (r, k) in sorted(rows)]
    st.invalidate()


# ---------------------------------------------------------------------------
# The tick (Phase 4)
# ---------------------------------------------------------------------------

def tick_techniques(world: "WorldState", acc=None) -> list["Event"]:
    """Phase 4 with techniques on: practice, inventions, gains/losses, eras."""
    st = world.techniques
    if not isinstance(st, TechniqueState):
        return []
    events: list = []
    civ_idx = _civ_indices(world)
    ctrl = _controllers(world, civ_idx)
    links = _contacts(world, ctrl)
    suit = _suitability(world, ctrl, links)
    if st.initialized_turn is None:
        _initialize(world, st, ctrl, suit)
        st.known = []
        st.controllers = []
    old_rows = {(r, k): p for r, k, p, *_ in st.rows}
    practice, meta = _update_practice(world, st, ctrl, links, suit)
    regions = world.regions
    n_civs = len(world.civilizations)
    members_of = [[r for r, c in enumerate(ctrl) if c == ci] for ci in range(n_civs)]
    held_before = {c for c in st.controllers if c >= 0}
    # Research reads the civ practice measured (and smoothed) at the last tick.
    levels_before = [dict(st.civ_levels[ci]) if ci < len(st.civ_levels) and ci in held_before else {}
                     for ci in range(n_civs)]
    invented: dict[int, int] = {}
    for ci, civ in enumerate(world.civilizations):
        if not civ.regions or not members_of[ci]:
            continue
        if ci < len(st.known) and ci in held_before:
            known = set(st.known[ci])
        else:  # a new polity knows what its land practises
            known = {k for k in range(_K)
                     if any(practice.get((r, k), 0.0) >= GAIN_LEVEL for r in members_of[ci])}
        k = _invent(world, st, ci, civ, members_of[ci], known, practice, meta, suit,
                    levels_before[ci], acc, events)
        if k is not None:
            invented[ci] = k
    known_now = _gains_and_losses(world, st, ctrl, old_rows, practice, meta, invented, events)
    # Civ practice is smoothed over ticks, so people moving between a civ's
    # regions do not swing its era; a new polity starts from its measurement.
    levels: list[dict[int, float]] = []
    for ci in range(n_civs):
        if not members_of[ci]:
            levels.append({})
            continue
        raw = {k: _civ_practice(practice, suit, regions, members_of[ci], k) for k in range(_K)}
        if ci in held_before and ci < len(st.civ_levels):
            prev = dict(st.civ_levels[ci])
            raw = {k: (1.0 - LEVEL_SMOOTHING) * prev.get(k, 0.0) + LEVEL_SMOOTHING * v
                   for k, v in raw.items()}
        levels.append(raw)
    _derive_eras(world, st, ctrl, known_now, levels, practice, suit, acc, events)
    st.rows = [(r, k, practice[(r, k)], *meta[(r, k)]) for (r, k) in sorted(practice)]
    st.known = [sorted(s) for s in known_now]
    st.controllers = list(ctrl)
    st.civ_levels = [
        [(k, _q(v)) for k, v in sorted(lv.items()) if v >= 0.01] for lv in levels
    ]
    st.last_tick_turn = world.turn
    st.invalidate()
    return events


# ---------------------------------------------------------------------------
# Effects (each called only behind ``techniques_on``)
# ---------------------------------------------------------------------------

def _civ_level(world, civ_i: int, key: str) -> float:
    st = world.techniques
    if civ_i < 0 or civ_i >= len(st.civ_levels):
        return 0.0
    k = TECHNIQUE_INDEX[key]
    for kk, v in st.civ_levels[civ_i]:
        if kk == k:
            return v
    return 0.0


def _civ_levels(world, civ_i: int) -> dict[int, float]:
    st = world.techniques
    if civ_i < 0 or civ_i >= len(st.civ_levels):
        return {}
    return dict(st.civ_levels[civ_i])


def _region_level(world, region_i: int, key: str) -> float:
    return world.techniques.practice_map().get((region_i, TECHNIQUE_INDEX[key]), 0.0)


def _region_index(world, region) -> int:
    st = world.techniques
    cache = st._cache
    index = getattr(cache, "region_index", None)
    if index is None:
        index = {r.name: i for i, r in enumerate(world.regions)}
        cache.region_index = index
    return index.get(region.name, -1)


def military_factor(world, civ, attacking: bool) -> float:
    """Battle strength multiplier from the civ's practised arms techniques."""
    levels = _civ_levels(world, _civ_index_of(world, civ))
    if not levels:
        return 1.0
    side = 0 if attacking else 1
    bonus = sum(eff[side] * levels.get(TECHNIQUE_INDEX[key], 0.0) for key, eff in MILITARY_EFFECTS.items())
    return min(MILITARY_CAP, 1.0 + bonus)


def build_cost(world, region, infra_type, cost: int) -> int:
    """Treasury cost of a build in ``region`` after its building techniques."""
    from chronicler.models import InfrastructureType
    r = _region_index(world, region)
    if r < 0:
        return cost
    pm = world.techniques.practice_map()
    discount = sum(d * pm.get((r, TECHNIQUE_INDEX[key]), 0.0) for key, d in BUILD_DISCOUNT.items())
    if infra_type == InfrastructureType.FORTIFICATIONS:
        discount += sum(d * pm.get((r, TECHNIQUE_INDEX[key]), 0.0)
                        for key, d in FORTIFICATION_DISCOUNT.items())
    factor = max(BUILD_FLOOR, 1.0 - discount)
    return max(0, int(cost * factor + 0.5))


def epidemic_cfr_factors(world) -> list[float]:
    """Per region (index order): fatality multiplier from practised medicine."""
    pm = world.techniques.practice_map()
    out = []
    for r in range(len(world.regions)):
        reduction = sum(d * pm.get((r, TECHNIQUE_INDEX[key]), 0.0) for key, d in CFR_REDUCTION.items())
        out.append(max(CFR_FLOOR, 1.0 - reduction))
    return out


def quarantine_efficacy(world, civ_name: str | None, base: float) -> float:
    """Share of foreign import pressure a quarantine of ``civ_name`` stops."""
    ci = _civ_indices(world).get(civ_name, -1) if civ_name else -1
    bonus = sum(b * _civ_level(world, ci, key) for key, b in QUARANTINE_BONUS.items())
    return min(QUARANTINE_CAP, base + bonus)


def credit_factor(world, civ_i: int) -> float:
    """Credit capacity and debt ceiling multiplier from practised banking."""
    return 1.0 + sum(b * _civ_level(world, civ_i, key) for key, b in CREDIT_BONUS.items())


def yield_multiplier(world, region, rtype: int) -> float:
    """Harvest multiplier for one resource slot (1.0 with techniques off).

    The single ecology hook: grain from irrigation and the ploughs, fish from
    coastal sailing, each weighted by the region's practice.
    """
    if not techniques_on(world):
        return 1.0
    from chronicler.techniques_state import FISH, GRAIN
    if rtype == GRAIN:
        table = GRAIN_YIELD
    elif rtype == FISH:
        table = FISH_YIELD
    else:
        return 1.0
    r = _region_index(world, region)
    if r < 0:
        return 1.0
    pm = world.techniques.practice_map()
    return 1.0 + sum(b * pm.get((r, TECHNIQUE_INDEX[key]), 0.0) for key, b in table.items())


def extend_trade_routes(world, routes: set, embargo_set: set, region_map: dict) -> None:
    """Trade range: regions practising celestial navigation trade two hops
    across a coastal region, and those practising road building two hops
    along a road (the navigation and railways focus capabilities, by region)."""
    from chronicler.models import InfrastructureType
    from chronicler.resources import _trade_disposition_score

    pm = world.techniques.practice_map()
    nav = TECHNIQUE_INDEX["celestial_navigation"]
    road = TECHNIQUE_INDEX["roads"]
    ranging = sorted({r for (r, k), p in pm.items() if k in (nav, road) and p >= RANGE_PRACTICE})
    regions = world.regions
    for i in ranging:
        if i >= len(regions):
            continue
        r1 = regions[i]
        if r1.controller is None:
            continue
        sea = pm.get((i, nav), 0.0) >= RANGE_PRACTICE
        land = pm.get((i, road), 0.0) >= RANGE_PRACTICE
        for mid_name in r1.adjacencies:
            mid = region_map.get(mid_name)
            if mid is None:
                continue
            ok = (sea and mid.terrain == "coast") or (land and any(
                inf.type == InfrastructureType.ROADS and inf.active for inf in mid.infrastructure))
            if not ok:
                continue
            for hop2_name in mid.adjacencies:
                hop2 = region_map.get(hop2_name)
                if hop2 is None or hop2.controller is None or hop2.controller == r1.controller:
                    continue
                pair = tuple(sorted([r1.controller, hop2.controller]))
                if pair in embargo_set or pair in routes:
                    continue
                rel_ab = world.relationships.get(pair[0], {}).get(pair[1])
                rel_ba = world.relationships.get(pair[1], {}).get(pair[0])
                if _trade_disposition_score(rel_ab) >= 2 and _trade_disposition_score(rel_ba) >= 2:
                    routes.add(pair)


# ---------------------------------------------------------------------------
# Viewer / analytics summaries
# ---------------------------------------------------------------------------

def snapshot_summary(world) -> dict:
    """Small per-turn summary for ``TurnSnapshot.techniques``."""
    st = world.techniques
    known: dict[str, int] = {}
    practised: dict[str, int] = {}
    for ci, civ in enumerate(world.civilizations):
        if not civ.regions:
            continue
        known[civ.name] = len(st.known[ci]) if ci < len(st.known) else 0
        levels = st.civ_levels[ci] if ci < len(st.civ_levels) else []
        practised[civ.name] = sum(1 for _, v in levels if v >= PRACTISED)
    return {"known": known, "practised": practised, "rows": len(st.rows)}


def extract_technique_metrics(bundles: list[dict]) -> dict:
    """Per-run technique numbers from bundles that carry ``history[n].techniques``."""
    runs = []
    for bundle in bundles:
        history = bundle.get("history", [])
        series = [s.get("techniques") for s in history if s.get("techniques") is not None]
        if not series:
            continue
        per_turn = [sum(s["known"].values()) / len(s["known"]) if s["known"] else 0.0 for s in series]
        ws = bundle.get("world_state", {}).get("techniques") or {}
        runs.append({
            "turns": len(series),
            "mean_known_per_civ": round(sum(per_turn) / len(per_turn), 3),
            "final_known_per_civ": round(per_turn[-1], 3),
            "counts": dict(ws.get("counts", {})),
        })
    if not runs:
        return {}
    return {"runs": len(runs), "by_seed": runs}
