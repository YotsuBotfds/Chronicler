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

Two tracks: **Depth** (M48-M53, agent interiority at current scale) and **Scale** (M54-M61b, parallelism, spatial systems, logistics, and scale validation at 500K-1M agents). Depth track validates before scale track begins. Viewer/data-plane work now lives in the separate Phase 7.5 roadmap and starts after M61b freezes the export contract.

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
| M54c | Rust Politics Migration | Scale | M54a | 7-11 |
| M55a | Spatial Substrate | Scale | M54a | 4-5 |
| M55b | Spatial Asabiya | Scale | M55a | 3-4 |
| M56a | Settlement Detection | Scale | M55a | 2.5-3.5 |
| M56b | Urban Effects | Scale | M56a | 2.5-3.5 |
| M57a | Marriage Matching & Lineage Schema | Scale | M50, M55a | 2.5-3.5 |
| M57b | Households, Inheritance & Joint Migration | Scale | M57a | 3-4 |
| M58a | Merchant Mobility | Scale | M54b, M55a, M42-M43 | 3-4 |
| M58b | Trade Integration & Macro Convergence | Scale | M58a | 3-4 |
| M59a | Information Packets & Diffusion | Scale | M50, M55a | 2-3 |
| M59b | Perception-Coupled Behavior | Scale | M59a | 2.5-3.5 |
| M60a | Campaign Logistics | Scale | M55a, M59a | 3-4 |
| M60b | Battles & Occupation | Scale | M60a | 2.5-3.5 |
| M61a | Scale Harness & Determinism | Scale | M54a-c, M55a-b, M56a-b, M57a-b, M58a-b, M59a-b, M60a-b | 2.5-3.5 |
| M61b | Scale Validation & Calibration | Scale | M61a | 3-4.5 |

**Core Phase 7 estimate:** 92-129 days across 23 milestones/sub-milestones. **Phase 7.5 viewer follow-on:** 11-14 days in the separate viewer roadmap. **Combined Phase 7 + 7.5 program:** 103-143 days before enrichment pull-in. Realistic combined estimate including integration cost, regression/debug loops, and session overhead: **115-155 days**. No contingency buffer; plan operationally for milestone reviews every 2-3 milestones with scope cuts if needed.

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

**Constants:** 6 decay rates + 6 thresholds + 6 weights + ~16 restoration conditions + 3 infrastructure constants = ~37 `[CALIBRATE]` constants. Tuned in M53.

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
> 2. **Hidden M55a dependency.** "Shared region" formation triggers fire for every co-located agent pair. At 500 agents/region, that's 125K pairs per region per tick — O(N²). This is expensive at 50K agents without spatial partitioning. M55a's spatial hash would fix this (only check nearby agents), but M50 is in the Depth track (before M55a). The M50 spec must either: (a) use a coarser proximity proxy (agent index within region), (b) run formation checks every N ticks instead of every tick, or (c) accept O(N²) at Depth scale and optimize when M55a lands.
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

M48, M50, and M55a are designed as separate systems, but their interaction produces something bigger: **emergent cohorts.**

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
- Children can inherit legacy memories from both parents if the marriage/lineage system exists (M57a+), otherwise from the single parent tracked by M39

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

> `[REVIEW B-3]` **Adjusted for pre-M55a context.** M53 runs before spatial positioning exists. With 500 agents sharing a famine memory in a region, all share the bond eligibility trigger. At 8 relationship slots per agent, the probability of 10+ agents forming mutual bonds (bidirectional, each in the other's slot list) from a pool of 500 is low without spatial clustering. M53 validates the *interaction works* (memory → bond → behavioral effect). Full cohort validation at 10+ agents deferred to M61b, after M55a's spatial hash enables proximity-based formation. Distinguish first-generation cohorts (20-50 turn lifecycle) from inherited cohorts (legacy-memory descendants, potentially multi-generational).

- **Cohort emergence (depth-scale threshold):** Do groups of 5+ agents with mutual bonds and shared memories form consistently across 200-seed runs? Measure: count agent clusters where ≥80% of members share at least one memory event_type+turn AND have mutual friend/grudge bonds. **Full validation (10+ agents) deferred to M61b** after spatial positioning enables proximity-gated formation.
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

## Scale Track (M54-M61b)

### M54a/b/c: Rust Phase Migration

> `[REVIEW B-1]` **Split into three sub-milestones with independent merge gates.** The original M54 (25-35 days) is larger than any previous milestone by 3×. Each phase migration has different data dependency profiles, different parallelization strategies, and different FFI surface requirements. Splitting matches the M43a/M43b and M38a/M38b precedent, provides three checkpoints instead of one, and allows M54b/M54c to plan against the FFI pattern established by M54a. A regression at the economy migration doesn't block politics migration progress. M54b and M54c can partially overlap after M54a establishes the pattern.

**Goal:** Migrate the three heaviest Python phases to Rust with rayon parallelism, removing the Amdahl's Law bottleneck before agent count increases.

**Sub-milestones:**

**M54a: Ecology Migration (8-11 days).** Per-region, embarrassingly parallel. Soil/water/forest coupling is local to each region. rayon `par_iter` over regions. Simplest of the three — start here to establish the migration pattern and FFI surface. Gate: determinism test at 1/4/8/16 threads. Establishes the Arrow-batch-in, Arrow-batch-out FFI pattern for M54b/c. The generic sort infrastructure that earlier planning sketches attached here was ultimately absorbed by M55a.

**M54b: Economy Migration (10-14 days).** `economy.py` (1,015 lines pre-M47, ~1,095 after tatonnement) has transport costs, perishability tables, stockpile accumulation/decay/cap, salt preservation, conservation law tracking, shock detection, trade dependency classification, and the raider modifier. Trade flow computation has cross-region data dependencies — region-level parallelism with synchronization at the trade flow step. The most complex migration. `[REVIEW]` Estimate revised from 9-12 to 10-14 to account for EconomyTracker state handoff and trade flow synchronization design work. Gate: determinism test + conservation law verification.

**M54c: Politics Migration (7-11 days).** Secession and federation checks can read agent distributions directly from the pool instead of round-tripping through Python snapshots. Complex stateful logic but fewer data dependencies than economy. Gate: determinism test + bit-identical `--agents=off` output.

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

**Goal:** Build the radix sort machinery and benchmark harness for cache-efficient agent pool iteration. Earlier planning attached a region-index-only precursor to M54a, but the final M55 closeout kept the whole sort story in M55a: one generic index-sort module supports both region-key ordering and full Morton/Z-order keys once `(x, y)` exists.

**Rationale:** At 1M agents, the SoA pool exceeds L2 cache. Agent order in memory is determined by allocation/deallocation patterns, which have no relationship to spatial position. Full-pool sweeps (satisfaction, demographics, wealth decay) benefit significantly from memory locality — agents processed sequentially should be spatially proximate.

**Final M55a implementation target:**
- Radix sort on composite keys, operating on the agent pool's index array (not moving SoA data — sort the index, then iterate in sorted order)
- Region-key control/fallback path: `region_index`
- Morton path: `(region_index, morton(x, y), agent_id)` so same-region agents stay contiguous while within-region locality improves
- Benchmark harness: measure tick time with arena order vs. region-key ordering vs. Morton ordering at 50K, 100K, 500K, and 1M agents (synthetic pools for the larger sizes)
- Activation threshold: only sort above `SPATIAL_SORT_AGENT_THRESHOLD` `[CALIBRATE]` (target: 100K). Below threshold, arena order is fine — the pool fits in L2.

**Sort frequency:** Every tick. Radix sort on `u32` keys at 1M elements takes ~4ms. If the tick is 200ms, that's 2% overhead for a potential 15-30% speedup on cache-sensitive phases. Start with every tick; reduce frequency only if profiling shows the sort itself is a bottleneck.

**Determinism:** Sort must produce identical ordering given identical pool state — verify with seed comparison test.

#### NUMA-Aware Iteration (Experimental)

**Goal:** Evaluate whether CCD-aware thread pinning improves tick performance on the 9950X's 2-CCD topology. +0.5 day if pursued.

**Approach:** Partition the region list into two halves (roughly equal agent count), pin each half to a CCD via thread affinity, run rayon within each partition. Cross-partition interactions (trade routes, migration between partitions) require a synchronization step.

**Decision gate:** Profile the agent tick at 500K agents with and without CCD affinity. If cross-CCD traffic is less than 10% of tick time, skip it — the engineering complexity isn't worth marginal gains. Document results regardless of whether the optimization ships.

---

### M55a: Spatial Substrate

**Goal:** Give agents continuous `(x, y)` coordinates, deterministic movement, spatial indexing, and proto-settlement clustering pressure. This is the substrate milestone: make space *real* before layering spatially emergent institutions or civ-level formulas on top.

**Depends on:** M54a. M55a absorbs the generic sort infrastructure and Morton activation itself, so the spatial branch still starts as soon as M54a lands and no longer waits on M54c.

**Storage:** 2 x `f32` = 8 bytes/agent.

**Tick integration:**
- Agents have a position within their region's unit square `[0,1) x [0,1)`.
- Migration changes region and resets position deterministically within the new region.
- Within-region movement uses weak drift toward attractors plus short-range density attraction and a repulsion/saturation term.
- Proximity queries use a per-region spatial hash with O(1) average neighborhood lookup.

**Proto-settlement clustering pressure:** M55a explicitly owns the forces that make M56a viable as a detection milestone instead of an artificial creator. Start with deterministic attractor seeds from geography and existing simulation facts:
- river/coast access,
- high-yield resource sites,
- temples,
- capital or administrative centers where available.

Layer occupation-weighted attraction on top of those seeds:
- farmers prefer resource/yield attractors,
- clergy prefer temple attractors,
- merchants prefer route/intersection attractors once available.

Add weak local density attraction with a cap plus repulsion so clusters become persistent hotspots rather than single-point collapse.

**Spatial hash:** At ~500 agents/region, a 10x10 grid gives roughly 5 agents per cell. Neighbor checks become `9 cells x ~5 agents = ~45 candidates`, which is the whole point of landing this before the larger social/logistics milestones.

**Morton sort activation:** With real coordinates available, extend M54a's region-index sort key to a full Morton/Z-order key: `morton_code(region_index, x, y)`. Region index stays in the high bits so same-region agents stay contiguous; `(x, y)` ordering improves cache locality within each region.

**Required diagnostics:** M55a should already export the metrics later milestones need:
- hotspot persistence / non-uniform density,
- attractor occupancy,
- spatial hash occupancy distribution,
- Morton sort determinism/perf counters.

**Gate:** Spatial state is deterministic across thread counts, hotspot formation is measurably non-uniform, and the hash/sort infrastructure is trustworthy enough for downstream systems.

---

### M55b: Spatial Asabiya

**Goal:** Replace the civ-level asabiya scalar with a spatially emergent quantity derived from regional frontier status, then expose the resulting mean/variance structure to collapse and military-projection logic.

**Depends on:** M55a.

**Phase 6 asabiya is unchanged until this milestone lands.** `civ.asabiya` continues to exist as a field; M55b changes where it comes from, not how the rest of the code reads it.

**Baseline formulation (Turchin-inspired):**

Frontier region:
```text
S(t+1) = S(t) + r0 * S(t) * (1 - S(t))
```

Interior region:
```text
S(t+1) = S(t) - delta * S(t)
```

Civ-level asabiya:
```text
civ.asabiya = weighted_average(region_asabiya, weights=region_population)
```

**Preferred spec question:** keep the current binary frontier/interior model as the simple baseline, but evaluate a cheap "frontier fraction" variant in the spec if binary oscillation looks too sharp:
```text
f = foreign_neighbors / total_neighbors
growth = r0 * f * S * (1 - S)
decay = delta * (1 - f) * S
```

**Transition strategy:** When M55b lands, Phase 6 Culture can either:
- guard old direct asabiya mutations when spatial asabiya is active, or
- continue to mutate and then be overwritten by the regional aggregation.

The roadmap preference remains the second approach if it avoids Phase 6 rework, but the spec should make the transition explicit.

**Phase 10 extension:** Collapse logic can now read both mean asabiya and *variance*. High mean + extreme regional variance becomes a richer collapse precursor than a single civ-level scalar.

**Phase 4 extension:** Military projection decays with distance from the capital:
```text
P = A * mean(S) * exp(-d / h)
```
This gives MOVE_CAPITAL and campaign range more structural grounding before M60b battle resolution enters the picture.

**Landlocked ally concern:** Civs surrounded by federation or same-faith neighbors may need a soft-frontier factor in M61b if pure frontier/interior dynamics decay them toward zero.

**Constants:**

| Constant | Role | Calibrate in |
|----------|------|-------------|
| `ASABIYA_FRONTIER_GROWTH_RATE` (r0) | Logistic growth rate on frontier regions | M61b |
| `ASABIYA_INTERIOR_DECAY_RATE` (delta) | Linear decay rate in interior regions | M61b |
| `ASABIYA_POWER_DROPOFF` (h) | Distance decay factor for military projection | M61b |
| `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD` | Variance level that triggers elevated collapse risk | M61b |

---

### M56a: Settlement Detection

**Goal:** Detect and persist settlement structure from the clustering pressure created in M55a. This milestone answers "where are the proto-cities?" without yet wiring all urban/rural effects.

**Depends on:** M55a.

**Key insight:** clustering is still detection, not creation. M55a owns the forces that make hotspots appear; M56a labels, persists, and names them.

**Mechanism:**
- Per-region density-based clustering every `SETTLEMENT_DETECTION_INTERVAL` ticks.
- Clusters above threshold become settlement candidates.
- Candidates that persist through consecutive passes become named settlements with stable IDs and `founding_turn`.

**Settlement inertia:** Settlements get an inertia counter based on population and age. If a cluster dissolves briefly, inertia absorbs the hit; if the cluster persists, inertia resets. This is the anti-flicker layer.

**Storage:** Per-region settlement list on the Python side, analogous to artifacts: low volume, high narrative value, and easy to expose to analytics/narration.

**Gate:** Settlements form, persist, and dissolve plausibly; IDs remain stable; clustering diagnostics are available before M56b starts consuming the results mechanically.

---

### M56b: Urban Effects

**Goal:** Turn settlements from labels into mechanical context by wiring urban/rural modifiers into needs, production, culture, safety, and narration.

**Depends on:** M56a.

**Behavioral split:**
- Urban agents: higher material/social access, lower safety, faster cultural drift, stronger market/temple exposure.
- Rural agents: higher food efficiency, higher safety, slower cultural drift, weaker material access.

**Runtime state:** Rust only needs a per-agent `is_urban: bool` or `settlement_id: u16`-style signal for downstream behavior. Keep the heavy settlement objects in Python-side world state.

**Gate:** Urban/rural effects are measurable and legible without destabilizing unrelated needs or economy baselines.

---

### M57a: Marriage Matching & Lineage Schema

**Goal:** Add proximity-based marriage formation and land the schema migration from single-parent to two-parent lineage. This is the invasive data-model half of the marriage milestone.

**Depends on:** M50 and M55a.

**Matching:** Per-region, per-tick (or per-N ticks). Eligible nearby agents form marriage bonds based on compatibility and opportunity, not global optimization. Cross-faith marriages remain possible but rarer.

**Schema migration:** `parent_id` becomes `parent_ids: [u32; 2]` with `PARENT_NONE` sentinels for single-parent cases. Dynasty logic must stay compatible.

**Scope guard:** This milestone does **not** yet take on pooled wealth, joint migration, or widowhood behavior. It establishes the durable social/data substrate first.

**Gate:** Marriage bonds form correctly, births and lineage resolution still work, and the schema migration does not destabilize dynasty/succession logic.

---

### M57b: Households, Inheritance & Joint Migration

**Goal:** Build the household-level mechanics on top of M57a's bond/schema substrate.

**Depends on:** M57a.

**Household model:**
- married pairs pool income/wealth for household-level material context,
- children inherit from both parents,
- joint migration moves spouses together,
- widowhood hands pooled wealth and child custody to the surviving spouse.

**Scope guard:** No divorce, no polygamy, no complex household trees. The value is in economic and lineage coherence, not relationship-drama simulation.

**Gate:** Household economics, migration, and inheritance all work together without regressing wealth, demographics, or dynasty systems.

---

### M58a: Merchant Mobility

**Goal:** Make merchants physically move goods through space. This milestone is about route choice, cargo reservation/loading, transit state, and travel - not yet full macro-convergence against the abstract economy.

**Depends on:** M54b, M55a, and M42-M43.

**Mechanism:**
- merchants evaluate candidate destinations from visible price differentials,
- choose a route,
- reserve/load goods from regional surplus,
- travel one region per turn with spatial updates,
- keep in-transit state visible to diagnostics.

**Compute profile:** At 50K merchants and ~5-10 candidate routes each, this is already a major parallel workload. Splitting it from M58b keeps the first debugging pass focused on movement and state transitions rather than economy-wide calibration fallout.

**Required diagnostics:** route choice distributions, in-transit goods, merchant trip duration, and route profitability counters.

**Gate:** Merchants move coherently through the world and transit state is inspectable before their effects are used as the new macro trade truth.

---

### M58b: Trade Integration & Macro Convergence

**Goal:** Turn merchant movement into economy-level outcomes and validate that the agent path converges toward the M42-M43 abstract baseline.

**Depends on:** M58a.

**Integration responsibilities:**
- delivery/write-back of goods,
- regional supply/availability effects,
- merchant wealth realization,
- stale-vs-current price interpretation where needed,
- analytics surfaces needed for baseline comparison.

**M42-M43 remains the macro specification.** The abstract trade model still serves as:
1. the `--agents=off` path,
2. the regression baseline,
3. the narration/analytics scaffold.

M58b is where the doubled trade code surface earns its keep: the agent-level system has to produce comparable macro patterns, not just "interesting" local behavior.

**Gate:** Price gradients, trade volumes, and food sufficiency stay within an acceptable comparison band versus the abstract model.

---

### M59a: Information Packets & Diffusion

**Goal:** Build the packet substrate that lets agents carry cross-region knowledge through the social graph with lag and decay.

**Depends on:** M50 and M55a.

**Mechanism:**
- information packets of the form `(info_type, source_region, turn, intensity)`,
- 2-4 active packets per agent,
- propagation probability weighted by relationship sentiment / channel type,
- decay and staleness on each hop,
- diagnostics for source channel, freshness, and lag.

**Propagation priorities:** trade opportunity and threat warning should spread fastest; religious and political signals can move more slowly or along more selective bond types.

**Gate:** Diffusion is deterministic, inspectable, and already emitting the lag/staleness statistics M59b and M61b will need.

---

### M59b: Perception-Coupled Behavior

**Goal:** Let agents actually act on propagated information, including stale or partially wrong information.

**Depends on:** M59a.

**Behavioral effects:**
- merchants react to learned trade opportunities,
- migrants and loyalists react to distant threats,
- agents can act on stale data if conditions changed before the packet arrived.

This is where M59 stops being an information layer and becomes a decision-system modifier.

**Gate:** Cross-region awareness changes behavior in measurable ways without making needs or loyalty feel instantly omniscient.

---

### M60a: Campaign Logistics

**Goal:** Build army rally, marching, supply, morale, and desertion before adding battle-resolution complexity.

**Depends on:** M55a and M59a.

**Mechanism:**
- WAR selects a staging region,
- soldiers rally and march through the region graph,
- supply line length, unmet needs, and information quality influence morale and desertion,
- campaign state is visible even before the first battle resolves.

**Why split here:** Logistics bugs and combat bugs are different categories. M60a should prove that campaigns move plausibly and stop naturally before battle outcome tuning starts.

**Gate:** Armies rally and march coherently, campaign range is limited by logistics rather than arbitrary caps, and supply/desertion diagnostics are ready for M60b and M61b.

---

### M60b: Battles & Occupation

**Goal:** Resolve battles and conquests using the campaign substrate from M60a.

**Depends on:** M60a.

**Mechanism:**
- battle resolution based on army composition, morale, terrain, and supply context,
- casualties become actual agent deaths,
- survivors return, garrison, or occupy conquered territory,
- occupation aftermath feeds the wider simulation without inventing a tactical mini-game.

**Scope guard:** No formations, flanking, or per-soldier duel simulation. The campaign remains the core abstraction.

**Gate:** Battle outcomes are believable, occupation/conquest side effects remain consistent with the rest of the sim, and the war system stays understandable at the aggregate level.

---

### M61a: Scale Harness & Determinism

**Goal:** Build the harness that measures whether the scale track is trustworthy before spending time tuning it.

**Depends on:** M54a-c, M55a-b, M56a-b, M57a-b, M58a-b, M59a-b, and M60a-b.

**Responsibilities:**
- cross-thread determinism replays (1/4/8/16 threads),
- memory-budget and perf benchmarks,
- Morton sort benchmark comparisons,
- replay hooks and milestone-owned debug counters,
- NUMA experiment harness/documentation.

**Structural rule:** validation plumbing should ship with the milestone that creates the behavior, not appear for the first time in M61. M61a is the assembly point for those signals, not their origin.

**Gate:** You trust the measuring instruments before using them to approve or reject the full scale track.

---

### M61b: Scale Validation & Calibration

**Goal:** Calibrate the scale-track systems at 500K-1M agents and sign off the full simulation-side Phase 7 program.

**Depends on:** M61a.

**Critical validations:**
- **Determinism:** same seed, identical output regardless of thread count.
- **Performance:** tick time under 200ms at 1M agents on 16 cores.
- **Memory:** total pool under 250MB at 1M agents.
- **Behavioral stability:** same qualitative emergent patterns at 500K as at 50K.
- **Settlement emergence:** cities form in 80%+ of large runs and do not flicker pathologically.
- **Trade patterns:** M58b stays within the agreed comparison band versus M42-M43.
- **Military realism:** campaign range is naturally limited by supply/morale to ~3-5 regions.
- **Spatial asabiya collapse prediction:** variance predicts elevated collapse risk within a useful lead window.
- **Spatial asabiya expansion balance:** frontier growth and interior decay reach equilibrium in stable empires.
- **Landlocked ally check:** allied-border civs do not decay to zero solidarity without a soft-frontier correction.
- **Cohort scaling:** the cohort dynamics validated at M53 still emerge at 500K-1M.
- **Full cohort validation (deferred from M53):** authoritative 10+ agent threshold with real spatial proximity.

**Spatial asabiya constants tuned here:**

| Constant | Role |
|----------|------|
| `ASABIYA_FRONTIER_GROWTH_RATE` (r0) | Logistic growth on frontier regions |
| `ASABIYA_INTERIOR_DECAY_RATE` (delta) | Linear decay in interior regions |
| `ASABIYA_POWER_DROPOFF` (h) | Distance decay for military projection |
| `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD` | Variance trigger for elevated collapse risk |
| `SOFT_FRONTIER_FACTOR` (if needed) | Reduced growth rate for allied-border regions |

---

### Phase 7.5 Follow-On: Viewer & Bundle Compatibility

Viewer/data-plane work now lives in the separate Phase 7.5 roadmap:
`docs/superpowers/roadmaps/chronicler-phase75-viewer-roadmap.md`

The handoff remains:
- **M62a:** Export Contracts & Bundle v2
- **M62b:** Viewer Data Plane & Spatial Foundations
- **M62c:** Entity, Trade & Network Panels

Phase 7 now ends at M61b, when the simulation outputs and validation surfaces are stable enough for the viewer to target without chasing schema churn.

---

## Per-Agent Memory Budget

| System | Bytes/agent | At 50K | At 500K | At 1M |
|--------|-------------|--------|---------|-------|
| Phase 6 baseline | 68 | 3.4MB | 34MB | 68MB |
| Memory ring buffer (M48, 8 slots) | 64 | 3.2MB | 32MB | 64MB |
| Needs (M49) | 24 | 1.2MB | 12MB | 24MB |
| Deep relationships (M50) | 48 | 2.4MB | 24MB | 48MB |
| Spatial position (M55a) | 8 | 0.4MB | 4MB | 8MB |
| Settlement flag (M56a/M56b) | 2 | 0.1MB | 1MB | 2MB |
| Marriage (M57a) | 4 | 0.2MB | 2MB | 4MB |
| Info packets (M59a, 4 slots) | 24 | 1.2MB | 12MB | 24MB |
| **Phase 7 total** | **242** | **12.1MB** | **121MB** | **242MB** |

242MB at 1M agents. 192GB DDR5 provides ~790× headroom.

Mule flag is 1 bit on GreatPerson (Python-side, negligible). Utility overrides are a small dict on GreatPerson (Python-side, negligible). Morton sort keys are transient (computed, sorted, discarded). Spatial asabiya is per-region (not per-agent — stored on Region, ~200 regions × 4 bytes = negligible).

---

## Dependency Graph

```text
M47 (Phase 6 tuning)
  -> M48 (Agent Memory + Mule Promotions) -----------+
       -> M49 (Needs System)                         |
       -> M50 (Deep Relationships) <- M40           |
            -> [feeds M57a, M59a]                   |
       -> M51 (Multi-Gen Memory) <- M39             |
       -> M52 (Artifacts + Mule Artifacts)          |
                                                     |
M53 (Depth Tuning) <- M48-M52 ----------------------+
  -> M54a (Rust Ecology)
       -> M54b (Rust Economy)                       <- can overlap with M54c and the spatial branch
       -> M54c (Rust Politics)                      <- can overlap with M54b and the spatial branch
       -> M55a (Spatial Substrate + Sort Infrastructure)
            -> M55b (Spatial Asabiya)
            -> M56a (Settlement Detection)
                 -> M56b (Urban Effects)
            -> M57a (Marriage + Lineage Schema) <- M50
                 -> M57b (Households)
            -> M59a (Information Packets) <- M50
                 -> M59b (Perception-Coupled Behavior)
            -> M60a (Campaign Logistics) <- M59a
                 -> M60b (Battles + Occupation)
M54b + M55a + M42-M43 -> M58a (Merchant Mobility)
                           -> M58b (Trade Integration + Macro Convergence)

M61a (Scale Harness) <- M54a-c, M55a-b, M56a-b, M57a-b, M58a-b, M59a-b, M60a-b
  -> M61b (Scale Validation + Calibration)
       -> Phase 7.5 / M62a-M62c (Viewer & Bundle Compatibility)
```

`[REVIEW]` M54c is politics-only, and the spatial branch starts as soon as M54a lands instead of waiting on the full Rust migration set. After M54a landed without the planned precursor sort work, M55a absorbed both the generic sort infrastructure and Morton activation. Phase 7 itself now ends at M61b; the viewer handoff lives in the separate Phase 7.5 roadmap.

---

## Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Mule influence via time-bounded civ-level weight modifier (0.5-0.8 floor, 20-30 turn active window, 10 turn fade), not permanent subtle nudge | Asimov's Mule doesn't nudge — he warps. A permanent 0.3 additive weight is undetectable in the action distribution. A 0.5-0.8 weight for 20-30 turns creates a dramatic, narratively visible window. Time-bounding prevents permanent simulation distortion. |
| D2 | Generic sort infrastructure and Morton activation ship together in M55a | M54a landed without the precursor sort module. M55a has the full spatial context, so it ships one generic index-sort module with a region-key control path, Morton runtime path, and shared benchmark harness. |
| D3 | Phase 6 asabiya unchanged; M55b replaces computation | Clean transition. Phase 6 code ships as-is. M55b swaps the source of `civ.asabiya` from direct mutation to regional aggregation. No Phase 6 rework. |
| D4 | M59 reframed as perception lag layer, not flavor system | Information propagation is the formalization of the macro→micro channel. Perfect local perception (M49) + graph-distance lag (M59) gives tunable coupling. Design notes only — no code or dependency change. |
| D5 | Memory ring buffer 8 slots (CALIBRATE 6-8), not 4 | 4 slots fills in 4 turns. M51 legacy memories occupy 2 slots at birth. 8 slots lets agents accumulate enough lived experience for cohort dynamics to form. +32 bytes/agent = 32MB at 1M, negligible. |
| D6 | M42-M43 abstract trade is the macro specification for M58b, not legacy code | Abstract model serves as `--agents=off` path, regression baseline, and narration scaffold. Agent-level trade must converge to similar macro distributions. Doubled code surface is the cost of calibration rigor. |
| D7 | Needs mechanically orthogonal to satisfaction, exposed to narrator | "Content but spiritually adrift" is a valid narrative state. No mechanical coupling needed. Risk of incoherence only if narrator can't see need state — so expose it. |
| D8 | Settlement detection every 10-20 ticks with inertia counter in M56a, not per-tick creation | Clustering detects what M55a drift/attractor dynamics already created. Inertia = f(population, age) prevents flicker. Older/larger settlements persist through temporary dips. |
| D9 | Validation plumbing ships with each split milestone, not only in M53/M61 | Each system should land with its minimum extractors, debug counters, and replay hooks while the implementation context is fresh. Tuning passes aggregate signals; they should not invent observability from scratch. |

---

## New Constants Summary

| Constant | Source | Calibrate in |
|----------|--------|-------------|
| `MULE_PROMOTION_PROBABILITY` | Mule promotions (M48) | M53 |
| `MULE_UTILITY_PERTURBATION_SCALE` | Mule promotions (M48) | M53 |
| `MULE_UTILITY_FLOOR` | Mule promotions (M48) | M53 |
| `MULE_ACTIVE_WINDOW` | Mule promotions (M48) | M53 |
| `MULE_FADE_TURNS` | Mule promotions (M48) | M53 |
| `ASABIYA_FRONTIER_GROWTH_RATE` | Spatial asabiya (M55b) | M61b |
| `ASABIYA_INTERIOR_DECAY_RATE` | Spatial asabiya (M55b) | M61b |
| `ASABIYA_POWER_DROPOFF` | Spatial asabiya (M55b) | M61b |
| `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD` | Spatial asabiya (M55b) | M61b |
| `SPATIAL_SORT_AGENT_THRESHOLD` | Region/Morton sort infra (M55a) | M61b |
| `SETTLEMENT_DETECTION_INTERVAL` | Settlement detection (M56a) | M61b |

11 new constants. All deferred to existing tuning passes (M53 for depth, M61b for scale).

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
| 1400 | Spatial position init + drift | M55a |
| 1500 | Settlement detection noise | M56a |
| 1600 | Marriage matching | M57a |
| 1700 | Merchant route selection | M58a |
| 1800 | Information propagation noise | M59a |
| 1900 | Military rally / desertion rolls | M60a |

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
| Two-parent lineage (`parent_id` -> `parent_ids`) | No breakage — schema migration lands in M57a, while household behavior waits for M57b. Dynasty resolution for two-parent lineage remains a design question handled in the M57 spec. | — |
| Spatial positioning determinism | M55a adds the new `STREAM_OFFSETS` entries for position init and drift. Existing registry pattern and collision test (`agent.rs:202`) handle this. | — |

---

## Phase 8-9 Horizon

See `chronicler-phase8-governance-roadmap.md` for the Phase 8 Governance draft roadmap (M63-M67). Brainstorm-level ideas remain in `chronicler-phase8-9-horizon.md`. Phase 9 Culture milestones (M68-M73) and deferred items are cataloged at the end of the Phase 8 roadmap.

---

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Memory system creates feedback loops with satisfaction | High | M53 tuning gate before scale. Memory satisfaction weight is `[CALIBRATE]` with hard cap. |
| Needs system adds too many tuning dimensions (37+ constants) | Medium | Reduce to 4 needs if 6 proves intractable. Fewer well-tuned needs > many poorly-tuned. |
| Deep relationships saturate at maximum sentiment (all friends) | Medium | Slot eviction + sentiment decay prevent saturation. Rivalry/grudge formation balances positive bonds. |
| Rust phase migration introduces non-determinism | High | Per-phase determinism tests: same seed, different thread counts, bit-identical output. |
| Spatial hash performance at 1M agents | Medium | Grid cell size tuning. Fallback: k-d tree per region if hash degrades. |
| Agent-level trade doubles trade code (abstract + agent paths) | Medium | Abstract path is calibration specification, not dead weight. Accept the code surface. |
| Military units make WAR action too detailed (mini-wargame creep) | Medium | Scope guard: aggregate battle resolution only. No per-soldier combat. |
| 242 bytes/agent exceeds L1 per-region at high density | Low | At 500 agents × 242 bytes = 121KB, exceeds 64KB L1. Mitigated by SoA layout — each phase accesses specific fields, not whole agent. Working set per phase stays in L1. |
| Spatial asabiya creates expansion feedback loop | Medium | Logistic ceiling `(1 - S)` is self-limiting. Interior decay offsets frontier growth at scale. Validate in M61b. |
| Mule frequency too high destabilizes simulation | Low | 5-10% of already-rare GreatPerson promotions. ~1 Mule per 100 turns at 50K agents. Weight cap (2.5x) and time-bounding limit influence. |
| Morton sort overhead exceeds cache benefit at low agent counts | Low | Only activate above `SPATIAL_SORT_AGENT_THRESHOLD` (target: 100K). Below threshold, arena order is fine. |
| M59 perception lag makes needs system feel unresponsive | Medium | Agents always have perfect knowledge of own region (M49). M59 lag only affects cross-region information. Local conditions are immediate. |
| Landlocked allies decay to zero asabiya | Medium | Flag for M61b. Soft frontier factor for federation/same-faith borders if needed. Don't pre-solve — validate first. |
| Cohort dynamics don't emerge due to independent tuning of M48/M50 | High | M53 explicitly validates cohort emergence as a cross-system target. If cohorts don't form, investigate memory decay, bond threshold, and slot eviction before proceeding. |
| M54 schedule risk from three complex Rust migrations | High | `[REVIEW B-1]` Mitigated: split into M54a/b/c with independent merge gates. M54a establishes the shared migration pattern. M54b remains the critical path; M54c can slip without blocking M55a. |
| M50 architecture gap — Python formation vs. Rust storage at 500K agents | High | `[REVIEW B-2]` M50 spec must resolve: (1) formation interface (Python signals vs Rust-owned logic), (2) O(N²) scaling without M55a's spatial hash, (3) M40 transition plan. See B-2 inline tag on M50 section. |
| M53 cohort threshold structurally unreachable pre-M55a | Medium | `[REVIEW B-3]` Mitigated: threshold lowered to 5+ agents at M53 (depth scale), full 10+ validation deferred to M61b (post-spatial). |
| Calibration cascade across five tuning passes (M47→M53→M61→M67→M72) | Medium | `[REVIEW B-4]` Establish constant-locking discipline: constants frozen in one pass cannot be re-tuned in subsequent passes without explicit approval. Each pass produces a frozen snapshot. |
| 2.5x action weight cap designed for 3 contributors, now has 5 | Medium | `[REVIEW B-5]` Phase 6 has 3 (traditions, tech focus, factions). Phase 7 adds Mule (4th). Phase 8 institutions would be 5th. Cap mechanism needs resolution before M63 — either raise cap, add per-system contribution limits, or priority scheme. Phase 8 planning concern, not Phase 7. |
| M58 enrichment scope creep (gravity model, production functions) | Medium | `[REVIEW]` Endogenous route formation enrichment feels essential for agent-level trade value proposition. Expect 3-5 days of enrichment pull-in. Build interface to accept dynamic routes from day one, even if gravity model lands later. |
| Phase 7→8 "elite" concept bridge gap | Low | `[REVIEW]` Phase 8 EMP needs elite vs. wealthy distinction. Phase 7 has no "status" concept. Either M49 includes a status need, or M61a/M61b extractors compute PSI input quantities (median wealth, urbanization rate, youth bulge fraction). Resolve in Phase 8 spec, not Phase 7. |
