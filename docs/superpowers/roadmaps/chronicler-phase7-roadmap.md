# Chronicler Phase 7 — Deep Society: Saturating the Hardware

> **Status:** Draft. Phase 6 architecture finalized through M45. M47 tuning pass outstanding — affects calibration baselines, not Phase 7 structure.
>
> **Phoebe + Cici review (2026-03-19):** 6 blocking issues, 11 observations. Key changes: M54 split into M54a/b/c, M50 architecture gap flagged, M53 cohort validation adjusted, RNG stream offsets reserved, 2.5x cap revision noted for Phase 8. See inline `[REVIEW]` tags.
>
> **Phase 6 prerequisite:** M47 tuning pass landed. M47 validates Phase 6 system interactions before Phase 7 adds new layers.
>
> **Structural principle:** Depth first, then scale. Ship agent interiority at current agent counts (10-50K), validate emergent behaviors, then parallelize and scale to 500K-1M. Calibrating new mechanics and validating parallel correctness simultaneously is too many variables.
>
> **Inspiration sources:** Turchin's metaethnic frontier theory (spatial asabiya), BioDynaMo HPC research (cache-efficient agent iteration), Project Psychohistory (Mule outlier individuals), hybrid SD/ABM coupling research (perception lag formalization). See `docs/superpowers/phase7-inspiration-amendments.md` for full thread analysis.

---

## Why Deep Society

Phase 6 gives agents traits, values, beliefs, wealth, relationships, and occupations. But they have no memory — a soldier who survived three wars is identical to one who's never fought. They have no inner motivation beyond satisfaction — a prosperous merchant has no unmet spiritual need driving him to the temple. Their relationships are typed edges, not lived bonds with sentiment that drifts through shared experience. The land beneath them is abstract — a region is a bucket of agents, not a place with neighborhoods, markets, and walls.

Phase 7 gives agents inner lives and puts them in space. Five capabilities that Phase 6 structurally cannot deliver:

1. **Agent memory.** A farmer remembers the famine. A convert remembers persecution. A general remembers the battle where his rival betrayed him. Memory feeds grudges, gratitude, trauma, and pride — turning agents from stateless reactors into beings shaped by their past.

2. **Individual motivation.** Satisfaction measures how well an agent is doing. Needs measure what an agent is missing. A wealthy merchant with high satisfaction but unmet spiritual need seeks the temple. A safe but isolated scholar seeks community. Needs create behavioral diversity among identical-stat agents — the missing ingredient for emergent culture.

3. **Lived relationships.** Phase 6 social edges are typed and static between formation events. Phase 7 relationships have sentiment that drifts through shared experience — co-survivors bond, competitors develop grudges, friends who end up on opposite sides of a schism lose trust. The social graph becomes dynamic and emotionally grounded.

4. **Spatial awareness.** Agents exist at positions within regions. Proximity drives disease, trade, social influence, and clustering. Dense clusters become proto-cities with urban economics. Sparse areas remain rural. Geography stops being a stat block and becomes a lived landscape.

5. **Multi-generational memory.** Dynasties remember ancestral grievances. A war started because of an execution three generations ago. Inherited grudges and inherited pride create narrative arcs spanning the entire chronicle.

These five capabilities are designed as separate systems, but their most important product is **emergent** — see "Cross-System Interaction: Emergent Cohorts" below M50.

---

## Milestone Overview

Two tracks: **Depth** (M48-M53, agent interiority at current scale) and **Scale** (M54-M59, parallelism and spatial systems at 500K-1M agents). Depth track validates before scale track begins.

| # | Milestone | Track | Depends On | Est. Days |
|---|-----------|-------|------------|-----------|
| M48 | Agent Memory | Depth | M47 | 6-8 |
| M49 | Needs System | Depth | M48 | 5-7 |
| M50 | Deep Relationships | Depth | M48, M40 | 5-7 |
| M51 | Multi-Generational Memory | Depth | M48, M39 | 4-5 |
| M52 | Artifacts & Significant Items | Depth | M48 | 3.5-4.5 |
| M53 | Depth Tuning Pass | Depth | M48-M52 | 4-6 |
| M54a | Rust Ecology Migration | Scale | M53 | 8-11 |
| M54b | Rust Economy Migration | Scale | M54a | 10-14 |
| M54c | Rust Politics Migration + Spatial Sort | Scale | M54a | 7-11 |
| M55 | Spatial Positioning | Scale | M54a-c | 6-8 |
| M56 | Settlement Emergence | Scale | M55 | 5-7 |
| M57 | Marriage & Households | Scale | M50, M55 | 5-7 |
| M58 | Agent-Level Trade | Scale | M55, M42-M43 | 5-7 |
| M59 | Information Propagation | Scale | M50, M55 | 4-6 |
| M60 | Military Units | Scale | M55 | 5-7 |
| M61 | Scale Tuning Pass | Scale | M54a-c, M55-M60 | 5-8 |
| M62 | Phase 7 Viewer | Both | M61 | 7-9 |

**Total estimate:** 102-140 days across 17 milestones. `[REVIEW]` Revised from 100-132 — M54 split adds checkpoint overhead but no net scope change. Realistic estimate including enrichment pull-in, integration cost, and session overhead: **115-155 days**. No contingency buffer; plan operationally for milestone reviews every 2-3 milestones with scope cuts if needed.

---

## Depth Track (M48-M53)

### M48: Agent Memory

**Goal:** Give each agent a ring buffer of recent experiences with emotional valence and decay, feeding into satisfaction, decision utility, relationship formation, and narration. Includes Mule promotion detection for history-bending outlier characters.

**Storage:** 8-slot ring buffer per agent, SoA in Rust pool. `[CALIBRATE]` range: 6-8 slots.

```
event_type: u8    — what happened (famine, battle, persecution, migration, promotion, ...)
actor_id: u16     — who was involved (civ, named character, or self)
turn: u16         — when it happened
intensity: i8     — emotional weight (-128 to 127, positive = good, negative = bad)
decay_rate: u8    — how fast it fades (0 = permanent, 255 = gone next tick)
```

8 bytes × 8 slots = 64 bytes/agent. At 50K agents = 3.2MB. Trivial.

**Why 8 slots, not 4:** An agent who fights a battle, endures a famine, gets persecuted, and migrates has filled 4 slots in 4 turns. M51 writes 2 legacy memories into children's buffers at birth — a child of a significant parent would start with only 2 free slots for their entire life at 4-slot capacity. That's not "shaped by the past" — it's "past crowds out the present." 8 slots gives agents room to accumulate enough lived experience for cohort dynamics (shared memories → bond eligibility → collective behavior) to form. The memory budget difference is 32 bytes/agent — 32MB at 1M agents, negligible against 192GB DDR5.

**Tick integration:**
- Memories decay each tick: `intensity = intensity × (1.0 - decay_rate / 255.0)` (with integer approximation)
- Memories below intensity threshold are eligible for overwrite by new events
- New events written by: demographics (birth/death of kin), behavior (battle participation, migration), conversion tick (faith change), satisfaction (famine/prosperity thresholds)

> `[REVIEW]` **Memory decay non-linearity.** The per-tick multiplier formula has a sharp knee: `decay_rate=128` → intensity halves every tick (forgotten in ~7 ticks). `decay_rate=25` → halves every ~7 ticks (forgotten in ~50). Most of the 0-255 range produces either "instantly forgotten" or "permanent." Consider half-life parameterization in the M48 spec — store `half_life_turns: u8` and derive the per-tick factor, giving more intuitive tuning: "this memory fades over ~20 turns" instead of "decay_rate 25."

**Behavioral effects:**
- Satisfaction modifier: sum of active memory intensities × `MEMORY_SATISFACTION_WEIGHT` `[CALIBRATE]`
- Decision utility modifier: specific event types shift specific action utilities (battle memory → modified WAR utility, famine memory → increased DEVELOP/TRADE utility)
- Relationship formation input: shared memories (same event_type + turn + region) → bond eligibility in M50

**Narration exposure:**
- Top memories for named characters included in narrator context
- "General Kiran, who remembers the siege of Ashfall and the betrayal at the river crossing..."

**Event type registry:** Enumerate all memory-eligible events. Keep the list small (~12-16 types). Each type has a default intensity and decay rate. The registry lives in `agent.rs` alongside constants.

> **Enrichment (from Stanford Generative Agents research):** Three insights from the generative_agents memory architecture that refine M48 design:
>
> 1. **Eviction by lowest (recency × importance), not pure FIFO.** Stanford's unbounded memory uses implicit decay (old memories are less likely to be retrieved), but Chronicler's 8-slot ring buffer must explicitly evict. Pure age-based overwrite loses intense old memories (a formative famine) to trivial recent events (a routine harvest). Eviction score = `turns_since_event × (1 / abs(intensity))` — high score = old AND weak = evict first. Intense old memories survive; weak recent ones get overwritten. One comparison per slot on write (~8 ops), negligible.
>
> 2. **Importance-budget reflection trigger.** Rather than synthesizing memories on a fixed schedule, accumulate intensity of incoming events and trigger synthesis when the budget depletes. High-drama periods (war, famine, persecution) burn through the budget fast and trigger frequent synthesis; quiet periods don't. For M48, this maps to: when cumulative intensity of new memories since last synthesis exceeds `MEMORY_SYNTHESIS_BUDGET` `[CALIBRATE]`, compute a deterministic "assessment" (e.g., update relationship sentiment toward involved actors, adjust need weights). No LLM needed — structured synthesis from structured data.
>
> 3. **Three-factor retrieval weighting.** Stanford weights retrieval as recency:relevance:importance = 0.5:3:2 — relevance dominates 6:1 over recency. For M48's narrator context selection (which memories to expose for named characters), this means: prioritize memories relevant to the current curated moment (same region, same actors, same event type) over merely recent ones. The narrator should hear about "General Kiran remembers the siege" when narrating a battle, not "General Kiran remembers last month's harvest."
>
> Source: joonspk-research/generative_agents. Full analysis in `docs/superpowers/references/external-repo-catalog.md`.
>
> **Phoebe disposition (2026-03-19):** Enrichment 1 (eviction) → M53 calibration candidate, deferred from M48 (protects Mule-eligible memories). Enrichment 2 (importance-budget synthesis) → deferred to M50+ (depends on relationship system and needs system as output targets, not M48 scope). Enrichment 3 (retrieval weighting) → deferred narration refinement, can land anytime without simulation changes.

> **Enrichment (not in estimate, from Minerva research):** **Generalize Mule's acquired-trait pattern to all GreatPersons.** The Mule system is a special case of a general pattern: simulation events → acquired traits → mechanical effects. Minerva (ShiJbey/minerva) implements this as rule-based queries over event history: "won 3 wars → Warlike trait → +martial modifier + WAR proclivity." With M48's memory ring buffer, Chronicler has the event history substrate to support this. Implementation: after arc classification in Phase 10, run a set of trait acquisition rules against each GreatPerson's memory buffer and deed history. Example rules: 3+ Battle memories → `battle_hardened` trait (+0.1 WAR utility for civ); 2+ Famine memories → `bitter` trait (+0.1 FUND_INSTABILITY); Prosperity + Victory dominant → `golden_age_leader` (+0.1 DEVELOP, INVEST_CULTURE). Each trait carries a typed modifier stack (like Mule's `utility_overrides` but generalized) with conflicting-trait constraints (battle_hardened conflicts with pacifist). Trait inheritance via `inheritance_chance` feeds M51's multi-generational memory. This turns M45's narrative-only arcs into mechanically meaningful character development. The Mule becomes the extreme case (rare, high-magnitude) of a general system where all GreatPersons accumulate softer traits from their lived experience. Source: ShiJbey/minerva `acquired_trait_system.py`, Cellule/npc-generator weighted-table-with-side-effects pattern.

**Phase 6 dependency check:** M48 reads from existing Phase 6 systems (demographics, behavior, conversion) but doesn't modify them. It's additive — existing satisfaction and utility computations gain a memory term, they don't restructure.

#### Mule Promotions

**Concept:** Rare outlier individuals whose decision model is warped by their dominant memory, producing historically improbable actions that bend the simulation's trajectory during a dramatic window of influence. Inspired by Asimov's Mule — unpredictability from a *person*, not an event (emergence.py handles event-level black swans).

**Trigger:** When `_process_promotions` creates a new GreatPerson, roll against `MULE_PROMOTION_PROBABILITY` `[CALIBRATE]` (target: 5-10%). On success, the GreatPerson receives a `mule: bool` flag.

**Memory-driven utility overrides:** Extract the agent's strongest memory (highest absolute intensity) from the ring buffer at promotion time. The memory's event type determines which civ-level action weights the Mule modifies:

- General whose dominant memory is famine → DEVELOP and TRADE weight boosted, WAR weight suppressed
- Merchant whose dominant memory is persecution → FUND_INSTABILITY weight boosted, TRADE weight suppressed
- Priest whose dominant memory is conquest → WAR weight boosted, INVEST_CULTURE weight suppressed

The mapping is an explicit `event_type → ActionType` table (~8 entries, covering the emotionally intense event types: famine, battle, persecution, conquest, migration, schism, epidemic, exile). Not every event type produces a Mule variant.

**Storage:** New fields on GreatPerson: `utility_overrides: dict[ActionType, float]`, `mule: bool`. Written once at promotion. Python-side — GreatPersons are low-volume named characters. The active window is computed from `born_turn` (which is the promotion turn for GreatPersons).

**Mechanism — time-bounded weight modifier:** The Mule's overrides feed into the civ-level action engine as an additional weight modifier, using the same architecture as factions and tech focus. The Mule's influence is **time-bounded**:

- **Active window** (`MULE_ACTIVE_WINDOW` `[CALIBRATE]`, target: 20-30 turns post-promotion): full modifier. The Mule's preferred action receives at least `MULE_UTILITY_FLOOR` `[CALIBRATE]` (target: 0.5-0.8) additive weight. Suppressed actions receive a negative modifier (clamped so total weight cannot go below 0.1x). The combined action weight multiplier cap (2.5x) still applies.
- **Fade period** (`MULE_FADE_TURNS` `[CALIBRATE]`, target: ~10 turns): modifier scales linearly from full to zero. Institutions adapt. The character ages. The urgency fades.
- **After fade:** overrides zeroed. The character remains a GreatPerson but no longer distorts civ action weights.

**Why time-bounded, not permanent:** Asimov's Mule doesn't nudge — he warps. A permanent 0.3 additive weight on one action in an 11-action space is a 30-60% increase that's barely detectable in the action distribution. A 0.5-0.8 weight for 20-30 turns creates a dramatic, narratively visible window where the Mule reshapes their civilization's direction — then the system absorbs the shock and normalizes. The curator flags the active window as a high-priority narrative arc.

**Why weight modifier, not action override:** Action selection is civ-level (Phase 8, `action_engine.py`). Individual characters don't select actions — civilizations do. The Mule nudges civ behavior through the existing weight system rather than requiring a new per-character action resolution path.

**Frequency math:** At 50K agents, expect ~5-15 GreatPerson promotions per 100 turns. At 5-10% Mule rate, that's ~0-1 Mules per 100 turns. One Mule per era is the right frequency for a history-bending individual.

**Narration exposure:** Mule characters are high-priority targets for the curator pipeline. The narrator context includes the memory that warped them and the active window's remaining turns: "General Ashani, who never forgot the great famine of her youth, turned the army's swords into plowshares and authored the agricultural reforms that fed the empire for a generation."

**Determinism:** The Mule's "unpredictability" comes from the unusual combination of memory and role, not from extra randomness. Given the same seed, the same agent is promoted, has the same dominant memory, and receives the same utility overrides.

> **Enrichment (not in estimate, from Minerva research):** **Generalize Mule's acquired-trait pattern to all GreatPersons.** The Mule system is a special case of a general pattern: simulation events → acquired traits → mechanical effects. Minerva (ShiJbey/minerva) implements this as rule-based queries over event history: "won 3 wars → Warlike trait → +martial modifier + WAR proclivity." With M48's memory ring buffer, Chronicler has the event history substrate to support this. Implementation: after arc classification in Phase 10, run a set of trait acquisition rules against each GreatPerson's memory buffer and deed history. Example rules: 3+ Battle memories → `battle_hardened` trait (+0.1 WAR utility for civ); 2+ Famine memories → `bitter` trait (+0.1 FUND_INSTABILITY); Prosperity + Victory dominant → `golden_age_leader` (+0.1 DEVELOP, INVEST_CULTURE). Each trait carries a typed modifier stack (like Mule's `utility_overrides` but generalized) with conflicting-trait constraints (battle_hardened conflicts with pacifist). Trait inheritance via `inheritance_chance` feeds M51's multi-generational memory. This turns M45's narrative-only arcs into mechanically meaningful character development. The Mule becomes the extreme case (rare, high-magnitude) of a general system where all GreatPersons accumulate softer traits from their lived experience. Source: ShiJbey/minerva `acquired_trait_system.py`, Cellule/npc-generator weighted-table-with-side-effects pattern.

---

### M49: Needs System

**Goal:** 6 needs as per-agent floats that decay per tick and are restored by conditions, creating individual motivation distinct from satisfaction.

**Storage:** 6 × f32 = 24 bytes/agent (reduced from the 8-need sketch — 6 is sufficient, avoids tuning an 8-dimensional space).

| Need | Decay Source | Restoration |
|------|-------------|-------------|
| Safety | Constant slow decay | No war, no persecution, high loyalty region |
| Material | Constant slow decay | Wealth above threshold, food sufficiency > 1.0 |
| Social | Constant slow decay | Relationships exist (M50), high region population |
| Spiritual | Constant slow decay | Temple in region (M38a), same-faith majority |
| Autonomy | Constant slow decay | Not in conquered region, not persecuted minority |
| Purpose | Constant slow decay | Active in meaningful occupation (scholar researching, soldier at war, merchant trading profitably) |

**Behavioral effects:**
- Unmet needs shift utility weights. A spiritually starved agent overvalues temple-building regions (migration pull). A socially isolated agent resists migration away from populated areas.
- Needs modify occupation switching thresholds — an agent with unmet material need is more likely to switch to a profitable occupation.
- Needs do NOT directly affect satisfaction. Satisfaction remains the aggregate well-being metric. Needs influence *decisions*, not *state*.

**Design distinction — orthogonality resolved:** Satisfaction = "how am I doing?" Needs = "what am I missing?" The two systems are mechanically orthogonal — they combine in the decision function, not in the satisfaction formula. The Rust satisfaction formula is unchanged.

A "content but spiritually adrift" merchant is a valid simulation state. The tension between external prosperity and inner emptiness is one of the most compelling character dynamics a narrator can work with. The resolution: **expose need state to the narrator alongside satisfaction for named characters.** The narrator decides salience — same pattern as M40 relationships, M43b trade dependency. No mechanical coupling needed. The risk of incoherence exists only if the narrator can't see the need state, so we make sure it can.

**Perception model — perfect regional knowledge:** M49 assumes agents have immediate knowledge of their own region's conditions: food sufficiency, temple presence, war status, etc. Agents know everything about their own region instantly, nothing about other regions. This is correct for the depth track where the goal is to validate needs mechanics against satisfaction at current scale. M59 (Information Propagation) later adds realistic perception lag for cross-region knowledge — calibrate the response before adding the delay.

**Constants:** 6 decay rates + ~18 restoration conditions = ~24 `[CALIBRATE]` constants. Tuned in M53.

---

### M50: Deep Relationships

**Goal:** Extend M40's named-character social edges to per-agent relationship storage with sentiment drift, replacing typed edges with lived bonds.

**Storage:** 8 relationship slots per agent, packed SoA.

```
target_id: u32    — who
sentiment: i8     — how they feel (-128 hate to 127 love)
bond_type: u8     — kin, mentor, rival, friend, co-religionist, grudge
```

6 bytes × 8 slots = 48 bytes/agent. At 50K agents = 2.4MB.

**Relationship to M40:** M40 social edges are named-character-only, Python-side, event-driven formation. M50 extends relationships to all agents, Rust-side, with continuous sentiment drift. M40's edge types (Mentor, Rival, Marriage, ExileBond, CoReligionist) map directly to M50 bond types. The M40 Python-side graph becomes a view layer over M50's Rust-side storage for named characters.

> `[REVIEW B-2]` **Architecture gap — three open design questions for M50 spec:**
>
> 1. **Formation/dissolution interface.** Current M40 uses `replace_social_edges()` (full Arrow graph replacement each turn). At 500K agents × 8 slots × 6 bytes = 24MB, full replacement per turn is too expensive. M50 relationships must live permanently in Rust with incremental updates. The M50 spec must define whether Python sends formation/dissolution commands (signals) or Rust owns formation logic entirely (requires access to event types, faith assignments, etc.).
>
> 2. **Hidden M55 dependency.** "Shared region" formation triggers fire for every co-located agent pair. At 500 agents/region, that's 125K pairs per region per tick — O(N²). This is expensive at 50K agents without spatial partitioning. M55's spatial hash would fix this (only check nearby agents), but M50 is in the Depth track (before M55). The M50 spec must either: (a) use a coarser proximity proxy (agent index within region), (b) run formation checks every N ticks instead of every tick, or (c) accept O(N²) at Depth scale and optimize when M55 lands.
>
> 3. **M40 transition plan.** Python-side formation logic in `relationships.py` (`form_and_sync_relationships()` coordinator, rivalry/mentorship/marriage/exile/co-religionist functions) depends on world state not available in Rust. Define whether this logic migrates to Rust, becomes a signal-based command interface, or stays Python-side with only storage moving to Rust.

**Formation triggers:**
- Shared region + shared memory (M48) → friend or grudge (depending on event valence)
- Kin detection via M39 parent_id → kin bond (automatic)
- Same belief in minority-faith region → co-religionist
- Wealth differential in same region → rival (if competitive personalities)
- Age gap + same occupation + same region → mentor (mirrors M40 logic)

**Sentiment drift:**
- Co-located bonds strengthen slowly (+1/turn when in same region)
- Separated bonds decay slowly (-1/turn when in different regions)
- Shared positive events boost sentiment
- Shared negative events (famine, persecution) can either boost (trauma bond) or reduce (blame) depending on personality traits

**Slot management:** When all 8 slots are full and a new bond forms, weakest sentiment bond is evicted. This naturally prunes stale relationships and keeps the strongest connections active.

**Narrative payoff:** "The merchant Hala, whose childhood friend now commands the army besieging her city..." — relationships that formed organically through shared experience, now in conflict.

> **Enrichment (not in estimate, from generative_agents research):** **Importance-budget synthesis trigger.** Rather than checking bond formation on a fixed schedule or every tick, accumulate the intensity of incoming M48 memories and trigger a synthesis pass when the budget depletes. New per-agent field: `synthesis_budget: u8` (starts at `SYNTHESIS_BUDGET_MAX` `[CALIBRATE]`, decremented by each new memory's `|intensity|`). When budget hits 0: scan the agent's memory buffer, compute a deterministic assessment of each source_civ (sum of signed intensities from memories involving that civ → net disposition), and use this as a bond formation/dissolution input. High-drama periods (war, famine, persecution) burn through the budget fast and trigger frequent reassessment; quiet periods don't waste compute. No LLM needed — structured synthesis from structured data. The budget creates natural "moments of reflection" that are themselves narratively interesting ("after the third famine, the people's loyalty finally broke"). ~1 byte/agent + ~20 lines Rust. Source: joonspk-research/generative_agents reflection trigger (adapted from LLM-driven to deterministic).
>
> **Enrichment (not in estimate, from Axelrod research):** **Similarity-gated bond formation probability.** Instead of uniform formation probability for co-located agents, scale bond formation chance by cultural similarity: `P(form) = shared_traits / total_traits`. Agents sharing culture, belief, and occupation form bonds readily; agents differing on all three almost never do. This creates natural in-group clustering without hardcoded ethnic/religious boundaries. Combined with the existing shared-memory trigger, it means two agents must be both culturally compatible AND share a formative experience to bond — a high bar that produces meaningful relationships rather than noise. Source: PeWeX47/Axelrod-Model, Axelrod "The Dissemination of Culture" (1997).
>
> **Enrichment (not in estimate):** M50's homophily-based bond formation aligns with Axelrod's dissemination model — agents interact only if culturally similar. Key finding: homophily strength matters far more than network topology for cultural fragmentation outcomes. Focus M53 tuning on bias weights, not connectivity graph structure. Bounded confidence extension (interact only if similarity > threshold τ) creates hysteresis — once divergent, hard to reconverge — which maps to M50's slot eviction creating permanent estrangement. Source: Axelrod, "The Dissemination of Culture" (1997).

> **Enrichment (not in estimate):** M50 is the natural attachment point for diaspora tracking — `diaspora_registry: dict[civ_id, dict[region_id, population]]` tracking displaced populations. Chain migration uses the same relationship edges (diaspora at destination reduces migration cost). Enclave vs. assimilation dynamics emerge from cultural distance + diaspora size + host tolerance. See `docs/superpowers/design/brainstorm-simulation-depth-and-parameters.md` §E9.

#### Cross-System Interaction: Emergent Cohorts

M48, M50, and M55 are designed as separate systems, but their interaction produces something bigger: **emergent cohorts.**

The chain: agents who share a memory (same famine, same battle) → eligible for friend bonds (M50 formation trigger). Friends who stay co-located → bonds strengthen (+1/turn). Shared trauma + spatial clustering + strong bonds = a group of 10-30 agents with mutual bonds, shared memories, and collective grievances. These are *clans* — not designed, not named, but structurally real.

A cohort of famine survivors with grudges against the ruling civ, shared safety needs (M49), and strong internal bonds has the social substrate for collective action — rebellion, mass migration, occupation switching. This is the most important emergent behavior in the entire Phase 7 design.

**M53 must validate cohort emergence explicitly.** If M48/M50 are tuned in isolation — memory decay too fast, bond formation threshold too high, slot eviction too aggressive — the interaction that makes them worth building together never materializes. See M53 validation targets.

---

### M51: Multi-Generational Memory

**Goal:** When an agent dies, their strongest memories transfer to children as legacy memories, creating dynasties that carry ancestral grudges and pride across generations.

**Depends on:** M48 (memory system), M39 (parent_id lineage).

**Mechanism:**
- On agent death, extract top 2 memories by absolute intensity
- Compress: halve intensity, set decay_rate to slow (long-lasting but not permanent)
- Write to children's memory ring buffer as legacy memories (new event_type: `LEGACY`)
- Children can inherit legacy memories from both parents if marriage system exists (M57), otherwise from the single parent tracked by M39

**Behavioral effect:** A dynasty whose founder was executed carries a grudge memory for 2-3 generations. Each generation the intensity halves, so the grudge naturally fades unless reinforced by new events. A dynasty whose founder led a great conquest carries pride that makes descendants more bold in WAR utility.

**Scope guard:** Legacy memories use the existing M48 ring buffer — they occupy regular memory slots and compete with the agent's own experiences. A young agent with 2 legacy memories has 6 slots for their own experiences (at 8-slot capacity). As their own memories accumulate and intensify, weak legacy memories get evicted. This is correct — recent experience should eventually outweigh ancestral memory, unless the ancestral event was truly formative.

**Compute cost:** Negligible. 2 memory copies per death event. No per-tick cost beyond existing M48 decay.

> **Enrichment (not in estimate, from DYNASTY research):** **Succession scoring via genealogical distance.** DYNASTY (atanvardo/DYNASTY) implements compact cognatic primogeniture: `score = genealogical_distance + sibling_rank + sex_penalty`. Lower score wins the title. This could replace or supplement Chronicler's current dynasty succession logic with a formal scoring function that supports multiple succession laws as different scoring formulas — primogeniture (eldest child first), gavelkind (split titles among children by modifying the score to round-robin), elective (filter candidates by faction vote weight instead of genealogical distance). Also from DYNASTY: **2-parent-1-random trait mixing** for family resemblance (1 trait from father, 1 from mother, 1 random — simple but effective across generations) and **royal numbering post-processing** (scan all rulers sharing a throne name, assign Roman numerals). Source: atanvardo/DYNASTY `score()` function.

---

### M52: Artifacts & Significant Items

**Goal:** Track significant objects (holy relics, hereditary weapons, works of art) with origin stories, ownership chains, and narrative significance. Includes Mule artifact creation as a lasting narrative anchor for outlier characters.

**Storage:** Python-side, per-civ. ~50-200 artifacts per civ. Not per-agent SoA — artifacts are low-volume, high-narrative-value objects.

```python
@dataclass
class Artifact:
    name: str                    # generated at creation
    artifact_type: str           # relic, weapon, artwork, trade_good, manifesto
    creator_id: int              # agent who created/found it
    origin_turn: int             # when it was created
    origin_event: str            # what caused its creation
    holder_id: Optional[int]     # current agent holder (None = institutional)
    holder_civ: int              # current civ
    history: list[str]           # ownership chain as narrative fragments
    prestige_value: float        # contribution to civ prestige
    mule_origin: bool = False    # True if created by a Mule character's action
```

**Creation triggers:**
- Temple construction → holy relic
- Named character promotion with high prestige → hereditary weapon or artwork
- Major conquest → captured relic (transfers from defeated civ)
- High-wealth merchant → luxury trade good
- **Mule action success** → Mule-specific artifact (see below)

**Mule artifact creation:** When the civ-level action engine selects the action favored by a living Mule-flagged GreatPerson during their active window AND the action resolves successfully, create an artifact tied to that action:

- General who favors DEVELOP, civ develops → "The Treatise of [Name]" (artwork type, prestige bonus)
- Merchant who favors FUND_INSTABILITY, civ destabilizes → "The Manifesto of [Name]" (manifesto type, faction influence)
- Priest who favors WAR, civ conquers → "The Banner of [Name]" (relic type, conversion bonus in conquered region)

The causation is narratively valid — the Mule's persistent weight modifier tilted the civ toward this action, even if it wasn't the sole cause. Artifact creation must occur during the active window, not the fade period. The artifact persists after the character dies and after their influence fades, carrying their legacy into future generations.

**Narrative exposure:** Artifacts appear in narrator context when their holder is a named character in a curated moment. "General Kiran carries the Blade of Ashfall, forged by his grandfather during the founding wars."

**Mechanical effects (light):**
- Temple with relic: prestige bonus, conversion rate boost
- Captured relic: casus belli for original owner (diplomatic tension)
- Hereditary weapon: holder satisfaction boost (purpose need in M49)
- Mule artifact: prestige bonus + thematic modifier (e.g., conversion bonus from Banner, faction influence from Manifesto)

**Scope guard:** Artifacts are narrative hooks, not a full item system. No inventory, no crafting, no equipment slots. Each artifact is a story-generating object with mechanical effects limited to prestige and conversion modifiers.

> **Enrichment (not in estimate):** M52's artifact type enum is the natural home for cultural production — works of art, philosophical treatises, monuments. Cultural golden ages where prosperity enables creative output that defines a civilization's identity. Monuments as visible landmarks on maps. See brainstorm §E7.

---

### M53: Depth Tuning Pass

**Goal:** Calibrate M48-M52 systems and validate emergent behavior at current agent scale (10-50K) before scaling.

**Method:** Same as M47 — 200-seed × 500-turn runs, metric extraction, constant adjustment.

**Key validation targets:**

*Individual system health:*
- Memory intensity distributions are not degenerate (not all zero, not all saturated)
- Needs create behavioral diversity (agents with identical traits but different need states make different decisions — measurable via occupation switching variance)
- Relationships form and dissolve at reasonable rates (~3-5 active bonds per agent at steady state)
- Legacy memories persist for 2-3 generations (measurable via dynasty memory chain length)
- Artifacts accumulate at 1-3 per civ per 100 turns

*Emergent cohort validation (critical):*

> `[REVIEW B-3]` **Adjusted for pre-M55 context.** M53 runs before spatial positioning exists. With 500 agents sharing a famine memory in a region, all share the bond eligibility trigger. At 8 relationship slots per agent, the probability of 10+ agents forming mutual bonds (bidirectional, each in the other's slot list) from a pool of 500 is low without spatial clustering. M53 validates the *interaction works* (memory → bond → behavioral effect). Full cohort validation at 10+ agents deferred to M61, after M55's spatial hash enables proximity-based formation. Distinguish first-generation cohorts (20-50 turn lifecycle) from inherited cohorts (legacy-memory descendants, potentially multi-generational).

- **Cohort emergence (depth-scale threshold):** Do groups of 5+ agents with mutual bonds and shared memories form consistently across 200-seed runs? Measure: count agent clusters where ≥80% of members share at least one memory event_type+turn AND have mutual friend/grudge bonds. **Full validation (10+ agents) deferred to M61** after spatial positioning enables proximity-gated formation.
- **Cohort behavioral distinctiveness:** Do cohorts produce measurably different collective behavior vs. unaffiliated agents? Measure: compare occupation switching rate, migration rate, and rebellion participation between cohort members and non-cohort agents with similar stats.
- **Cohort lifecycle (first-generation):** Do first-generation cohorts form, persist for meaningful durations (20-50 turns), and eventually dissolve as members die or scatter? Permanent cohorts or instant dissolution both indicate broken tuning.
- **Cohort lifecycle (inherited):** Do legacy-memory descendants of original cohort members form kin bonds with each other? Multi-generational persistence is valid (historical identity groups are real), but measure separately from first-generation lifecycle.

If cohorts don't emerge at the 5+ threshold, investigate: memory decay too fast (agents forget before bonds form), bond formation threshold too high (shared memory not sufficient), slot eviction too aggressive (bonds pruned before they strengthen), formation check frequency too low, or 8 memory slots still insufficient.

*Mule validation:*
- **Mule frequency:** ~0-1 Mule per 100 turns at 50K agents
- **Mule impact window:** Mule-flagged characters produce measurably different civ action distributions during their active window vs. pre-Mule and post-fade baselines
- **Mule narrative visibility:** Active window generates at least one curator-selected event in 80%+ of Mule instances
- **Mule artifact rate:** ~50-70% of Mules produce an artifact during their active window (depends on action success rate)

*Regression:*
- No regression in Phase 6 calibrated behaviors (satisfaction distribution, Gini, rebellion rate)

**Mule constants tuned here:**

| Constant | Role | Target Range |
|----------|------|-------------|
| `MULE_PROMOTION_PROBABILITY` | Chance of Mule flag on GreatPerson promotion | 5-10% |
| `MULE_UTILITY_PERTURBATION_SCALE` | Magnitude of utility weight override | `[CALIBRATE]` |
| `MULE_UTILITY_FLOOR` | Minimum additive weight on Mule's preferred action during active window | 0.5-0.8 |
| `MULE_ACTIVE_WINDOW` | Turns of full influence post-promotion | 20-30 |
| `MULE_FADE_TURNS` | Turns over which modifier linearly decays to zero | ~10 |

**Gate:** M53 must pass before scale track begins. If depth systems create unstable dynamics at 50K agents, they'll be worse at 500K.

> **Implementation note (2026-03-22):** M53a tuning/freeze completed and the canonical M53b rerun passed on `tuning/codex_m53_secession_threshold25.yaml`. Dedicated duplicate-seed exported-data determinism smokes remain PASS, while the full `1-200` / `500` turn batch records determinism as `SKIP` because it contains no duplicate pairs. All blocking oracles passed (`community 200/200`, `needs 199/200`, `era 200/200 with 0 silent collapses`, `cohort 200/200`, `artifacts PASS`, `arcs 6 families / 199 seeds with 3+ types`, `regression PASS`), so `M54a` and the rest of the scale track are now unblocked.

> **Enrichment (not in estimate, from abm-ccid research):** **Fermi function for agent decisions.** Replace hard thresholds in `behavior.rs` decision model with `P(switch) = 1 / (1 + exp(-beta * (utility_dest - utility_current)))`. Beta controls sharpness: low beta = exploratory (agents try suboptimal options), high beta = exploitative (agents reliably pick the best option). This applies to migration, occupation switching, and rebellion decisions. Combined with a **two-gate architecture**: hard threshold first (satisfaction below `CONSIDERATION_THRESHOLD` → even consider switching?), then Fermi comparison of alternatives. Prevents agent churning when conditions are adequate while making decisions near the threshold probabilistic rather than deterministic cliff-edges. The beta parameter is a single `[CALIBRATE]` constant per decision type (~3 constants). Source: sandeepdhakal/abm-ccid, Fermi imitation rule from evolutionary game theory.

---

## Scale Track (M54-M60)

### M54a/b/c: Rust Phase Migration

> `[REVIEW B-1]` **Split into three sub-milestones with independent merge gates.** The original M54 (25-35 days) is larger than any previous milestone by 3×. Each phase migration has different data dependency profiles, different parallelization strategies, and different FFI surface requirements. Splitting matches the M43a/M43b and M38a/M38b precedent, provides three checkpoints instead of one, and allows M54b/M54c to plan against the FFI pattern established by M54a. A regression at the economy migration doesn't block politics migration progress. M54b and M54c can partially overlap after M54a establishes the pattern.

**Goal:** Migrate the three heaviest Python phases to Rust with rayon parallelism, removing the Amdahl's Law bottleneck before agent count increases.

**Sub-milestones:**

**M54a: Ecology Migration (8-11 days).** Per-region, embarrassingly parallel. Soil/water/forest coupling is local to each region. rayon `par_iter` over regions. Simplest of the three — start here to establish the migration pattern and FFI surface. Gate: determinism test at 1/4/8/16 threads. Establishes the Arrow-batch-in, Arrow-batch-out FFI pattern for M54b/c.

**M54b: Economy Migration (10-14 days).** `economy.py` (1,015 lines pre-M47, ~1,095 after tatonnement) has transport costs, perishability tables, stockpile accumulation/decay/cap, salt preservation, conservation law tracking, shock detection, trade dependency classification, and the raider modifier. Trade flow computation has cross-region data dependencies — region-level parallelism with synchronization at the trade flow step. The most complex migration. `[REVIEW]` Estimate revised from 9-12 to 10-14 to account for EconomyTracker state handoff and trade flow synchronization design work. Gate: determinism test + conservation law verification.

**M54c: Politics Migration + Spatial Sort (7-11 days).** Secession and federation checks can read agent distributions directly from the pool instead of round-tripping through Python snapshots. Complex stateful logic but fewer data dependencies than economy. Spatial sort infrastructure bundled here (radix sort machinery + benchmark harness). Gate: determinism test + bit-identical `--agents=off` output.

**Architecture change — end-state goal:** The Python turn loop is reduced to pure orchestration: calling Rust phases, collecting results, and feeding the narrator. Each phase calls into Rust via PyO3, Rust executes with rayon, returns results. The 10-phase structure is preserved — execution moves, not design.

**FFI surface:** Each migrated phase gets a single PyO3 entry point that accepts world state as Arrow batches and returns mutations as Arrow batches. Same pattern as the existing agent tick, extended to more phases.

**Risk:** This is infrastructure, not gameplay. Bugs here are concurrency bugs — race conditions, non-deterministic ordering. Every migrated phase needs a determinism test: same seed must produce identical output regardless of thread count. rayon's `par_iter` with deterministic reduction (sorted outputs, index-ordered writes) provides this, but it must be verified per phase.

**Economy migration notes:** M42-M43 landed with `@dataclass` result objects and dict/list structures — Arrow-translatable, no exotic Python types. Two migration details beyond the main translation work: (1) `EconomyTracker` (M43b) maintains dual-EMA state across turns — migration must decide whether EMA state lives in Rust permanently or round-trips through Python each turn. (2) `EconomyResult.conservation` is validation/diagnostic infrastructure, not simulation logic — migrating it is optional overhead; candidate for staying Python-side.

**Tooling (installed):**
- `cargo-nextest` — parallel test runner with flaky test detection. Use for determinism test suites (same seed, different thread counts).
- `cargo-flamegraph` — flamegraph generation from perf data. Profile each Python phase before migration to identify hot paths, then profile the Rust port to validate improvement.
- `cachegrind` / `cargo-profiler` — L1/L2 cache miss profiling, line-by-line. Use to validate that Morton sort actually improves cache behavior at 500K+ agents.
- `cargo-expand` — macro expansion viewer. Use to inspect PyO3 `#[pyfunction]`/`#[pyclass]` generated code when debugging FFI surface.
- `cargo-machete` — unused dependency detection. Run after each phase migration to keep the crate lean.

**Tooling (add as dev-dependencies at M54 start):**
- `criterion` — statistical benchmarking with regression detection. Per-phase tick time measurement, Morton sort benchmark harness.
- `iai-callgrind` — instruction-count benchmarking (deterministic, no wall-clock variance). Ideal for verifying that Rust ports don't regress across commits.
- `rayon_logs` — rayon work-stealing visualization. Generates SVG timelines showing thread utilization. Use to diagnose whether parallelization saturates 16 cores.

#### Spatial Sort Infrastructure

**Goal:** Build the radix sort machinery and benchmark harness for cache-efficient agent pool iteration, using a region-index-only sort key. M55 later extends this to a full Morton Z-curve key with (x,y) interleaving once spatial coordinates exist. +1 day on the M54 total.

**Rationale:** At 1M agents, the SoA pool exceeds L2 cache. Agent order in memory is determined by allocation/deallocation patterns, which have no relationship to spatial position. Full-pool sweeps (satisfaction, demographics, wealth decay) benefit significantly from memory locality — agents processed sequentially should be spatially proximate.

**M54 implementation:**
- Radix sort on `u32` keys, operating on the agent pool's index array (not moving SoA data — sort the index, then iterate in sorted order)
- Sort key in M54: `region_index` as the full key. Agents in the same region become contiguous in iteration order. This alone improves cache behavior for per-region phases.
- Benchmark harness: measure tick time with region-sorted order vs. arena order at 50K, 100K, 500K, and 1M agents (synthetic pools for the larger sizes)
- Activation threshold: only sort above `SPATIAL_SORT_AGENT_THRESHOLD` `[CALIBRATE]` (target: 100K). Below threshold, arena order is fine — the pool fits in L2.

**Sort frequency:** Every tick. Radix sort on `u32` keys at 1M elements takes ~4ms. If the tick is 200ms, that's 2% overhead for a potential 15-30% speedup on cache-sensitive phases. Start with every tick; reduce frequency only if profiling shows the sort itself is a bottleneck.

**Determinism:** Sort must produce identical ordering given identical pool state — verify with seed comparison test.

#### NUMA-Aware Iteration (Experimental)

**Goal:** Evaluate whether CCD-aware thread pinning improves tick performance on the 9950X's 2-CCD topology. +0.5 day if pursued.

**Approach:** Partition the region list into two halves (roughly equal agent count), pin each half to a CCD via thread affinity, run rayon within each partition. Cross-partition interactions (trade routes, migration between partitions) require a synchronization step.

**Decision gate:** Profile the agent tick at 500K agents with and without CCD affinity. If cross-CCD traffic is less than 10% of tick time, skip it — the engineering complexity isn't worth marginal gains. Document results regardless of whether the optimization ships.

---

### M55: Spatial Positioning

**Goal:** Give agents continuous (x,y) coordinates within their region. Proximity drives social influence, disease transmission, resource access. Includes spatial asabiya decomposition and full Morton sort activation.

**Storage:** 2 × f32 = 8 bytes/agent (was estimated at 4 bytes in Phase 6 considerations — 8 is correct for two f32 coordinates).

**Tick integration:**
- Agents have a position within their region's unit square [0,1) × [0,1)
- Migration changes region AND resets position (random within new region)
- Within-region movement: small random drift per tick toward attractors (resources, temples, markets)
- Proximity queries: spatial hash grid per region, O(1) average neighbor lookup

**Spatial hash:** Per-region grid, cell size tuned to average interaction radius. At 500 agents per region, a 10×10 grid gives ~5 agents per cell. Neighbor checks = 9 cells × 5 agents = 45 candidates. Cache-friendly, parallelizable per region.

**Morton sort prerequisite:** The spatial hash grid (M55) and the Morton sort (infrastructure from M54) are complementary. The hash provides O(1) neighbor lookup for interaction queries. The sort ensures that sequential memory access during full-pool sweeps benefits from cache locality. Both are needed at scale — the hash for random access, the sort for sequential access.

**Morton sort activation:** With M55's spatial coordinates available, extend M54's region-index-only sort key to a full Morton Z-curve: `morton_code(region_index, x, y)` — region index as the high bits ensures agents in the same region are contiguous, and the Morton interleaving of (x,y) within each region preserves 2D locality. An approximate sort (radix sort on the top 16 bits of the Morton code) is sufficient for cache benefit.

**Downstream effects:**
- Disease transmission (M35): severity scales with local density
- Social influence: cultural drift weighted by proximity
- Relationship formation (M50): proximity is a prerequisite for friend/rival bonds
- Resource access: farmers near resource sites produce more (position × yield interaction)
- **Spatial asabiya** (see below)

#### Spatial Asabiya Decomposition

**Goal:** Replace the civ-level asabiya scalar with a spatially emergent quantity. Per-region asabiya grows on frontier regions and decays in interior regions. The civ-level value becomes a population-weighted average of regional values.

**Phase 6 asabiya is unchanged.** The current Phase 6 civ-level asabiya mutation (Phase 6 Culture, routed through StatAccumulator as `keep`) ships as-is through M47. M55 replaces the underlying computation — `civ.asabiya` continues to exist as a field, but its value is now sourced from regional aggregation rather than direct mutation.

**Formulas (Turchin's metaethnic frontier theory):**

Frontier region (adjacency list includes a region belonging to a different civilization):
```
S(t+1) = S(t) + r0 * S(t) * (1 - S(t))
```

Interior region (all adjacent regions belong to the same civilization):
```
S(t+1) = S(t) - delta * S(t)
```

Civ-level asabiya:
```
civ.asabiya = weighted_average(region_asabiya, weights=region_population)
```

**Computation:** O(regions × avg_adjacency) per turn. Trivial — frontier detection is a set membership check on region adjacency lists.

**StatAccumulator change:** Asabiya routing changes from `keep` (direct mutation in Phase 6) to a post-M55 computation that reads regional frontier status from the adjacency graph. Existing code that reads `civ.asabiya` continues to work — it reads a spatially-derived value instead of a directly-mutated one.

**Phase 10 extension — variance-based collapse:** With spatial decomposition, Phase 10 collapse logic can additionally read asabiya *variance*. An empire with high average asabiya but extreme variance (zealous frontier, decadent core) is more collapse-prone than one with uniform moderate solidarity. Historically accurate (late Roman Empire, late Abbasid Caliphate) and generates richer narrative hooks for the curator pipeline.

**Phase 4 integration — power projection decay:** Military strength degrades with distance from the capital: `P = A * mean(S) * exp(-d/h)`. This naturally limits expansion and creates a reason for MOVE_CAPITAL actions beyond the current heuristics. Pairs well with M60's supply line mechanics.

**Landlocked ally concern:** Civs entirely surrounded by allies (federation members, same-faith neighbors) could decay to zero asabiya with no recovery mechanism. Flag for M61 calibration — federation membership or same-faith adjacency may need to count as soft frontiers with reduced but non-zero growth rate (`r0 * SOFT_FRONTIER_FACTOR`). Don't solve now; validate in M61 200-seed runs.

> `[REVIEW]` **Frontier gradient vs. binary classification.** The frontier/interior distinction is binary — a region either has a foreign neighbor or it doesn't. Historically, many empires had *degrees* of frontier-ness (border marches, buffer zones, contested regions that flip frequently). Binary classification produces sharp oscillations: a region that was frontier one turn becomes interior the next when a neighbor is conquered, switching from growth to decay instantly. Consider a "frontier fraction" — `f = foreign_neighbors / total_neighbors`. The growth formula becomes `S(t+1) = S(t) + r0 * f * S(t) * (1 - S(t))` and the decay `S(t+1) = S(t) - delta * (1 - f) * S(t)`. One line of arithmetic, smooths the transition. Flag for M55 spec — the binary model may be good enough; the gradient is cheap insurance.

> `[REVIEW O-5]` **Asabiya transition strategy.** The Phase 6 Culture phase asabiya mutations (StatAccumulator `keep` routing) will still exist in code when M55 lands. The M55 spec must explicitly state the transition: either (a) guard Phase 6 asabiya mutations when M55 is active (cleaner, requires feature flag), or (b) let Phase 6 mutations fire, then overwrite with M55 regional aggregation (wasteful but safe, no Phase 6 rework). Option (b) matches the "no Phase 6 rework" claim in this roadmap.

> `[REVIEW O-11]` **Multi-empire frontier oscillation.** Two expanding empires sharing a frontier both get frontier growth simultaneously. If both are in their growth phase, the logistic ceiling `(1 - S)` self-limits each independently — but the mutual frontier persists as long as both empires exist, meaning neither transitions to interior decay. Validate in M61: do two adjacent expanding empires produce stable frontier dynamics or runaway mutual asabiya?

**Constants:**

| Constant | Role | Calibrate in |
|----------|------|-------------|
| `ASABIYA_FRONTIER_GROWTH_RATE` (r0) | Logistic growth rate on frontier regions | M61 |
| `ASABIYA_INTERIOR_DECAY_RATE` (delta) | Linear decay rate in interior regions | M61 |
| `ASABIYA_POWER_DROPOFF` (h) | Distance decay factor for military projection | M61 |
| `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD` | Variance level that triggers elevated collapse risk | M61 |

> **Enrichment (not in estimate):** M55's spatial density enables a disease system upgrade from M35b's endemic baseline to a full SEIRS model — transmission rate (beta) scales with population density, urban settlements (M56) become disease amplifiers, quarantine as a policy tradeoff (reduces contact rate at cost of trade penalty). See brainstorm §E3.

---

### M56: Settlement Emergence

**Goal:** Agent clusters become proto-cities with urban/rural distinction driving different economic and social dynamics.

**Depends on:** M55 (spatial positioning).

**Key insight — detection, not creation:** Spatial drift forces (attraction to other agents, markets, resources) create the clusters. Clustering is a *detection* step that labels what already exists. This means clustering can run every 10-20 ticks rather than every tick — it's observing emergent structure, not forcing it. This is much cheaper and naturally avoids flicker.

**Mechanism:**
- Per-region: run density-based clustering on agent positions every N ticks (`SETTLEMENT_DETECTION_INTERVAL` `[CALIBRATE]`, target: 10-20 ticks)
- Clusters above density threshold → settlement candidate
- New clusters that persist through 2 consecutive detection passes → named settlement with `founding_turn`

**Settlement inertia:** Settlements have an `inertia_counter = f(population, age)`. Older, larger settlements are harder to kill. Each detection pass: if the settlement's cluster dissolved, decrement inertia. At zero, the settlement dissolves. If the cluster persists, inertia resets. A fishing camp that disperses after one bad turn vanishes; a 200-turn city with 500 agents persists through a temporary population dip.

```python
@dataclass
class Settlement:
    name: str
    region: str
    founding_turn: int
    population: int
    economic_character: str    # based on dominant occupations
    infrastructure: float      # grows with population persistence
    inertia: int               # f(population, age), decremented on cluster dissolution
```

**Urban/rural distinction:**
- Urban agents: higher material need satisfaction (markets, temples nearby), lower safety (crime analog from density), higher social need satisfaction, faster cultural drift (exposure to diversity)
- Rural agents: lower material access, higher safety, slower cultural drift, higher food production efficiency

**Storage:** Per-region settlement list, Python-side (like artifacts — low volume, high narrative value). Rust only needs a per-agent `is_urban: bool` or `settlement_id: u16` flag for behavioral modifiers.

**Narrative payoff:** "The river settlement of Karesh grew from a fishing camp to a thriving port, its markets drawing merchants from three civilizations." Cities emerge from agent behavior — no city-building action required.

---

### M57: Marriage & Households

**Goal:** Pair matching, household income pooling, inheritance, joint migration decisions. Extends M39 single-parent lineage into full family units.

**Depends on:** M50 (deep relationships), M55 (spatial positioning for proximity-based matching).

**Matching:** Per-region, per-tick (or per-N-ticks). Eligible agents (age range, unmarried) in proximity form marriage bonds. Matching is not optimal — agents marry who's nearby and compatible, not the globally best match. Personality compatibility: similar values ± tolerance. Cross-faith marriages possible but lower probability.

**Household model:**
- Married pair pools income (combined wealth for satisfaction purposes)
- Children inherit from both parents (M39 extended to two-parent)
- Joint migration: married agents move together (one decides, both relocate)
- Widowhood: surviving spouse keeps pooled wealth, children stay with survivor

**M39 extension:** `parent_id` becomes `parent_ids: [u32; 2]` with `PARENT_NONE` sentinel for single-parent cases. Dynasty detection logic handles two-parent lineage.

**Scope guard:** No divorce, no polygamy, no complex family structures. Marriage is a pair bond that persists until death. Keep it simple — the narrative value is in household economics and two-parent inheritance, not in relationship drama.

---

### M58: Agent-Level Trade

**Goal:** Merchant agents physically carry goods along spatial paths, replacing M42-M43's abstract carry model with agent-level economic simulation.

**Depends on:** M55 (spatial positioning), M42-M43 (goods model and trade infrastructure).

**Mechanism:**
- Merchant agents evaluate available routes (price differentials visible from their region)
- Select highest-margin route, load goods from regional surplus
- Travel along path (1 region per turn, spatial position updates)
- Deliver goods, collect margin as wealth
- Return or continue to next opportunity

> **Enrichment (not in estimate):** Route formation can be endogenous rather than static: trade route probability ∝ `(pop_A × pop_B) / distance²`. Routes activate when expected profit exceeds threshold. Merchants learn via exponential moving average of profitability — routes persist or dissolve based on realized returns. This means when a civ develops luxury goods, routes spontaneously form; wars shut routes down automatically (profit drops). ~100-150 lines Python + 20 lines Rust signal write-back. M58's agent merchants then operate on this dynamic route network rather than static paths. Source: Enhanced Gravity Model (Frontiers in Physics 2019).

> **Enrichment (not in estimate):** Formalize production as `output[good] = f(inputs)` via sparse matrix. When inputs are scarce, production throttles to `min(available[input] / required[input])` across all inputs. Creates cascade effects: coal mine disruption → steel throttle → sword production drops → military power weakens. O(G²) per civ, negligible. ~120 lines extending `economy.py` goods definitions with input requirements. Source: ABIDES-Economist (arxiv 2024), BazaarBot (gamedeveloper.com).

**Key change from M42:** Merchants now physically relocate during trade. This means merchant count in a region fluctuates as merchants travel. A region that sends all its merchants on long routes temporarily loses export capacity. This creates realistic boom-bust cycles in trade — merchant departure → local surplus → price drop → merchants return.

**Route planning:** Each merchant evaluates ~5-10 candidate destinations per turn. At 50K merchants, this is 250K-500K route evaluations — parallelizable per agent, significant compute. This is one of the core compute-hungry systems that fills cores.

**M42-M43 as calibration target (resolved):** The abstract trade model survives alongside agent-level trade, reframed: M42-M43's abstract model is the **macro-level specification** for M58. Agent-level trade should converge to similar macro distributions — price gradients, trade volumes, food sufficiency patterns. If it doesn't, something is wrong with the agent-level mechanics, not with the abstract model.

The abstract model serves three roles:
1. **`--agents=off` path.** Bit-identical aggregate behavior.
2. **Regression baseline.** M61 validates that agent-level trade produces comparable macro patterns.
3. **Narration scaffold.** Analytics extractors and the narrator can read either abstract or agent-level data through the same bundle schema.

This means the work going into M42-M43 now is not at risk of being wasted — it's building the specification that M58 must satisfy. Accept the doubled trade code surface as the cost of backward compatibility and calibration rigor.

---

### M59: Information Propagation

**Goal:** The primary channel through which agents perceive conditions beyond their immediate region. Information about distant events travels through the social graph with temporal lag proportional to graph distance — well-connected agents learn fast, isolated agents learn slow.

**Depends on:** M50 (deep relationships), M55 (spatial positioning).

**Design framing — perception lag layer:** Before M59, agents in region A know nothing about a famine in region B until they migrate there or the famine's effects propagate through the economy (food price spike). After M59, information about region B's famine travels through the social graph — a merchant with a trade partner in region B learns about the famine 1-2 turns after it starts, and may preemptively migrate or stockpile.

M59 is not just a flavor system (rumors are interesting). It formalizes the macro→micro perception channel with temporal lag. The lag is the graph distance between the agent and the information source, measured in hops per turn. This complements M49's "perfect regional knowledge" — agents always know their own region immediately, but cross-region awareness depends on social connectivity.

**Relationship to M49:** M49 validates needs mechanics with perfect local perception. M59 adds realistic perception lag for cross-region information. This is the right sequencing — calibrate the response before adding the delay. No structural dependency change (M59 still depends on M50 and M55, not M49).

**Mechanism:**
- Information packets: `(info_type: u8, source_region: u16, turn: u16, intensity: u8)` = 6 bytes
- Each agent holds 2-4 active information packets (`[CALIBRATE]`)
- Per-tick: with probability proportional to relationship sentiment, copy information to connected agents
- Information degrades as it propagates (intensity decreases per hop)
- BFS-like diffusion across agent networks — O(edges) per tick

**Information types with propagation weights:**

Each information type carries a `propagation_weight` that controls how quickly it spreads through the social graph. This is the tunable coupling constant from hybrid SD/ABM research — independent per-signal, not hardwired:

| Info Type | Propagation Weight | Rationale |
|-----------|-------------------|-----------|
| Trade opportunity | High | Merchants actively share price information |
| Threat warning | High | Survival-critical, shared urgently |
| Religious event | Medium | Spread through co-religionist bonds preferentially |
| Political rumor | Low | Unreliable, spread slowly through weak ties |

Propagation weights are `[CALIBRATE]` constants tuned in M61.

**Behavioral effects:**
- Agents act on information: trade opportunity → merchant migration, threat → pre-emptive migration or loyalty shift
- Information lag creates realistic fog-of-war: frontier agents learn about distant threats turns after they happen
- False/outdated information: if conditions change before information arrives, agents act on stale data — realistic and narratively interesting

**Compute:** At 500K agents with ~5 edges each, 2.5M edge traversals per tick. With spatial partitioning and rayon, this parallelizes well across cores.

---

### M60: Military Units

**Goal:** Soldier agents form armies that march, siege, and fight. Battle resolution grounded in agent state rather than abstract rolls.

**Depends on:** M55 (spatial positioning).

**Mechanism:**
- WAR action triggers army formation: soldiers in the aggressor's regions rally to a designated staging region
- Army marches: soldiers physically move through regions toward target (1 region/turn)
- Battle resolution: when army reaches target, combat resolves based on soldier count, morale (satisfaction), terrain, supply line length
- Survivors return or occupy conquered territory
- Casualties are actual agent deaths, not abstract population reduction

**Supply lines:** Army strength degrades with distance from home territory. Long campaigns are risky — soldiers' needs (safety, material) go unmet, morale drops, desertion increases. This creates natural limits on expansion without artificial range caps. Pairs with M55's spatial asabiya power projection decay (`exp(-d/h)`) — military effectiveness and social solidarity both diminish with distance from the core.

**Narrative payoff:** "The army of Aram marched three regions to besiege Karesh. By the time they arrived, half the soldiers had deserted — their families were starving back home, and the merchant Hala's embargo had cut their supply lines."

> **Enrichment (not in estimate):** Current war triggers are power-disparity based. Fearon identifies three structural conditions that explain war better than raw power: (1) **Commitment problems** — declining power is tempted to preempt before parity shifts; (2) **Information asymmetry** — mutual overconfidence when perception gap > 40%; (3) **No settlement zone** — overlapping claims leave no mutually acceptable division. Integration: check power trajectory (declining → preventive war risk), information gap (how well do civs estimate each other's strength — pairs with M59's perception lag), and settlement feasibility. This enriches M60 from "armies fight" to "wars start for structural reasons." Source: Fearon, "Rationalist Explanations for War" (Stanford 1995).

> **Enrichment (not in estimate):** War risk spikes at power parity (ratio within ±15%), especially when the rising power is revisionist (dissatisfied with status quo). 3-5× more war-likely at parity than at clear dominance. Integration: compute pairwise power trajectories, flag pairs approaching parity, feed into war risk modifier in action engine. O(n log n). Complements Fearon's commitment problem mechanism.

**Scope guard:** Not a tactical wargame. No formations, no flanking, no per-soldier combat rolls. Battle resolution is aggregate (army-level stats computed from soldier agent states). The value is in the campaign — march, supply, morale — not in the fight itself.

---

### M61: Scale Tuning Pass

**Goal:** Calibrate M54-M60 systems at target agent scale (500K-1M) and validate parallel correctness.

**Critical validations:**
- **Determinism:** Same seed produces identical output regardless of thread count (1, 4, 8, 16 threads)
- **Performance:** Tick time under 200ms at 1M agents on 16 cores
- **Memory:** Total pool under 250MB at 1M agents
- **Behavioral stability:** Same emergent patterns at 500K as at 50K (scale shouldn't change qualitative behavior)
- **Settlement emergence:** Cities form in 80%+ of runs at 500K+ agents
- **Trade patterns:** Agent-level trade produces similar macro distributions to M42-M43 abstract model (price gradients, trade volumes, food sufficiency within ±20% of abstract baseline)
- **Military realism:** Campaign range naturally limited by supply/morale to 3-5 regions
- **Spatial asabiya — collapse prediction:** Asabiya variance predicts collapse within 20 turns in 70%+ of 200-seed runs where variance exceeds `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD`
- **Spatial asabiya — expansion balance:** Frontier growth and interior decay reach equilibrium in stable empires (asabiya does not trend monotonically in either direction over 200+ turns)
- **Spatial asabiya — landlocked ally check:** Civs fully surrounded by federation allies for 50+ turns do not decay to zero asabiya. If they do, calibrate soft frontier factor.
- **Morton sort:** Tick time with Morton sort vs. arena order at 500K and 1M agents (expect 15-30% improvement on full-pool sweeps). Identical pool ordering given identical spatial state (determinism check).
- **NUMA experiment:** Results documented regardless of whether the optimization ships
- **Cohort scaling:** Emergent cohorts validated in M53 at 50K still form at 500K-1M. Cohort size scales sublinearly with agent count (expect 15-50 member cohorts at 500K, not 150-500).
- **Full cohort validation (deferred from M53):** `[REVIEW B-3]` M53 validates at 5+ agents without spatial proximity. M61 validates the full 10+ agent threshold with M55 spatial hash enabling proximity-gated bond formation. This is the authoritative cohort emergence test.

**Spatial asabiya constants tuned here:**

| Constant | Role |
|----------|------|
| `ASABIYA_FRONTIER_GROWTH_RATE` (r0) | Logistic growth on frontier regions |
| `ASABIYA_INTERIOR_DECAY_RATE` (delta) | Linear decay in interior regions |
| `ASABIYA_POWER_DROPOFF` (h) | Distance decay for military projection |
| `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD` | Variance trigger for elevated collapse risk |
| `SOFT_FRONTIER_FACTOR` (if needed) | Reduced growth rate for allied-border regions |

---

### M62: Phase 7 Viewer

**Goal:** Full viewer redesign covering Phase 7 spatial/interiority systems AND all deferred Phase 3-6 viewer requirements (M46 dropped from Phase 6 — viewer redesigned from the ground up here).

**Phase 7 components:**
- Spatial agent map (zoomable from region-level to agent-level)
- Settlement overlay (city boundaries, population, character)
- Trade route visualization (merchant paths, goods flow)
- Army march visualization (troop movement, supply lines)
- Character detail panel: memory timeline, needs radar, relationship graph
- Artifact display on character and civ panels
- Mule character indicator (distinctive marker on character panel, memory-that-warped-them displayed, active window countdown)
- Asabiya heatmap overlay (per-region, frontier vs. interior shading)

**Phase 3-4 backlog (from dropped M46):**

| Component | Feature | Source |
|-----------|---------|--------|
| CivPanel | Tech focus badge (icon + tooltip) | M21 |
| CivPanel | Faction influence bar (four-segment: MIL/MER/CUL/CLR) | M22 + M38 |
| RegionMap | Ecology variables on hover (soil/water/forest progress bars) | M23 |
| RegionMap | Intelligence quality indicator (confidence ring or fog overlay) | M24 |

**Phase 5 agent data (from dropped M46):**

| Component | Feature | Source |
|-----------|---------|--------|
| RegionMap | Population heatmap (agent count, color by mean satisfaction) | M30 |
| RegionMap | Occupation distribution donut on region hover | M30 |
| TerritoryMap | Named character markers (icon + name label) | M30 |
| TerritoryMap | Migration flow arrows (aggregate direction/volume, 10-turn window) | M30 |

**Phase 6 material world (from dropped M46):**

| Component | Feature | Source |
|-----------|---------|--------|
| RegionMap | Resource icons per region (crop/mineral/special) | M34 |
| RegionMap | Seasonal indicator (spring/summer/autumn/winter badge) | M34 |
| RegionMap | River overlay (blue lines connecting river-adjacent regions) | M35 |
| RegionMap | Disease severity heatmap layer (toggle) | M35 |
| RegionMap | Trade flow arrows (goods type + volume along routes) | M42-M43 |

**Phase 6 society (from dropped M46):**

| Component | Feature | Source |
|-----------|---------|--------|
| CharacterPanel | Personality radar chart (3 axes: boldness, ambition, loyalty) | M33 |
| CharacterPanel | Character arc timeline (horizontal, key events marked) | M45 |
| CharacterPanel | Family tree (vertical, max 3 generations) | M39 |
| CharacterPanel | Social network (d3-force mini-graph, relationships to other named chars) | M40 |
| CharacterPanel | Religious identity + faith icon | M37-M38 |
| RegionMap | Cultural identity overlay (color by dominant cultural values) | M36 |
| RegionMap | Religious majority overlay (color by dominant faith) | M37 |
| CivPanel | Wealth distribution histogram + Gini coefficient | M41 |
| CivPanel | Class tension indicator | M41 |
| CivPanel | Goods production/consumption balance | M42 |
| CivPanel | Trade dependency indicator | M43 |

**Bundle schema:** `bundle_version` bump with Phase 6+7 additions: named_characters (personality, dynasty, faith, arc_type, relationships, memory, needs, mule_flag, utility_overrides), agent_wealth_distribution, cultural_map, religious_map, goods_economy, resource_map, spatial data, settlement data, regional_asabiya, artifacts.

**Estimated scope:** ~5000-7000 lines TypeScript. Current viewer is ~5,300 lines; Phase 7 redesign includes spatial visualization, agent interiority, and the Phase 3-6 backlog. Designing it all at once avoids rework.

---

## Per-Agent Memory Budget

| System | Bytes/agent | At 50K | At 500K | At 1M |
|--------|-------------|--------|---------|-------|
| Phase 6 baseline | 68 | 3.4MB | 34MB | 68MB |
| Memory ring buffer (M48, 8 slots) | 64 | 3.2MB | 32MB | 64MB |
| Needs (M49) | 24 | 1.2MB | 12MB | 24MB |
| Deep relationships (M50) | 48 | 2.4MB | 24MB | 48MB |
| Spatial position (M55) | 8 | 0.4MB | 4MB | 8MB |
| Settlement flag (M56) | 2 | 0.1MB | 1MB | 2MB |
| Marriage (M57) | 4 | 0.2MB | 2MB | 4MB |
| Info packets (M59, 4 slots) | 24 | 1.2MB | 12MB | 24MB |
| **Phase 7 total** | **242** | **12.1MB** | **121MB** | **242MB** |

242MB at 1M agents. 192GB DDR5 provides ~790× headroom.

Mule flag is 1 bit on GreatPerson (Python-side, negligible). Utility overrides are a small dict on GreatPerson (Python-side, negligible). Morton sort keys are transient (computed, sorted, discarded). Spatial asabiya is per-region (not per-agent — stored on Region, ~200 regions × 4 bytes = negligible).

---

## Dependency Graph

```
M47 (Phase 6 tuning)
 └─► M48 (Agent Memory + Mule Promotions) ──────┐
      ├─► M49 (Needs System)                     │
      ├─► M50 (Deep Relationships) ◄── M40       │
      │    └─► [feeds M57, M59]                  │
      ├─► M51 (Multi-Gen Memory) ◄── M39         │
      └─► M52 (Artifacts + Mule Artifacts)       │
                                                  │
 M53 (Depth Tuning) ◄── M48-M52 ────────────────┘
  └─► M54a (Rust Ecology Migration)
       ├─► M54b (Rust Economy Migration)          ← can overlap with M54c
       └─► M54c (Rust Politics + Spatial Sort)    ← can overlap with M54b
            └─► M55 (Spatial Positioning + Asabiya + Morton) ◄── M54a-c
                 ├─► M56 (Settlement Emergence)
                 ├─► M57 (Marriage) ◄── M50
                 ├─► M58 (Agent-Level Trade) ◄── M42-M43
                 ├─► M59 (Info Propagation / Perception Lag) ◄── M50
                 └─► M60 (Military Units)

 M61 (Scale Tuning) ◄── M54a-c, M55-M60
  └─► M62 (Phase 7 Viewer)
```

`[REVIEW]` M54 split into M54a/b/c. M54b and M54c depend on M54a (which establishes the migration FFI pattern) but can partially overlap with each other. M55 depends on all three completing. No other dependency changes.

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Mule influence via time-bounded civ-level weight modifier (0.5-0.8 floor, 20-30 turn active window, 10 turn fade), not permanent subtle nudge | Asimov's Mule doesn't nudge — he warps. A permanent 0.3 additive weight is undetectable in the action distribution. A 0.5-0.8 weight for 20-30 turns creates a dramatic, narratively visible window. Time-bounding prevents permanent simulation distortion. |
| D2 | Morton sort infrastructure in M54, full activation in M55 | M54 has no spatial coordinates — can only sort by region index. M55 provides (x,y), enabling full Morton Z-curve. Split avoids dependency contradiction. |
| D3 | Phase 6 asabiya unchanged; M55 replaces computation | Clean transition. Phase 6 code ships as-is. M55 swaps the source of `civ.asabiya` from direct mutation to regional aggregation. No Phase 6 rework. |
| D4 | M59 reframed as perception lag layer, not flavor system | Information propagation is the formalization of the macro→micro channel. Perfect local perception (M49) + graph-distance lag (M59) gives tunable coupling. Design notes only — no code or dependency change. |
| D5 | Memory ring buffer 8 slots (CALIBRATE 6-8), not 4 | 4 slots fills in 4 turns. M51 legacy memories occupy 2 slots at birth. 8 slots lets agents accumulate enough lived experience for cohort dynamics to form. +32 bytes/agent = 32MB at 1M, negligible. |
| D6 | M42-M43 abstract trade is the macro specification for M58, not legacy code | Abstract model serves as `--agents=off` path, regression baseline, and narration scaffold. Agent-level trade must converge to similar macro distributions. Doubled code surface is the cost of calibration rigor. |
| D7 | Needs mechanically orthogonal to satisfaction, exposed to narrator | "Content but spiritually adrift" is a valid narrative state. No mechanical coupling needed. Risk of incoherence only if narrator can't see need state — so expose it. |
| D8 | Settlement detection every 10-20 ticks with inertia counter, not per-tick creation | Clustering detects what spatial drift already created. Inertia = f(population, age) prevents flicker. Older/larger settlements persist through temporary dips. |

---

## New Constants Summary

| Constant | Source | Calibrate in |
|----------|--------|-------------|
| `MULE_PROMOTION_PROBABILITY` | Mule promotions (M48) | M53 |
| `MULE_UTILITY_PERTURBATION_SCALE` | Mule promotions (M48) | M53 |
| `MULE_UTILITY_FLOOR` | Mule promotions (M48) | M53 |
| `MULE_ACTIVE_WINDOW` | Mule promotions (M48) | M53 |
| `MULE_FADE_TURNS` | Mule promotions (M48) | M53 |
| `ASABIYA_FRONTIER_GROWTH_RATE` | Spatial asabiya (M55) | M61 |
| `ASABIYA_INTERIOR_DECAY_RATE` | Spatial asabiya (M55) | M61 |
| `ASABIYA_POWER_DROPOFF` | Spatial asabiya (M55) | M61 |
| `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD` | Spatial asabiya (M55) | M61 |
| `SPATIAL_SORT_AGENT_THRESHOLD` | Morton sort (M54) | M61 |
| `SETTLEMENT_DETECTION_INTERVAL` | Settlement emergence (M56) | M61 |

11 new constants. All deferred to existing tuning passes (M53 for depth, M61 for scale).

---

## RNG Stream Offset Reservations `[REVIEW O-2]`

Current `STREAM_OFFSETS` in `agent.rs` uses ranges 0-800 (7 entries). Phase 7 adds 11 new RNG-consuming systems. Pre-assign ranges to prevent determinism collisions across concurrent milestone work. Each milestone spec must assign its offset from this table.

| Offset | System | Milestone |
|--------|--------|-----------|
| 900 | Memory decay / event intensity variance | M48 |
| 1000 | Needs restoration rolls | M49 |
| 1100 | Relationship formation / dissolution | M50 |
| 1200 | Legacy memory inheritance variance | M51 |
| 1300 | Mule promotion rolls | M48 (Mule) |
| 1400 | Spatial position init + drift | M55 |
| 1500 | Settlement detection noise | M56 |
| 1600 | Marriage matching | M57 |
| 1700 | Merchant route selection | M58 |
| 1800 | Information propagation noise | M59 |
| 1900 | Military rally / desertion rolls | M60 |

---

## Determinism Guardrails

Determinism is a Phase 7 merge gate, not just an M61 validation topic. Any milestone that changes simulation state must preserve cross-process determinism. Any milestone that adds parallel execution must additionally preserve identical output across 1/4/8/16 threads.

- Never use Python `hash(...)`, Rust randomized hash iteration, or raw container iteration order to seed RNG, break ties, or order outputs. Derive stable keys from explicit simulation identifiers and canonical field ordering.
- Never use module-global RNGs or ad hoc randomness on the simulation path. All new randomness must flow through the registered per-phase/per-feature RNG streams.
- Every RNG-consuming feature must reserve a `STREAM_OFFSETS` entry before implementation. Reusing an existing offset is a bug unless intentional and documented in the milestone spec.
- All sorts, reducers, and parallel writes must have explicit stable secondary keys. Equal region or Morton keys must not fall back to arena/allocation order.
- Canonicalize unordered collections before decisions, tie-breaks, FFI boundaries, or serialization. `HashMap`/`HashSet`, Python `set`, and any equivalent structures must be sorted by stable IDs or explicit keys before they influence simulation state or exported ordering.
- Add determinism coverage with the feature: cross-process seed replay for new state-changing systems, cross-thread replay for parallel phases, and comparison helpers that scrub metadata-only fields unless artifact-level determinism is the explicit goal.

These rules apply to Phase 7 core milestones and the Phase 7.5 export/stable-ID follow-on work. Stable IDs must never depend on allocation order, randomized hashes, or transient container layout.

---

## `life_events` Bitfield Capacity `[REVIEW O-10]`

Current `life_events: u8` uses bits 0-6 (`REBELLION=0, MIGRATION=1, WAR_SURVIVAL=2, LOYALTY_FLIP=3, OCC_SWITCH=4, IS_NAMED=5, CONVERSION=6`). Only bit 7 is unused. M48's memory system may need additional life_event flags for memory-writing events. If any new bit is needed, expand to `u16` — this changes the SoA layout (+1 byte/agent) and the Arrow snapshot schema. Flag in M48 spec: decide whether to expand proactively or reuse existing bits.

---

## Open Questions (Resolve During M54 Spec)

1. **Analytics interface for Rust-migrated phases.** Python analytics extractors (`analytics.py`) consume WorldState post-turn. If ecology/economy/politics move to Rust: (A) Rust phases return results as Arrow batches, extractors consume batches (consistent with existing agent tick FFI pattern); (B) Rust writes results back to WorldState Python objects, extractors unchanged. Option A is more consistent but requires designing the Arrow schema for each phase's output. M54 spec decision.

---

## Resolved Questions

| Question | Resolution | Decision |
|----------|-----------|----------|
| Does M42-M43 abstract trade survive alongside M58? | Yes — reframed as macro specification | D6 |
| Should needs affect satisfaction or stay orthogonal? | Orthogonal. Narrator sees both. | D7 |
| Settlement persistence across turns? | Detection every 10-20 ticks + inertia counter | D8 |
| Two-parent lineage (`parent_id` → `parent_ids`) | No breakage — planned schema migration across ~7 files in Rust and Python, all within M57 scope. Dynasty resolution for two-parent lineage is a design question handled in M57 spec. | — |
| Spatial positioning determinism | M55 adds 2 new `STREAM_OFFSETS` entries for position init and drift. Existing registry pattern and collision test (`agent.rs:202`) handle this. | — |

---

## Phase 8-9 Horizon

See `chronicler-phase8-9-horizon.md` for brainstorm-level ideas on governance, institutions, cultural traits, and revolution dynamics. Not committed scope.

---

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Memory system creates feedback loops with satisfaction | High | M53 tuning gate before scale. Memory satisfaction weight is `[CALIBRATE]` with hard cap. |
| Needs system adds too many tuning dimensions (24+ constants) | Medium | Reduce to 4 needs if 6 proves intractable. Fewer well-tuned needs > many poorly-tuned. |
| Deep relationships saturate at maximum sentiment (all friends) | Medium | Slot eviction + sentiment decay prevent saturation. Rivalry/grudge formation balances positive bonds. |
| Rust phase migration introduces non-determinism | High | Per-phase determinism tests: same seed, different thread counts, bit-identical output. |
| Spatial hash performance at 1M agents | Medium | Grid cell size tuning. Fallback: k-d tree per region if hash degrades. |
| Agent-level trade doubles trade code (abstract + agent paths) | Medium | Abstract path is calibration specification, not dead weight. Accept the code surface. |
| Military units make WAR action too detailed (mini-wargame creep) | Medium | Scope guard: aggregate battle resolution only. No per-soldier combat. |
| 242 bytes/agent exceeds L1 per-region at high density | Low | At 500 agents × 242 bytes = 121KB, exceeds 64KB L1. Mitigated by SoA layout — each phase accesses specific fields, not whole agent. Working set per phase stays in L1. |
| Spatial asabiya creates expansion feedback loop | Medium | Logistic ceiling `(1 - S)` is self-limiting. Interior decay offsets frontier growth at scale. Validate in M61. |
| Mule frequency too high destabilizes simulation | Low | 5-10% of already-rare GreatPerson promotions. ~1 Mule per 100 turns at 50K agents. Weight cap (2.5x) and time-bounding limit influence. |
| Morton sort overhead exceeds cache benefit at low agent counts | Low | Only activate above `SPATIAL_SORT_AGENT_THRESHOLD` (target: 100K). Below threshold, arena order is fine. |
| M59 perception lag makes needs system feel unresponsive | Medium | Agents always have perfect knowledge of own region (M49). M59 lag only affects cross-region information. Local conditions are immediate. |
| Landlocked allies decay to zero asabiya | Medium | Flag for M61. Soft frontier factor for federation/same-faith borders if needed. Don't pre-solve — validate first. |
| Cohort dynamics don't emerge due to independent tuning of M48/M50 | High | M53 explicitly validates cohort emergence as a cross-system target. If cohorts don't form, investigate memory decay, bond threshold, and slot eviction before proceeding. |
| M54 schedule risk from three complex Rust migrations | High | `[REVIEW B-1]` Mitigated: split into M54a/b/c with independent merge gates. Ecology (M54a) establishes pattern. Economy (M54b) is the critical path. Politics + spatial sort (M54c) can partially overlap with M54b. |
| M50 architecture gap — Python formation vs. Rust storage at 500K agents | High | `[REVIEW B-2]` M50 spec must resolve: (1) formation interface (Python signals vs Rust-owned logic), (2) O(N²) scaling without M55 spatial hash, (3) M40 transition plan. See B-2 inline tag on M50 section. |
| M53 cohort threshold structurally unreachable pre-M55 | Medium | `[REVIEW B-3]` Mitigated: threshold lowered to 5+ agents at M53 (depth scale), full 10+ validation deferred to M61 (post-spatial). |
| Calibration cascade across five tuning passes (M47→M53→M61→M67→M72) | Medium | `[REVIEW B-4]` Establish constant-locking discipline: constants frozen in one pass cannot be re-tuned in subsequent passes without explicit approval. Each pass produces a frozen snapshot. |
| 2.5x action weight cap designed for 3 contributors, now has 5 | Medium | `[REVIEW B-5]` Phase 6 has 3 (traditions, tech focus, factions). Phase 7 adds Mule (4th). Phase 8 institutions would be 5th. Cap mechanism needs resolution before M63 — either raise cap, add per-system contribution limits, or priority scheme. Phase 8 planning concern, not Phase 7. |
| M58 enrichment scope creep (gravity model, production functions) | Medium | `[REVIEW]` Endogenous route formation enrichment feels essential for agent-level trade value proposition. Expect 3-5 days of enrichment pull-in. Build interface to accept dynamic routes from day one, even if gravity model lands later. |
| Phase 7→8 "elite" concept bridge gap | Low | `[REVIEW]` Phase 8 EMP needs elite vs. wealthy distinction. Phase 7 has no "status" concept. Either M49 includes a status need, or M61 extractors compute PSI input quantities (median wealth, urbanization rate, youth bulge fraction). Resolve in Phase 8 spec, not Phase 7. |
