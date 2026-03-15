# M22: Factions & Succession Integration -- Design Spec

**Date:** 2026-03-15
**Status:** Draft
**Prerequisites:** M21 (Tech Specialization) landed

## Overview

Internal politics from competing weight vectors. Three factions (military, merchant, cultural) compete for influence within each civilization via zero-sum normalized influence. Faction dominance biases action selection, shapes succession outcomes, modifies crisis probability, and creates path dependence through nonlinear tipping points.

M22 does not replace M17's succession crisis state machine. Factions influence the inputs and weights -- the crisis flow (trigger → tick → resolve) is preserved. All changes are additive.

This milestone also bundles the secession viability fix identified during P4 tuning: capacity-weighted region selection for secession breakaway (Option 3) plus an absorption safety net for structurally unviable splinter civs (Option 2).

## Data Model

### FactionType Enum (models.py)

```python
class FactionType(str, Enum):
    MILITARY = "military"
    MERCHANT = "merchant"
    CULTURAL = "cultural"
```

### FactionState Model (models.py)

```python
class FactionState(BaseModel):
    influence: dict[FactionType, float] = Field(
        default_factory=lambda: {
            FactionType.MILITARY: 0.33,
            FactionType.MERCHANT: 0.33,
            FactionType.CULTURAL: 0.34,
        }
    )
    power_struggle: bool = False
    power_struggle_turns: int = 0
```

Influence always sums to 1.0 -- normalized after every modification. Zero-sum competition.

### Civilization (models.py)

New field:

```python
factions: FactionState = Field(default_factory=FactionState)
```

Default equal influence ensures backward compatibility with all existing scenarios and bundles.

### CivSnapshot (models.py)

New field:

```python
factions: FactionState | None = None
```

Populated alongside existing snapshot fields in main.py. Enables M19 analytics to track faction influence distributions over time.

## Influence Shift System

### Shift Table

Checked during faction tick in phase 10 (consequences). Each outcome shifts influence for the relevant faction:

| Outcome | MIL | MER | CUL |
|---|---|---|---|
| Win war | +0.10 | -- | -- |
| Lose war | -0.10 | +0.05 | +0.05 |
| Trade income > military cost | -- | +0.08 | -- |
| Treasury bankruptcy | -- | -0.15 | +0.05 |
| Cultural work / movement adopt | -- | -- | +0.08 |
| Successful expansion | +0.05 | +0.03 | -- |
| Famine in controlled region | -0.03 | -0.03 | +0.06 |
| Tech focus matches faction | +0.05 for matching faction |

Multiple shifts can occur per turn. All shifts applied, then normalized to sum=1.0.

### Influence Shift Detection

Shifts are detected by scanning `world.events_timeline` for the current turn during the faction tick. The same event type strings and outcome detection patterns used by `count_faction_wins()` (see Power Struggle Resolution) apply here:

- **War win/loss:** `event_type == "war"` with `len(actors) >= 2`. Attacker win = `"attacker_wins"` in description and `civ.name == actors[0]`. Defender win = `"defender_wins"` in description and `civ.name == actors[1]`.
- **Successful trade:** `event_type == "trade"` with `len(actors) >= 2` (successful trade has two actors).
- **Successful expansion:** `event_type == "expand"` with `importance >= 5`.
- **Cultural work:** `event_type == "cultural_work"`.
- **Movement adoption:** `event_type == "movement_adoption"`.
- **Famine:** `event_type == "famine"` with `civ.name in actors`.
- **Treasury bankruptcy:** Checked directly from civ state (`civ.treasury <= 0`), not from events.
- **Trade income > military cost:** Checked from civ state (treasury delta this turn vs military maintenance cost), not from events.
- **Tech focus match:** `event_type == "tech_focus_selected"` (emitted by M21) with matching `FOCUS_FACTION_MAP` entry.

### Tech Focus → Faction Mapping

M21's cross-cutting concern #3 states this mapping is M22's responsibility. Applied as a +0.05 shift when a civ selects a tech focus on era advancement:

```python
FOCUS_FACTION_MAP: dict[str, FactionType] = {
    # Roadmap-defined (3 per faction)
    "navigation": FactionType.MERCHANT,
    "commerce": FactionType.MERCHANT,
    "banking": FactionType.MERCHANT,
    "metallurgy": FactionType.MILITARY,
    "fortification": FactionType.MILITARY,
    "naval_power": FactionType.MILITARY,
    "scholarship": FactionType.CULTURAL,
    "printing": FactionType.CULTURAL,
    "media": FactionType.CULTURAL,
    # Completed from M21 effects table
    "agriculture": FactionType.MERCHANT,     # economy +10, BUILD/TRADE weights
    "exploration": FactionType.MILITARY,     # military +5, EXPLORE/WAR weights
    "mechanization": FactionType.MERCHANT,   # economy +10, BUILD/TRADE weights
    "railways": FactionType.MERCHANT,        # economy +5, BUILD/TRADE weights
    "networks": FactionType.MERCHANT,        # economy +10, TRADE/DIPLOMACY weights
    "surveillance": FactionType.MILITARY,    # stability +10, DIPLOMACY/WAR weights
}
```

**Distribution: 7 merchant, 5 military, 3 cultural.** The merchant skew reflects that most focuses are economy-oriented. Self-balancing: merchant factions lack the +0.10 single-event swing that military gets from war wins, and cultural works fire more reliably than trade detection. The asymmetry in tech focus mapping is offset by asymmetry in the influence shift table. M19b analytics will confirm.

The +0.05 shift fires once on tech focus selection (era advancement), not per turn. At ~5 era advancements per game, that's +0.25 total faction influence from tech focus across an entire run -- meaningful but not dominant.

### Great Person Per-Turn Bonuses

Applied during faction tick, before normalization:

- Active general GP: military +0.03/turn
- Active merchant GP: merchant +0.03/turn
- Active prophet GP: cultural +0.03/turn
- Active scientist GP: +0.02 to faction matching `civ.active_focus` via `FOCUS_FACTION_MAP` (None if no active focus)
- GP death removes the bonus implicitly -- the GP is no longer active, so the per-turn check skips it

### Normalization

```python
def normalize_influence(factions: FactionState) -> None:
    total = sum(factions.influence.values())
    if total > 0:
        for ft in FactionType:
            factions.influence[ft] /= total
    # Floor: no faction drops below 0.05 (prevents extinction)
    for ft in FactionType:
        if factions.influence[ft] < 0.05:
            factions.influence[ft] = 0.05
    # Re-normalize after floor enforcement
    total = sum(factions.influence.values())
    for ft in FactionType:
        factions.influence[ft] /= total
```

The 0.05 floor prevents a faction from being permanently eliminated. A suppressed military faction can recover if wars start going badly for the merchant-led government. Without the floor, a faction at 0.0 is dead forever, removing the comeback dynamics that make the system interesting.

### Dominance Shift Detection

After normalization, compare the new dominant faction to the previous dominant. If changed, emit a `"faction_dominance_shift"` event. Track the previous dominant as a local variable within the tick function -- no persistent state needed since dominance is derivable from influence values.

## Action Weight Integration

### Faction Weight Table

```python
FACTION_WEIGHTS: dict[FactionType, dict[ActionType, float]] = {
    FactionType.MILITARY: {WAR: 1.8, EXPAND: 1.5, DIPLOMACY: 0.6, TRADE: 0.7},
    FactionType.MERCHANT: {TRADE: 1.8, BUILD: 1.5, EMBARGO: 1.3, WAR: 0.5},
    FactionType.CULTURAL: {INVEST_CULTURE: 1.8, DIPLOMACY: 1.5, WAR: 0.4, EXPAND: 0.6},
}
```

Actions not listed in a faction's table get a 1.0 modifier (no bias).

### Exponentiation Formula -- Dominant Faction Only

```python
def get_faction_weight_modifier(civ: Civilization, action: ActionType) -> float:
    dominant = max(civ.factions.influence, key=civ.factions.influence.get)
    influence = civ.factions.influence[dominant]
    faction_weight = FACTION_WEIGHTS.get(dominant, {}).get(action, 1.0)
    return faction_weight ** influence
```

Only the dominant faction's weight table applies, scaled exponentially by its influence. The exponentiation creates nonlinear tipping points:

| Influence | WAR weight (MIL dominant) | Effect |
|---|---|---|
| 0.33 (equal) | 1.8^0.33 = 1.21x | Mild bias |
| 0.50 | 1.8^0.50 = 1.34x | Moderate bias |
| 0.60 | 1.8^0.60 = 1.43x | Clear bias |
| 0.80 | 1.8^0.80 = 1.62x | Strong bias |

**Why dominant-only, not all-factions multiplicative:** The all-factions approach (`product of weight^influence for each faction`) nearly cancels at realistic influence levels. A military-dominant civ at 0.6 MIL / 0.2 MER / 0.2 CUL produces: WAR = `1.8^0.6 × 0.5^0.2 × 0.4^0.2 = 1.43 × 0.87 × 0.83 ≈ 1.03x` -- effectively no bias. The dominant-only formula gives the clean tipping-point scaling the roadmap intended.

Suppression weights (WAR: 0.4 for cultural) only apply when cultural IS dominant -- a cultural-dominant civ actively suppresses war, a merchant-dominant civ doesn't.

### Weight Cap Dependency

M22 relies on M21's 2.5x global cap in `compute_weights()` (action_engine.py). M22 does NOT add its own cap. The faction modifier feeds into the same multiplication pipeline as trait × tradition × focus. Worst case pre-cap: trait (2.0x) × tradition (1.2x) × focus (1.5x) × faction (1.43x) ≈ 5.1x → capped to 2.5x with proportional scaling.

If M21 ships without the cap, M22 must add it. The cap code:

```python
# In compute_weights(), after all multiplicative modifiers, before streak breaker:
max_weight = max(weights.values())
if max_weight > 2.5:
    scale = 2.5 / max_weight
    for action in weights:
        weights[action] *= scale
```

### Integration Point in compute_weights()

Called after tradition modifiers (line 585), before streak breaker (line 587):

```python
# M22: Faction weight modifier
from chronicler.factions import get_faction_weight_modifier
for action in ActionType:
    if weights[action] > 0:
        weights[action] *= get_faction_weight_modifier(civ, action)
```

## Power Struggles

### Trigger Condition

Detected during faction tick: two factions within 0.05 influence AND both above 0.30.

```python
def check_power_struggle(factions: FactionState) -> tuple[FactionType, FactionType] | None:
    sorted_factions = sorted(factions.influence.items(), key=lambda x: x[1], reverse=True)
    top, second = sorted_factions[0], sorted_factions[1]
    if top[1] - second[1] < 0.05 and second[1] > 0.30:
        return (top[0], second[0])
    return None
```

### Effects While Active

- **Stability drain:** `stability -= int(3 * get_severity_multiplier(civ))` per turn. M18 severity multiplier applied -- power struggle stability drain is event damage, not a fixed structural cost.
- **Action effectiveness -20%:** Action resolution stat changes (treasury gains, military changes, culture gains) multiplied by 0.8 when `civ.factions.power_struggle` is True. Applied in each `_resolve_*` function, same pattern as the severity multiplier.
- Power struggle timer increments each turn.

### Resolution

Forced when `power_struggle_turns > 5`:

```python
def get_struggling_factions(civ: Civilization) -> tuple[FactionType, FactionType]:
    """Return the two factions within 0.05 influence that are both above 0.30."""
    sorted_factions = sorted(civ.factions.influence.items(), key=lambda x: x[1], reverse=True)
    return (sorted_factions[0][0], sorted_factions[1][0])

def resolve_win_tie(world: WorldState, civ: Civilization,
                    contenders: tuple[FactionType, FactionType]) -> FactionType:
    """Break tie: faction with more recent win. Still tied: military wins."""
    min_turn = world.turn - 10
    latest = {ft: -1 for ft in contenders}
    for event in world.events_timeline:
        if event.turn < min_turn or civ.name not in event.actors:
            continue
        for ft in contenders:
            if _event_is_win(event, civ, ft):
                latest[ft] = max(latest[ft], event.turn)
    if latest[contenders[0]] != latest[contenders[1]]:
        return max(latest, key=latest.get)
    # Still tied: military wins (the generals have swords)
    if FactionType.MILITARY in contenders:
        return FactionType.MILITARY
    return contenders[0]  # arbitrary if neither is military (rare)

def resolve_power_struggle(civ: Civilization, world: WorldState) -> list[Event]:
    contenders = get_struggling_factions(civ)
    wins = {}
    for ft in contenders:
        wins[ft] = count_faction_wins(world, civ, ft, lookback=10)

    if wins[contenders[0]] != wins[contenders[1]]:
        winner = max(wins, key=wins.get)
    else:
        winner = resolve_win_tie(world, civ, contenders)

    turns = civ.factions.power_struggle_turns
    shift_faction_influence(civ.factions, winner, +0.15)
    civ.factions.power_struggle = False
    civ.factions.power_struggle_turns = 0
    return [Event(
        turn=world.turn, event_type="power_struggle_resolved",
        actors=[civ.name],
        description=f"{civ.name}: {winner.value} faction prevails after {turns} turns of infighting.",
        importance=7,
    )]
```

`_event_is_win(event, civ, faction_type)` is an internal helper that reuses the same event type matching logic as `count_faction_wins` (returns `True` if the event counts as a win for the given faction).

### Win Counting -- Stateless Event Scanner

Power struggles resolve rarely (~once every 20-50 turns per civ). Scanning 10 turns of events at resolution time is trivially cheap. No rolling counters, no state to serialize or keep consistent across succession.

```python
def count_faction_wins(world: WorldState, civ: Civilization,
                       faction_type: FactionType, lookback: int = 10) -> int:
    min_turn = world.turn - lookback
    count = 0
    for event in world.events_timeline:
        if event.turn < min_turn:
            continue
        if civ.name not in event.actors:
            continue
        if faction_type == FactionType.MILITARY:
            if event.event_type == "war" and len(event.actors) >= 2:
                is_attacker = event.actors[0] == civ.name
                if (is_attacker and "attacker_wins" in event.description) or \
                   (not is_attacker and "defender_wins" in event.description):
                    count += 1
            elif event.event_type == "expand" and event.importance >= 5:
                count += 1
        elif faction_type == FactionType.MERCHANT:
            if event.event_type == "trade" and len(event.actors) >= 2:
                count += 1
        elif faction_type == FactionType.CULTURAL:
            # Note: tech_advancement is NOT counted here -- it feeds into faction
            # influence via FOCUS_FACTION_MAP separately. Including it in win counting
            # would double-count its faction impact.
            if event.event_type in ("cultural_work", "movement_adoption"):
                count += 1
    return count
```

Event type strings verified against the codebase: `"war"` (action_engine.py:253), `"expand"` (action_engine.py:107), `"trade"` (action_engine.py:132), `"cultural_work"` (simulation.py:810), `"movement_adoption"` (movements.py:107). War outcomes distinguished by description content (`result.outcome` string embedded at action_engine.py:254). Expansion success distinguished by importance threshold (6 for success at action_engine.py:108, 2 for failure at action_engine.py:112). Trade success distinguished by actor count (2 actors for success at action_engine.py:132, 1 for failure at action_engine.py:136). Note: `"tech_advancement"` (tech.py:104) is NOT counted as a cultural win -- tech focus mapping via `FOCUS_FACTION_MAP` handles the faction influence shift separately.

## Succession Integration

All modifications target `src/chronicler/succession.py`. M17's state machine (trigger → tick → resolve) is preserved.

### Leader--Faction Alignment

```python
TRAIT_FACTION_MAP: dict[str, FactionType] = {
    # Military-aligned traits
    "aggressive": FactionType.MILITARY,
    "expansionist": FactionType.MILITARY,
    "martial": FactionType.MILITARY,
    # Merchant-aligned traits
    "diplomatic": FactionType.MERCHANT,
    "cautious": FactionType.MERCHANT,
    "mercantile": FactionType.MERCHANT,
    # Cultural-aligned traits
    "visionary": FactionType.CULTURAL,
    "scholarly": FactionType.CULTURAL,
    "pious": FactionType.CULTURAL,
}

def get_leader_faction_alignment(leader: Leader, factions: FactionState) -> float:
    """
    How well the leader's trait aligns with the dominant faction.
    Returns 0.0 (misaligned) to 1.0 (perfect alignment).
    """
    leader_faction = TRAIT_FACTION_MAP.get(leader.trait)
    if leader_faction is None:
        return 0.5  # neutral traits (e.g., "resilient") don't help or hurt
    return factions.influence.get(leader_faction, 0.33)
```

Creates a feedback loop: a military leader in a merchant-dominated civ faces higher crisis probability. If the crisis resolves with a merchant-aligned candidate, the new leader is better aligned and the civ stabilizes.

### Crisis Probability Modifier

Added to `compute_crisis_probability()` in `succession.py` (currently lines 28-56). New modifiers inserted into the existing multiplicative chain:

```python
# M22 faction modifiers (added after existing tradition modifiers)
if civ.factions.power_struggle:
    modifiers *= 1.4  # internal instability from competing factions

alignment = get_leader_faction_alignment(civ.leader, civ.factions)
if alignment > 0.5:
    modifiers *= 0.8   # leader aligned with dominant faction = stability
elif alignment < 0.2:
    modifiers *= 1.3   # leader misaligned with dominant faction = tension
```

### Faction-Weighted Candidate Generation

Replaces the default "all civs as diplomatic" loop in `trigger_crisis()` (succession.py lines 68-82):

```python
FACTION_CANDIDATE_TYPE: dict[FactionType, str] = {
    FactionType.MILITARY: "general",
    FactionType.MERCHANT: "elected",    # merchant faction favors council selection
    FactionType.CULTURAL: "heir",       # cultural faction favors legitimacy
}

GP_ROLE_TO_FACTION: dict[str, FactionType] = {
    "general": FactionType.MILITARY,
    "merchant": FactionType.MERCHANT,
    "prophet": FactionType.CULTURAL,
}

GP_SUCCESSION_TYPE: dict[str, str] = {
    "general": "general",
    "merchant": "elected",
    "prophet": "heir",
}

def generate_faction_candidates(civ: Civilization, world: WorldState) -> list[dict]:
    candidates = []
    dominant = get_dominant_faction(civ.factions)

    # Internal candidates -- one per faction with sufficient influence
    for faction_type in FactionType:
        influence = civ.factions.influence[faction_type]
        if influence < 0.15:
            continue  # faction too weak to field a candidate
        candidates.append({
            "type": FACTION_CANDIDATE_TYPE[faction_type],
            "faction": faction_type.value,
            "weight": influence,
            "backer_civ": None,
        })

    # External candidates -- allied/friendly civs back their own dominant faction
    for other in world.civilizations:
        if other.name == civ.name or not other.regions:
            continue
        rel = world.relationships.get(other.name, {}).get(civ.name)
        if rel and rel.disposition in (Disposition.ALLIED, Disposition.FRIENDLY):
            other_dominant = get_dominant_faction(other.factions)
            candidates.append({
                "type": FACTION_CANDIDATE_TYPE[other_dominant],
                "faction": other_dominant.value,
                "weight": 0.1,
                "backer_civ": other.name,
            })

    # Great person candidates -- M17's general-to-leader pathway
    for gp in civ.great_persons:
        if gp.alive and gp.active and gp.role in ("general", "merchant", "prophet"):
            gp_faction = GP_ROLE_TO_FACTION[gp.role]
            faction_boost = 0.10 if gp_faction == dominant else 0.0
            candidates.append({
                "type": GP_SUCCESSION_TYPE[gp.role],
                "faction": gp_faction.value,
                "weight": civ.factions.influence[gp_faction] + faction_boost,
                "backer_civ": None,
                "great_person": gp.name,
            })

    return candidates
```

### Weighted Crisis Resolution

Replaces uniform random selection in `resolve_crisis()` (succession.py lines 91-136):

**Division of labor between `generate_successor` and `resolve_crisis`:**

`generate_successor()` (leaders.py:187-230) creates a Leader object, applies succession-type stat effects (general: -10 stability/+10 military, usurper: -30 stability, elected: +10 stability), calls `inherit_grudges(old_leader, new_leader)` at flat 0.5 rate, resets `civ.action_counts`, and returns the Leader. It does NOT assign `civ.leader`, mark `old_leader.alive = False`, call `apply_leader_legacy`, or create exiles.

`resolve_crisis()` (succession.py:91-136) is the caller that handles those steps: marks old leader dead, applies legacy, calls `generate_successor`, assigns `civ.leader`, cleans up crisis state, and emits the `succession_crisis_resolved` event. Note: `resolve_crisis` also calls `inherit_grudges` a second time (succession.py:119), which is a pre-existing double-inheritance bug -- M22's replacement function corrects this.

`resolve_crisis_with_factions` mirrors `resolve_crisis`'s full flow, replacing candidate selection and grudge inheritance:

```python
def resolve_crisis_with_factions(civ: Civilization, world: WorldState) -> list[Event]:
    from chronicler.leaders import generate_successor, apply_leader_legacy

    rng = random.Random(world.seed + world.turn + hash(civ.name))
    events = []

    candidates = civ.succession_candidates
    if not candidates:
        # Fallback: existing M17 resolution (no factions involved)
        return resolve_crisis(civ, world)

    # 10% outsider chance -- populist surprise, ignores faction weights
    if rng.random() < 0.10:
        winner = rng.choice(candidates)
    else:
        # Weighted selection by faction influence
        weights = [c["weight"] for c in candidates]
        winner = rng.choices(candidates, weights=weights, k=1)[0]

    force_type = winner["type"]
    old_leader = civ.leader
    old_leader.alive = False

    # Apply legacy (mirrors resolve_crisis line 101-103)
    legacy_event = apply_leader_legacy(civ, old_leader, world)
    if legacy_event:
        events.append(legacy_event)

    # generate_successor creates Leader, applies stat effects, inherits grudges at 0.5
    new_leader = generate_successor(civ, world, seed=world.seed, force_type=force_type)

    # Override grudge inheritance with faction-aware rates.
    # generate_successor already applied flat 0.5 -- clear and re-apply.
    # (Also fixes the pre-existing double-inheritance in resolve_crisis.)
    new_leader.grudges = []
    inherit_grudges_with_factions(old_leader, new_leader, civ.factions)

    # Assign new leader (generate_successor does NOT do this)
    civ.leader = new_leader

    # Faction influence shift from resolution
    winning_faction = FactionType(winner["faction"])
    shift_faction_influence(civ.factions, winning_faction, +0.15)

    # GP winner: transfer identity to new leader
    if "great_person" in winner:
        gp = next((g for g in civ.great_persons if g.name == winner["great_person"]), None)
        if gp:
            new_leader.name = gp.name
            new_leader.trait = gp.trait
            gp.alive = False
            gp.fate = "ascended_to_leadership"

    # External backer relationship bonus -- upgrade disposition one step
    if winner.get("backer_civ"):
        if civ.name in world.relationships and winner["backer_civ"] in world.relationships[civ.name]:
            rel = world.relationships[civ.name][winner["backer_civ"]]
            rel.disposition = upgrade_disposition(rel.disposition)
            # upgrade_disposition: new helper in factions.py
            # hostile -> suspicious -> neutral -> friendly -> allied

    # Exile old leader (existing M17 logic -- create_exiled_leader handles GP
    # creation internally, returns str | None for host civ name)
    create_exiled_leader(old_leader, civ, world)

    # Emit succession_crisis_resolved event with faction context (importance 8)
    events.append(Event(
        turn=world.turn, event_type="succession_crisis_resolved",
        actors=[civ.name],
        description=(f"{civ.name} succession crisis resolved: {winning_faction.value} "
                     f"faction prevails, {new_leader.name} takes power."),
        importance=8,
    ))

    # Clean up crisis state (mirrors resolve_crisis lines 122-123)
    civ.succession_crisis_turns_remaining = 0
    civ.succession_candidates = []

    return events
```

### Crisis ↔ Power Struggle Interaction (4 Rules)

**Rule 1: Power struggle accelerates crisis probability.** Covered above -- `× 1.4` modifier in `compute_crisis_probability`.

**Rule 2: Crisis pauses power struggle timer.** Added as a guard in `tick_crisis()` (succession.py lines 85-88):

```python
def tick_crisis(civ: Civilization, world: WorldState) -> None:
    civ.succession_crisis_turns_remaining -= 1
    # M22: Freeze power struggle during succession crisis
    # Don't tick power struggle -- the crisis is priority
```

The power struggle timer is NOT incremented during crisis turns. The faction tick in phase 10 checks `civ.succession_crisis_turns_remaining > 0` and skips power struggle processing.

**Rule 3: Crisis resolution can end power struggle.** The winning faction's +0.15 influence shift (from resolution) likely pushes it past the 0.05 gap threshold, ending the power struggle. If the 10% outsider wins with a different faction, the power struggle may continue after the crisis.

**Rule 4: No double stability drain.** During a crisis, the civ already loses stability from `succession_crisis_turns_remaining > 0`. The power struggle's stability drain (`-3/turn × severity`) is paused (Rule 2). This prevents catastrophic double drain that would make every power-struggle-triggered crisis a death spiral.

### Exile Restoration Faction Check

Added to `check_exile_restoration()` in `succession.py` (lines 251-290). Modifier applied to the existing `base_prob`:

```python
# M22: Faction alignment modifies restoration probability
exile_faction = GP_ROLE_TO_FACTION.get(gp.role)
origin_dominant = get_dominant_faction(origin_civ.factions)

if exile_faction and exile_faction == origin_dominant:
    base_prob *= 0.3   # their faction already rules -- no narrative reason to return
elif exile_faction:
    base_prob *= 1.5   # opposing faction welcomes them back
```

Creates a pattern: a general exiled by a merchant-faction-dominated civ can return when stability drops (military is needed) and the military faction has regained influence.

### Faction-Aware Grudge Inheritance

Replaces the flat 0.5 inheritance rate in `inherit_grudges()`:

```python
def inherit_grudges_with_factions(old_leader: Leader, new_leader: Leader,
                                   factions: FactionState) -> None:
    old_faction = TRAIT_FACTION_MAP.get(old_leader.trait)
    new_faction = TRAIT_FACTION_MAP.get(new_leader.trait)

    # Same-faction leaders share enemies; different-faction leaders start fresh
    if old_faction and new_faction and old_faction == new_faction:
        inheritance_rate = 0.7   # faction continuity preserves grudges
    elif old_faction != new_faction:
        inheritance_rate = 0.3   # faction change dilutes grudges
    else:
        inheritance_rate = 0.5   # neutral trait -- default rate

    for g in old_leader.grudges:
        inherited_intensity = g["intensity"] * inheritance_rate
        if inherited_intensity >= 0.01:
            new_leader.grudges.append({**g, "intensity": inherited_intensity})
```

## Secession Viability Fix

Bundled in M22 because M22 already touches `politics.py` for faction-weighted secession and needs to be aware of twilight tick interactions for power struggle pausing.

### Option 3: Capacity-Weighted Region Selection

Modifies `sorted_regions` in `politics.py` (lines 119-123). Replaces pure distance sort with composite score:

```python
region_map = {r.name: r for r in world.regions}

def _secession_score(rn: str, _civ=civ) -> float:
    d = graph_distance(world.regions, _civ.capital_region or _civ.regions[0], rn)
    dist = d if d >= 0 else 0
    cap = effective_capacity(region_map[rn]) if rn in region_map else 0
    # Higher score = more likely to secede: far + high capacity
    return dist * 0.7 + cap * 0.3

sorted_regions = sorted(civ.regions, key=_secession_score, reverse=True)
```

Distance still dominates (far regions secede), but among equidistant regions, higher-capacity ones are preferred. A civ with distant plains AND distant desert loses the plains to secession, not the desert. The seceding faction takes viable territory because viable territory is worth fighting for.

### Option 2: Absorption Safety Net

~5 lines added to the existing twilight tick in `politics.py`. One additional condition, same absorption logic:

```python
def total_effective_capacity(civ: Civilization, world: WorldState) -> int:
    """Sum of effective_capacity across all civ-controlled regions. New helper."""
    region_map = {r.name: r for r in world.regions}
    return sum(effective_capacity(region_map[rn]) for rn in civ.regions
               if rn in region_map)

# In check_twilight or equivalent, after existing twilight checks:
# If total effective capacity < 10 and civ has existed for 30+ turns, absorb.
# Use leader.reign_start as founding proxy -- for secession-born civs, the first
# leader is created at secession time; for original civs, reign_start is ~0.
civ_age = world.turn - civ.leader.reign_start
if total_effective_capacity(civ, world) < 10 and civ_age > 30:
    absorb_into_neighbor(civ, world)  # existing twilight absorption logic
```

Catches edge cases where Option 3's weighting still produces a desert splinter. Triggered by structural incapacity (total capacity < 10 and civ age > 30 turns) instead of stat decline.

`total_effective_capacity` is a new helper function in `politics.py` -- builds `region_map` (existing codebase pattern, see politics.py:117, 273, 787) and sums `effective_capacity` across civ regions. `civ_age` uses `civ.leader.reign_start` as a founding proxy since `Civilization` has no `founded_turn` field; this works because secession-born civs get a new leader at creation and original civs have `reign_start ≈ 0`.

## Faction Events

Three new event types emitted by the faction system. Required for M19 analytics (faction dynamics tracking), M20 curator (narrating faction tipping points), and the never-fire detector.

### power_struggle_started (importance 6)

Emitted when power struggle is first detected in the faction tick:

```python
Event(
    turn=world.turn, event_type="power_struggle_started",
    actors=[civ.name],
    description=f"{civ.name}: {ft1.value} and {ft2.value} factions vie for dominance.",
    importance=6,
)
```

### power_struggle_resolved (importance 7)

Emitted when power struggle resolves (forced after 5 turns):

```python
Event(
    turn=world.turn, event_type="power_struggle_resolved",
    actors=[civ.name],
    description=f"{civ.name}: {winner.value} faction prevails after {turns} turns of infighting.",
    importance=7,
)
```

### faction_dominance_shift (importance 5)

Emitted when the dominant faction changes after normalization:

```python
Event(
    turn=world.turn, event_type="faction_dominance_shift",
    actors=[civ.name],
    description=f"{civ.name}: {new_dominant.value} faction eclipses {old_dominant.value}.",
    importance=5,
)
```

## Simulation Integration

### New Module: src/chronicler/factions.py

Contains all faction logic:

- `FactionType`, `FactionState` re-exported from models.py
- `FACTION_WEIGHTS` table
- `FOCUS_FACTION_MAP` table
- `TRAIT_FACTION_MAP` table
- `FACTION_CANDIDATE_TYPE`, `GP_ROLE_TO_FACTION`, `GP_SUCCESSION_TYPE` mapping tables
- `normalize_influence(factions)` -- normalization with 0.05 floor
- `shift_faction_influence(factions, faction_type, amount)` -- shift + normalize
- `get_dominant_faction(factions)` -- returns faction with highest influence
- `get_leader_faction_alignment(leader, factions)` -- alignment score
- `get_faction_weight_modifier(civ, action)` -- exponentiation formula
- `check_power_struggle(factions)` -- trigger detection
- `resolve_power_struggle(civ, world)` -- event-scanning resolution
- `count_faction_wins(world, civ, faction_type, lookback)` -- stateless event scanner
- `tick_factions(world)` -- main per-turn entry point
- `generate_faction_candidates(civ, world)` -- succession candidate generation
- `resolve_crisis_with_factions(civ, world)` -- weighted crisis resolution
- `inherit_grudges_with_factions(old_leader, new_leader, factions)` -- variable rate
- `upgrade_disposition(disposition)` -- step disposition up one level (hostile→suspicious→neutral→friendly→allied)
- `get_struggling_factions(civ)` -- return the two factions within 0.05 influence
- `resolve_win_tie(world, civ, contenders)` -- break win count ties by recency, then military
- `_event_is_win(event, civ, faction_type)` -- internal: does this event count as a win for this faction

### Phase Ordering

Faction tick runs in phase 10 (consequences), called from `phase_consequences()` in `simulation.py`:

```python
# In phase_consequences():
from chronicler.factions import tick_factions
turn_events.extend(tick_factions(world))
```

Runs AFTER event-generating phases (war, trade, culture) so that the current turn's outcomes feed into influence shifts. The tick function:

1. For each civ with regions:
   a. Record current dominant faction
   b. Scan current-turn events for influence shifts
   c. Apply GP per-turn bonuses
   d. Normalize influence
   e. Check for dominance shift, emit event if changed
   f. If `succession_crisis_turns_remaining > 0`: skip power struggle processing (Rule 2)
   g. Else: check power struggle trigger, tick power struggle timer, apply stability drain, check forced resolution

### Succession Module Modifications

All changes to `succession.py` are additive:

- `compute_crisis_probability()`: add faction modifier block (~5 lines)
- `trigger_crisis()`: call `generate_faction_candidates()` from factions.py instead of default loop (~3 lines changed)
- `resolve_crisis()`: call `resolve_crisis_with_factions()` from factions.py for weighted selection (~3 lines changed)
- `tick_crisis()`: add comment noting power struggle freeze is handled in faction tick (~0 code lines)
- `check_exile_restoration()`: add faction alignment modifier (~6 lines)

`inherit_grudges()` call replaced with `inherit_grudges_with_factions()` inside `resolve_crisis_with_factions`.

## Files Modified

| File | Changes |
|---|---|
| `src/chronicler/factions.py` (new) | All faction logic: influence shifts, normalization, power struggles, faction weights, candidate generation, win counting, leader alignment, mapping tables (~350 lines) |
| `src/chronicler/models.py` | FactionType enum, FactionState model, `factions` field on Civilization, `factions` field on CivSnapshot (~25 lines) |
| `src/chronicler/succession.py` | Crisis probability faction modifier, faction candidate generation call, weighted resolution call, exile faction check (~20 lines modified) |
| `src/chronicler/politics.py` | Secession region scoring (capacity-weighted), `total_effective_capacity` helper, absorption safety net in twilight tick (~20 lines) |
| `src/chronicler/action_engine.py` | Faction weight modifier call in `compute_weights()` (~5 lines) |
| `src/chronicler/simulation.py` | `tick_factions()` call in phase 10 consequences (~3 lines) |
| `src/chronicler/main.py` | Populate `factions` in CivSnapshot (~1 line) |
| `tests/test_factions.py` (new) | Comprehensive test suite: influence shifts, normalization, power struggles, weight modifiers, candidate generation, win counting, secession scoring (~200 lines) |

**Total:** ~450 lines production code, ~200 lines tests, across 6 source files + 1 new module + 1 test file.

## Cross-Cutting Concerns

1. **M18 severity multiplier:** Power struggle stability drain (`-3/turn`) goes through `get_severity_multiplier(civ)`. Influence shifts are faction balance changes, not stat damage -- severity does not apply to them.

2. **M21 weight cap dependency:** M22 relies on M21's 2.5x global cap in `compute_weights()`. M22 does NOT add its own. If M21 ships without the cap, M22 must add it (code provided in Weight Cap Dependency section).

3. **M19 analytics:** Faction events (`power_struggle_started`, `power_struggle_resolved`, `faction_dominance_shift`) feed into the never-fire detector and event firing rate table. CivSnapshot `factions` field enables time-series analysis of faction influence distributions.

4. **Scenario compatibility:** `factions` field defaults to equal influence (FactionState default). Existing scenarios work unchanged. Missing `factions` on deserialization uses the default.

5. **Narrative engine:** Faction events have importance 5-7, placing them in the curator's mid-high range. Power struggle resolution (7) is on par with succession events, appropriate for a system that determines who rules.

6. **Suggested implementation order:** (1) Data model + core module (FactionState, normalization, influence shifts), (2) Action weight integration, (3) Power struggles, (4) Succession integration, (5) Secession viability fix. Each step testable in isolation with deterministic seeds.
