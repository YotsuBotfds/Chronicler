# M38b: Schisms, Pilgrimages & Persecution

> **Status:** Design approved. Ready for implementation planning.
>
> **Depends on:** M38a (temples & clergy) for `temple_prestige`, `faith_id` on temples, clergy faction influence. M37 (belief systems) for belief registry, `compute_conversion_signals()`, `conquest_conversion_boost` lifecycle pattern, `NAMED_PROPHET_MULTIPLIER`, `civ_majority_faith`. M36 (cultural identity) for penalty cap infrastructure (Decision 10). M30 (named characters) for GreatPerson model and promotion.
>
> **Scope:** Three subsystems — persecution (Rust penalty signal + Python detection), schisms (Python faith splitting + Rust conversion spread), pilgrimages (Python-only narrative arcs on GreatPerson). Minimal Rust changes (~15 lines in satisfaction.rs and tick.rs). One new region batch column. No new Rust modules. ~100-120 lines Rust, ~250-300 lines Python, ~300 lines tests.
>
> **Implementation order:** Persecution → Schisms → Pilgrimages (each independently shippable).
>
> **Estimate:** 5-7 days (persecution 1-2, schisms 2-3, pilgrimages 1-2).

---

## Overview

M37 creates per-agent religious belief with event-driven conversion. M38a adds institutional power — temples project faith, clergy competes for political influence. But religion has no *consequences*. A Militant faith and a Pacifist faith behave identically toward minorities. Faiths never fracture under internal pressure. Named characters have no religious arcs.

M38b adds the dynamics that make religion a driver of civilizational history:

- **Persecution** gives Militant faiths teeth — institutional oppression of religious minorities drives migration, rebellion, and martyrdom. It consumes the remaining -0.15 of the Decision 10 satisfaction budget.
- **Schisms** fracture faiths along doctrinal fault lines caused by game-state conditions — persecution, clergy dominance, conquest. A schism creates a new faith locally; M37's existing conversion mechanics handle organic spread.
- **Pilgrimages** create multi-turn character arcs for named characters — a priest journeys to the holiest temple of their faith and returns as a Prophet.

**Design principle:** M38b is almost entirely event detection and emission. The behavioral machinery already exists in M37 (conversion), M36 (penalty cap), and M32 (utility decisions). Persecution adds one region batch signal that Rust reads in existing code paths. Schisms create new beliefs that M37's conversion system spreads. Pilgrimages are Python-side GreatPerson state with narrative events. No new abstractions, no new Rust tick stages, no new action types.

---

## Design Decisions

### Decision 1: Implementation Order — Persecution First

**Order:** Persecution → Schisms → Pilgrimages.

**Why persecution first:** It consumes existing data. M37 already produces faith minorities (conquest conversion, initial assignment). M38a provides clergy faction. Persecution wires the remaining -0.15 satisfaction budget, adds rebel/migrate utility modifiers, and fires mass migration events. No new data structures — it reads `agent.belief`, `region.majority_belief`, and doctrine lookups. Simplest of the three to implement and immediately makes the religious system consequential.

**Why schisms second:** Without persecution already wired, schisms produce new faiths that just exist. With persecution wired first, a schism in a Militant civ instantly cascades: faith splits → new minority → persecution fires → migration wave → secession risk. The interaction is automatic because persecution already reads belief distributions.

**Why pilgrimages third:** Mechanically standalone. Needs `temple_prestige` (M38a) and named character selection, but doesn't interact with persecution or schisms mechanically. A pilgrimage is a character arc — narratively rich but doesn't affect population dynamics. Can slip without blocking M39.

### Decision 2: Discrete Doctrine Gate, Not Continuous Threshold

M37's Stance doctrine axis is discrete: -1 (Pacifist), 0 (Neutral), +1 (Militant). Persecution fires only for Militant (+1) faiths. No threshold constant needed — the doctrine axis IS the gate.

**Why not continuous intensity from doctrine value:** The doctrine axes aren't continuous (0.0-1.0). They're ternary. A continuous formula (`Militant_doctrine × (1 - minority_ratio)`) assumes a float it doesn't have. The binary gate is the natural consequence of the data model.

**What non-Militant faiths have:** M37's religious mismatch satisfaction penalty (-0.10) applies to any agent whose belief differs from the region majority, regardless of doctrine. That's passive tension — "surrounded by people who don't share my faith." Persecution is active institutional oppression on top of that. Only Militant faiths have the doctrinal mandate to enforce conformity.

### Decision 3: Identity Penalty Stacking Is Intentional

Cultural (-0.15 max, M36) + religious (-0.10, M37) + persecution (-0.15 max, M38b) = -0.40, exactly the Decision 10 cap. No additional diminishing returns or sub-caps.

An agent who is culturally foreign, religiously minority, AND actively persecuted is living through the historical experience of conquered peoples under hostile empires. Satisfaction at 0.1-0.2 means they will rebel or migrate. That's the Albigensian Crusade, the Jewish diaspora, the Huguenot exodus. The systems produce historically legible behavior.

**Self-correcting dynamics:**
- Persecuted agents migrate out → minority ratio drops → persecution intensity drops (the `1 - minority_ratio` term)
- Persecuted agents rebel → instability → the persecuting civ has reduced capacity to persecute
- Martyrdom boost → conversion rate rises → more agents adopt the persecuted faith → minority ratio rises → persecution intensity drops
- Cultural drift (M36) slowly assimilates the cultural penalty away (~50-100 turns), even if religious penalty persists

Each of the three penalties has a different decay mechanism. The -0.40 cap prevents satisfaction from hitting zero (which would depopulate regions instantly). M47 tunes individual weights within the budget if triple-minority scenarios prove too harsh.

### Decision 4: Issue-Driven Schisms, Not Random

Schisms are caused by observable game state, not dice rolls. The trigger condition determines which doctrine axis flips. This produces schisms with clear narrative causation that the chronicle engine can explain.

**Why not random perturbation:** Random perturbation is what you do when you don't have causation. The game state that triggered the schism IS the cause. "The faith split when the persecuted coastal converts rejected Militant doctrine" is a story. "The faith split and randomly became Proselytizing" is noise.

**Why not "most contentious axis":** Agents don't have individual doctrines — faiths have doctrines, agents have `faith_id`. You can't measure intra-faith disagreement because all believers share the same doctrine vector. The contention is between game state and doctrine, not between believers. Issue-driven captures this correctly.

### Decision 5: Schisms Are Local Birth Events

A schism converts all agents of the original faith in the triggering region to the splinter faith. M37's existing conversion mechanics handle organic spread from there. The schism creates; conversion spreads. Two separate systems doing what they're each built for.

**Why not probabilistic per-agent spread:** Building a bespoke spread algorithm duplicates what `compute_conversion_signals()` already does. The splinter faith starts in one region with priests of the new faith. If it inherited Proselytizing doctrine (or flipped TO Proselytizing), those priests convert in adjacent regions through existing mechanics.

**Cross-civ assignment:** The schism flips all agents of the original faith in the region regardless of civ affiliation. A conquered border region can create a splinter faith spanning two civs from turn one. Faith transcends political boundaries.

### Decision 6: Pilgrimages Are Narrative-Only

No physical agent movement. The agent stays in their home region in the Rust pool. Python's GreatPerson tracks the pilgrimage destination and return turn. Departure and return are named events.

**Why not physical movement:** The current model has no Python→Rust path for moving a specific individual agent. Python sends signals, Rust mutates agents. Adding `move_agent(agent_id, target_region)` FFI for 5-15 events across an entire simulation has terrible ROI. Phase 7's spatial agent system enables physical pilgrimage movement as a natural extension.

**No during-pilgrimage satisfaction bonus.** The agent can't receive an individual satisfaction modifier from Python without per-agent FFI — the same architectural constraint that prevents physical movement. The return effects (+0.10 skill boost, Prophet title) are the whole mechanical package. The narrative engine handles the spiritual fulfillment during the journey.

### Decision 7: Prophet Is a Title, Not an Occupation

"Prophet" is `arc_type = "Prophet"` on GreatPerson, not a new `occ` value. The agent stays occ=4 (Priest) in the Rust pool. M37's `NAMED_PROPHET_MULTIPLIER = 2.0` already doubles conversion rate for named priests — a returned pilgrim benefits automatically.

**Why not a new occupation:** A new `occ` value means Rust-side changes to the occupation enum, satisfaction formulas, faction alignment, demand_shift calculations. All for a role that maybe 3-5 characters hold across a 500-turn run. The occupation system is for population-scale roles. "Prophet" is a narrative distinction on a named individual.

**Forward-compatible with M45:** M45 plans `arc_type` on GreatPerson with "Prophet" explicitly listed as an archetype. M38b sets the tag; M45 wires arc-aware narration.

---

## Subsystem 1: Persecution

### Persecution Detection

Per-turn check in Phase 10 for each region in each civ:

```python
# Doctrine lookup: belief_registry[faith_id].doctrines is list[int],
# DOCTRINE_STANCE = 2, values: -1 (Pacifist), 0 (Neutral), +1 (Militant)
civ_faith = belief_registry[civ.civ_majority_faith]
if civ_faith.doctrines[DOCTRINE_STANCE] != 1:  # Only Militant faiths persecute
    continue

for region in civ.regions:
    # Count minority agents from the agent snapshot (same scan used for
    # compute_majority_belief; implementation should consolidate into one pass)
    minority_count = snapshot_count_where(
        region, lambda a: a.belief != civ.civ_majority_faith
    )
    if minority_count == 0:
        continue
    minority_ratio = minority_count / region.population
    intensity = 1.0 * (1.0 - minority_ratio)
    region.persecution_intensity = intensity
```

### Intensity Formula

`intensity = 1.0 × (1 - minority_ratio)`

Smaller minorities face harsher persecution:
- 40% minority → intensity 0.60 (large enough to resist, softer treatment)
- 10% minority → intensity 0.90 (isolated, easy to target, brutal)

### Agent Effects (Scaled by Intensity)

| Effect | Formula | At i=0.60 | At i=0.90 |
|--------|---------|-----------|-----------|
| Satisfaction penalty | -0.15 × intensity | -0.09 | -0.135 |
| Rebel utility boost | +0.30 × intensity | +0.18 | +0.27 |
| Migrate utility boost | +0.20 × intensity | +0.12 | +0.18 |

**Rust delivery:** One new `Float32` column on the region RecordBatch: `persecution_intensity: f32`. Python computes and sets per region per turn. Rust reads in `satisfaction.rs` (adds penalty before Decision 10 cap) and `tick.rs` (adds to rebel and migrate utility). ~15 lines Rust total across both files.

### Mass Migration Event

```python
MASS_MIGRATION_THRESHOLD = 0.15  # [CALIBRATE]

persecuted_ratio = persecuted_count / region.population
if persecuted_ratio > MASS_MIGRATION_THRESHOLD:
    emit_named_event("Mass Migration", importance=6,
                     details={"faith": persecuted_faith, "region": region.name})
```

Percentage-based, not absolute count. A 50-agent region needs 8 persecuted agents; a 500-agent region needs 75.

### Martyrdom Boost

Reuses M37's `conquest_conversion_boost` lifecycle pattern — one new `Float32` on Region:

**What counts as a persecution death:** Any agent death (from demographics mortality) where the dead agent was in a region with `persecution_intensity > 0` AND the agent's belief differed from the civ's majority faith. This is a Python-side check on the snapshot diff (dead agents list) — no Rust-side death tagging needed. The proxy is imprecise (an old-age death of a minority agent counts), but at population scale the correlation between persecution and minority deaths is strong enough. The narrative engine can distinguish cause-of-death for named characters.

```python
# Count persecution deaths from snapshot diff (Python, Phase 10):
for dead_agent in region.deaths_this_turn:
    if (region.persecution_intensity > 0
            and dead_agent.belief != civ.civ_majority_faith):
        persecution_deaths_in_region += 1

# Martyrdom boost (same lifecycle as conquest_conversion_boost):
if persecution_deaths_in_region > 0:
    region.martyrdom_boost = min(
        region.martyrdom_boost + MARTYRDOM_BOOST_PER_EVENT,
        MARTYRDOM_BOOST_CAP
    )

# Linear decay each turn:
region.martyrdom_boost -= MARTYRDOM_BOOST_PER_EVENT / MARTYRDOM_DECAY_TURNS
region.martyrdom_boost = max(region.martyrdom_boost, 0.0)

# Fed into compute_conversion_signals() alongside conquest_boost:
conversion_rate += region.martyrdom_boost
```

Multiple deaths in the same turn add one `PER_EVENT`. Deaths across turns stack to the cap. This makes sustained persecution progressively counterproductive — the cost of persecution. A Militant civ must weigh: "persecution clears minorities from this region but strengthens their faith through martyrdom."

| Constant | Default | Notes |
|----------|---------|-------|
| `MARTYRDOM_BOOST_PER_EVENT` | 0.05 | Per turn with persecution deaths |
| `MARTYRDOM_BOOST_CAP` | 0.20 | Max regional boost |
| `MARTYRDOM_DECAY_TURNS` | 10 | Linear decay duration |

All `[CALIBRATE]` for M47. Numbers mirror M37's conquest boost lifecycle for consistency.

### Persecution Named Events

| Event | Importance | Trigger |
|-------|-----------|---------|
| "Persecution of [faith] in [region]" | 6 | First turn persecution_intensity > 0 in a region |
| "Mass Migration from [region]" | 6 | persecuted_ratio > MASS_MIGRATION_THRESHOLD |

---

## Subsystem 2: Schisms

### Schism Detection

Per-turn check in Phase 10. At most one schism per civ per turn — if multiple regions qualify, pick the one with the highest minority ratio.

```python
# Phase 10 schism check per civ:
if len(belief_registry) >= MAX_FAITHS:
    return  # Registry full, no schisms

best_region = None
best_minority_ratio = 0.0

for region in civ.regions:
    # faith_counts: dict[int, int] computed from agent snapshot
    # (same snapshot scan as persecution minority_count and
    # compute_majority_belief — consolidate into one pass)
    faith_counts = count_beliefs_in_region(snapshot, region)
    for faith_id, count in faith_counts.items():
        if faith_id == civ.civ_majority_faith:
            continue
        ratio = count / region.population
        if ratio > SCHISM_MINORITY_THRESHOLD and ratio > best_minority_ratio:
            best_region = region
            best_minority_ratio = ratio
            schism_faith_id = faith_id

if best_region is not None:
    fire_schism(best_region, schism_faith_id)
```

### Trigger→Axis Mapping

Checked top-to-bottom, first match wins. Deterministic: same trigger always produces the same doctrinal change. Flips to opposite pole (not neutral) — schisms produce extremes.

| Priority | Trigger Condition | Axis Flipped | Narrative Frame |
|----------|-------------------|-------------|-----------------|
| 1 | Active persecution in the schism region (`persecution_intensity > 0`) | Stance (Militant↔Pacifist) | "The oppressed rejected the sword" / "The persecuted took up arms" |
| 2 | Clergy faction dominance (`clergy_influence > 0.40`) | Structure (Hierarchical↔Egalitarian) | "The faithful rebelled against the priesthood" / "The flock demanded order" |
| 3 | Trade-dependent region (`food_imported_ratio > 0.60`) | Ethics (Ascetic↔Prosperity) | Inert until M43; fallback handles |
| 4 | Region changed hands within last 10 turns (`current_turn - region.last_conquered_turn < 10`; requires `last_conquered_turn: int` on Region, set by WAR resolution in Phase 5 — if field does not exist, implementation plan must add it) | Outreach (Insular↔Proselytizing) | "The conquered closed their doors" / "The conquered sought converts" |
| 5 | **Fallback** (no trigger matches) | Axis with lowest absolute value | Organic drift — "theological dispute" |

**The trade-dependent trigger (row 3) requires M43.** Until M43 ships, that row is inert — the trigger condition never evaluates true because trade dependency detection doesn't exist. The fallback handles the case gracefully.

### Faith Splitting

```python
def fire_schism(region, original_faith_id):
    original = belief_registry[original_faith_id]

    # Copy doctrine, flip one axis based on trigger
    new_doctrine = original.doctrine.copy()
    axis, direction = determine_schism_axis(region, original)
    new_doctrine[axis] = -new_doctrine[axis]  # Opposite pole

    # Register new faith
    splinter = Belief(
        name=generate_schism_name(original.name),
        doctrine=new_doctrine,
    )
    splinter_id = belief_registry.append(splinter)

    # Convert all agents of original faith in region (cross-civ)
    for agent in region.agents:
        if agent.belief == original_faith_id:
            agent.belief = splinter_id

    emit_named_event("Schism", importance=7, details={
        "original_faith": original.name,
        "splinter_faith": splinter.name,
        "region": region.name,
        "axis_flipped": axis,
    })
```

### Secession Risk Modifier

When a region's majority faith differs from its civ's majority faith (which a schism can cause), add +10 to secession risk check. This connects to the existing secession mechanics — the spec does not define new secession logic, only the modifier.

### Reformation Detection

Reformation fires when the splinter faith exceeds `REFORMATION_THRESHOLD` (60%) of the civ's agents — not merely a plurality. This prevents minor faith shuffles from triggering civilization-defining events. `compute_civ_majority_faith()` from M37 returns the most common belief and its ratio; the reformation check adds the threshold gate.

```python
# Per-turn check after conversion processing:
majority_faith, majority_ratio = compute_civ_majority_faith(civ)
if (majority_faith != civ.previous_majority_faith
        and majority_ratio >= REFORMATION_THRESHOLD):
    emit_named_event("Reformation", importance=8, details={
        "civ": civ.name,
        "old_faith": belief_registry[civ.previous_majority_faith].name,
        "new_faith": belief_registry[majority_faith].name,
    })
    civ.previous_majority_faith = majority_faith
```

One new field: `civ.previous_majority_faith` to detect the transition. The threshold ensures reformation is a decisive shift, not demographic noise.

### Self-Similarity

Splinter faiths can themselves schism if they hit >30% minority in a region. No faith-level cooldown. The one-per-civ-per-turn limit prevents cascade-in-one-turn. Reformations beget counter-reformations — historically accurate.

### Belief Registry Capacity

M37's belief registry has `MAX_FAITHS = 16`. With 4-6 starting civs, 10-12 slots remain for schisms. At 1-3 schisms per 500-turn run per faith, the cap is unlikely to bind. If it does, schisms stop firing — the religious landscape has fractured as much as the data model allows. M47 can raise `MAX_FAITHS` if needed (hard ceiling is 255 at `u8` belief index).

### Schism Named Events

| Event | Importance | Trigger |
|-------|-----------|---------|
| "Schism of [faith] in [region]" | 7 | Schism fires |
| "Reformation of [civ]" | 8 | `civ_majority_faith` changes |

---

## Subsystem 3: Pilgrimages

### Candidate Selection

Per-turn check in Phase 10 for eligible named characters. Guards prevent overfire:

```python
# Max one departure per faith per turn
faiths_departed_this_turn = set()

for gp in great_persons:
    if gp.pilgrimage_destination is not None:
        continue  # Already on pilgrimage
    if gp.arc_type == "Prophet":
        continue  # Already completed a pilgrimage
    if gp.agent.belief in faiths_departed_this_turn:
        continue  # One departure per faith per turn

    agent = gp.agent
    is_priest = agent.occupation == OCC_PRIEST
    is_loyal = agent.personality.loyal > 0.5

    if not (is_priest or is_loyal):
        continue
    if agent.loyalty <= 0.5:
        continue

    # Find highest-prestige temple of their faith
    destination = max(
        (t for t in temples if t.faith_id == agent.belief),
        key=lambda t: t.temple_prestige,
        default=None,
    )
    if destination is None:
        continue  # No temple of their faith exists

    begin_pilgrimage(gp, destination)
    faiths_departed_this_turn.add(agent.belief)
```

### Pilgrimage Lifecycle

```python
def begin_pilgrimage(gp, destination):
    gp.pilgrimage_destination = destination.region.name
    gp.pilgrimage_return_turn = current_turn + randint(5, 10)
    emit_named_event("Pilgrimage Departure", importance=4, details={
        "character": gp.name,
        "destination": destination.region.name,
        "faith": belief_registry[gp.agent.belief].name,
    })

def check_pilgrimage_returns(current_turn):
    for gp in great_persons:
        if gp.pilgrimage_destination is None:
            continue
        if current_turn < gp.pilgrimage_return_turn:
            continue

        # Return effects
        gp.agent.skill += 0.10  # Occupation skill boost
        gp.arc_type = "Prophet"
        gp.life_events |= LIFE_EVENT_PILGRIMAGE  # Bit 7
        gp.pilgrimage_destination = None
        gp.pilgrimage_return_turn = None

        emit_named_event("Pilgrimage Return", importance=5, details={
            "character": gp.name,
            "title": "Prophet",
            "faith": belief_registry[gp.agent.belief].name,
        })
```

### Data Model (Python-side GreatPerson)

Two new fields:

```python
pilgrimage_destination: str | None = None   # Region name
pilgrimage_return_turn: int | None = None   # Turn to fire return event
```

### Prophet Promotion Bypass

A regular priest who isn't yet a GreatPerson can be promoted through pilgrimage, bypassing the normal skill-based promotion path. The candidate selection loop should include promotion-eligible priests (high loyalty, meet pilgrimage criteria) and promote them to GreatPerson as part of `begin_pilgrimage()`. Must verify promotion slot limit isn't exceeded before promoting.

### M37 Interaction

`NAMED_PROPHET_MULTIPLIER = 2.0` already doubles conversion rate for named priests in a region. A pilgrim-returned Prophet benefits from this automatically. No new multiplier needed.

### Pilgrimage Named Events

| Event | Importance | Trigger |
|-------|-----------|---------|
| "Pilgrimage of [character] to [destination]" | 4 | Pilgrimage begins |
| "Return of Prophet [character]" | 5 | Pilgrimage return |

---

## Testing Strategy

### Tier 1: Per-Subsystem (Independent)

**Persecution:**
- Militant-only gate: verify Neutral and Pacifist faiths produce `persecution_intensity = 0`
- Intensity scaling: verify formula at known minority ratios (10%, 30%, 50%)
- Region batch delivery: verify `persecution_intensity` column is read by satisfaction.rs and tick.rs
- Martyrdom boost lifecycle: set → decay → cap → reset, mirroring conquest boost tests
- Mass migration threshold: verify percentage-based trigger at varying region populations
- Identity stacking: verify cultural + religious + persecution penalties hit Decision 10 cap (-0.40) and don't exceed it

**Schisms:**
- Trigger detection: verify >30% minority fires, ≤30% doesn't
- Axis mapping: test all 5 trigger conditions + fallback, verify correct axis flips
- Local agent assignment: verify all faith-matching agents in region convert (cross-civ)
- One-per-civ-per-turn: verify highest minority ratio wins when multiple regions qualify
- Registry cap guard: verify no schism fires when `len(belief_registry) >= MAX_FAITHS`
- Reformation detection: verify event fires when `civ_majority_faith` changes
- Secession modifier: verify +10 applied when region faith ≠ civ faith

**Pilgrimages:**
- Candidate selection: verify loyalty threshold, occupation filter, one-per-faith-per-turn limit
- Already-on-pilgrimage guard: verify no re-triggering
- Already-a-Prophet guard: verify no repeat pilgrimages
- Destination selection: verify highest-prestige temple of correct faith
- Lifecycle timing: verify return fires at correct turn
- Prophet assignment: verify `arc_type = "Prophet"` and `LIFE_EVENT_PILGRIMAGE` bit set on return
- Promotion bypass: verify non-GreatPerson priest can be promoted through pilgrimage

### Tier 2: Interaction (Regression Harness)

- **Persecution → martyrdom → conversion:** Verify persecution deaths produce martyrdom boost that increases conversion rate in `compute_conversion_signals()`
- **Schism → persecution cascade:** Verify schism in Militant civ creates new minority → persecution fires → migration utility spikes
- **Full cascade:** Schism in Militant civ → persecution → martyrdom → splinter faith spreads via M37 conversion → reformation threshold check
- **Pilgrimage frequency:** Verify 1-3 pilgrimages per 500-turn run per faith `[CALIBRATE]`

---

## Forward Dependencies

| Item | Depends On | Notes |
|------|-----------|-------|
| Trade-dependent schism trigger (Ethics axis) | M43 | Row 3 in trigger table is inert until M43; fallback handles |
| Doctrine-axis modifiers on persecution intensity | M47 | Stance-only for M38b. Other axes (Hierarchical enforcement, Insular targeting) are M47 tuning candidates |
| Physical pilgrimage movement | Phase 7 | Narrative-only for M38b; Phase 7 spatial agent system enables physical movement |
| Prophet arc-aware narration | M45 | `arc_type = "Prophet"` tag set in M38b; M45 wires narration |
| All `[CALIBRATE]` constants | M47 | Martyrdom boost, mass migration threshold, pilgrimage frequency |

---

## Constants Summary

| Constant | Default | Subsystem | Notes |
|----------|---------|-----------|-------|
| `MARTYRDOM_BOOST_PER_EVENT` | 0.05 | Persecution | `[CALIBRATE]` |
| `MARTYRDOM_BOOST_CAP` | 0.20 | Persecution | `[CALIBRATE]` |
| `MARTYRDOM_DECAY_TURNS` | 10 | Persecution | `[CALIBRATE]` |
| `MASS_MIGRATION_THRESHOLD` | 0.15 | Persecution | Ratio, not count. `[CALIBRATE]` |
| `PERSECUTION_SAT_PENALTY` | -0.15 | Persecution | Decision 10 budget allocation |
| `PERSECUTION_REBEL_BOOST` | +0.30 | Persecution | `[CALIBRATE]` |
| `PERSECUTION_MIGRATE_BOOST` | +0.20 | Persecution | `[CALIBRATE]` |
| `SCHISM_MINORITY_THRESHOLD` | 0.30 | Schisms | `[CALIBRATE]` |
| `SCHISM_SECESSION_MODIFIER` | +10 | Schisms | `[CALIBRATE]` |
| `REFORMATION_THRESHOLD` | 0.60 | Schisms | Fraction of civ agents. `[CALIBRATE]` |
| `PILGRIMAGE_DURATION_MIN` | 5 | Pilgrimages | Turns |
| `PILGRIMAGE_DURATION_MAX` | 10 | Pilgrimages | Turns |
| `PILGRIMAGE_SKILL_BOOST` | +0.10 | Pilgrimages | On return |

---

## Roadmap Divergences

| Roadmap Says | Spec Does | Why |
|-------------|-----------|-----|
| `Militant_doctrine × (1 - minority_ratio)` | `1.0 × (1 - minority_ratio)` when Stance == +1, else 0.0 | Stance is discrete (-1/0/+1), not continuous. The ternary axis is the gate. |
| >20 agents persecuted → mass migration | `persecuted_count / population > 0.15` | Fixed threshold is population-insensitive. Percentage-based scales to region size. |
| Migration event with special flag (pilgrimage) | Narrative-only, no physical movement | No Python→Rust path for moving individual agents. FFI cost not justified for 5-15 events per run. |
| +0.15 satisfaction during pilgrimage | Dropped | Can't deliver individual agent satisfaction from Python without per-agent FFI. Return effects are the mechanical package. |
| 3-4 days estimate | 5-7 days | Three subsystems with interaction testing. Persecution 1-2, schisms 2-3, pilgrimages 1-2. |
