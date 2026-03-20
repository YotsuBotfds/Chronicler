# M47d: War Frequency Calibration — Design Spec

> **Status:** Approved
> **Date:** 2026-03-19
> **Problem:** 204–508 wars per 500-turn run (target: 5–40). Population collapses to 1–5 agents by T500.
> **Root cause:** Action engine war selection frequency, not satisfaction. Binary stability damper is a cliff, not a ramp. No per-civ war fatigue. Multiplicative war boosters hit 2.5x cap regularly.

---

## Four Mechanisms

### Mechanism 1: Smooth WAR Damper

**Replace binary cliff with linear ramp.**

Current code (`_apply_situational`, action_engine.py):
```python
if civ.stability <= 20:
    weights[ActionType.DIPLOMACY] *= 3.0
    weights[ActionType.WAR] *= 0.1
```

New:
```python
# Smooth WAR damper — linear ramp from floor to 1.0
war_damper = max(min(civ.stability / K_WAR_DAMPER_THRESHOLD, 1.0), K_WAR_DAMPER_FLOOR)
weights[ActionType.WAR] *= war_damper

# Binary DIPLOMACY boost stays — qualitative regime change at low stability
if civ.stability <= 20:
    weights[ActionType.DIPLOMACY] *= 3.0
```

**Behavior:**
- Stability 30+: no penalty (multiplier = 1.0)
- Stability 15: WAR weight halved (0.5x)
- Stability 5: WAR weight at 0.17x
- Stability 0: WAR weight at floor (0.05x), not zero — desperate empires with armies can still declare war

**Placement:** Inside `_apply_situational`, BEFORE multiplicative boosters. The damper represents material capacity to wage war; the boosters (rival, grudge, martial tradition, etc.) represent motivation. Capacity constrains, motivation amplifies.

**DIPLOMACY asymmetry (intentional):** The DIPLOMACY *= 3.0 boost stays as a binary cliff at stability <= 20. This represents a qualitative regime change — "this civ is on the edge of collapse and desperately seeks peace." The WAR damper is a gradient because it represents material capacity, which degrades linearly with stability. The asymmetry is by design.

**Interaction with no-hostile guard:** The existing `if not has_hostile: WAR *= 0.1` at line 886–887 is a separate mechanism that stacks multiplicatively. At stability 15 with no hostile neighbors: `0.5 * 0.1 = 0.05`. This is weaker suppression than the old `0.1 * 0.1 = 0.01` but the no-hostile case is already rare — civs without hostile neighbors don't select WAR anyway.

**Insufficient alone:** Phoebe confirms the damper alone won't hit the 5–40 war target. The multiplicative booster stack (rival × grudge × martial × tech × faction) can push a damped WAR weight back above other actions. Mechanisms 2 and 3 are necessary complements.

---

### Mechanism 2: War-Weariness Accumulator

**Per-civ exponential decay accumulator tracking war fatigue.**

New field on `Civilization`: `war_weariness: float = 0.0`

#### Update Logic

Fires once per turn after `phase_action()` returns, before Phase 9. Same tick for all civs.

```
For each living civ (len(regions) > 0):
    # Determine if civ chose WAR this turn via action_history
    chose_war = (world.action_history.get(civ.name, []) or [None])[-1] == ActionType.WAR.value

    if chose_war:
        weariness = weariness * K_WAR_WEARINESS_DECAY + K_WAR_WEARINESS_INCREMENT
    else:
        weariness *= K_WAR_WEARINESS_DECAY

    # Passive weariness from active wars (attacker or defender)
    for war in world.active_wars:
        if civ.name in war:
            weariness += K_WAR_PASSIVE_WEARINESS
```

**Detection mechanism:** "Civ chose WAR this turn" is determined via `world.action_history[civ.name][-1]`, which is populated by `phase_action()` at simulation.py before the weariness tick runs.

**Double-counting on declaration turn (intentional):** A civ that declares war gets INCREMENT (1.0) + PASSIVE (0.15) = 1.15 on the first turn. The new war IS in `active_wars` by the time the tick runs (appended during action resolution). Combined first-turn penalty is `1/(1 + 1.15/3) = 0.72x` — mild enough to not suppress counter-attacks.

#### Effect on Action Weights

In `compute_weights`, AFTER multiplicative boosters, BEFORE 2.5x cap:

```python
war_weariness_penalty = 1.0 / (1.0 + civ.war_weariness / K_WAR_WEARINESS_DIVISOR)
weights[ActionType.WAR] *= war_weariness_penalty
```

**Placement rationale:** After boosters means weariness acts as a counterweight to the entire booster stack. A war-weary civ cannot be "motivated out of" its fatigue by grudges or traditions. Before the 2.5x cap means weariness reduces WAR's contribution to the max-weight calculation, giving other actions more room.

#### Steady-State Analysis

| Scenario | Weariness | WAR Multiplier |
|---|---|---|
| Chronic warmonger (WAR every turn, 1 active war) | ~23.0 | 0.12x |
| Chronic warmonger (WAR every turn, 2 fronts) | ~26.0 | 0.10x |
| Chronic warmonger (WAR every turn, 3 fronts) | ~29.0 | 0.09x |
| One war, then stop — after 14 turns | ~0.5 | 0.86x |
| One war, then stop — after 46 turns | ~0.1 | 0.97x |
| Defender in 1 active war (never chose WAR) | ~3.0 | 0.50x |
| Defender in 2 active wars | ~6.0 | 0.33x |

**Defender penalty (accepted):** Defenders accumulate passive weariness at K_PASSIVE_WEARINESS=0.15 per war per turn. This is intentional — populations tire of war regardless of who started it. The rate is low enough (0.15 vs 1.0 for attackers) that defenders can still counter-attack. The compound effect with the stability damper is aggressive for multi-front defenders, which models the realistic collapse of states under sustained multi-front pressure. K_PASSIVE_WEARINESS is [CALIBRATE]-tagged for adjustment.

#### Guards

- **Dead civ guard:** `if len(civ.regions) == 0: continue` in the update tick.
- **Extinction reset:** Set `war_weariness = 0.0` when a civ's last region is lost (including vassalization/absorption). Prevents restored civs from inheriting stale fatigue.

---

### Mechanism 3: Peace Dividend

**Per-civ accumulator boosting DEVELOP/TRADE weights during peaceful periods.**

New field on `Civilization`: `peace_momentum: float = 0.0`

#### Update Logic

Same tick as weariness (after `phase_action()`, before Phase 9).

```
For each living civ (len(regions) > 0):
    is_aggressor = (civ chose WAR this turn) or
                   any(w[0] == civ.name for w in world.active_wars)
    is_defender = any(w[1] == civ.name for w in world.active_wars) and not is_aggressor
    is_at_peace = not is_aggressor and not is_defender

    if is_at_peace:
        peace_momentum = min(peace_momentum + K_PEACE_MOMENTUM_BONUS, K_PEACE_MOMENTUM_CAP)
    elif is_aggressor:
        peace_momentum *= K_PEACE_MOMENTUM_WAR_DECAY
    elif is_defender:
        peace_momentum *= K_PEACE_MOMENTUM_DEFENDER_DECAY
```

**Aggressor semantics (explicit):** A civ is an aggressor if it chose WAR this turn OR if it is `w[0]` (the original attacker) in any active war. This means the aggressor penalty persists until peace is made — creating an incentive to pursue diplomacy to end wars you started. A civ that started a war 50 turns ago and has been trying to make peace is still treated as aggressor. This is by design.

**Per-turn aggressor decay (intentional design choice):** The 0.3x decay applies every turn the civ is classified as aggressor. After 5 turns: `momentum * 0.3^5 ≈ 0`. This means aggressors lose ALL peace dividend within 5 turns of declaring war and it stays at zero for the war's duration (potentially hundreds of turns). This is intentional — the peace dividend rewards *being peaceful*, and a civ at war should not receive DEVELOP/TRADE boosts regardless of how long the war drags on. The incentive structure is: (1) don't start wars, (2) end wars quickly via DIPLOMACY. **Overcorrection risk:** If the 200-seed validation shows war frequency drops below 5 (the target floor), K_PEACE_MOMENTUM_WAR_DECAY is the primary knob to adjust — either raise toward 1.0 (slower decay) or switch to one-shot application (apply once on war declaration instead of per-turn).

**Momentum cap:** Capped at K_PEACE_MOMENTUM_CAP (20.0) to prevent weight degeneracy. Without the cap, 100 peaceful turns would give DEVELOP an 11x bonus, consuming the entire weight budget via the 2.5x cap and suppressing all other actions.

**Decay on war, not hard-reset:** Aggressor decay (0.3x per turn) and defender decay (0.8x per turn) avoid a hard-reset cliff. A civ with momentum 20 that gets attacked: `20 * 0.8 = 16` on the first turn — reduced but not erased, recovers once peace is made. Aggressors lose momentum rapidly (20 → 6 → 1.8 → 0.5 over 3 turns) — this is severe by design.

#### Effect on Action Weights

In `compute_weights`, same placement as weariness (after boosters, before cap):

```python
develop_bonus = 1.0 + civ.peace_momentum / K_PEACE_DEVELOP_DIVISOR
trade_bonus = 1.0 + civ.peace_momentum / K_PEACE_TRADE_DIVISOR
weights[ActionType.DEVELOP] *= develop_bonus
weights[ActionType.TRADE] *= trade_bonus
```

**INVEST_CULTURE and BUILD excluded:** INVEST_CULTURE already has a 2.0x situational boost in `_apply_situational`. Adding a peace dividend would make it dominant for peaceful civs. BUILD has no existing boost but keeping the dividend focused on the two core economic actions maintains calibration simplicity.

**Ordering with weariness:** Both touch different weights (weariness → WAR, peace → DEVELOP/TRADE). Order between them does not matter. Both fire in the same block for clarity.

#### Interaction with `apply_long_peace()`

Complementary, not redundant. Global `peace_turns` (30-turn threshold) handles world-level effects: military restlessness, economic redistribution, allied disposition decay. Per-civ `peace_momentum` handles individual action preferences. They operate at different scales.

**Long peace interaction:** When M47d succeeds and war frequency drops, `apply_long_peace` will start firing (requires 30 turns of zero active wars worldwide). The alliance decay downgrades ALLIED → FRIENDLY (not to HOSTILE), so it does not directly create WAR-eligible targets. Hostile neighbors would need to emerge from natural disposition drift or other mechanisms. Worth monitoring but not blocking.

#### Guards

Same as weariness: dead civ guard, extinction reset (including vassalization/absorption).

---

### Mechanism 4: Secession Threshold

**Deferred calibration pass.**

M47c lowered secession threshold from 20 → 10 because hybrid stability was 15–30 and the old threshold fired constantly. Once mechanisms 1–3 reduce war frequency and stability floats higher, secession at threshold 10 may become too rare.

**Approach:** Keep threshold at 10 for initial implementation. After 200-seed validation with mechanisms 1–3, check secession frequency. If < 1 per 500-turn run average, bump `K_SECESSION_LIKELIHOOD` threshold. Single constant in `tuning.py`, no design work needed.

---

## Constants

All [CALIBRATE]-tagged, extracted to `tuning.py`, added to `KNOWN_OVERRIDES`.

| Constant | Key | Default | Purpose |
|---|---|---|---|
| `K_WAR_DAMPER_THRESHOLD` | `action.war_damper_threshold` | 30.0 | Stability below which WAR weight is linearly dampened |
| `K_WAR_DAMPER_FLOOR` | `action.war_damper_floor` | 0.05 | Minimum WAR damper multiplier (prevents zero) |
| `K_WAR_WEARINESS_DECAY` | `action.war_weariness_decay` | 0.95 | Per-turn multiplicative weariness decay |
| `K_WAR_WEARINESS_INCREMENT` | `action.war_weariness_increment` | 1.0 | Weariness added when civ selects WAR |
| `K_WAR_PASSIVE_WEARINESS` | `action.war_passive_weariness` | 0.15 | Weariness per active war participation per turn |
| `K_WAR_WEARINESS_DIVISOR` | `action.war_weariness_divisor` | 3.0 | Denominator scaling in `1/(1 + w/K)` penalty |
| `K_PEACE_MOMENTUM_BONUS` | `action.peace_momentum_bonus` | 1.0 | Per peaceful turn increment |
| `K_PEACE_MOMENTUM_CAP` | `action.peace_momentum_cap` | 20.0 | Maximum peace_momentum value |
| `K_PEACE_MOMENTUM_WAR_DECAY` | `action.peace_momentum_war_decay` | 0.3 | Aggressor peace momentum decay factor |
| `K_PEACE_MOMENTUM_DEFENDER_DECAY` | `action.peace_momentum_defender_decay` | 0.8 | Defender peace momentum decay factor |
| `K_PEACE_DEVELOP_DIVISOR` | `action.peace_develop_divisor` | 10.0 | Maps momentum to DEVELOP weight bonus |
| `K_PEACE_TRADE_DIVISOR` | `action.peace_trade_divisor` | 10.0 | Maps momentum to TRADE weight bonus |

---

## Model Changes

### Civilization (models.py)

```python
war_weariness: float = 0.0
peace_momentum: float = 0.0
```

### CivSnapshot (models.py)

Add both fields for analytics visibility:
```python
war_weariness: float = 0.0
peace_momentum: float = 0.0
```

Wire into CivSnapshot constructor in `main.py`.

---

## Execution Order

Full action weight chain after M47d:

```
1. Base weights (0.2 per eligible action)
2. Trait profile multiplier (TRAIT_WEIGHTS)
3. _apply_situational:
   a. Smooth WAR damper: WAR *= max(min(stability / K_THRESHOLD, 1.0), K_FLOOR)  [NEW]
   b. DIPLOMACY *= 3.0 if stability <= 20  [EXISTING, unchanged]
   c. Military advantage: WAR *= 2.5 if military >= 70 && has_hostile  [EXISTING]
   d. Treasury/economy/population modifiers  [EXISTING]
   e. No-hostile guard: WAR *= 0.1  [EXISTING]
4. Rival boost (K_RIVAL_WAR_BOOST)
5. Grudge intensity multipliers
6. Martial tradition (1.2x)
7. Tech focus modifiers
8. Faction weight modifier
9. Holy war additive bonus
10. Raider additive bonus
11. Aggression bias (K_AGGRESSION_BIAS)
12. War-weariness penalty: WAR *= 1/(1 + weariness/K_DIVISOR)  [NEW]
13. Peace dividend: DEVELOP *= 1 + momentum/K; TRADE *= 1 + momentum/K  [NEW]
14. Streak-breaker (3–5 consecutive same action → 0.0)
15. 2.5x weight cap (proportional scaling)
```

---

## Files to Modify

| File | Changes |
|---|---|
| `src/chronicler/models.py` | `war_weariness`, `peace_momentum` on Civilization + CivSnapshot |
| `src/chronicler/action_engine.py` | Smooth damper in `_apply_situational`; weariness + peace effects in `compute_weights` |
| `src/chronicler/simulation.py` | Weariness/momentum update tick after `phase_action()`, extinction resets |
| `src/chronicler/tuning.py` | 12 new K_ constants + KNOWN_OVERRIDES entries |
| `src/chronicler/main.py` | Wire new fields into CivSnapshot constructor |
| `src/chronicler/world_gen.py` | Verify defaults are 0.0 (Field defaults should handle this) |

---

## Determinism

No new RNG sources. Both accumulators are purely arithmetic (decay, increment, clamp). No new RNG stream offsets needed. `--agents=off` output will change (action weights change in both modes) — this is expected and the 200-seed regression will capture the shift.

---

## Bundle Compatibility

Two new fields on CivSnapshot with defaults (0.0). Older bundles deserialize fine. No bundle version bump needed. No downstream consumer (viewer, analytics) breakage.

---

## Validation Plan

1. **Unit tests:** Verify each mechanism in isolation (damper ramp, weariness accumulation/decay, peace momentum accumulation/decay/cap, aggressor/defender distinction).
2. **Integration test:** 50-turn run verifying weariness and momentum update correctly, dead civ guards work, extinction resets fire.
3. **20-seed smoke test:** All 7 presets, 5 seeds each. Check war counts, stability trajectories, population survival.
4. **200-seed regression:** Compare war frequency distributions before/after. Target: 5–40 wars per 500-turn run. Check that secession frequency is still reasonable.
5. **Edge cases:** All-peaceful world (verify `apply_long_peace` interaction), single warmonger civ, two war-weary civs fighting.
