# M16: Memetic Warfare — Design Spec

**Date:** 2026-03-13
**Branch:** (to be created from main after M15 merge)
**Depends on:** M13b (trade routes, resources, trade_volume on Relationship), M14 (political topology, congress voting weight), M15 (terrain, infrastructure, adjacency). P1 stat migration (0-100 scale) must be complete.
**Scope:** Three sequential phases: M16a → M16b → M16c
**Note:** This spec supersedes the Phase 3 roadmap (`chronicler-phase3-roadmap.md`) for all M16 details. Where the roadmap and this spec disagree, this spec is authoritative.

## Overview

Culture is a strategic weapon, social glue, and fault line. M16 makes cultural values, regional identity, and ideological movements mechanically load-bearing — affecting disposition drift, territorial stability, tech advancement, and cross-border conflict.

All mechanics are pure Python simulation — no LLM calls required. The narrative engine describes what happened; it doesn't decide what happens.

### Design Principles

- **Culture as property AND culture as entity.** Values, identity, and prestige are properties of civs and regions. Movements are independent entities with lifecycles that spread, mutate, and create schisms.
- **Integer counter for ideology, not doctrinal content.** The simulation tracks *that* doctrinal differences exist and *how much* they've diverged. The narrative engine invents the content. Structure from simulation, meaning from narration.
- **Two modules, one domain boundary.** `culture.py` (culture as property of places/civs) and `movements.py` (ideas as independent entities that spread).

### Phase Summary

| Phase | Name | Module | Deliverable |
|-------|------|--------|-------------|
| M16a | Cultural Foundations | `culture.py` | Value-based disposition drift, cultural assimilation, cultural works enhancement, prestige |
| M16b | Movements & Schisms | `movements.py` | Movement emergence, trade-route spread, adoption, variant drift, schism detection |
| M16c | Strategic Culture | `culture.py`, `action_engine.py`, `tech.py` | Propaganda (INVEST_CULTURE action), paradigm shifts, cultural victory tracking |

### File Map

**New files:**
- `src/chronicler/culture.py` — culture as property: value drift, assimilation, prestige, propaganda, victory tracking
- `src/chronicler/movements.py` — ideas as entities: emergence, spread, adoption, variant drift, schism detection
- `tests/test_culture.py` — tests for culture.py
- `tests/test_movements.py` — tests for movements.py

**Modified files:**
- `src/chronicler/models.py` — new fields on Civilization, Region, Relationship, WorldState; new Movement model
- `src/chronicler/tech.py` — extend ERA_BONUSES with paradigm shift multipliers, add `get_era_bonus()` accessor
- `src/chronicler/simulation.py` — phase integration hooks, INVEST_CULTURE action resolution
- `src/chronicler/action_engine.py` — INVEST_CULTURE weighting and eligibility
- `src/chronicler/world_gen.py` — initialize cultural_identity on regions
- `src/chronicler/bundle.py` — extend snapshots with cultural data

---

## Phase M16a: Cultural Foundations

### Goal

Give values mechanical teeth. Currently decorative — after M16a, shared/opposing values cause disposition drift between civs, conquered regions resist foreign rule, and cultural works produce prestige that affects trade and diplomacy.

### Model Changes

**`Civilization` (models.py) — new fields:**
```python
prestige: int = 0  # accumulated from cultural works, decays -1/turn, min 0
```

Prestige decays at -1/turn (minimum 0). Reflects *recent* cultural output, not lifetime accumulation. A civ that stops producing cultural works loses prestige over ~50 turns.

**`Region` (models.py) — new fields:**
```python
cultural_identity: str | None = None  # set to controller at world gen
foreign_control_turns: int = 0        # turns under non-identity controller
```

`cultural_identity` defaults to `None`, set to controller's name during world generation (in `world_gen.py` after region assignment). `foreign_control_turns` resets to 0 when controller changes to match identity, or when assimilation completes.

**`Relationship` (models.py) — new fields:**
```python
disposition_drift: int = 0  # accumulator for value-based + movement disposition shifts
```

Drift accumulates per-turn. At +10 disposition upgrades one level (drift resets to 0). At -10 downgrades one level (drift resets to 0). The reset-on-trigger is critical — without it, drift keeps accumulating past the threshold and you get multiple level jumps in consecutive turns. Shared values take ~5 turns to shift one level.

### Value Opposition Table

```python
VALUE_OPPOSITIONS: dict[str, str] = {
    "Freedom": "Order",
    "Order": "Freedom",
    "Liberty": "Order",
    "Tradition": "Knowledge",
    "Knowledge": "Tradition",
    "Honor": "Cunning",
    "Cunning": "Honor",
    "Piety": "Cunning",
    "Self-reliance": "Trade",
    "Trade": "Self-reliance",
}
```

Values not in table (Strength, Destiny) are neutral — no opposition but can still create shared-value bonuses. The full vocabulary is implicitly constrained by this table and `CIV_TEMPLATES` in `world_gen.py`: Freedom, Order, Liberty, Tradition, Knowledge, Honor, Cunning, Piety, Self-reliance, Trade, Strength, Destiny (12 values total).

**Note:** "Liberty" and "Freedom" both oppose "Order" but are distinct values for shared-value bonuses. A civ with ["Freedom"] and a civ with ["Liberty"] do NOT get a shared-value bonus — they are different strings. They are synonyms for opposition purposes only.

### Ideological Compatibility — `apply_value_drift(world)`

Runs in phase 10 (consequences), after `tick_movements` (M16b) so movement co-adoption effects are current.

```python
For each civ pair (A, B):
    shared = count of values in A.values that also appear in B.values
    opposing = count of (v_a, v_b) pairs where VALUE_OPPOSITIONS[v_a] == v_b

    net_drift = (shared * 2) - (opposing * 2)  # per turn

    # Movement co-adoption effects added here (see M16b)

    relationship[A][B].disposition_drift += net_drift

    if disposition_drift >= 10:
        upgrade disposition one level, reset drift to 0
    elif disposition_drift <= -10:
        downgrade disposition one level, reset drift to 0
```

**Performance note:** O(N²) per turn where N = number of civs. Fine for 4-6 civs in Phase 3. If Phase 4's batch runner scales to 20+ civs, this becomes the hot loop. Add a docstring noting this.

### Cultural Assimilation — `tick_cultural_assimilation(world)`

Runs in phase 10 (consequences), after `apply_value_drift`.

**First control** (identity is None): `cultural_identity = controller` immediately, no timer. There's no existing culture to resist. Applied in expand/conquest resolution.

**Foreign controller** (identity != controller, both non-None):
- `foreign_control_turns += 1`
- At `ASSIMILATION_THRESHOLD` (15) turns: `cultural_identity = controller`, `foreign_control_turns = 0`, generate event
- Ongoing stability drain: `controller_civ.stability -= ASSIMILATION_STABILITY_DRAIN` per mismatched region per turn
  - **Exception:** regions in the first `RECONQUEST_COOLDOWN` (10) turns after reconquest are exempt from per-turn drain — the `restless_population` ActiveCondition covers them instead. Guard: `if foreign_control_turns < RECONQUEST_COOLDOWN: skip drain`

**Reconquest** (controller changes to match identity): `foreign_control_turns = 0`. If the region was previously assimilated (identity was changed by a foreign controller), apply `ActiveCondition("restless_population", duration=RECONQUEST_COOLDOWN, severity=5)` — stability -1/turn for 10 turns. This replaces the per-turn drain for the cooldown period, preventing double-dipping.

**`ASSIMILATION_STABILITY_DRAIN = 3`** — calibrated for the 0-100 stat scale (P1-dependent). On 1-10 scale, -1 was appropriate; on 0-100, -3 produces equivalent pressure. Parametrized as a constant for P1 migration.

### Cultural Works Enhancement

Modifies existing `phase_cultural_milestones` (phase 6):

```python
# On cultural work production (existing threshold check):
civ.asabiya += 0.05
civ.culture = clamp(civ.culture + 5, 0, 100)  # post-P1 0-100 scale
civ.prestige += 2
```

**Note:** Culture stat boost uses 0-100 scale (post-P1), not 1-10. The +5 is equivalent to old +1 at the new scale.

### Prestige — `tick_prestige(world)`

Runs in phase 2 (automatic effects), alongside treasury income and military maintenance.

Single function handles both decay and income effects:

1. **Decay:** `civ.prestige = max(0, civ.prestige - 1)` for all civs
2. **Income effects:**
   - Trade income bonus: `prestige // 5` (+1 per 5 prestige)
   - Congress voting weight (M14c): `prestige // 3` added to negotiating power

### Constants (M16a)

```python
ASSIMILATION_THRESHOLD = 15          # turns for cultural identity to flip
ASSIMILATION_STABILITY_DRAIN = 3     # per mismatched region per turn (P1-dependent)
RECONQUEST_COOLDOWN = 10             # turns of restless_population after reconquest
```

### World Generation Changes (`world_gen.py`)

After region assignment in `assign_civilizations`:

```python
for region in world.regions:
    if region.controller:
        region.cultural_identity = region.controller
```

### Exports from `culture.py` (M16a)

- `apply_value_drift(world)` — phase 10
- `tick_cultural_assimilation(world)` — phase 10
- `tick_prestige(world)` — phase 2
- `VALUE_OPPOSITIONS` — constant

### Phase Integration (M16a)

| Function | Phase | Called from |
|----------|-------|------------|
| `tick_prestige` | 2 (Automatic Effects) | `apply_automatic_effects` |
| Cultural works enhancement | 6 (Cultural Milestones) | `phase_cultural_milestones` |
| `apply_value_drift` | 10 (Consequences) | `phase_consequences` |
| `tick_cultural_assimilation` | 10 (Consequences) | `phase_consequences` |

---

## Phase M16b: Movements & Schisms

### Goal

Ideas become independent entities with lifecycles. Movements emerge from civs, spread along trade routes, get adopted, and eventually splinter into incompatible variants that flip alliances into rivalries. Protestant/Catholic dynamics from mechanical drift.

### Model Changes

**`WorldState` (models.py) — new fields:**
```python
movements: list[Movement] = Field(default_factory=list)
next_movement_id: int = 0  # monotonic counter, never reuse IDs
```

Monotonic counter prevents ID collision if movements are ever removed in future milestones.

**New model — `Movement` (models.py):**
```python
class Movement(BaseModel):
    id: str                    # e.g. "movement_0", "movement_1"
    origin_civ: str            # civ that spawned it
    origin_turn: int           # when it emerged
    value_affinity: str        # from origin civ's values
    adherents: dict[str, int] = Field(default_factory=dict)  # civ_name → variant counter
```

The `adherents` dict serves double duty: keys = who has adopted, values = variant counter for schism tracking. Variant counter starts at `int(SHA256(civ_name + movement_id).hexdigest(), 16) % SEEDED_OFFSET_RANGE`, increments by 1 every `VARIANT_DRIFT_INTERVAL` turns. Uses `hashlib.sha256` (not Python's built-in `hash()`) for determinism across processes — `hash()` is randomized per-process since Python 3.3.

### Movement Emergence — `_check_emergence(world)`

Every `MOVEMENT_EMERGENCE_INTERVAL` (30) turns, scan all civs and score:

```python
score = (culture / STAT_MAX) + (1 - stability / STAT_MAX) + era_bonus
```

Where `era_bonus`:
- TRIBAL/BRONZE: `0.0`
- IRON/CLASSICAL: `0.1`
- MEDIEVAL/RENAISSANCE: `0.2`
- INDUSTRIAL/INFORMATION: `0.3`

**Normalization:** Both culture and stability are divided by `STAT_MAX` (100 post-P1, imported from `utils.py` where P1 defines it), producing values in [0, 1]. This formula survives P1 scale migration without retuning.

Highest scorer spawns the movement. **Tiebreaker:** `SHA256(f"{seed}:{turn}:movement_origin")` — among tied civs, pick the one whose name hashes lowest with this salt. Consistent with disaster rolls, build selection, and every other deterministic choice in the codebase.

**Empty values guard:** if `winner.values` is empty, skip emergence for this interval. A valueless civ shouldn't spawn a movement.

Movement created:
```python
movement = Movement(
    id=f"movement_{world.next_movement_id}",
    origin_civ=winner.name,
    origin_turn=world.turn,
    value_affinity=winner.values[0],  # primary value
    adherents={winner.name: _seeded_offset(winner.name, movement.id)},
)
world.movements.append(movement)
world.next_movement_id += 1
```

Origin civ auto-adopts with seeded starting offset. Generate a `NamedEvent` appended to `world.named_events` with `event_type="movement_emergence"`, `importance=6`. The `name` field is generated by a new `generate_movement_name(civ, world, seed)` function in `named_events.py`, following the existing pattern of `generate_battle_name`, `generate_treaty_name`, etc.

**Name generation for all M16 event types:** All M16 events use `NamedEvent` (appended to `world.named_events`), not plain `Event`. Each event type needs a name generator added to `named_events.py`:
- `generate_movement_name(civ, world, seed)` — for emergence and adoption events
- `generate_schism_name(civs, world, seed)` — for schism events
- `generate_propaganda_name(civ, region, world, seed)` — for propaganda campaigns
- `generate_cultural_milestone_name(civ, milestone_type, world, seed)` — for hegemony and enlightenment events

These follow the existing `_seed_rng` + template pattern in `named_events.py`.

### Movement Spread — `_process_spread(world)`

Each turn, for each active movement, **snapshot the adherent set** before processing:

```python
current_adherents = list(movement.adherents.keys())
```

For each civ in `current_adherents`, check all other civs with `trade_volume > 0` toward the adherent:

```python
compatibility = 100 if movement.value_affinity in target.values
               else 0 if VALUE_OPPOSITIONS.get(movement.value_affinity) in target.values
               else 50

adoption_probability = trade_volume * compatibility / 100
rng = random.Random(seed + world.turn + hash_str(movement.id + target.name))  # deterministic per-civ-per-movement
roll = rng.randint(0, 99)
if roll < adoption_probability and target.name not in movement.adherents:
    movement.adherents[target.name] = _seeded_offset(target.name, movement.id)
    generate NamedEvent(event_type="movement_adoption", importance=5)
```

**Value compatibility is binary match:**
- Shared value (movement affinity in civ's values): `100`
- Opposing value (opposition table match): `0`
- Neutral (neither shared nor opposed): `50`

**No single-turn cascades.** Iterating over the snapshot prevents a movement from spreading through an entire trade network in one turn. A civ adopted this turn can only spread the movement starting next turn.

### Variant Drift — `_increment_variants(world)`

All adherents tick on the same cadence, tied to the movement's birth turn:

```python
if (world.turn - movement.origin_turn) % VARIANT_DRIFT_INTERVAL == 0:
    for civ_name in movement.adherents:
        movement.adherents[civ_name] += 1
```

**Late adopters do not retroactively receive missed increments.** A civ adopting on turn 55 for a movement born on turn 30 gets its seeded offset, then its first increment on turn 60 (the next tick). A civ adopting on turn 61 waits until turn 70. Adoption timing and seeded offset are both intentional sources of divergence.

### Schism Detection — `_detect_schisms(world)`

After variant increment, check all adherent pairs:

```python
for each pair (A, B) in movement.adherents:
    divergence = abs(adherents[A] - adherents[B])
    if divergence >= SCHISM_DIVERGENCE_THRESHOLD:
        # Fire-once guard: check events_timeline
        if not any(
            e.event_type == "movement_schism"
            and A in e.actors and B in e.actors
            and movement.id in e.description
            for e in world.named_events
        ):
            generate NamedEvent(
                event_type="movement_schism",
                importance=7,
                actors=[A, B],
                description=f"[{movement.id}] Schism between {A} and {B}",
            )
```

### Disposition Effects (integrated into `apply_value_drift`)

After base value drift computation, `apply_value_drift` adds movement co-adoption effects:

```python
for movement in world.movements:
    for each adherent pair (A, B):
        divergence = abs(movement.adherents[A] - movement.adherents[B])
        if divergence < SCHISM_DIVERGENCE_THRESHOLD:
            relationship.disposition_drift += 5  # co-adopter bonus
        else:
            relationship.disposition_drift += -5  # schism penalty
```

- Compatible co-adopters (divergence < 3): +5 drift toward friendly
- Incompatible variants (divergence >= 3): -5 drift toward hostile
- Non-adopters: 0 effect (indifference, not hostility)
- Multiple movements stack

### Constants (M16b)

```python
MOVEMENT_EMERGENCE_INTERVAL = 30     # turns between emergence checks
SCHISM_DIVERGENCE_THRESHOLD = 3      # variant counter difference for schism
VARIANT_DRIFT_INTERVAL = 10          # turns between variant counter increments
SEEDED_OFFSET_RANGE = 3              # hash % this value for starting offset
```

### Internal Helpers

```python
def _seeded_offset(civ_name: str, movement_id: str) -> int:
    """Deterministic starting variant offset. Uses SHA256 for cross-process consistency."""
    return int(hashlib.sha256((civ_name + movement_id).encode()).hexdigest(), 16) % SEEDED_OFFSET_RANGE

def _hash_str(s: str) -> int:
    """Deterministic string hash for RNG seeding. Replaces Python's non-deterministic hash()."""
    return int(hashlib.sha256(s.encode()).hexdigest(), 16) % (2**31)
```

### Exports from `movements.py`

- `tick_movements(world)` — public API, calls internal helpers in order:
  1. `_check_emergence(world)`
  2. `_process_spread(world)`
  3. `_increment_variants(world)`
  4. `_detect_schisms(world)`
- `MOVEMENT_EMERGENCE_INTERVAL` — constant

### Phase Integration (M16b)

| Function | Phase | Called from |
|----------|-------|------------|
| `tick_movements` | 10 (Consequences) | `phase_consequences` — called **first** in phase 10, before `apply_value_drift` |

---

## Phase M16c: Strategic Culture

### Goal

Culture becomes a weapon. High-culture civs project propaganda into rival regions, era advancement changes mechanical rules, and cultural dominance generates landmark narrative events.

### Propaganda — INVEST_CULTURE Action

**New action type** in `action_engine.py`:

```python
ActionType.INVEST_CULTURE  # added to enum
```

**Eligibility:** `civ.culture >= CULTURE_PROJECTION_THRESHOLD` (60). Weight = 0.0 if below threshold.

**Action resolution** (in `simulation.py`):

Register in `ACTION_REGISTRY` if available (P3); otherwise add elif branch to `_resolve_action` and flag for P3 migration.

```
cost: PROPAGANDA_COST (5) treasury
target: one rival-controlled region adjacent to any of the civ's regions
eligibility guard: cultural_identity != projecting_civ.name (can't target regions already culturally yours)
target selection: among valid targets, pick the region with highest foreign_control_turns
    (closest to assimilation). Tiebreaker: SHA256(f"{seed}:{turn}:propaganda:{civ.name}"),
    pick tied region whose name hashes lowest.
effect: target region's foreign_control_turns += PROPAGANDA_ACCELERATION (3)
```

This doesn't directly flip `cultural_identity` — it accelerates the existing assimilation timer. A civ projecting propaganda into a rival region for 5 consecutive turns adds 15 to `foreign_control_turns`, which (combined with the natural +1/turn) triggers assimilation in ~8 turns instead of 15.

**INFORMATION era override:** `tech.get_era_bonus(era, "culture_projection_range", default=1)`. At INFORMATION era, returns `-1` (global) — target region doesn't need adjacency.

**Defender counter-spend** (reaction registry):

Registered as `REACTION_REGISTRY["INVEST_CULTURE"] = counter_propaganda_reaction`. Trigger condition: fires automatically when `resolve_invest_culture` targets a region. The reaction receives `(world, defender_civ, target_region, seed)` — same signature as M15b's scorched earth reaction.

```python
# Defender = current controller of the targeted region
def counter_propaganda_reaction(world, defender, region, seed):
    if defender.treasury >= COUNTER_PROPAGANDA_COST:  # 3
        defender.treasury -= COUNTER_PROPAGANDA_COST
        # Negate the propaganda acceleration (net effect: +0 from propaganda, +1 from natural tick)
    else:
        # Defender cannot counter — full propaganda effect applies
        pass
```

Auto-fires, no action slot consumed by defender. Defender bleeds treasury passively. Attacker pays action slot + treasury; defender pays treasury only. This asymmetry makes propaganda oppressive to defend against without being free to project.

Generate `NamedEvent(event_type="propaganda_campaign", importance=5)` on use.

**Action engine weights** for INVEST_CULTURE:

```python
TRAIT_WEIGHTS additions (all 10 traits):
"aggressive":     {INVEST_CULTURE: 0.3}
"cautious":       {INVEST_CULTURE: 1.3}
"opportunistic":  {INVEST_CULTURE: 0.8}
"zealous":        {INVEST_CULTURE: 0.5}
"ambitious":      {INVEST_CULTURE: 1.0}
"calculating":    {INVEST_CULTURE: 1.5}
"visionary":      {INVEST_CULTURE: 2.0}  # highest — cultural influence aligns with visionary leaders
"bold":           {INVEST_CULTURE: 0.4}
"shrewd":         {INVEST_CULTURE: 1.8}  # soft power as leverage
"stubborn":       {}                      # defaults to 1.0 via profile.get()

Situational modifiers:
- culture < 60: weight = 0.0
- has rival-adjacent regions: ×2.0
```

### Technological Paradigm Shifts

**Extend `ERA_BONUSES` in `tech.py`:**

```python
# NOTE: Stat bonus values shown below (military: 1, economy: 2, etc.) are pre-P1 values.
# P1 will migrate these to the 0-100 scale (e.g., military: 10, economy: 20).
# M16 only adds the multiplier/range keys — it does NOT modify existing stat bonuses.
ERA_BONUSES: dict[TechEra, dict[str, float]] = {
    TechEra.BRONZE:      {"military": 1, "military_multiplier": 1.0},
    TechEra.IRON:        {"economy": 1, "military_multiplier": 1.3},
    TechEra.CLASSICAL:   {"culture": 1, "fortification_multiplier": 1.0},
    TechEra.MEDIEVAL:    {"military": 1, "fortification_multiplier": 2.0},
    TechEra.RENAISSANCE: {"economy": 2, "culture": 1},
    TechEra.INDUSTRIAL:  {"economy": 2, "military": 2},
    TechEra.INFORMATION: {"culture_projection_range": -1},  # -1 = global
}
```

**Docstring note on `ERA_BONUSES`:** Stat keys (`military`, `economy`, `culture`) are one-time bonuses applied at era advancement. Multiplier/range keys (`military_multiplier`, `fortification_multiplier`, `culture_projection_range`) are ongoing modifiers queried per-turn by consuming modules. Consumers should always use `get_era_bonus()`, never read the dict directly.

**Bonus values are multipliers with 1.0 as identity**, except `culture_projection_range` which uses `-1` as sentinel for global (consistent with `known_regions: None` meaning omniscient). Positive int = hop count from civ's regions.

**New accessor in `tech.py`:**

```python
def get_era_bonus(era: TechEra, key: str, default: float = 0.0) -> float:
    """Look up an era-specific bonus. Returns default if key not present for this era."""
    return ERA_BONUSES.get(era, {}).get(key, default)
```

**Paradigm shift event:** When a civ advances to an era that has a multiplier != 1.0 or a special projection key, generate `NamedEvent(event_type="paradigm_shift", importance=7)`.

### Cultural Victory Tracking — `check_cultural_victories(world)`

Runs in phase 10 (consequences), **last** in the phase 10 sequence — after all other culture effects have resolved.

These are narrative milestones, not win conditions. The simulation does not end. No state flags, no persistent changes — pure event generation.

**Cultural hegemony:**

```python
for civ in world.civilizations:
    others_combined = sum(c.culture for c in world.civilizations if c != civ)
    if civ.culture > others_combined:
        # Fire-once guard
        if not any(
            e.event_type == "cultural_hegemony" and civ.name in e.actors
            for e in world.named_events
        ):
            generate NamedEvent(
                event_type="cultural_hegemony",
                importance=9,
                actors=[civ.name],
            )
```

**Universal enlightenment:**

```python
all_civ_names = {c.name for c in world.civilizations}
for movement in world.movements:
    if set(movement.adherents.keys()) == all_civ_names:
        # Fire-once guard — embed movement ID in description
        if not any(
            e.event_type == "universal_enlightenment"
            and movement.id in e.description
            for e in world.named_events
        ):
            generate NamedEvent(
                event_type="universal_enlightenment",
                importance=10,
                actors=list(movement.adherents.keys()),
                description=f"[{movement.id}] Universal enlightenment achieved",
            )
```

If M17 or M18 later needs a persistent flag for hegemony/enlightenment, that's a two-line addition in that milestone's scope — not M16's problem.

### Constants (M16c)

```python
PROPAGANDA_COST = 5                  # treasury per INVEST_CULTURE action
PROPAGANDA_ACCELERATION = 3          # foreign_control_turns added per propaganda action
COUNTER_PROPAGANDA_COST = 3          # treasury auto-deducted from defender
CULTURE_PROJECTION_THRESHOLD = 60    # minimum culture to use INVEST_CULTURE
```

### Exports from `culture.py` (M16c additions)

- `check_cultural_victories(world)` — phase 10
- `resolve_invest_culture(world, civ, target_region)` — action resolution in phase 4-5

### Phase Integration (M16c)

| Function | Phase | Called from |
|----------|-------|------------|
| INVEST_CULTURE resolution | 4-5 (Action) | `_resolve_action` / `ACTION_REGISTRY` |
| `check_cultural_victories` | 10 (Consequences) | `phase_consequences` — called **last** in phase 10 |

---

## Integration Summary

### Complete Phase 10 Ordering (Consequences)

The order within phase 10 is causally significant:

1. **`tick_movements(world)`** — emergence, spread, variant drift, schism detection. Produces adoption state.
2. **`apply_value_drift(world)`** — base value drift from shared/opposing values + movement co-adoption effects from step 1. Produces disposition changes.
3. **`tick_cultural_assimilation(world)`** — region identity shifts. Reads stability environment affected by value drift from step 2.
4. **`check_cultural_victories(world)`** — read-only snapshot after all culture effects have resolved. Must run last to catch universal enlightenment from this turn's adoptions.

### Complete Phase 2 (Automatic Effects)

`tick_prestige(world)` runs alongside existing treasury income and military maintenance.

### New Event Types

| Event Type | Importance | Generated By | Fire-Once Guard |
|------------|-----------|-------------|-----------------|
| `movement_emergence` | 6 | `_check_emergence` | Implicit (clock-based) |
| `movement_adoption` | 5 | `_process_spread` | Implicit (adherent check) |
| `movement_schism` | 7 | `_detect_schisms` | Check `named_events` for same movement + actor pair |
| `propaganda_campaign` | 5 | INVEST_CULTURE resolution | None (repeatable action) |
| `cultural_assimilation` | 6 | `tick_cultural_assimilation` | Implicit (identity flip is one-time) |
| `paradigm_shift` | 7 | Tech advancement check | Implicit (era advancement is one-time) |
| `cultural_hegemony` | 9 | `check_cultural_victories` | Check `named_events` for same actor |
| `universal_enlightenment` | 10 | `check_cultural_victories` | Check `named_events` for movement.id in description |

All M16 events are `NamedEvent` objects appended to `world.named_events` (not `Event` objects in `world.events_timeline`). Each event type requires a name generated by functions in `named_events.py`.

### Snapshot Changes (`bundle.py`)

Extend viewer snapshots for Chronicle Viewer (M11) visualization:

- **`CivSnapshot`**: add `prestige: int`
- **Region snapshot**: add `cultural_identity: str | None`
- **`TurnSnapshot`**: add `movements: list[dict]` (id, value_affinity, adherent count, origin_civ)

### All Constants

```python
# culture.py
ASSIMILATION_THRESHOLD = 15          # turns for cultural identity to flip
ASSIMILATION_STABILITY_DRAIN = 3     # per mismatched region per turn (P1-dependent)
RECONQUEST_COOLDOWN = 10             # turns of restless_population after reconquest
PROPAGANDA_COST = 5                  # treasury per INVEST_CULTURE action
PROPAGANDA_ACCELERATION = 3          # foreign_control_turns added per propaganda action
COUNTER_PROPAGANDA_COST = 3          # treasury auto-deducted from defender
CULTURE_PROJECTION_THRESHOLD = 60    # minimum culture to use INVEST_CULTURE

# movements.py
MOVEMENT_EMERGENCE_INTERVAL = 30     # turns between emergence checks
SCHISM_DIVERGENCE_THRESHOLD = 3      # variant counter difference for schism
VARIANT_DRIFT_INTERVAL = 10          # turns between variant counter increments
SEEDED_OFFSET_RANGE = 3              # hash % this value for starting offset
```

---

## Edge Cases for Testing

These edge cases are where bugs hide. Tests must cover all of them.

### M16a Edge Cases

- **Drift crossing +10 and -10 in same turn:** Two civ pairs where one has shared values and one has opposing values. Verify both level changes fire independently.
- **Assimilation at exactly turn 15:** Region with `foreign_control_turns = 14` ticks to 15. Verify identity flips and event fires on that exact turn.
- **Reconquest at turn 14:** Region reconquered one turn before assimilation. `foreign_control_turns` resets to 0, no flip. Restless population condition applied.
- **Empty values list:** Civ with `values = []` contributes no drift (shared=0, opposing=0, net_drift=0).
- **Reconquest drain exemption:** Region in first 10 turns after reconquest skips per-turn stability drain; `restless_population` condition covers it instead.

### M16b Edge Cases

- **Movement emergence tiebreaker:** All civs score identically. SHA256 tiebreaker must produce deterministic, consistent winner.
- **Spread to valueless civ:** Target civ with `values = []` gets compatibility = 50 (neutral). Verify adoption can occur at sufficient trade_volume.
- **Variant drift on adoption turn:** Civ adopts on a tick turn (`(world.turn - movement.origin_turn) % 10 == 0`). Does the new adherent increment immediately? Yes — they're in the adherent dict when the increment loop runs.
- **Schism between identical offsets:** Two civs with same `hash % 3` offset but different adoption timing. Verify divergence comes from missed ticks, not from the offset alone.
- **No single-turn cascade:** Civ A adopts, spreads to B in same tick, B should NOT spread to C in the same tick. Snapshot guard prevents this.

### M16c Edge Cases

- **Propaganda with defender treasury = 0:** No counter-spend, full +3 acceleration applies.
- **INFORMATION-era global projection:** Civ targets a non-adjacent region. Verify adjacency check is bypassed when `get_era_bonus(era, "culture_projection_range") == -1`.
- **Propaganda tips assimilation:** Region at `foreign_control_turns = 14` receives propaganda (+3). Assimilation triggers at 17 (> threshold 15). Verify identity flip on the next `tick_cultural_assimilation` call.
- **Two civs propaganda same region:** Both spend treasury, both accelerate `foreign_control_turns`. Defender counter-spends against each separately (6 treasury total). Verify both effects apply.
- **Cultural hegemony oscillation:** Civ achieves hegemony (event fires), then loses it next turn as others grow. Event should NOT fire again when they re-achieve hegemony (fire-once guard).
