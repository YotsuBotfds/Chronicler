# M18: Emergence and Chaos — Design Spec

**Status:** Design approved, pending implementation plan
**Date:** 2026-03-14
**Depends on:** M13 (Resources), M14 (Politics), M15 (Living World), M16 (Memetic Warfare), M17 (Great Person Engine)

## Overview

M18 is the Phase 3 capstone. It adds rare, high-impact cross-system interactions that make long simulations genuinely surprising. Every system M13-M17 is predictable in isolation; M18 creates emergent unpredictability by reading state from all prior systems and producing consequences that cascade through them.

**Design philosophy:** Black swans should feel *earned* — "of course the overextended empire collapsed when the plague hit" — not random. M18 events read structural fragility and respond to it. The simulation doesn't conspire against civilizations; their own fragility does.

**Architecture:** Single `emergence.py` module containing all M18 logic, called from existing turn phases. No new phases added. Cross-system interactions are the feature — centralizing them in one readable module makes those interactions explicit rather than invisible import chains.

## Four Subsystems

1. **Black Swan Events** — Rare catastrophes (pandemic, supervolcano, resource discovery, tech accident) gated by structural preconditions
2. **Stress Index & Cascade Failures** — Per-civ fragility metric that amplifies the severity of negative events
3. **Technological Regression** — Knowledge loss triggered by catastrophic structural failure
4. **Ecological Succession** — Minimal proof-of-concept: two terrain transitions (deforestation, rewilding)

---

## 1. Data Model Additions

### WorldState additions

```python
# Stress tracking
stress_index: int = 0  # Global aggregate (max across all civs), recomputed each turn

# Black swan state
black_swan_cooldown: int = 0  # Turns until another black swan can fire
pandemic_state: list[PandemicRegion] = []  # Active pandemic tracking

# Terrain transition rules (defaults, overridable via ScenarioConfig)
terrain_transition_rules: list[TerrainTransitionRule] = Field(
    default_factory=lambda: [
        TerrainTransitionRule(from_terrain="forest", to_terrain="plains",
                              condition="low_fertility", threshold_turns=50),
        TerrainTransitionRule(from_terrain="plains", to_terrain="forest",
                              condition="depopulated", threshold_turns=100),
    ]
)

# Climate offset for supervolcano phase advancement
# ClimateConfig addition:
phase_offset: int = 0  # Added to turn count in get_climate_phase()
```

### Civilization additions

```python
civ_stress: int = 0  # Per-civ stress, recomputed each turn

# Start-of-turn snapshots for regression trigger detection
regions_start_of_turn: int = 0  # Set at top of run_turn
was_in_twilight: bool = False    # Set from decline_turns > 0 at top of run_turn
```

### Region additions

```python
low_fertility_turns: int = 0  # Consecutive turns with fertility < 0.3; resets on recovery
```

### New models

```python
class PandemicRegion(BaseModel):
    """Tracks pandemic spread per-region."""
    region_name: str
    severity: int  # 1-3, keyed off region infrastructure count
    turns_remaining: int  # 4-6, decrements each turn

class TerrainTransitionRule(BaseModel):
    """Configurable terrain transformation rule."""
    from_terrain: str
    to_terrain: str
    condition: str  # "low_fertility" or "depopulated"
    threshold_turns: int  # Consecutive turns before transform triggers
```

### ScenarioConfig additions

```python
chaos_multiplier: float = 1.0  # Scalar on all M18 event probabilities
black_swan_cooldown_turns: int = 30  # Minimum gap between black swans (global)
# terrain_transition_rules: overrides WorldState defaults if provided
```

---

## 2. Black Swan Events

### Base probability and gating

- **Base probability per turn:** 0.005 (0.5%) × `chaos_multiplier`
- **Gate:** `world.black_swan_cooldown == 0`
- **Cooldown:** Global (not per-type). When any black swan fires, `black_swan_cooldown = black_swan_cooldown_turns` (default 30). At 2-3 events per 500 turns, per-type cooldowns add complexity without value. Global cooldown prevents "two simultaneous catastrophes" which are extremely hard to narrate well.
- **Selection:** Weighted random among eligible event types

### Event type eligibility and weights

| Event | Weight | Eligibility condition |
|-------|--------|----------------------|
| **Pandemic** | 3 | Any civ has 3+ active trade routes |
| **Supervolcano** | 2 | Any cluster of 3+ mutually adjacent *controlled* regions exists |
| **Resource Discovery** | 2 | Any region has 0 specialized resources |
| **Technological Accident** | 1 | Any civ at INDUSTRIAL+ era |

Eligibility conditions mean the simulation naturally unlocks more black swan types as it develops. Early-game black swans are limited to supervolcano and resource discovery. Pandemic and tech accident require trade networks and industrialization respectively.

### Stress as severity modifier, not frequency modifier

The stress index does **not** increase black swan probability. Frequency stays at 0.5% × chaos_multiplier regardless of stress. Instead, stress determines how severely black swan *consequences* hit (via the cascade severity multiplier described in Section 3). This keeps event density predictable while making consequences scale with fragility.

### 2a. Pandemic

The most complex black swan — spreads over multiple turns along trade routes.

**Origin:** Select a random region controlled by the civ with the most active trade routes. The trade-network-as-vector design: the most connected civ is patient zero. If a merchant great person exists (M17), their trade routes count toward the total (they're passive super-spreaders — the infrastructure they built is the highway the plague travels on).

**Spread:** Each turn, the pandemic spreads from infected regions to adjacent regions that share a trade route with any infected region's controller. Non-trading neighbors are safe (isolation advantage). No region is infected twice in the same pandemic — the wave passes through and moves on. When all adjacent trade-connected regions are already infected or recovered, spread stops naturally. The pandemic burns out when all `PandemicRegion.turns_remaining` hit 0.

**Per-civ effects (aggregate, not per-region):** Effects apply once per civ per turn, regardless of how many of their regions are infected. More infected regions increase spread probability to neighbors, not damage.
- `population -= min(severity × 3, 12)`
- `economy -= min(severity × 2, 8)`
- Severity per region = `1 + len(region.infrastructure) // 2` (capped at 3). The per-civ severity is the max across their infected regions.
- Per-region severity reflects infrastructure density as a proxy for population concentration.

**Duration:** `PandemicRegion.turns_remaining` starts at 4-6 (random per region). M17 interaction: scientist great person in an infected civ reduces duration by 1 turn (knowledge-based containment).

**Leader kill check:** 5% per turn per infected civ (one roll per civ, not per region). If the leader dies, existing succession logic in `leaders.py` fires.

### 2b. Supervolcano

Instant-impact, geographically concentrated.

**Target:** Select a random cluster of 3+ mutually adjacent controlled regions. Prefer clusters containing mountain regions (volcanic association). At least one region in the cluster must have a controller (volcanoes in empty wilderness are narratively boring).

**Immediate effects on all regions in cluster:**
- `fertility = 0.1` (devastated)
- All infrastructure destroyed: `region.infrastructure = []`, `region.pending_build = None`
- Controlling civ (per affected region): `population -= 20`, `stability -= 15`

**Secondary effects:**
- Climate cycle advanced by 1 phase via `climate_config.phase_offset += 1` (volcanic winter)
- Creates `ActiveCondition(condition_type="volcanic_winter", duration=5, severity=40)` affecting all civs with regions adjacent to the blast zone
- M17 interaction: if a folk hero's origin region is in the blast zone, the civ gains +0.05 asabiya (rallying around shared trauma)

### 2c. Resource Discovery

The positive black swan — creates strategic tension without destruction.

**Target:** Select a random region with 0 specialized resources.

**Effect:** Add 1-2 specialized resources chosen from `{Resource.FUEL, Resource.RARE_MINERALS}` (late-game strategic resources). A barren region suddenly gaining FUEL is "you just found oil." FUEL is required for INDUSTRIAL era advancement; RARE_MINERALS are the late-game strategic resource.

**Diplomatic consequence:** All civs controlling regions adjacent to the discovery get `disposition_drift -= 1` toward the controller (jealousy/desire). If the region is uncontrolled, all adjacent controllers get `disposition_drift -= 1` toward each other (competition for unclaimed wealth).

### 2d. Technological Accident

Industrial+ era environmental hazard.

**Target:** Select a random region controlled by an INDUSTRIAL+ era civ. Prefer regions with mines (industrial activity).

**Immediate effects:**
- Target region: `fertility -= 0.3`
- All regions within 2 adjacency hops: `fertility -= 0.15`
- M17 interaction: scientist great person in the responsible civ reduces radius from 2 hops to 1 (containment)

**Diplomatic fallout:** Civs controlling affected neighbor regions get `disposition_drift -= 2` toward the polluter. Creates a "you poisoned our land" grievance.

---

## 3. Stress Index & Cascade Failures

### Per-civ stress computation

Computed fresh each turn at the end of Phase 10 (Consequences). Stored on `Civilization.civ_stress` for next turn's use:

```python
def compute_civ_stress(civ: Civilization, world: WorldState) -> int:
    stress = 0

    # Active wars (3 per war)
    stress += sum(1 for w in world.active_wars if civ.name in w) * 3

    # Famine in controlled regions (2 per famine region)
    stress += sum(1 for r in world.regions
                  if r.controller == civ.name and r.famine_cooldown > 0) * 2

    # Active secession risk (4 if stability < 20 with 3+ regions)
    if civ.stability < 20 and len(civ.regions) >= 3:
        stress += 4

    # Active pandemic in controlled regions (2 per infected region)
    stress += sum(1 for p in world.pandemic_state
                  if any(r.controller == civ.name
                         for r in world.regions if r.name == p.region_name)) * 2

    # Recent turbulent succession (2 if general/usurper within last 5 turns)
    if (civ.leader.succession_type in ("general", "usurper")
            and world.turn - civ.leader.reign_start <= 5):
        stress += 2

    # In twilight (3)
    if civ.decline_turns > 0:
        stress += 3

    # Active disaster conditions (2 per condition)
    stress += sum(1 for c in world.active_conditions
                  if civ.name in c.affected_civs
                  and c.condition_type in ("drought", "volcanic_winter")) * 2

    # Overextension (1 per region beyond 6)
    stress += max(0, len(civ.regions) - 6)

    return min(stress, 20)  # Cap at 20
```

### Global stress (viewer metric)

```python
world.stress_index = max(civ.civ_stress for civ in world.civilizations)
```

Max, not average — the most stressed civ represents the global instability peak. Used for viewer color-coding (green/yellow/red) and narrative context only. All mechanical calculations use per-civ stress.

### Cascade severity multiplier

```python
def get_severity_multiplier(civ: Civilization) -> float:
    return 1.0 + (civ.civ_stress / 20) * 0.5
```

- Stress 0: 1.0× (normal)
- Stress 10: 1.25× (noticeably worse)
- Stress 20 (cap): 1.5× (maximum amplification)

**Applies to:** All negative stat modifications (stability loss, economy loss, population loss, famine severity, pandemic damage per turn). The implementer should audit all negative stat modifications in Phase 1 (climate disasters), Phase 5 (war outcomes), Phase 7 (random events), and Phase 10 (consequences) and wrap them with `int(base_amount * get_severity_multiplier(civ))`.

**Does NOT apply to:** Positive events, asabiya dynamics, tech regression probability.

### Why severity amplifier, not frequency amplifier

A fragile civ doesn't attract more events — it suffers more from the events that hit everyone. The simulation doesn't conspire against you; your own structural weaknesses compound. This keeps event density predictable (important for narrative pacing) while making fragility mechanically punishing.

### M17 structural interactions (no explicit coupling)

- **Resilience tradition** (doubles stability gains): counteracts cascade multiplier on stability loss through faster recovery. No M18-aware code needed — the tradition does its thing, the multiplier does its thing.
- **Diplomatic tradition:** Civs leaning on federation allies weather the economy multiplier better.
- These are structural protections, not probabilistic shields. No "prestige reduces regression probability" formulas.

---

## 4. Technological Regression

### Trigger conditions

Checked once per turn in Phase 10, after stress computation. Not a random event — a consequence of catastrophic structural failure.

| Trigger | Probability | Condition |
|---------|------------|-----------|
| **Capital loss + territorial collapse** | 30% | Lost capital this turn AND `civ.regions_start_of_turn > 0` AND `len(civ.regions) / civ.regions_start_of_turn < 0.5` |
| **Entered twilight** | 50% | `civ.decline_turns > 0 and not civ.was_in_twilight` (transitioned this turn) |
| **Black swan while critically stressed** | 20% | Any black swan fired this turn AND `civ.civ_stress >= 15` |

**Selection rule:** If multiple triggers match, use the **highest probability** among them (not first-in-order). Two simultaneous catastrophes → higher regression chance, not lower. Only one regression per civ per turn regardless.

**Probabilities are flat** — not multiplied by `chaos_multiplier`. The chaos multiplier affects black swan frequency, which indirectly affects trigger 3.

**Start-of-turn snapshots:** `civ.regions_start_of_turn` and `civ.was_in_twilight` are set at the top of `run_turn` before any phases execute. This allows Phase 10 to detect within-turn transitions.

### Regression effect

Step back one tech era. Reverse the stat bonuses granted on advancement:

```python
def remove_era_bonus(civ: Civilization, era: TechEra) -> None:
    """Reverse of apply_era_bonus in tech.py."""
    bonuses = ERA_BONUSES.get(era, {})
    for stat, amount in bonuses.items():
        if isinstance(amount, int) and hasattr(civ, stat):
            current = getattr(civ, stat)
            setattr(civ, stat, clamp(current - amount, STAT_FLOOR.get(stat, 0), 100))
```

Non-integer bonuses (`military_multiplier`, `fortification_multiplier`, `culture_projection_range`) are dynamically looked up via `get_era_bonus(civ.tech_era, key)`, so dropping an era loses those modifiers automatically — no reversal code needed.

### Cultural consequences (free, no new code)

- Dropping from INFORMATION loses `culture_projection_range: -1` (global reach) → movements contract to adjacency-based spread automatically
- Dropping from INDUSTRIAL loses `economy: 20, military: 20` → direct stat hit
- Paradigm shift bonuses (IRON's `military_multiplier: 1.3`, MEDIEVAL's `fortification_multiplier: 2.0`) disappear because they're era-keyed lookups

The existing era bonus system responds correctly to a lower `tech_era` value. No new coupling code.

### Recovery

Re-advancement through the normal `check_tech_advancement` path. Same culture/economy/treasury requirements, same resource requirements. M17's scientist great person applies their -30% tech cost modifier to re-advancement, making recovery faster for civs with institutional knowledge.

No special recovery mode or accelerated path. The normal tech system handles it.

### Floor

Cannot regress below TRIBAL. If a TRIBAL-era civ would regress, nothing happens.

---

## 5. Ecological Succession (Minimal Version)

Two terrain transitions as proof-of-concept. The full four-transition system (adding desertification, marsh drainage) deferred to Phase 4 when M19's analytics infrastructure enables tuning.

### Terrain transition rules

Stored on `WorldState.terrain_transition_rules` (persists across save/load). Defaults to two rules. Overridable via ScenarioConfig. To disable: set to empty list.

**Deforestation:** Forest with fertility < 0.3 for 50+ consecutive turns → Plains
- Tracked via `Region.low_fertility_turns` (incremented/reset in Phase 9)
- On transition: `region.terrain = "plains"`, `region.carrying_capacity += 20` (cleared forest = arable land, supports larger agricultural populations), `region.fertility = 0.5`
- Resets `low_fertility_turns = 0`

**Rewilding:** Plains with no controller for 100+ consecutive turns → Forest
- Tracked via `world.turn - region.depopulated_since` (existing field, no new counter)
- On transition: `region.terrain = "forest"`, `region.carrying_capacity -= 10`, `region.fertility = 0.7`
- Resets `depopulated_since = None`

### Processing (Phase 9 internal ordering)

Within Phase 9, the explicit order is:
1. All fertility calculations run (existing logic)
2. Increment or reset `low_fertility_turns` based on new fertility value
3. Check terrain transitions via `tick_terrain_succession(world)`

### Narrative value

An empire strips its forests through overuse (fertility drops from overpopulation) → deforestation creates plains → empire collapses (M14 politics) → centuries pass with no controller → forest grows back (rewilding). Two rules, one complete historical cycle.

---

## 6. Turn Phase Integration

No new phases. M18 hooks into existing phases:

```
run_turn():
    # --- Start-of-turn snapshots (NEW) ---
    for civ in world.civilizations:
        civ.regions_start_of_turn = len(civ.regions)
        civ.was_in_twilight = civ.decline_turns > 0

    # Phase 1: Environment
    phase_environment(world, seed)
    check_black_swans(world, seed)          # NEW — after climate disasters

    # Phase 2-8: Unchanged
    ...
    tick_pandemic(world)                     # NEW — in Phase 2 (Automatic Effects)
    ...

    # Phase 9: Fertility
    phase_fertility(world)                   # Existing (includes fertility calc)
    # Internal to phase_fertility or called after:
    # (a) increment/reset low_fertility_turns
    # (b) tick_terrain_succession(world)     # NEW

    # Phase 10: Consequences
    phase_consequences(world)                # Existing
    check_tech_regression(world)             # NEW — after consequences
    compute_all_stress(world)                # NEW — last (feeds next turn)

    # Decrement black_swan_cooldown
    if world.black_swan_cooldown > 0:
        world.black_swan_cooldown -= 1
```

### Module structure

All M18 logic in `src/chronicler/emergence.py`:
- `check_black_swans(world, seed)` — probability roll, eligibility check, dispatch
- `_apply_pandemic_origin(world, seed)` — pandemic initialization
- `_apply_supervolcano(world, seed)` — supervolcano effects
- `_apply_resource_discovery(world, seed)` — resource discovery effects
- `_apply_tech_accident(world, seed)` — tech accident effects
- `tick_pandemic(world)` — per-turn pandemic spread and damage
- `compute_civ_stress(civ, world)` — per-civ stress calculation
- `compute_all_stress(world)` — stress for all civs + global aggregate
- `get_severity_multiplier(civ)` — cascade severity lookup
- `check_tech_regression(world)` — trigger check and regression application
- `tick_terrain_succession(world)` — ecological transition check

`remove_era_bonus()` goes in `tech.py` alongside the existing `apply_era_bonus()`.

---

## 7. Testing Strategy

- **Black swan frequency:** Run 1000-turn simulation with fixed seed, verify 4-6 black swans fire (±1 for randomness). Verify no two black swans within cooldown window.
- **Eligibility gating:** Verify pandemic doesn't fire before any civ has 3+ trade routes. Verify tech accident doesn't fire before INDUSTRIAL era.
- **Pandemic spread:** Create a 5-civ scenario with known trade routes. Trigger pandemic. Verify spread follows trade routes, not just adjacency. Verify isolated (no-trade) civs are unaffected.
- **Pandemic damage caps:** Verify per-civ damage doesn't exceed `min(severity × 3, 12)` population and `min(severity × 2, 8)` economy per turn regardless of infected region count.
- **Stress computation:** Set up known stress conditions (2 wars, 1 famine, 8 regions). Verify `compute_civ_stress` returns expected value.
- **Severity multiplier:** Verify `get_severity_multiplier` at stress 0, 10, 20 returns 1.0, 1.25, 1.5.
- **Tech regression triggers:** Test each trigger in isolation. Verify highest-probability selection when multiple triggers match.
- **Tech regression reversal:** Advance a civ to INDUSTRIAL, trigger regression, verify stats match pre-INDUSTRIAL values (accounting for clamp).
- **Ecological succession:** Run a forest region at fertility 0.1 for 50 turns, verify transition to plains with correct capacity/fertility values. Run a plains region depopulated for 100 turns, verify transition to forest.
- **Terrain transition rules:** Verify empty rules list disables succession. Verify custom rules are applied correctly.
- **Integration:** 5-turn smoke test with all systems active. Verify no crashes, state consistency, events logged.
