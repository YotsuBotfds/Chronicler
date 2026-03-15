# M24: Information Asymmetry — Design Spec

**Date:** 2026-03-15
**Status:** Draft
**Prerequisites:** M22 (Factions & Succession) landed
**Estimated size:** ~150 lines production, ~120 lines tests

## Overview

Add a perception layer between civilizations: when one civ evaluates another's stats for decision-making, it reads a *perceived* value distorted by Gaussian noise scaled to intelligence accuracy. Accuracy is recomputed from existing relationships each turn — no new state to persist. The system creates mistaken wars, hidden declines, trade naivety, and deterrence from perception, all from ~150 lines of code touching 6 callsites.

M24 does not add espionage actions, accuracy decay, or perception-affected combat outcomes. It is a passive computation derived entirely from existing world state.

### Design Principles

1. **Stateless accuracy.** Recomputed from scratch each turn. No per-pair persistence, no decay tracking, no stale caches.
2. **Decisions, not outcomes.** Perceived stats affect the decision to act (attack, rebel, trade). Outcomes use actual stats. You attack because you *think* they're weak; you fight their *actual* army.
3. **None means unknown.** Zero accuracy = the observer has never encountered the target. `get_perceived_stat` returns `None`, and callsites skip that target entirely. No random noise for civilizations you don't know exist.

## Data Model

### No New Model on Civilization

The design sketch proposed `IntelligenceState` with `known_civs: dict[str, float]`. Since accuracy is recomputed from state each turn (no persistence), this model is unnecessary. `compute_accuracy()` derives everything from existing relationships, factions, great persons, and grudges. Zero new fields on `Civilization`, zero migration concern.

### TurnSnapshot Extension (models.py)

Two new fields for M19 analytics visibility:

```python
per_pair_accuracy: dict[str, dict[str, float]] = Field(default_factory=dict)
# observer_name → target_name → accuracy (0.0–1.0)
# Only pairs where accuracy > 0.0 (known civs)

perception_errors: dict[str, dict[str, dict[str, int]]] = Field(default_factory=dict)
# observer_name → target_name → stat_name → signed error
# Sign convention: perceived - actual
#   positive = observer overestimates target
#   negative = observer underestimates target
# Stats captured: military, economy, stability
# Only pairs where accuracy > 0.0
```

**Size:** For 8 civs, worst case 56 pairs × 3 stats = 168 error entries + 56 accuracy entries per turn. Negligible in snapshot JSON.

**Analytics use cases:**
- "How often does information asymmetry lead to mistaken wars?" — check if `perception_errors[attacker][defender]["military"]` was > 10 on the turn WAR was selected.
- "Do merchant-dominant civs systematically underestimate military threats?" — filter by faction, check sign distribution on military errors.

## Core Logic — `intelligence.py`

New module. Two public functions, one event helper.

### `compute_accuracy(observer, target, world) → float`

Recomputed from state each turn. Sources stack additively, capped at 1.0.

```python
def compute_accuracy(observer: Civilization, target: Civilization, world: WorldState) -> float:
    if observer.name == target.name:
        return 1.0  # perfect self-knowledge

    accuracy = 0.0  # start at zero, add sources

    # Geographic proximity
    if shares_adjacent_region(observer, target, world):
        accuracy += 0.3

    # Trade relationship
    if has_active_trade_route(observer, target, world):
        accuracy += 0.2

    # Federation membership
    if in_same_federation(observer, target, world):
        accuracy += 0.4

    # Vassal/overlord relationship
    if is_vassal_of(observer, target, world) or is_vassal_of(target, observer, world):
        accuracy += 0.5

    # At war (direct or proxy)
    if at_war(observer, target, world):
        accuracy += 0.3

    # M22 faction bonus
    dominant = get_dominant_faction(observer.factions)
    if dominant == FactionType.MERCHANT:
        accuracy += 0.1   # trade networks = intel networks
    elif dominant == FactionType.CULTURAL:
        accuracy += 0.05  # cultural exchange

    # M17 great person bonuses
    for gp in observer.great_persons:
        if gp.alive and gp.active:
            if gp.role == "merchant":
                accuracy += 0.05  # personal trade connections
            if gp.is_hostage and gp.civilization == target.name:
                accuracy += 0.3   # hostage reports home

    # M17 grudge bonus
    for g in observer.leader.grudges:
        if g["rival_civ"] == target.name and g["intensity"] > 0.3:
            accuracy += 0.1  # you study your enemies

    return min(1.0, accuracy)
```

### Accuracy Ranges by Relationship

| Relationship | Typical Accuracy | Noise Range (±) |
|---|---|---|
| No contact (fog of war) | 0.0 | N/A (None) |
| Adjacent regions only | 0.3 | ±14 |
| Adjacent + trade | 0.5 | ±10 |
| Federation member | 0.7+ | ±6 |
| Vassal/overlord | 0.8+ | ±4 |
| Adjacent + war + grudge | 0.7 | ±6 |
| Max (all sources stacked) | 1.0 | ±0 |

### `get_perceived_stat(observer, target, stat, world) → int | None`

Returns `None` when accuracy is 0.0 (unknown civ). Otherwise returns actual stat + Gaussian noise.

```python
def get_perceived_stat(observer: Civilization, target: Civilization,
                       stat: str, world: WorldState) -> int | None:
    accuracy = compute_accuracy(observer, target, world)
    if accuracy == 0.0:
        return None  # target unknown to observer

    noise_range = int((1.0 - accuracy) * 20)
    if noise_range == 0:
        return getattr(target, stat)

    rng = random.Random(hash((world.seed, observer.name, target.name, world.turn, stat)))
    noise = int(rng.gauss(0, noise_range / 2))  # σ = half the range
    noise = max(-noise_range, min(noise_range, noise))  # clip to ±noise_range
    return max(0, min(100, getattr(target, stat) + noise))
```

**Determinism:** Same observer, same target, same turn, same stat = same perceived value. The seed ensures perceptions don't change mid-turn.

**Noise distribution:** Gaussian with σ = noise_range/2, clipped to ±noise_range. Most perceptions are close to truth with occasional large errors. More realistic than uniform (where +14 and +1 are equally likely at accuracy 0.3).

### `emit_intelligence_failure(attacker, defender, perceived_mil, actual_mil, world) → Event`

Called after war resolution when the attacker lost and `perceived_mil <= 0.7 * actual_mil`. Emits an event with:
- `event_type`: `"intelligence_failure"`
- `importance`: 7
- `details`: perception gap (perceived vs actual military), attacker name, defender name
- Curator scores these highly — "Vrashni attacked Kethani, believing them weaker than they were"

Only emitted on *reveal* (lost war with bad intel). Correct intelligence produces no event — that's just normal gameplay.

## Callsite Integration

Six integration points. Five existing callsites modified, one new callsite added.

### Callsite 1 (NEW): WAR Target Weight Bias — `action_engine.py`

In `compute_weights()` or `_apply_situational()`, when computing WAR weight for a potential target:

```python
perceived_mil = get_perceived_stat(observer, target, "military", world)
if perceived_mil is None:
    # Unknown civ — not a valid WAR target
    continue

ratio = observer.military / max(1, perceived_mil)
if ratio > 1.4:
    war_weight_multiplier = 1.4   # target looks weak → aggressive
elif ratio < 0.7:
    war_weight_multiplier = 0.6   # target looks strong → deterred
else:
    # Linear interpolation between 0.6 and 1.4
    war_weight_multiplier = 0.6 + (ratio - 0.7) / (1.4 - 0.7) * (1.4 - 0.6)
```

Per-target multiplier. Slots into existing weight computation without changing action resolution or targeting architecture.

### Callsite 2: Trade Resolution — `action_engine.py` (~line 438–439)

```python
# BEFORE:
gain1 = max(1, civ2.economy // 3)
gain2 = max(1, civ1.economy // 3)

# AFTER:
perceived_econ_2 = get_perceived_stat(civ1, civ2, "economy", world)
perceived_econ_1 = get_perceived_stat(civ2, civ1, "economy", world)
# NOTE: None should be unreachable here — trade requires an active route,
# which grants +0.2 accuracy. If this fires, compute_accuracy has a bug.
gain1 = max(1, (perceived_econ_2 if perceived_econ_2 is not None else civ2.economy) // 3)
gain2 = max(1, (perceived_econ_1 if perceived_econ_1 is not None else civ1.economy) // 3)
```

Trade gains based on what you *think* the partner's economy is. Decision 3 exception: trade uses perceived because you overestimate the deal's value (narratively interesting, mechanically simple).

### Callsite 3: Tribute Collection — `politics.py` (~line 374)

```python
# BEFORE:
tribute = math.floor(vassal.economy * vr.tribute_rate)

# AFTER:
perceived_econ = get_perceived_stat(overlord, vassal, "economy", world)
# NOTE: None should be unreachable — vassal/overlord grants +0.5 accuracy.
# If this fires, compute_accuracy has a bug.
tribute = math.floor((perceived_econ if perceived_econ is not None else vassal.economy) * vr.tribute_rate)
```

Overlord collects what they *think* the vassal produces. A vassal in decline can temporarily hide its weakness.

### Callsite 4: Vassal Rebellion — `politics.py` (~lines 395–396)

```python
# BEFORE:
overlord.stability >= 25
overlord.treasury >= 10

# AFTER:
perceived_stab = get_perceived_stat(vassal, overlord, "stability", world)
perceived_treas = get_perceived_stat(vassal, overlord, "treasury", world)
# NOTE: None should be unreachable — vassal/overlord grants +0.5 accuracy.
# If this fires, compute_accuracy has a bug.
(perceived_stab if perceived_stab is not None else overlord.stability) >= 25
(perceived_treas if perceived_treas is not None else overlord.treasury) >= 10
```

Vassal decides to rebel based on perceived overlord strength. A weak overlord that *appears* strong deters rebellion.

### Callsite 5: Congress Power Ranking — `politics.py` (~lines 685–697)

```python
# BEFORE:
power = (civ.military + civ.economy + fed_allies * 10) / max(longest_war, 1)

# AFTER (per-observer perception):
# Congress organizer = highest actual culture (unchanged, world fact)
organizer = max(participants, key=lambda c: c.culture)

# Organizer perceives each participant's power
# Only military and economy are wrapped — fed_allies and longest_war are world facts
for civ in participants:
    perceived_mil = get_perceived_stat(organizer, civ, "military", world)
    perceived_econ = get_perceived_stat(organizer, civ, "economy", world)
    # Self-perception is always accurate (compute_accuracy returns 1.0 for self)
    # None filtered: if organizer doesn't know a civ, they're excluded from ranking
    if perceived_mil is not None and perceived_econ is not None:
        power = (perceived_mil + perceived_econ + fed_allies * 10) / max(longest_war, 1)
```

Each civ would ideally perceive different power levels, but for simplicity the congress organizer's perceptions determine the power ranking. Self-accuracy is 1.0, so the organizer always perceives their own power correctly.

### Callsite 6: Intelligence Failure Event — `action_engine.py` (~line 336+)

After `resolve_war()` returns a loss for the attacker:

```python
perceived_mil = get_perceived_stat(attacker, defender, "military", world)
if perceived_mil is not None and perceived_mil <= 0.7 * defender.military:
    events.append(emit_intelligence_failure(
        attacker, defender, perceived_mil, defender.military, world
    ))
```

### Unchanged Callsites (Actual Stats)

| Location | Why actual |
|---|---|
| `resolve_war()` combat math | Outcomes use real stats (Decision 3) |
| Congress host selection (highest culture) | World fact, not observer decision |
| Mercenary hiring sort | Mercenaries are on the ground, know who's weakest |

## Viewer Display

### Accuracy Bar — Relationship Panel

On the relationship panel between two civs, display an **accuracy bar** (0–100%) showing the observer's intelligence accuracy toward the target. Sources listed as icons/badges below the bar (adjacency, trade, federation, war, faction, GP).

### Ghost Bars — Perceived vs Actual Stats

When hovering a target civ, stat bars show the **observer's perceived values**. If the viewer has high accuracy (≥0.8) on the target, overlay dimmed "ghost bars" showing actual stats behind the perceived bars — revealing the gap. Below 0.8 accuracy, the viewer sees only what the observer sees, preserving the fog-of-war feel.

This means the viewer experiences the same uncertainty as the civilization they're watching. The reveal is earned through relationship building, not UI chrome.

## Testing Strategy

### Unit Tests (`test_intelligence.py`)

1. **Self-accuracy:** `compute_accuracy(civ, civ, world)` returns 1.0.
2. **Zero contact:** Two civs with no relationship → accuracy 0.0, `get_perceived_stat` returns `None`.
3. **Source stacking:** Adjacent + trade → 0.5, add federation → 0.9, cap at 1.0.
4. **Determinism:** Same inputs → same perceived value across calls.
5. **Noise bounds:** At accuracy 0.3 (noise_range ±14), perceived value stays within [actual-14, actual+14], clamped to [0, 100].
6. **Faction bonus:** Merchant-dominant civ gets +0.1 accuracy.
7. **GP bonus:** Active merchant GP → +0.05. Hostage held by target → +0.3.
8. **Grudge bonus:** Grudge with intensity > 0.3 toward target → +0.1.
9. **Intelligence failure event:** Emitted when perceived_mil ≤ 0.7 × actual and attacker lost.
10. **No event on correct intel:** Attacker loses but intel was accurate → no event.

### Integration Tests

11. **Trade uses perceived economy:** Two civs with accuracy 0.5 — trade gain differs from actual economy // 3.
12. **Vassal rebellion uses perceived stability:** Overlord with actual stability 20 but perceived ≥ 25 → rebellion suppressed.
13. **Congress power ranking uses organizer perception:** Organizer with low accuracy toward a strong civ → that civ underranked.
14. **WAR weight bias:** Civ perceives neighbor as weak → WAR weight multiplied by 1.4.
15. **Snapshot captures accuracy and errors:** After a turn, `TurnSnapshot.per_pair_accuracy` and `perception_errors` populated correctly with signed errors (perceived - actual).

### M19 Validation

Run batch analytics before/after M24 lands. Check:
- Do perception errors produce enough variance to affect decisions?
- Does the WAR weight multiplier change war frequency meaningfully?
- Are intelligence_failure events firing at a reasonable rate (not 0%, not every war)?

## Scope Boundaries

**In scope:**
- `intelligence.py`: `compute_accuracy`, `get_perceived_stat`, `emit_intelligence_failure`
- 6 callsite integrations (5 existing + 1 new WAR weight)
- TurnSnapshot extension (2 fields)
- Viewer: accuracy bar + ghost bars on relationship panel

**Out of scope:**
- Espionage as an action type (passive computation only)
- Accuracy decay over time (recomputed from state)
- Perception-affected combat outcomes (decisions only)
- Per-turn accuracy persistence (stateless)
- New model fields on Civilization (none needed)

## File Changes

| File | Change | Lines (est.) |
|---|---|---|
| `intelligence.py` (NEW) | `compute_accuracy`, `get_perceived_stat`, `emit_intelligence_failure`, relationship helpers | ~80 |
| `action_engine.py` | WAR weight bias (new), trade perception, intelligence failure event | ~30 |
| `politics.py` | Tribute, rebellion, congress perception | ~25 |
| `simulation.py` | Snapshot population (per_pair_accuracy, perception_errors) | ~15 |
| `models.py` | TurnSnapshot fields | ~5 |
| **Total production** | | **~155** |
| `test_intelligence.py` (NEW) | Unit + integration tests | ~120 |
