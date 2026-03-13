# M14: Political Topology — Design Spec

**Date:** 2026-03-13
**Branch:** (to be created from main after M13 merge)
**Depends on:** M13b (treasury, trade routes, adjacency graph, active wars, resources)
**Scope:** Four sequential phases: M14a → M14b → M14c → M14d
**Note:** This spec supersedes the Phase 3 roadmap (`chronicler-phase3-roadmap.md`) for all M14 details. Where the roadmap and this spec disagree, this spec is authoritative.

## Overview

Power is expensive to hold and interesting to lose. M14 makes empires structurally unstable through governing costs, secession mechanics, subordination structures, indirect power projection, and systemic feedback loops that ensure no equilibrium lasts.

All mechanics are pure Python simulation — no LLM calls required. The narrative engine describes what happened; it doesn't decide what happens.

### Design Principles

- **Instability from arithmetic.** Governing costs, secession probability, vassal rebellion — all emerge from simple formulas interacting with existing stats. No scripted "empire collapses" events.
- **Political structures as emergent responses.** Vassals reduce governing cost. Federations counter dominant powers. Proxy wars exploit instability. Each structure exists because the mechanics create demand for it.
- **One module, clean interface.** All political mechanics live in `src/chronicler/politics.py`. Models in `models.py`. Integration via function calls from `simulation.py` phase hooks.

### Phase Summary

| Phase | Name | Deliverable |
|-------|------|-------------|
| M14a | Imperial Foundations | Governing cost, capital designation/movement, civil war/secession |
| M14b | Subordination & Alliance | Vassal states, federations |
| M14c | Indirect Power | Proxy wars, diplomatic congresses, governments in exile |
| M14d | Systemic Dynamics | Balance of power, fallen empires, civilizational twilight, the long peace problem |

---

## Phase M14a: Imperial Foundations

### Goal

Make large empires expensive to hold. Distance from capital creates pressure; secession is the release valve. These three systems — governing cost, capitals, secession — are tightly coupled and ship together.

### Model Changes

**`Civilization`:**
```python
capital_region: str | None = None  # set during world_gen; scenario can override
```

Defaults to `None`, set to the civ's first region during world generation. Scenario YAML can specify `capital: "Region Name"` on a civ override.

**`ScenarioConfig` (scenario.py):**
```python
secession_pool: list[CivOverride] = Field(default_factory=list)
```

Defined but unused in M14a. M14c/M14d will check it before falling back to auto-generation.

### New Module: `src/chronicler/politics.py`

All M14 political mechanics live here. Exports functions called by `simulation.py` from the appropriate turn phases.

### Governing Cost

Runs in `apply_automatic_effects` (phase 2) each turn via `politics.apply_governing_costs(world)`.

**Formula:**

```python
For each civ with region_count > 2:
    treasury_cost = (region_count - 2) * 2  # flat treasury drain

    stability_cost = 0
    for region in civ.regions (excluding capital):
        dist = graph_distance(capital_region, region)
        treasury_cost += dist * 2
        stability_cost += dist * 1

    civ.treasury -= treasury_cost
    civ.stability -= stability_cost
```

**Design notes:**
- No flat stability penalty per region count. Only distance-based stability drain. This prevents instant collapse of compact empires — a 6-region empire where all regions are adjacent to the capital pays only 5 stability/turn (5 regions × distance 1), creating pressure over 10-20 turns rather than 2.
- Treasury has both flat and distance components. Money drains are recoverable through trade; stability is what triggers secession, so it needs careful tuning.
- A compact 3-region empire with all regions adjacent to capital pays: treasury `(3-2)*2 + 1*2 = 4`, stability `1*1 = 1`. Manageable.
- A sprawling 6-region empire with max distance 4 from capital pays: treasury `(6-2)*2 + sum(distances)*2`, stability `sum(distances)`. Hemorrhaging unless rich.

### Capital Designation & Movement

**Capital loss** (checked via `politics.check_capital_loss(world)` in phase 10, consequences):
- If `capital_region` not in `civ.regions`:
  - `stability -= 20`
  - Trigger leader succession check (existing `leaders.py` mechanism)
  - Set `capital_region` to best remaining region: filter to `civ.regions` first, then pick region with highest `carrying_capacity * fertility`
- The filter to `civ.regions` is critical — if the civ lost multiple regions in the same turn, the "best" region must be one they still control.

**MOVE_CAPITAL action** (new deliberate action):

Added to `ActionType` enum. Registered via `@register_action(ActionType.MOVE_CAPITAL)`.

- **Eligibility:** `treasury >= 15`, `region_count >= 2`
- **Resolution:**
  - `treasury -= 15`
  - Apply `ActiveCondition("capital_relocation", [civ.name], duration=5, severity=10)` — drains stability by 10/turn for 5 turns via existing condition system
  - Set `capital_region` to target region: most central region by average graph distance to all other owned regions
- **Weight profile:** Low across all traits (desperation move, not routine). `cautious` and `visionary` get slight bias.

### Civil War / Secession

**Trigger check** (via `politics.check_secession(world)` in phase 10, consequences, after capital loss check and after the stability clamp):

- Guard: `stability < 20 AND region_count >= 3`
- Probability per turn: `(20 - stability) / 100`
  - At stability 0: 20% per turn
  - At stability 15: 5% per turn
  - Uses post-clamp stability value (if governing costs push stability to -5 but clamp brings it to 0, probability is based on 0)
- Seeded: `world.seed + turn + hash(civ.name)`

**Proxy war interaction:** If a `ProxyWar` (M14c) targets this civ's most-distant region, add `0.05` to the base probability.

**Breakaway spawn:**

1. Sort civ's regions by `graph_distance(capital_region, region)`, descending
2. Breakaway takes the most distant `ceil(region_count / 3)` regions (minimum 1)
3. New civ created with:
   - **Name:** Prefix pool `["Free", "Eastern", "Western", "Northern", "Southern", "New", "Upper", "Lower", "Greater"]` combined with parent name or breakaway's most prominent region name. Deterministic selection from `world.seed + turn + hash(parent.name)`.
   - **Stats:** Breakaway gets `floor(stat * breakaway_ratio)` for population, military, economy, treasury. Parent gets `stat - breakaway_amount`. No stats created or destroyed.
   - **Culture:** `culture = parent.culture` (cultural continuity)
   - **Stability:** `40` (fresh start energy)
   - **Tech era:** Inherits parent's tech era (they didn't forget how to smelt iron when they seceded)
   - **Trait:** Parent's trait with one random swap from the trait pool (rebellion often produces opposite temperament)
   - **Leader:** Generated from parent's `leader_name_pool` (cultural consistency). New leader with randomized trait.
   - **Domains/values:** Parent's domains with one random value swap (ideological divergence that motivated the split)
   - **Asabiya:** `0.7` (revolutionary vigor)
   - **Capital:** Set to the breakaway's first region (closest to parent border — the "new capital")
   - **Disposition:** HOSTILE toward parent. NEUTRAL toward everyone else.
4. Parent civ: loses those regions, stats reduced per formula above, `stability -= 10` additional shock
5. Named event: "The Secession of [Breakaway Name]" (importance 9)

### Integration Points

- `simulation.py` calls `politics.apply_governing_costs(world)` in phase 2 (automatic effects)
- `simulation.py` calls `politics.check_capital_loss(world)` in phase 10 (consequences)
- `simulation.py` calls `politics.check_secession(world)` in phase 10 (consequences), after capital loss and stability clamp
- `action_engine.py` registers `MOVE_CAPITAL` handler via `@register_action`
- `action_engine.py` `get_eligible_actions` adds MOVE_CAPITAL eligibility check
- `world_gen.py` sets `capital_region` during civ creation

### Verification

- Governing cost: 3-region compact empire pays less than 6-region sprawling empire
- Distance scaling: distant regions cost more stability than adjacent ones
- No flat stability cost per region — only distance-based
- Capital loss: triggers -20 stability, succession check, reassignment to best remaining region (filtered to civ.regions)
- MOVE_CAPITAL: costs 15 treasury, applies 5-turn relocation condition, picks most central region
- Secession: only fires when `stability < 20 AND regions >= 3`, uses post-clamp stability
- Breakaway civ: inherits tech, gets culturally consistent name, starts HOSTILE to parent
- Stat split: `floor(stat * ratio)` for breakaway, parent gets remainder — no stats created or destroyed
- Parent: loses regions and proportional stats plus -10 stability shock
- Existing scenarios produce valid runs without secession (stability stays above 20 in short runs)
- `secession_pool` field defined on scenario config but unused

---

## Phase M14b: Subordination & Alliance

### Goal

Two flavors of multi-civ political structures: vassals (coercive, tribute-based) and federations (consensual, defense-based). Both respond to the imperial pressure M14a creates.

### Model Changes

**New models in `models.py`:**

```python
class VassalRelation(BaseModel):
    overlord: str        # civ name
    vassal: str          # civ name
    tribute_rate: float = Field(default=0.15, ge=0.0, le=1.0)
    turns_active: int = 0

class Federation(BaseModel):
    name: str
    members: list[str]   # civ names
    founded_turn: int
```

**`WorldState`:**
```python
vassal_relations: list[VassalRelation] = Field(default_factory=list)
federations: list[Federation] = Field(default_factory=list)
```

**`Relationship`:**
```python
allied_turns: int = 0  # consecutive turns at ALLIED disposition
```

Incremented when disposition == ALLIED, reset to 0 only when disposition drops below FRIENDLY (not just below ALLIED). Two civs hovering between ALLIED and FRIENDLY for 15 turns clearly want to federate; two that drop to SUSPICIOUS don't.

### Vassal States

**Creation trigger:** After a war is won (existing war resolution), the victor chooses between absorption (existing behavior) and vassalization via `politics.choose_vassalize_or_absorb(winner, loser, world)`.

**Choice logic:**
- Vassalize when `winner.stability > 40` (strong empires prefer tributaries over direct control — less governing cost)
- No region count guard — single-region vassals paying tribute are historically common (city-states under empire protection)
- Personality influence (weighted coin flip, seeded on `world.seed + turn + hash(winner.name)`):
  - `ambitious`, `aggressive`: bias toward absorption (want direct control)
  - `cautious`, `diplomatic`, `visionary`: bias toward vassalization
- If conditions not met, existing absorption logic applies unchanged

**Vassalization resolution:**
1. Remove `(winner, loser)` from `active_wars` and `war_start_turns`
2. Loser keeps all regions, identity, and internal governance
3. Create `VassalRelation(overlord=winner.name, vassal=loser.name, tribute_rate=0.15)`
4. Set disposition: overlord → vassal = SUSPICIOUS, vassal → overlord = HOSTILE (resentful submission)
5. Vassal cannot declare wars (filtered out in `get_eligible_actions` when civ is a vassal)
6. Named event: "The Subjugation of [Vassal]" (importance 7)

**Tribute collection** (in `apply_automatic_effects` via `politics.collect_tribute(world)`):
```python
For each VassalRelation:
    tribute = floor(vassal.economy * relation.tribute_rate)
    vassal.treasury -= tribute
    overlord.treasury += tribute
    relation.turns_active += 1
```

**Vassal rebellion** (checked via `politics.check_vassal_rebellion(world)` in phase 10, after secession):
- Guard: `overlord.stability < 25 OR overlord.treasury < 10`
- Probability: `0.15` per turn when guard is met (flat — rebellion is opportunistic)
- On rebellion:
  - Remove `VassalRelation`
  - Vassal disposition toward overlord → HOSTILE
  - Vassal: `stability += 10`, `asabiya += 0.2` (independence energy)
  - Named event: "The [Vassal] Rebellion" (importance 8)
  - **Cascade:** Each remaining vassal of the same overlord gets an independent rebellion check at `0.05` probability, but only if that vassal's disposition toward the overlord is HOSTILE or SUSPICIOUS (one rebellion emboldens others, but loyal vassals hold)

**Vassal secession interaction:** Vassals can secede internally (M14a secession check still runs). If a vassal secedes, the breakaway is NOT a vassal of the overlord — it's a free civ. The overlord's vassal just got weaker, and a new hostile civ appeared.

### Federations

**Formation trigger** (checked via `politics.check_federation_formation(world)` in phase 10):

When any pair of civs reaches `allied_turns >= 10`:
- If one civ is already in a federation: invite the other to join (auto-accept if ALLIED)
- If neither is in a federation: create new federation
- If both are in different federations: no merge (too complex for M14b)
- Vassals cannot join federations (no independent foreign policy)
- An overlord CAN be in a federation, bringing vassals' military to shared defense

**Federation name:** Generated from a seed-deterministic pick: `"The [Adjective] [Noun]"` — e.g., "The Northern Accord", "The Iron Pact", "The Maritime League". Adjective pool drawn from members' region terrain. Noun pool: `["Accord", "Pact", "League", "Alliance", "Compact", "Coalition", "Confederation"]`.

Named event: "Formation of [Federation Name]" (importance 7)

**Federation mechanics:**

- **Shared defense:** When any member is *attacked* (WAR action targets them), all other members automatically enter war against the attacker. Added to `active_wars` and `war_start_turns`. Called via `politics.trigger_federation_defense(attacker, defender, world)` during action resolution.
  - **One layer deep:** Federation defense only triggers when a member is attacked, NOT when a member is the aggressor. If Civ A (in Federation X) attacks Civ B (in Federation Y), Federation Y members join against A. Federation X members do NOT auto-join to help A — A started the fight. X members only trigger if their territory is subsequently attacked.
- **Shared trade network:** All member pairs get trade routes regardless of adjacency. Computed in `get_active_trade_routes` — federation membership bypasses the adjacency requirement.
- **Attack restriction:** Members cannot target each other with WAR. Filtered in `get_eligible_actions`.

**Federation dissolution:**

- **Voluntary exit:** Automatic when a member's disposition toward any other member drops below FRIENDLY. Exiting civ: `stability -= 15`. All remaining members: `stability -= 5`.
- **Size collapse:** If federation drops to 1 member, dissolved automatically (no penalty).
- Named event: "Collapse of [Federation Name]" (importance 7)

### Integration Points

- `simulation.py` calls `politics.collect_tribute(world)` in phase 2 (automatic effects)
- `simulation.py` calls `politics.check_vassal_rebellion(world)` in phase 10 (consequences), after secession
- `simulation.py` calls `politics.check_federation_formation(world)` in phase 10 (consequences)
- `simulation.py` war resolution calls `politics.choose_vassalize_or_absorb(winner, loser, world)`
- `simulation.py` war resolution calls `politics.trigger_federation_defense(attacker, defender, world)`
- `action_engine.py` `get_eligible_actions` filters out WAR for vassals and WAR against federation co-members
- `resources.py` `get_active_trade_routes` checks federation membership for adjacency bypass

### Verification

- Vassalization: offered when `stability > 40`, personality-influenced choice
- Single-region vassals: valid (no region count guard)
- Tribute: correct treasury transfer each turn (`floor(vassal.economy * 0.15)`)
- Vassal rebellion: fires when overlord is weak (`stability < 25 OR treasury < 10`)
- Rebellion cascade: `0.05` probability for other vassals, only if HOSTILE/SUSPICIOUS toward overlord
- Vassal secession: breakaway is free, not vassal of overlord
- Federation: forms after 10 turns of ALLIED disposition
- Allied turns counter: resets only below FRIENDLY (not below ALLIED)
- Shared defense: one layer deep — defender's federation joins, attacker's doesn't
- Shared trade: federation members get trade routes without adjacency
- Federation dissolution: exiting member pays -15 stability, remaining members -5
- Vassals can't join federations or declare wars
- Overlord in federation brings vassals to shared defense
- Existing war/diplomacy tests unaffected

---

## Phase M14c: Indirect Power

### Goal

Second-order political mechanics — proxy wars, diplomatic congresses, and governments in exile. These exist because the M14a/M14b structures create conditions for them. Proxy wars destabilize vassals. Congresses resolve multi-front wars that federation defense produces. Governments in exile are the ghost of a conquered civ.

### Model Changes

**New models in `models.py`:**

```python
class ProxyWar(BaseModel):
    sponsor: str          # civ funding the destabilization
    target_civ: str       # civ being destabilized
    target_region: str    # specific region being targeted
    treasury_per_turn: int = 8
    turns_active: int = 0
    detected: bool = False

class ExileModifier(BaseModel):
    original_civ_name: str
    absorber_civ: str
    conquered_regions: list[str]    # regions that were the original civ's
    turns_remaining: int = 20
    recognized_by: list[str] = Field(default_factory=list)  # civs recognizing the exile
```

**`WorldState`:**
```python
proxy_wars: list[ProxyWar] = Field(default_factory=list)
exile_modifiers: list[ExileModifier] = Field(default_factory=list)
war_start_turns: dict[str, int] = Field(default_factory=dict)
    # key = "civ_a:civ_b" (sorted pair), value = start turn
    # populated when wars added to active_wars, cleaned when wars end
```

Note: `war_start_turns` is listed here but should be introduced alongside the first code that populates `active_wars` (M13b-1 or M14a, whichever ships first). If M13b-1 is already implemented by M14c, add `war_start_turns` as a patch to M13b-1's war tracking.

### Proxy Wars

**New deliberate action: FUND_INSTABILITY**

Added to `ActionType` enum. Registered via `@register_action(ActionType.FUND_INSTABILITY)`.

**Eligibility:**
- `treasury >= 8`
- At least one civ with HOSTILE or SUSPICIOUS disposition
- Target civ must control a region adjacent to one of sponsor's regions (need a border to funnel support)
- Sponsor is not a vassal

**Resolution:**
1. Choose target: most hostile neighbor with `region_count >= 3` (secession-eligible). Fallback: most hostile neighbor with `region_count >= 2`.
2. Choose target region: the target's region most distant from its capital.
3. Create `ProxyWar(sponsor=civ.name, target_civ=target.name, target_region=region.name)`
4. `sponsor.treasury -= 8`
5. No event generated — covert action. Events only appear if detected.

**Weight profile:** `cunning` gets highest weight. `cautious` and `diplomatic` bias toward FUND_INSTABILITY over WAR. `aggressive` and `bold` bias toward direct WAR.

**Ongoing effects** (in `apply_automatic_effects` via `politics.apply_proxy_wars(world)`):
```python
For each ProxyWar:
    sponsor.treasury -= 8
    proxy.turns_active += 1

    # Destabilization effects on target
    target_civ.stability -= 3
    target_civ.economy -= 2  # disrupted trade in target region

    # Auto-cancel if sponsor can't afford it
    if sponsor.treasury < 0:
        remove proxy war
```

The `+0.05` secession probability boost for the targeted region is applied during the secession check in M14a.

**Detection** (checked via `politics.check_proxy_detection(world)` in phase 10):
- Per turn probability: `target_civ.culture / 100` — high-culture civs are better at catching interference
- On detection:
  - `proxy.detected = True`
  - Disposition: sponsor → target becomes HOSTILE (if not already)
  - `target_civ.stability += 5` (rallying effect — external threat unifies)
  - Named event: "[Sponsor] Exposed Funding Separatists in [Target Region]" (importance 7)
  - Proxy war continues unless sponsor cancels (detected doesn't mean stopped, just politically costly)

**Cancellation conditions:**
- Sponsor's treasury drops below 0
- Target civ loses the targeted region (to secession or conquest)
- Target and sponsor reach FRIENDLY+ disposition
- Sponsor is conquered/absorbed

### Diplomatic Congresses

**No new action.** Congresses are events, not choices.

**Trigger** (checked via `politics.check_congress(world)` in phase 7, random events):
- Guard: 3+ unique civs currently in `active_wars`
- Probability: `0.05` per turn when guard is met
- Seeded: `world.seed + turn`

**Congress resolution:**

1. Identify participants: every civ involved in at least one active war
2. Compute negotiating power per participant:
   ```python
   longest_war = world.turn - min(
       war_start_turns[key] for key in war_start_turns
       if civ.name in key.split(":")
   )
   power = (military + economy + federation_allies_count * 10) / max(longest_war, 1)
   ```
3. Roll outcome (seeded, three options):
   - **Full peace (40%):** All `active_wars` among participants cleared. All `war_start_turns` entries cleaned. All participant dispositions set to NEUTRAL. Named event: "The Congress of [capital region of highest-culture participant]" (importance 9).
   - **Partial ceasefire (35%):** The two highest-power participants settle. Their wars end, dispositions → NEUTRAL. Others continue. Named event (importance 7).
   - **Collapse (25%):** Nothing changes. All participants: `stability -= 5`. Named event: "The Failed Congress" (importance 6).

### Governments in Exile

**Trigger:** When a civ loses its last region (absorbed in war — existing elimination logic in `phase_consequences`).

**On elimination** (via `politics.create_exile(eliminated_civ, conquering_civ, world)`):
1. Create `ExileModifier`:
   ```python
   ExileModifier(
       original_civ_name=eliminated_civ.name,
       absorber_civ=conquering_civ.name,
       conquered_regions=[...regions that were the eliminated civ's],
       turns_remaining=20
   )
   ```
2. Eliminated civ still removed from `world.civilizations` (no longer acts)
3. Named event: "Fall of [Civ Name] — Government in Exile Declared" (importance 8)

**Ongoing effects** (in `apply_automatic_effects` via `politics.apply_exile_effects(world)`):
```python
For each ExileModifier:
    absorber.stability -= 5  # restless conquered population
    exile.turns_remaining -= 1
    if turns_remaining <= 0:
        remove ExileModifier  # population has assimilated
```

**Exile recognition** (side effect of DIPLOMACY action resolution):
- When a civ performs DIPLOMACY and there are active exile modifiers: if the diplomat's disposition toward the absorber is HOSTILE/SUSPICIOUS, they auto-recognize the exile (added to `recognized_by`)
- Named event: "[Civ] Recognizes [Original Civ] Government in Exile" (importance 5)

**Restoration event** (checked via `politics.check_restoration(world)` in phase 10):
- Guard: `absorber.stability < 20 AND exile.turns_remaining > 0`
- Base probability: `0.05` per turn
- Bonus: `+0.03` per civ in `recognized_by` per turn
- On restoration:
  1. Respawn in conquered region with highest `carrying_capacity * fertility`
  2. Stats: `population=30, military=20, economy=20, culture=original_culture, stability=50, asabiya=0.8`
  3. Tech era: `max(TRIBAL, absorber_era - 1)` — knowledge atrophied in exile, floored at TRIBAL
  4. Leader: generated from original civ's `leader_name_pool`
  5. Disposition: HOSTILE toward absorber, NEUTRAL toward everyone else, FRIENDLY toward recognizers
  6. Absorber loses that region
  7. Remove `ExileModifier`
  8. Named event: "Restoration of [Original Civ Name]" (importance 9)

### Integration Points

- `ActionType.FUND_INSTABILITY` added to enum, registered with handler
- `simulation.py` calls `politics.apply_proxy_wars(world)` in phase 2 (automatic effects)
- `simulation.py` calls `politics.apply_exile_effects(world)` in phase 2 (automatic effects)
- `simulation.py` calls `politics.check_proxy_detection(world)` in phase 10 (consequences)
- `simulation.py` calls `politics.check_restoration(world)` in phase 10 (consequences)
- `simulation.py` calls `politics.check_congress(world)` in phase 7 (random events)
- `simulation.py` civ elimination logic calls `politics.create_exile(eliminated_civ, conquering_civ, world)`
- `action_engine.py` DIPLOMACY resolution checks for exile recognition opportunity
- M14a secession check gains proxy war `+0.05` boost for targeted region

### Verification

- FUND_INSTABILITY: costs 8/turn, -3 stability and -2 economy to target, auto-cancels on bankruptcy
- Proxy detection: probability = `target_culture / 100`, generates event and +5 stability rally on detection
- Proxy war continues after detection (detected != stopped)
- Congress: only triggers with 3+ unique civs at war, three weighted outcomes
- Congress naming: uses highest-culture participant's capital region
- War duration: computed from `war_start_turns`, not event count
- Exile: absorber gets -5 stability/turn for 20 turns on conquered regions
- Restoration: fires when absorber weak, probability boosted by recognition count
- Restoration tech era: `max(TRIBAL, absorber_era - 1)` — can't go below TRIBAL
- Restored civ: gets one region back, starts with fighting chance but not dominance
- Recognition: automatic side effect of DIPLOMACY, generates importance 5 event
- Proxy war boosts secession probability (+0.05) in targeted region

---

## Phase M14d: Systemic Dynamics

### Goal

Feedback loops that use the full M14 political system. Mechanically simple — modifier checks and stat adjustments, no new data structures beyond tracking fields. These ensure no equilibrium lasts: dominance triggers coalitions, fallen empires resurge, dying civs fade gracefully, and prolonged peace creates its own instabilities.

### Model Changes

**`Civilization`:**
```python
peak_region_count: int = 0           # updated whenever region_count increases
decline_turns: int = 0               # consecutive turns where stat sum is lower than 20 turns ago
stats_sum_history: list[int] = Field(default_factory=list)
    # rolling window of economy+military+culture sums, last 20 entries
prev_economy: int = 0                # for decline tracking (set end of each turn)
prev_military: int = 0
prev_culture: int = 0
```

**`WorldState`:**
```python
peace_turns: int = 0  # consecutive turns with no active wars
```

### Balance of Power

**Goal:** Prevent runaway winners. When one civ dominates, everyone else aligns against it.

**Power score** (computed in `apply_automatic_effects` via `politics.apply_balance_of_power(world)`):
```python
power_score(civ) = military + economy + len(civ.regions) * 5
total_power = sum(power_score(c) for c in living_civs)
```

**Trigger:** Any civ where `power_score / total_power > 0.40`.

**Effect:** All other civs get `+3 disposition toward each other` per turn (coalition pressure). Disposition drift capped at one disposition level per turn (can't jump HOSTILE to ALLIED in a single turn).

**Why +3 not +10:** At the 0-100 scale, +10/turn would federate the world against the dominant civ in 3-4 turns. +3 creates gradual alignment over 10-15 turns — enough time for the dominant civ to respond with diplomacy, proxy wars, or preemptive strikes. The pressure is inevitable but not instant.

**Federation interaction:** Coalition pressure naturally feeds into federation formation. Three civs drifting to ALLIED through balance-of-power and staying there 10 turns federate — an emergent mechanical counterweight.

**No new model fields.** Pure computation.

### Fallen Empire Modifier

**Goal:** Civs that lost greatness are dangerous. They remember who they were.

**Tracking:** `peak_region_count` set to `max(peak_region_count, len(civ.regions))` each turn in `apply_automatic_effects`.

**Trigger:** `peak_region_count >= 5 AND len(civ.regions) == 1`

**Effects** (in `apply_automatic_effects` via `politics.apply_fallen_empire(world)`):
- `asabiya = min(asabiya + 0.05, 1.0)` per turn (faster recovery than normal drift)
- WAR and EXPAND action weights multiplied by `2.0` in `get_eligible_actions`
- Balance-of-power coalition pressure against this civ reduced by 50% (others underestimate the fallen)

**Lifecycle:** Deactivates when `region_count >= 3` (recovered enough to be a normal power). Reactivates if they fall again.

**Narrative impact:** Creates "return of the king" arcs. A civ reduced to one region after holding six rebuilds with abnormal aggression and cohesion.

### Civilizational Twilight

**Goal:** Slow death for civs that can't recover. Whimper, not bang.

**Decline detection** (via `politics.update_decline_tracking(world)` at end of phase 10):

Rolling window approach:
1. Each turn, compute `current_sum = economy + military + culture`
2. Append to `stats_sum_history` (capped at 20 entries — oldest dropped when exceeding 20)
3. If `len(stats_sum_history) == 20`:
   - If `current_sum < stats_sum_history[0]`: `decline_turns += 1`
   - Else: `decline_turns = 0`
4. If `len(stats_sum_history) < 20`: not enough data, `decline_turns` stays at 0

This is robust against per-turn noise — a single good turn doesn't reset the counter. Only sustained recovery (sum higher than 20 turns ago) breaks the decline.

**Twilight trigger:** `decline_turns >= 20 AND len(civ.regions) == 1`

**Twilight effects** (in `apply_automatic_effects` via `politics.apply_twilight(world)`):
- `population -= 3` per turn (slow bleed)
- `culture -= 2` per turn (institutional decay)
- Named event on first entering twilight: "The Twilight of [Civ Name]" (importance 7)

**Revival conditions** (any one resets `decline_turns` to 0 and exits twilight):
- New leader with `asabiya > 0.6`
- Gains a region (conquest or restoration)
- Forms or joins a federation

**Peaceful absorption** (checked via `politics.check_twilight_absorption(world)` in phase 10):
- Trigger: `decline_turns >= 40` (20 turns in twilight with no revival)
- Absorbed by most culturally similar neighbor (highest `culture` stat among adjacent civs, ties broken by disposition)
- Follows existing absorption logic
- Creates `ExileModifier` with `turns_remaining=10` (shorter than conquest exile — less resentment in voluntary absorption)
- Named event: "The Quiet End of [Civ Name]" (importance 6)

### The Long Peace Problem

**Goal:** Sustained peace is dynamically interesting — a different kind of instability.

**Tracking:** `peace_turns` on WorldState. Reset to 0 when `len(active_wars) > 0`. Incremented in `apply_automatic_effects` when `len(active_wars) == 0`.

**Trigger:** `peace_turns >= 30`

**Effects** (in `apply_automatic_effects` via `politics.apply_long_peace(world)`):

1. **Military restlessness:** Civs with `military > 60`: `stability -= 2` per turn (idle armies are political liabilities)

2. **Economic inequality:** Each turn during long peace:
   - Richest civ (highest `economy`): `economy += 1` (structural advantage compounds)
   - Poorest civ (lowest `economy`): `economy -= 1` (falls further behind)
   - Stat changes, not just treasury — affects all downstream calculations (trade income, development costs, tech requirements)

3. **Disposition decay:** All ALLIED dispositions drift by `-1` per turn during long peace (without a common enemy, alliances fray). Doesn't immediately dissolve federations (allied_turns uses FRIENDLY threshold), but prolonged peace erodes federation conditions.

**Self-correcting:** The long peace creates conditions for its own end:
- Military-heavy civs lose stability → governing costs hurt more → potential secession → wars restart
- Economic inequality → poor civ gets desperate → WAR weighted higher → conflict
- Alliance erosion → federations dissolve → shared defense gone → opportunistic attacks
- `peace_turns` resets when any war begins

### Integration Points

All M14d mechanics in `politics.py`, called from existing phase hooks:

- `politics.apply_balance_of_power(world)` — phase 2, automatic effects
- `politics.apply_fallen_empire(world)` — phase 2, automatic effects
- `politics.apply_twilight(world)` — phase 2, automatic effects (stat drain)
- `politics.check_twilight_absorption(world)` — phase 10, consequences
- `politics.apply_long_peace(world)` — phase 2, automatic effects
- `politics.update_decline_tracking(world)` — end of phase 10, after all stat changes finalized
- `politics.update_peak_regions(world)` — phase 2, automatic effects (update peak tracking)

### Verification

- Balance of power: coalition drift activates at 40%+ power share, +3/turn capped at one disposition level per turn
- Balance of power: dominant civ eventually faces federated opposition
- Fallen empire: activates at peak 5+ regions reduced to 1, asabiya +0.05/turn + war/expand weight ×2.0
- Fallen empire: deactivates at 3+ regions, reactivates if they fall again
- Fallen empire: coalition pressure against them reduced by 50%
- Twilight: rolling window — current stat sum compared to 20 turns ago, not per-turn decline
- Twilight: requires 20 decline_turns AND single region
- Twilight: revival by new leader (asabiya > 0.6), region gain, or federation
- Twilight absorption: at 40 decline turns, absorbed by culturally similar neighbor, creates 10-turn exile
- Long peace: activates at 30 turns without wars
- Long peace: military restlessness (-2 stability for military > 60 civs)
- Long peace: economy stat change (+1 richest, -1 poorest) — not just treasury
- Long peace: ALLIED disposition decay -1/turn
- Long peace: self-correcting — instabilities trigger war, resetting counter
- `peak_region_count` never decreases
- `stats_sum_history` capped at 20 entries

---

## Cross-Cutting Concerns

### Turn Phase Order (unchanged from M13)

1. Environment — natural events
2. **Automatic Effects** — M13: trade income, military maintenance, war costs, embargo leakage, mercenary hire/decay. **M14 additions:** governing costs, tribute collection, proxy war effects, exile instability, balance of power, fallen empire, twilight drain, long peace effects, peak region tracking
3. Production — base income, condition penalties, population growth/decline
4. Technology — advancement checks
5. Action — deliberate actions. **M14 additions:** MOVE_CAPITAL, FUND_INSTABILITY
6. Cultural Milestones — cultural threshold checks
7. Random Events — cascading probability table. **M14 addition:** diplomatic congress check
8. Leader Dynamics — trait evolution
9. Fertility — degradation/recovery tick
10. Consequences — condition durations, asabiya, collapse checks. **M14 additions:** capital loss check, secession check (post-clamp), vassal rebellion, federation formation, proxy detection, restoration check, twilight absorption, decline tracking update

### New Module: `src/chronicler/politics.py`

Single module containing all M14 political mechanics. Exports:

**M14a:**
- `apply_governing_costs(world: WorldState) -> list[Event]`
- `check_capital_loss(world: WorldState) -> list[Event]`
- `check_secession(world: WorldState) -> list[Event]`

**M14b:**
- `collect_tribute(world: WorldState) -> list[Event]`
- `choose_vassalize_or_absorb(winner: Civilization, loser: Civilization, world: WorldState) -> bool`
- `trigger_federation_defense(attacker: str, defender: str, world: WorldState) -> list[Event]`
- `check_vassal_rebellion(world: WorldState) -> list[Event]`
- `check_federation_formation(world: WorldState) -> list[Event]`

**M14c:**
- `apply_proxy_wars(world: WorldState) -> list[Event]`
- `apply_exile_effects(world: WorldState) -> list[Event]`
- `create_exile(eliminated: Civilization, conqueror: Civilization, world: WorldState) -> ExileModifier`
- `check_proxy_detection(world: WorldState) -> list[Event]`
- `check_congress(world: WorldState) -> list[Event]`
- `check_restoration(world: WorldState) -> list[Event]`

**M14d:**
- `apply_balance_of_power(world: WorldState) -> list[Event]`
- `apply_fallen_empire(world: WorldState) -> list[Event]`
- `apply_twilight(world: WorldState) -> list[Event]`
- `check_twilight_absorption(world: WorldState) -> list[Event]`
- `apply_long_peace(world: WorldState) -> list[Event]`
- `update_decline_tracking(world: WorldState) -> None`
- `update_peak_regions(world: WorldState) -> None`

### ActionType Enum Expansion

```python
class ActionType(str, Enum):
    # Existing (M1-M13)
    EXPAND = "expand"
    DEVELOP = "develop"
    TRADE = "trade"
    DIPLOMACY = "diplomacy"
    WAR = "war"
    BUILD = "build"          # M13b-1
    EMBARGO = "embargo"      # M13a
    # M14 additions
    MOVE_CAPITAL = "move_capital"      # M14a
    FUND_INSTABILITY = "fund_instability"  # M14c
```

### Narrative Engine

Each phase adds new event types. No new LLM capabilities needed — richer structured data in prompts. Key narrative events:

- Secession: "The Secession of [Breakaway]" (importance 9)
- Capital loss / relocation
- Vassal subjugation and rebellion (importance 7-8)
- Federation formation and collapse (importance 7)
- Proxy war detection (importance 7)
- Diplomatic congress outcomes (importance 6-9)
- Government in exile declaration and restoration (importance 8-9)
- Exile recognition (importance 5)
- Civilizational twilight and quiet end (importance 6-7)

### Scenario Compatibility

All new fields have defaults:
- `capital_region`: `None` (set during world_gen)
- `secession_pool`: empty list (unused in M14)
- `vassal_relations`: empty
- `federations`: empty
- `proxy_wars`: empty
- `exile_modifiers`: empty
- `war_start_turns`: empty dict
- `peace_turns`: 0
- `peak_region_count`: 0
- `decline_turns`: 0
- `stats_sum_history`: empty list
- `allied_turns`: 0

Old scenarios work unchanged — new mechanics activate based on the systems that produce them.

### Viewer Bundle Extensions

**`TurnSnapshot` gains:**
- `vassal_relations: list[dict]` (serialized VassalRelation)
- `federations: list[dict]` (serialized Federation)
- `proxy_wars: list[dict]` (serialized ProxyWar, excluding `detected=False` entries for fog-of-war feel)
- `exile_modifiers: list[dict]` (serialized ExileModifier)
- `capitals: dict[str, str]` (civ name → capital region name)
- `peace_turns: int`

**`CivSnapshot` gains:**
- `is_vassal: bool`
- `is_fallen_empire: bool`
- `in_twilight: bool`
- `federation_name: str | None`

Viewer components render available data without new components — existing StatGraphs, EventLog, and TerritoryMap handle new fields. Political overlay (vassals, federations, capitals) is a natural extension of the territory map.

### Performance Budget

- `--simulate-only` 500 turns × 5 civs × 15 regions: < 5 seconds (M14 adds O(civs × regions) governing cost per turn — negligible)
- Graph utilities already O(V+E) from M13 P2
- No new external dependencies

### Dependency Chain

```
M13b (treasury, trade, adjacency, active wars)
  → M14a (governing cost, capital, secession)
    → M14b (vassals, federations)
      → M14c (proxy wars, congresses, exile)
        → M14d (balance of power, fallen empire, twilight, long peace)
```

Each phase testable in isolation before the next starts.

### Testing Strategy

**M14a tests:**
- Governing cost scales with distance, not flat region count
- Compact vs sprawling empire cost comparison
- Capital loss triggers succession and reassignment (filtered to owned regions)
- MOVE_CAPITAL action resolution
- Secession fires only at `stability < 20 AND regions >= 3`
- Secession uses post-clamp stability
- Breakaway stat split: `floor(ratio)` for breakaway, remainder for parent
- Breakaway inherits tech, gets cultural name, HOSTILE to parent
- 50-turn smoke test: empires that expand too fast experience secession

**M14b tests:**
- Vassalization choice respects stability guard and personality
- Tribute transfer correct each turn
- Vassal can't declare wars
- Rebellion at `0.15` when overlord weak
- Cascade rebellion at `0.05`, gated by vassal disposition
- Federation forms at 10 allied turns
- Allied turns reset only below FRIENDLY
- Shared defense one layer deep
- Federation trade bypasses adjacency
- Federation dissolution on member exit

**M14c tests:**
- FUND_INSTABILITY costs and effects correct
- Detection probability scales with culture
- Detection generates event and stability rally
- Congress triggers with 3+ war participants
- Congress outcomes weighted correctly
- War duration from `war_start_turns`
- Exile created on civ elimination
- Exile stability drain for 20 turns
- Recognition as DIPLOMACY side effect with event
- Restoration when absorber weak, boosted by recognition
- Restoration tech era floored at TRIBAL

**M14d tests:**
- Balance of power: coalition drift at 40%+ power share
- Fallen empire: activates at peak 5+, regions == 1
- Fallen empire: deactivates at regions >= 3
- Twilight: rolling window stat comparison over 20 turns
- Twilight absorption at 40 decline turns
- Long peace: activates at 30 turns, economy stat changes
- Long peace: self-corrects (instabilities → war → reset)
- All tracking fields update correctly

**Integration test:**
- 200-turn run with 5+ civs: verify at least one secession, one vassal relation, and one federation form from pure mechanics
- No crashes across all existing scenarios with M14 active
