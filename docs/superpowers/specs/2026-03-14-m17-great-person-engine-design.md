# M17: The Great Person Engine — Design Specification

> History is made by individuals under structural pressures. Leaders and notable figures become characters with arcs, earned through achievement, shaped by the world they inhabit.

## Overview

M17 adds named characters beyond leaders — generals, merchants, prophets, and scientists — who emerge from civilizational achievement, interact with each other and with leaders, and leave permanent marks on their civilization's identity through traditions and folk hero status.

**Dependencies**: M14 (vassals, federations, secession, exile), M16 (movements, cultural identity, prestige, ideological systems). Both must be complete before M17 work begins.

**Scope**: 9 subsystems across 4 implementation phases (~950 lines simulation code, ~1200-1400 lines tests).

---

## 1. Core Character System

### 1.1 GreatPerson Model

Parallel to `Leader`, not a replacement. The leader system (succession, trait evolution, legacy, rivalry) is mature and load-bearing across four milestones — M17 does not touch it. Great persons and leaders interact through events (capture, exile, defection) but are structurally separate.

**Shared field names for duck typing**: both `GreatPerson` and `Leader` expose `name`, `trait`, `civilization`, and `alive`. Event handlers that operate on "a person dies" or "a person changes hands" can consume either model without type-checking.

```python
class GreatPerson(BaseModel):
    name: str                              # from cultural name pool
    role: str                              # "general", "merchant", "prophet", "scientist", "exile"
    trait: str                             # personality trait (same pool as leaders)
    civilization: str                      # current owner (changes on capture)
    origin_civilization: str               # who spawned them (never changes)
    alive: bool = True
    active: bool = True                    # False when retired or dead
    fate: str = "active"                   # "active", "retired", "dead", "ascended"
    born_turn: int
    death_turn: int | None = None
    deeds: list[str] = []                  # named accomplishments
    region: str | None = None              # current location (for capture/exile)
    captured_by: str | None = None         # civ that captured them, if any
    is_hostage: bool = False
    hostage_turns: int = 0                 # turns held as hostage
    cultural_identity: str | None = None   # gains captor's identity after 10 hostage turns
    movement_id: int | None = None         # for prophets: which movement they champion
```

**Storage**:
- Active roster: `Civilization.great_persons: list[GreatPerson]`
- Archived: `WorldState.retired_persons: list[GreatPerson]` (on retirement, death, or ascension)

**Role types**:
- `"general"`, `"merchant"`, `"prophet"`, `"scientist"` — achievement-triggered, participate in modifier registry
- `"exile"` — special lifecycle role created when a leader is deposed. Does NOT participate in modifier registry, does NOT count against per-type cooldowns, follows capture-exemption logic for cap purposes. Completely different mechanics (pretender drain, restoration, extradition).

### 1.2 Domain-Tagged Modifier Registry

Great persons register passive modifiers consumed by turn phases. Each modifier has a `domain` tag; phase handlers query only their relevant domain via `get_modifiers(civ, domain)`.

```python
# Modifier shapes
{"source": "general_khotun", "domain": "military", "stat": "military", "value": 10}
{"source": "merchant_lysander", "domain": "trade", "stat": "trade_income", "value": 3, "per": "route"}
{"source": "scientist_hypatia", "domain": "tech", "stat": "tech_cost", "value": -0.30, "mode": "multiplier"}
{"source": "prophet_zara", "domain": "culture", "stat": "movement_spread", "value": "accelerated", "mode": "behavioral"}
```

**Implementation**: `get_modifiers(civ, domain)` iterates `civ.great_persons` and returns modifiers for active, non-hostage characters matching the domain. Computed on-the-fly each phase — no caching, no invalidation logic. The roster is small enough (max ~8-10 per civ) that iteration is negligible.

**Prophet exception**: the prophet's `"behavioral"` mode means the movement spread phase branches into accelerated logic (double adoption probability in adjacent civs) rather than adding a numeric value. Additionally, prophet exile-spread uses a `REACTION_REGISTRY` entry: when a prophet is exiled, their movement spreads to the destination civ with a one-time adoption check.

**Self-documenting**: looking at the modifier registry immediately shows which phases care about which great person types. Clean extension point for M18 — new character types register new domain tags without touching existing phase handlers.

### 1.3 Achievement-Triggered Generation

Great persons emerge when a civ crosses specific behavioral thresholds. Active civs produce more characters; stagnant civs produce fewer. No fixed cadence.

| Type | Trigger Condition | Cooldown |
|------|-------------------|----------|
| General | Win 3 wars within a 15-turn rolling window | 20 turns (per-type, per-civ) |
| Merchant | Maintain 4+ active trade routes for 10 consecutive turns | 20 turns |
| Prophet | First civ to adopt a movement (one-shot, once per movement), OR civ is movement origin and movement reaches 3+ adherents | 25 turns |
| Scientist | Advance a tech era, OR maintain economy ≥ 80 for 15 consecutive turns | 20 turns |

**Catch-up discount**: civs with zero active great persons get all thresholds reduced by 25% (e.g., general requires 2 wars instead of 3, merchant requires 3 routes instead of 4). Prevents permanent have/have-not divergence without guaranteeing characters to inactive civs.

**Scientist dual trigger**: era advancement is a discrete event (4-5 times per 500 turns). The economy threshold provides a repeatable achievement path — a rich civ that never advances eras can still produce scientists through sustained investment.

**Prophet first-adoption**: a one-shot bonus trigger, not the primary generation path. The second condition (3+ adherents while origin) is the recurring trigger.

**Cooldown tracking**: `WorldState.great_person_cooldowns: dict[str, dict[str, int]]` — maps `{civ_name: {role: last_spawn_turn}}`. A spawn is blocked if `current_turn - last_spawn_turn < cooldown`.

**Name generation**: drawn from existing cultural name pools (maritime, steppe, mountain, forest, desert, scholarly, military) based on the civ's cultural group. Names added to `WorldState.used_leader_names` to prevent reuse.

### 1.4 Lifecycle States

```
active → retired   (lifespan expired, peaceful — always)
active → dead      (killed by war, disaster, succession crisis)
active → ascended  (general becomes leader during succession crisis)
```

**Lifespan**: 20-30 turns, deterministic from `seed + born_turn + hash(name)`. On expiry: retirement. Lifespan expiry is ALWAYS retirement, never death. A character whose lifespan expires on the same turn as a battle still retires — they are not retroactively killed by the battle.

**Retirement**: archived to `WorldState.retired_persons`, removed from active roster and modifier registry. No downstream triggers. Narrative engine can reference historically.

**Death**: archived same way, but fires downstream systems:
- Folk hero check (if death was dramatic — see Section 5)
- Grudge resolution (if involved in a rivalry)
- Named event generation ("The Fall of General Khotun at the Siege of Ashenmoor")

**Dramatic death** (clear boolean, no judgment call): death occurred during war resolution (Phase 5), natural disaster event (Phase 7), or succession crisis (Phase 8). Anything else is non-dramatic.

**50-character global cap**: safety valve, not a gameplay mechanic. When a 51st character would spawn, force-retire the oldest character *of the spawning civ* — the cost stays local. Log a warning when the cap triggers; if it fires regularly, spawn rate or lifespan is miscalibrated and needs tuning.

**Recapture**: when a civ reconquers a region holding their captured character, the character reverts to `origin_civilization`. This is a war outcome — only triggers if the specific region containing the character is recaptured, not automatic.

**Capture placement**: captured characters are placed in the contested region where they were captured (the front), not teleported to the captor's capital. This makes recapture require retaking specific territory — more strategic and narratively interesting.

### 1.5 Base Role Distribution for Spawning

When a great person spawns and the role is determined by threshold, the base probability of each role is equal (25% each), modified by folk hero bias:
- Each folk hero of a given role applies ×1.3 to that role's selection probability
- Probabilities renormalized after bias application
- Example: 2 military folk heroes → general probability = `25% × 1.3 × 1.3 = 42.25%`, renormalized across all four roles

Note: this distribution only matters when multiple thresholds fire simultaneously on the same turn (rare). Normally, the specific threshold that was crossed determines the role directly.

---

## 2. Succession & Leadership

### 2.1 Succession Crises

On leader death (not retirement — leaders don't retire, they die or get deposed), if civ has 3+ regions, compute crisis probability:

```python
base = 0.15
region_factor = region_count / 5
instability_factor = 1 - (stability / 100)
modifiers = 1.0

# Escalation (multiplicative)
if succession_type != "heir":    modifiers *= 1.5   # no clear line of succession
if has_active_vassals:           modifiers *= 1.3   # vassals back rival candidates
if leader_reign < 5:            modifiers *= 1.2   # never consolidated power

# Suppression (multiplicative)
if asabiya > 0.7:               modifiers *= 0.6   # unified identity
if "martial" in traditions:     modifiers *= 0.8   # institutional discipline
if "resilience" in traditions:  modifiers *= 0.8   # learned to weather transitions
if leader_reign > 15:           modifiers *= 0.7   # established legitimacy

crisis_chance = clamp(base * region_factor * instability_factor * modifiers, 0.05, 0.40)
```

**Irreducible floor (0.05)**: even the most stable empire has a 5-10% crisis chance. History is full of unexpected succession disputes. The narrative engine needs access to this dramatic tool even in stable empires.

**Cap (0.40)**: prevents crisis from becoming inevitable. Even a failing empire has a 60% chance of orderly succession.

**Crisis duration**: 3-5 turns (deterministic from `seed + turn`).

**During crisis**:
- Stability -10 (immediate, on crisis start)
- Action effectiveness halved (all stat changes from actions ×0.5)
- Other civs can **back candidates** via DIPLOMACY sub-action (costs 10 treasury/turn of backing)

**Crisis state**: tracked on `Civilization`:
```python
succession_crisis_turns_remaining: int = 0  # 0 = no active crisis
succession_candidates: list[dict] = []       # [{"backer_civ": str, "type": str}]
```

**Resolution** (at crisis end):
- New leader's trait influenced by external backing:
  - Military-backed → aggressive or warlike trait
  - Trade-backed → cautious or shrewd trait
  - No external backing → trait from normal succession pool
- Backing the winner: +1 disposition level with new leader
- Backing the loser: -1 disposition level with new leader

**Nested crisis**: if another leader death occurs during an active crisis (extremely rare — assassination, disaster), crisis extends by 2 turns, additional stability -5.

### 2.2 General-to-Leader Conversion

If a general exists during a succession crisis, they automatically become a candidate with 50% chance of winning (highest among all candidate types). On winning:

- General's `GreatPerson` record archived with `fate="ascended"`
- New `Leader` created inheriting the general's `name` and `trait`
- General's military modifier deregistered (they're a leader now, not a great person)
- `succession_type` set to `"general"`
- Leader starts with `reign_start = current_turn` (reign length 0)
- The short-reign crisis multiplier (×1.2 when reign < 5) applies intentionally — military coups breed instability. This is a feature, not a bug.

### 2.3 Any-Great-Person Succession Entry

During a succession crisis, any great person (not just generals) can enter the succession pool at 20% probability (vs general's 50%). This opens the hostage-to-leader pipeline for all character types:

- A returned merchant or scientist who was culturally shaped by the enemy seizing power during a crisis
- A prophet riding a wave of popular movement support
- Selection probability: 20% for non-generals, 50% for generals
- If multiple great persons are candidates, highest probability wins (general > others)
- Same `fate="ascended"` archival and Leader creation process as generals

### 2.4 Exiled Leaders

When a leader is deposed (civil war, succession crisis where external candidate wins, coup):

- Deposed leader becomes a `GreatPerson` with `role="exile"`, stored on the host civ's `great_persons` list
- Host selection: random non-hostile civ, preference for highest disposition
- `civilization` set to host civ, `origin_civilization` set to deposed civ

**Host effects**: culture +3/turn while hosting an exile (prestige of sheltering a deposed ruler)

**Pretender drain**: origin civ gets stability -2/turn while the exile lives. Phase 2 finds relevant exiles by scanning all civs' `great_persons` lists for `role="exile" and origin_civilization == target_civ`. Simple O(n) scan on small lists.

**Extradition** (DIPLOMACY sub-action, costs 5 treasury):
- Compliance: exile removed, host's disposition with all other civs -1 level ("they looked weak")
- Refusal: disposition with origin civ -1 level, but all other civs' disposition toward host +1 level ("they stood firm")

**Recognition**: other civs can "recognize" the exile (same mechanic as M14's exile recognition — `recognized_by` list). Each recognizer adds +0.03/turn to restoration probability.

**Restoration check** (Phase 10, once per turn): fires only when origin civ's stability < 20.
- Base probability: `0.05 + (0.03 × len(recognized_by))`
- At 0.05/turn with stability stuck below 20: ~64% chance within 20 turns, ~92% within 50
- On success: exile returns as leader of origin civ, disposition +1 level with all recognizers, stability +15

**Exile lifespan**: 30 turns. If they die before restoration → dramatic death check (dramatic if origin civ had recognizers — "the king who never returned"). Folk hero eligible.

### 2.5 Legacy System Expansion

Extends existing 15+ turn reign legacy system. New legacy conditions:

**Golden Age Memory** (leader reigned 20+ turns AND economy grew by 30+ during reign):
- Next 2 leaders get asabiya +0.1
- Named event: "The Golden Memory of {leader}" (importance 7)

**Shame Memory** (leader lost the capital during their reign):
- Successor gets stability -10 but military +10 (revenge motivation)
- WAR action weight ×1.5 against the civ that took the capital
- Lasts until capital recovered or 20 turns, whichever first

**Fracture Memory** (secession occurred during leader's reign):
- Next leader biased 1.5× toward DEVELOP action
- Stability recovery rate ×1.5 (the civ is cautious about overextension)
- Lasts 15 turns

**Legacy-to-tradition crystallization**: each legacy type increments `Civilization.legacy_counts[type]`. When a threshold is reached, a tradition crystallizes (see Section 4).

---

## 3. Character Interactions

### 3.1 Personal Grudges

Leaders who lose wars gain a directional grudge against the winning civ.

**Storage** (on `Leader`):
```python
grudges: list[dict] = []
# Each: {"rival_name": str, "rival_civ": str, "intensity": float, "origin_turn": int}
```

**Mechanics**:
- On war loss: add grudge with `intensity=1.0` against winning leader
- WAR action weight against grudge target's civ: `×(1.0 + 0.5 × intensity)` — at full intensity, 1.5× bias
- Decay: intensity -0.1 every 5 turns (natural fading)
- Refreshed: if another war is lost to same civ, intensity resets to 1.0

**Grudge targets the civ, not just the leader**: the WAR weight boost applies against the rival's *civ*, regardless of whether the original rival leader is still alive. A dead rival's civ gets targeted for as long as the grudge persists.

**Accelerated decay after target death**: when the rival leader dies, decay rate doubles to -0.1 every 2.5 turns (effectively -0.2 per 5 turns). A fresh 1.0 grudge fades in ~25 turns post-death instead of ~50.

**Succession inheritance**: new leader inherits predecessor's grudges at 50% intensity. A 0.3 grudge inherited at 0.15 decays to nothing in ~10 turns. A fresh 1.0 grudge inherited at 0.5 lasts ~25 turns. Multi-generational feuds require repeated losses.

**Distinction from existing rival system**: rivals are leader-to-leader personal enemies (mutual, symmetric). Grudges are directional (loser → winner) and affect action weights. They stack when both apply.

**Great person interaction**: a general whose civ has a grudge gets +2 military modifier in wars against the grudge target civ (stacks with the base +10). Narratively: "General Khotun, whose people still remembered the humiliation at Ashenmoor, fought with particular fury."

### 3.2 Character Relationships

Lightweight pairwise system. No relationship graph — just modifiers on relevant events.

**Storage** (on `WorldState`):
```python
character_relationships: list[dict] = []
# Each: {"type": str, "person_a": str, "person_b": str, "civ_a": str, "civ_b": str, "formed_turn": int}
```

**Three relationship types**:

#### Rivalry
- **Formation**: both civs at war AND both have active generals (civ-level check, not region-specific). Same for merchants on overlapping trade routes, prophets championing opposing movements.
- **Effect**: when they directly oppose each other, resulting named event importance +2 ("The Duel of Generals" rather than just "Battle of...")
- **Death of one**: survivor gains a deed, +0.05 asabiya for survivor's civ
- **Dissolution**: on death or retirement of either party

#### Mentorship
- **Formation**: a great person exists when a leader of the same civ gains a compatible secondary_trait (scientist + builder/merchant, general + conqueror/warlike)
- **Effect**: leader's secondary_trait action weight bonus increased from ×1.3 to ×1.6 while mentor lives
- **On mentor death**: leader gains a deed ("Inherited the teachings of {mentor}")
- **Max 1 mentorship per leader**

#### Marriage Alliance
- **Formation**: two civs ALLIED for 10+ turns AND both have at least one great person. One-shot check per alliance, 30% chance.
- **Effect**: disposition floor at NEUTRAL between the two civs (can't drop below NEUTRAL while both persons live). Prevents hostility but doesn't lock in perpetual friendship.
- **Dissolution**: WAR action auto-dissolves the marriage. Manual dissolution costs stability -3 for the initiator.
- **Death of either spouse**: floor removed, disposition drifts normally. Named event generated.
- **One marriage per great person**. Marriage crosses role types (general can marry merchant from another civ).

### 3.3 Hostage Exchanges

After a peace treaty where the attacker lost, the losing civ sends a named character to the winner.

**Selection**: youngest great person from losing civ. If no great persons exist, a generic hostage is created (name from cultural pool, role="hostage", minimal mechanical effect — culture +1/turn for captor instead of +3).

**Placement**: hostage placed in the contested region (the front), not the captor's capital.

**Hostage mechanics**:
- `is_hostage=True`, `hostage_turns` increments each turn (Phase 2)
- Modifier effects **suspended** while hostage — they don't benefit the captor (prisoner, not recruit)
- Captor gains: culture +3/turn while holding a great person hostage (prestige of holding a noble prisoner)
- After 10 hostage turns: `cultural_identity` shifts to captor's civ name

**Release conditions**:
- Automatic after 15 turns (ransom assumed — costs origin civ 10 treasury if available, free otherwise)
- Early release via DIPLOMACY action (costs 15 treasury)
- Recapture: if captor loses the region the hostage is in during war

**Culturally converted hostage** (released after 10+ turns):
- `cultural_identity` set to captor's civ name
- If they later become a leader through succession (using the 20% any-great-person entry from Section 2.3): disposition +1 level toward former captor, trait influenced by captor's cultural values (50% chance of gaining a trait aligned with captor's values instead of normal succession pool)
- This is the "raised by the enemy" pipeline — cross-cultural pollination through the mechanism historically designed to prevent it

**Capture/hostage hook location**: these are war consequences, processed in Phase 5 immediately after `resolve_war` returns `attacker_wins`/`defender_wins`, alongside territorial changes and vassalization decisions.

---

## 4. Institutional Memory (Traditions)

Traditions are permanent civ-wide modifiers that crystallize from repeated historical patterns. A civ earns its identity through what it survives.

### 4.1 Storage

```python
# On Civilization
traditions: list[str] = []             # active tradition names
legacy_counts: dict[str, int] = {}     # tracks legacy condition firings across leaders
event_counts: dict[str, int] = {}      # tracks raw event counts (war_wins, famines_survived, etc.)
```

`event_counts` is a general-purpose counter, incremented on relevant events. Extensible for M18 without model changes.

### 4.2 Tradition Catalog

| Tradition | Direct Trigger | Crystallization Trigger | Effect |
|-----------|---------------|------------------------|--------|
| **Food Stockpiling** | `event_counts["famines_survived"] >= 3` | `legacy_counts["golden_age"] >= 2` (prosperity teaches saving) | Fertility floor 0.2 in all controlled regions (never below) |
| **Martial** | `event_counts["wars_won"] >= 5` | `legacy_counts["military"] >= 3` (three war-leaders forged a military culture) | Military +5 permanent; all neighbors' disposition drift -1 level/10 turns (fear) |
| **Diplomatic** | `event_counts["federation_turns"] >= 30` | `legacy_counts["fracture"] >= 2` (two secessions taught consensus) | Federation stability bonus +5; federation dissolution penalty reduced from -15 to -10 |
| **Resilience** | Capital lost and recovered (at least once) | `legacy_counts["shame"] >= 3` (three leaders lost and reclaimed the capital) | Stability recovery rate ×2 (stability gains from actions doubled) |

**Two-path acquisition**: direct triggers fire from cumulative events; crystallization fires from repeated legacy conditions across leader generations. Whichever fires first grants the tradition. No double-granting.

### 4.3 Tradition Interactions

**With succession crises**: Martial and Resilience both suppress crisis probability (×0.8 multiplicative, as specified in Section 2.1).

**With great person generation**: Martial tradition reduces general cooldown slightly (18 turns instead of 20). Diplomatic tradition does the same for merchants. Subtle bias, not dramatic.

**With action weights**: permanent biases — Martial → WAR ×1.2, Diplomatic → DIPLOMACY ×1.2, Resilience → DEVELOP ×1.1, Food Stockpiling → BUILD ×1.1 (irrigation preference).

**With narrative**: traditions stored on `CivSnapshot` for the narrative engine. "The Karthari, a people forged by famine and loss, had learned to stockpile grain..."

### 4.4 Constraints

- Max 4 traditions per civ (one of each type). No duplicates.
- Traditions are **permanent** — once earned, never lost.
- **Inheritance through secession**: breakaway civs inherit the parent's traditions (they share the cultural memory).
- Tradition checks run in Phase 10 (consequences), only when a relevant event has occurred that turn. Not every turn.

---

## 5. Capstone Systems

### 5.1 Patron Saints and Folk Heroes

When a great person or leader dies dramatically, they have a chance to become a folk hero — a permanent mark on the civ's identity.

**Dramatic death** (clear boolean):
- Death during war resolution (Phase 5)
- Death during natural disaster event (Phase 7)
- Death during succession crisis (Phase 8)
- Non-dramatic: all other deaths. Lifespan expiry is always retirement, never death — these are mutually exclusive fates.

**Folk hero roll**: 20% chance on dramatic death. Deterministic from `seed + death_turn + hash(name)`.

**Storage** (on `Civilization`):
```python
folk_heroes: list[dict] = []
# Each: {"name": str, "role": str, "death_turn": int, "death_context": str}
```

**Effects** (permanent):
- Asabiya +0.03 per folk hero (stacking)
- **Cultural name pool bias**: future great persons have ×1.3 probability of spawning with the folk hero's role. Base distribution is equal 25% per role; each folk hero applies ×1.3 to its role, then renormalized. Two military folk heroes: general probability = `25% × 1.3 × 1.3 = 42.25%`, renormalized.
- **Narrative weight**: folk heroes appear in chronicle prompts as "remembered figures," referenced across centuries

**Cap**: max 5 folk heroes per civ. Beyond 5, oldest folk hero's asabiya bonus is removed (memory fades) but name pool bias persists (cultural identity is deeper than living memory). Prevents asabiya from stacking to absurd levels over 500 turns.

### 5.2 Prophet Martyrdom

When a prophet dies dramatically and becomes a folk hero:
- The movement they championed gets permanent +0.1 adoption probability bonus in the prophet's civ (martyrdom effect)
- If the movement later schisms, the folk hero's civ's variant becomes the "orthodox" variant narratively (named event: "The Martyrdom of {prophet} defined the true faith")
- Other civs with the same movement: +1 disposition level toward the folk hero's civ (one-time, on folk hero creation)

### 5.3 Emergent Identity Feedback

Folk heroes and traditions stack naturally to create civilizational identity without explicit scripting:
- A civ with Martial tradition + 2 military folk heroes: high asabiya, biased toward war, feared by neighbors, producing generals at an accelerated rate
- A civ with Diplomatic tradition + prophet folk heroes: federation-oriented, movement-spreading, culturally influential
- These identities emerge from the civ's actual history — the spec does not code these interactions explicitly. The individual systems compose naturally.

---

## 6. Turn Loop Integration

### 6.1 Phase Placement

No new phases. M17 hooks into existing phases:

| Phase | M17 Work | Rationale |
|-------|----------|-----------|
| **Phase 2: Automatic Effects** | Hostage turn counter increment. Exile pretender stability drain (-2/turn, found by scanning all civs for `role="exile"`). Hostage cultural identity shift check (10 turns). | Passive per-turn effects alongside military maintenance, trade income. |
| **Phase 5: Action Resolution** | Great person modifiers consumed during action selection (grudge WAR weight, tradition biases) and resolution (general +10, merchant +3, scientist -30%). Candidate backing during succession crisis (DIPLOMACY sub-action). Extradition demand (DIPLOMACY sub-action). **Character capture and hostage exchange** as war consequences, immediately after `resolve_war` returns outcome. | Action selection applies weight biases first, then resolution applies modifiers. Both happen within Phase 5. |
| **Phase 8: Leader Dynamics** | Succession crisis trigger and resolution. General-to-leader conversion. Any-great-person succession entry. Exiled leader creation. Legacy condition firing → `legacy_counts` increment. Mentorship formation check. | Extends existing leader dynamics. Crisis is multi-turn state. |
| **Phase 10: Consequences** | Great person generation, lifespan expiry, folk hero checks, relationship checks, exile restoration, tradition checks. | Achievement checks need full turn state. Death/retirement at end of turn prevents mid-turn modifier inconsistency. |

### 6.2 Phase 10 Internal Ordering

Within Phase 10, M17 consequences execute in this specific order:

1. **Event counts update** — increment `war_wins`, `famines_survived`, etc. from this turn's events
2. **Great person generation** — check achievement thresholds, spawn if met (respects cooldowns, catch-up)
3. **Prophet movement acceleration** — accelerate spread for active prophets
4. **Relationship checks** — rivalry formation, mentorship formation, marriage alliance formation
5. **Exile restoration check** — fires before lifespan expiry (exile might restore before dying)
6. **Lifespan expiry** — retire characters past their lifespan (always retirement, never death)
7. **Folk hero check** — runs on dramatic deaths from earlier phases only (war Phase 5, disasters Phase 7, succession Phase 8). NOT on retirements from step 6.
8. **Tradition checks** — crystallization from `legacy_counts`, direct triggers from `event_counts`

### 6.3 Succession Crisis as Multi-Turn State

```python
# On Civilization
succession_crisis_turns_remaining: int = 0  # 0 = no crisis
succession_candidates: list[dict] = []       # [{"backer_civ": str, "type": str}]
```

- **Turn 0** (leader dies, crisis triggers): `turns_remaining` set to 3-5. Stability -10. Named event fires.
- **Turns 1-N**: action effectiveness ×0.5. Other civs can back candidates (10 treasury/turn).
- **Final turn**: crisis resolves. New leader created based on backing. Disposition adjustments applied.
- **Nested crisis**: if another leader death occurs during a crisis, extends by 2 turns, stability -5 additional.

---

## 7. Data Model Changes Summary

### On `Civilization` (new fields)

```python
great_persons: list[GreatPerson] = []
traditions: list[str] = []
legacy_counts: dict[str, int] = {}
event_counts: dict[str, int] = {}
folk_heroes: list[dict] = []
succession_crisis_turns_remaining: int = 0
succession_candidates: list[dict] = []
```

### On `Leader` (new fields)

```python
grudges: list[dict] = []
```

### On `WorldState` (new fields)

```python
retired_persons: list[GreatPerson] = []
character_relationships: list[dict] = []
great_person_cooldowns: dict[str, dict[str, int]] = {}  # {civ_name: {role: last_spawn_turn}}
```

### New model: `GreatPerson` (Section 1.1)

### On `CivSnapshot` (for viewer/narrative)

```python
great_persons: list[dict] = []   # active roster summary
traditions: list[str] = []
folk_heroes: list[str] = []      # names only
active_crisis: bool = False
```

---

## 8. Implementation Phasing

Ordered so each phase builds on the previous with no forward references:

### M17a — Character Foundation (~300 lines code, ~300-350 lines tests)
- `GreatPerson` model + all new fields on Civilization, WorldState, CivSnapshot
- Achievement-triggered generation with cooldowns, catch-up discount, dual scientist trigger
- Lifecycle: lifespan expiry → retirement, death as separate fate
- Modifier registry with `get_modifiers(civ, domain)` — domain-tagged, on-the-fly computation
- Phase 10 hooks for generation and retirement
- **Tests**: spawn thresholds (each type), cooldown enforcement, catch-up discount, 50-cap per-civ eviction, modifier application per domain, role distribution with folk hero bias (math verification), lifespan determinism

### M17b — Succession & Grudges (~250 lines code, ~300-350 lines tests)
- State-driven succession crisis formula (floor 0.05, cap 0.40, multiplicative modifiers)
- Multi-turn crisis state machine (action effectiveness halving, candidate backing)
- General-to-leader conversion (`fate="ascended"`, Leader creation, reign=0 intentional)
- Any-great-person succession entry at 20%
- Personal grudges on Leader (inheritance 50%, 2× decay after target death)
- Exiled leaders (role="exile", pretender drain, extradition, restoration check)
- Legacy expansion (golden age, shame, fracture memories) + `legacy_counts` tracking
- Phase 2 hooks (exile drain), Phase 8 hooks (crisis trigger/resolution)
- **Tests**: crisis probability under various state combinations, crisis multi-turn resolution, general ascension mechanics, grudge decay curves (normal vs post-death), grudge inheritance math, exile restoration probability over time, legacy condition firing, nested crisis handling

### M17c — Character Interactions (~200 lines code, ~300-350 lines tests)
- Rivalries (auto-formation boolean, importance boost, death-of-rival deed)
- Mentorships (formation condition, action weight boost, mentor death deed)
- Marriage alliances (NEUTRAL floor, WAR auto-dissolve, stability -3 manual dissolve)
- Hostage exchanges (capture in Phase 5 war aftermath, cultural conversion at 10 turns, release at 15, modifier suspension)
- Recapture mechanics (region-specific)
- **Tests**: rivalry formation conditions (each type), mentorship formation and effect, marriage floor enforcement and dissolution, hostage turn counter and cultural shift, hostage release (auto/early/recapture), captured character modifier suspension

### M17d — Institutional Memory & Capstone (~200 lines code, ~300-350 lines tests)
- `event_counts` tracking (war_wins, famines_survived, federation_turns, capital_recoveries)
- Traditions: 4 types, direct triggers, crystallization from legacy_counts, two-path deduplication
- Folk heroes: dramatic death boolean, 20% roll, permanent asabiya +0.03, role bias ×1.3
- Prophet martyrdom → movement adoption bonus, orthodoxy naming, disposition +1 level
- Tradition inheritance through secession
- Snapshot integration for narrative engine
- **Tests**: tradition triggers (both paths for each type), no double-granting, tradition effects on crisis/generation/action weights, folk hero generation conditions, asabiya stacking and 5-cap oldest-fade, role bias math (renormalization), prophet martyrdom effects, tradition inheritance through secession

---

## 9. Performance and Compatibility

**Performance**: great person roster is small per civ (typically 2-5 active). `get_modifiers()` iterates a tiny list — negligible cost. Tradition and folk hero checks are event-gated, not per-turn. 50-character global cap ensures bounded memory. No performance concerns at 500 turns × 10 civs.

**Scenario compatibility**: all new fields have sensible defaults (empty lists, zero counters). Existing scenarios work without modification — civs simply start with no great persons, no traditions, no folk heroes.

**Narrative engine**: `CivSnapshot` additions provide structured data for chronicle prompts. No new LLM capabilities needed — just richer context about active characters, traditions, and folk heroes.
