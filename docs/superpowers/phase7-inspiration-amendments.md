# Phase 7 Draft Amendments — Threads from the Inspiration Deep Dive

> **Status:** Proposed. For Phoebe review before incorporation into Phase 7 draft.
>
> **Source:** "Systems Architectures for Procedural Historiography" deep research document, cross-referenced against `chronicler-phase7-draft.md` and Phase 6 progress.
>
> **Date:** 2026-03-18

---

## Summary

Four threads from the inspiration document map onto existing Phase 7 milestones as enrichments. No new milestones required. Estimated additional implementation: 3-5 days total, distributed across affected milestones.

| Thread | Target Milestone | Nature of Change |
|--------|-----------------|------------------|
| Spatial Asabiya | M55 (Spatial Positioning) | New downstream effect + Phase 10 read change |
| Mule Promotions | M48 (Agent Memory) + M52 (Artifacts) | New GreatPerson variant + artifact trigger |
| Space-Filling Curves & NUMA | M54 (Rust Phase Migration) | Performance requirement + optimization pass |
| Bidirectional Feedback Formalization | M49 (Needs) + M59 (Info Propagation) | Design note clarifying perception lag model |

---

## Thread 1: Spatial Asabiya

### What the inspiration document says

Turchin's metaethnic frontier theory provides equations for spatially-resolved social solidarity. Asabiya grows logistically on frontier cells (bordering a different polity) and decays linearly in interior cells:

- Frontier: `S(t+1) = S(t) + r0 * S(t) * (1 - S(t))`
- Interior: `S(t+1) = S(t) - delta * S(t)`

Imperial asabiya is the average of regional values. Military power scales as `P = A * mean(S) * exp(-d/h)` where `d` is distance from capital and `h` is a logistic drop-off factor.

### Current state in Chronicler

Asabiya is a civ-level scalar, mutated in Phase 6 (Culture) and routed through the StatAccumulator as `keep`. It influences action weights and political stability but has no spatial decomposition. A 50-region empire has the same asabiya everywhere — the frontier province and the capital province are indistinguishable.

### Proposed amendment to M55

Add a sixth downstream effect to M55's "Downstream effects" section:

**Asabiya spatial decomposition.** With M55's per-agent coordinates and existing region adjacency, compute per-region asabiya as a derived quantity each turn. Regions whose adjacency list includes a region belonging to a different civilization receive the frontier growth formula. Regions entirely surrounded by same-civ territory receive the interior decay formula. The civ-level asabiya becomes the population-weighted average of regional values.

This replaces the current Phase 6 civ-level asabiya mutation with a spatially emergent version. The existing `keep` routing through the StatAccumulator changes to a post-M55 computation that reads regional frontier status from the adjacency graph.

### Downstream implications

**Phase 10 (Consequences):** Political collapse currently reads civ-level asabiya. With spatial decomposition, collapse logic can additionally read asabiya *variance* — an empire with high average asabiya but extreme variance (zealous frontier, decadent core) is more collapse-prone than one with uniform moderate solidarity. This is historically accurate (late Roman Empire, late Abbasid Caliphate) and generates richer narrative hooks.

**Phase 4 (Military):** The `exp(-d/h)` power projection formula means military strength degrades with distance from the capital. This naturally limits expansion and creates a reason for MOVE_CAPITAL actions beyond the current heuristics. Pairs well with M60's supply line mechanics.

**M61 validation target:** Add "asabiya variance predicts collapse within 20 turns in 70%+ of 200-seed runs where variance exceeds threshold."

### Implementation estimate

+1 day on M55. Per-region frontier detection is O(regions * avg_adjacency), trivial. The asabiya growth/decay formulas are four lines of arithmetic. The civ-level aggregation is a weighted average. The Phase 10 variance read is a single additional check.

### New constants

| Constant | Role | Calibrate in |
|----------|------|-------------|
| `ASABIYA_FRONTIER_GROWTH_RATE` (r0) | Logistic growth rate on frontier regions | M61 |
| `ASABIYA_INTERIOR_DECAY_RATE` (delta) | Linear decay rate in interior regions | M61 |
| `ASABIYA_POWER_DROPOFF` (h) | Distance decay factor for military projection | M61 |
| `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD` | Variance level that triggers elevated collapse risk | M61 |

### Risks

- Spatial asabiya creates a positive feedback loop: frontier expansion → more frontier → more asabiya growth → more expansion. Mitigation: the logistic ceiling `(1 - S)` in the frontier formula is self-limiting. As S approaches 1.0, growth slows to zero. Additionally, more territory means more interior regions, which decay — the two effects balance.
- Replacing the current civ-level asabiya mutation changes Phase 6 behavior. Mitigation: the civ-level value is preserved as an aggregate. Existing code that reads `civ.asabiya` continues to work — it just reads a spatially-derived value instead of a directly-mutated one.

---

## Thread 2: Mule Promotions

### What the inspiration document says

Project Psychohistory includes a "Mule" event — an unpredictable outlier individual whose actions break the statistical model. This is distinct from a black swan (emergence.py), which is an event. The Mule is a *person* whose decisions are statistically improbable given the current system state, creating cascading consequences that the macro model doesn't predict.

### Current state in Chronicler

GreatPerson promotions detect exceptional agents and lift them into the named character layer. Emergence.py handles black swan events. Neither system produces individuals whose *decision model* is deliberately warped. A promoted general behaves like any high-stat general — their utility weights follow the same formula. There's no mechanism for a general who suddenly pursues culture, or a priest who leads a military campaign.

### Proposed amendment to M48 + M52

**M48 addition — Mule flag on GreatPerson promotion:**

When `_process_promotions` creates a new GreatPerson, roll a low-probability check (5-10%, `[CALIBRATE]`). On success, the GreatPerson receives a `mule` flag. The Mule's utility weights receive a large perturbation derived from their dominant memory at promotion time:

- Extract the agent's strongest memory (highest absolute intensity) from the M48 ring buffer
- The memory's event type determines which utility weights get boosted and which get suppressed
- A general whose dominant memory is a famine → DEVELOP and TRADE utility boosted, WAR utility suppressed
- A merchant whose dominant memory is persecution → FUND_INSTABILITY utility boosted, TRADE utility suppressed
- A priest whose dominant memory is a conquest → WAR utility boosted, INVEST_CULTURE utility suppressed

The perturbation is a one-time write to the GreatPerson's utility modifier table (new field on GreatPerson: `utility_overrides: dict[ActionType, float]`). The override persists for the character's lifetime. This means the Mule's behavior is deterministic given the seed — their "unpredictability" comes from the unusual combination of memory and role, not from extra randomness.

**M52 addition — Mule artifact creation trigger:**

When a Mule-flagged GreatPerson's overridden utility drives an action that succeeds (the action engine resolves in their civ's favor), create an artifact tied to that action:

- General who develops agriculture → "The Treatise of [Name]" (artwork type, prestige bonus)
- Merchant who funds instability → "The Manifesto of [Name]" (relic type, faction influence)
- Priest who leads conquest → "The Banner of [Name]" (relic type, conversion bonus in conquered region)

This gives the Mule a lasting narrative anchor — the artifact persists after the character dies, carrying their legacy into future generations.

**Narration exposure:**

Mule characters are high-priority targets for the curator pipeline. Their actions represent the kind of history-bending moments that make chronicles feel organic. The narrator context should include the memory that warped them: "General Ashani, who never forgot the great famine of her youth, turned the army's swords into plowshares and authored the agricultural reforms that fed the empire for a generation."

### Implementation estimate

+1 day on M48 (Mule flag check during promotion, utility override table, memory-to-override mapping). +0.5 day on M52 (artifact creation trigger for Mule actions). Total: +1.5 days.

### New constants

| Constant | Role | Calibrate in |
|----------|------|-------------|
| `MULE_PROMOTION_PROBABILITY` | Chance of Mule flag on GreatPerson promotion | M53 |
| `MULE_UTILITY_PERTURBATION_SCALE` | Magnitude of utility weight override | M53 |

### Risks

- Too many Mules destabilize the simulation. Mitigation: 5-10% of GreatPerson promotions, and GreatPerson promotions are themselves rare. At 50K agents, expect ~5-15 GreatPersons per 100 turns, of which 0-1 are Mules. One Mule per 100 turns is the right frequency for a history-bending individual.
- Mule utility overrides conflict with the combined weight multiplier cap (2.5x). Mitigation: Mule overrides are additive to the base utility, then the cap applies. The Mule's behavior is unusual but not unbounded.
- Memory-to-override mapping requires an explicit event_type → ActionType table. Mitigation: keep the table small (~8 entries). Not every event type produces a Mule variant — only the emotionally intense ones (famine, battle, persecution, conquest, migration).

---

## Thread 3: Space-Filling Curves and NUMA-Aware Iteration

### What the inspiration document says

BioDynaMo's HPC research (cited: arXiv 2301.06984) demonstrates two techniques for cache-efficient agent-based simulation at scale:

1. **Space-filling curves:** Sorting agents along a Morton or Hilbert curve before tick processing ensures that spatially proximate agents are also proximate in memory. This reduces L1/L2 cache misses when phases access neighbors (social influence, disease, trade).

2. **NUMA-aware iteration:** On multi-CCD CPUs, partitioning the agent pool so each CCD processes agents in its local memory bank reduces cross-CCD latency.

### Current state in Chronicler

The Rust `AgentPool` uses a free-list arena. Agent order in memory is determined by allocation/deallocation patterns, which have no relationship to spatial position. At current scale (10-50K agents), this doesn't matter — the entire pool fits in L2 cache. At 500K-1M (Phase 7 target), the pool exceeds L2 and cache behavior becomes performance-critical.

The 9950X is a 2-CCD chip with two NUMA domains. rayon's work-stealing scheduler distributes work across cores but doesn't account for memory locality across CCDs.

### Proposed amendment to M54

Add a performance requirement to M54's scope:

**Post-migration optimization: spatial sort.** After M55 lands spatial coordinates, implement a per-tick (or per-N-ticks) sort of the agent pool along a Morton Z-curve derived from agent positions. The sort key is the Morton code of `(region_index, x, y)` — region index as the high bits ensures agents in the same region are contiguous, and the Morton interleaving of (x,y) within each region preserves 2D locality.

The sort doesn't need to be exact — an approximate sort (e.g., radix sort on the top 16 bits of the Morton code) is sufficient for cache benefit and much cheaper than a full comparison sort on 1M elements.

**NUMA partitioning (experimental).** Flag as a performance experiment in M54, not a hard requirement. The approach: partition the region list into two halves (roughly equal agent count), pin each half to a CCD via thread affinity, and run rayon within each partition. Cross-partition interactions (trade routes, migration between partitions) require a synchronization step.

Measure before committing to NUMA partitioning. Profile the agent tick at 500K agents with and without CCD affinity. If cross-CCD traffic is less than 10% of tick time, skip it — the engineering complexity isn't worth marginal gains.

### Proposed amendment to M55

Add a note to M55's spatial hash section:

**Morton sort prerequisite.** The spatial hash grid (M55) and the Morton sort (M54 post-migration) are complementary. The hash provides O(1) neighbor lookup for interaction queries. The sort ensures that sequential memory access during full-pool sweeps (satisfaction computation, demographics, wealth decay) benefits from cache locality. Both are needed at scale — the hash for random access, the sort for sequential access.

### Implementation estimate

+1 day on M54 (Morton sort implementation, radix sort on u32 keys, benchmark harness). NUMA experiment is +0.5 day if pursued. Total: +1-1.5 days.

### New M61 validation targets

- Tick time with Morton sort vs. arena order at 500K and 1M agents (expect 15-30% improvement on full-pool sweeps)
- Determinism: Morton sort must produce identical pool ordering given identical spatial state — verify with seed comparison test
- NUMA experiment results documented regardless of whether the optimization ships

### Risks

- Morton sort adds O(N log N) overhead per tick (or O(N) for radix sort). At 1M agents, radix sort on u32 keys takes ~4ms. If the tick is 200ms, that's 2% overhead for a potential 15-30% speedup on cache-sensitive phases. Favorable tradeoff.
- Sort frequency: every tick is safest for determinism. Every N ticks saves compute but allows cache degradation between sorts. Start with every tick, reduce frequency only if profiling shows the sort itself is a bottleneck.

---

## Thread 4: Bidirectional Feedback Formalization

### What the inspiration document says

Research on hybrid System Dynamics / Agent-Based Model interfaces (cited: ResearchGate publication 367128944) describes a bidirectional coupling where macro-level dynamics inform agent perception with a tunable temporal lag, and agent actions aggregate back to macro state with a different lag. The key insight is that the macro→micro and micro→macro channels should have independent coupling constants, not hardwired per-signal.

### Current state in Chronicler

The hybrid mode already implements bidirectional feedback: Python phases produce macro state, Rust agents react and produce micro state, agent aggregates overwrite civ stats. The one-turn lag on Gini (`AgentBridge._gini_by_civ`) is an informal instance of tunable coupling — Gini from turn N feeds turn N+1's satisfaction signals.

However, the coupling is signal-specific and ad hoc. Each FFI signal (farmer_income_modifier, food_sufficiency, merchant_margin, etc.) is wired individually with its own timing. There's no unified model of "how agents perceive macro state" vs. "how agent actions aggregate to macro state."

### Proposed amendment to M49 and M59

**M49 design note — perfect perception as Phase 7 starting point:**

M49 (Needs) assumes agents have immediate knowledge of their region's conditions: food sufficiency, temple presence, war status, etc. This is correct for the depth track (M48-M53) where the goal is to validate needs mechanics. Document explicitly that M49's perception model is "perfect regional knowledge" — agents know everything about their own region instantly, nothing about other regions.

**M59 scope clarification — information propagation as the perception lag layer:**

Reframe M59 from "rumors and warnings" to "the primary channel through which agents perceive conditions beyond their immediate region." The key design change:

Before M59, agents in region A know nothing about a famine in region B until they migrate there or the famine's effects propagate through the economy (food price spike). After M59, information about region B's famine travels through the social graph — a merchant with a trade partner in region B learns about the famine 1-2 turns after it starts, and may preemptively migrate or stockpile.

This means M59 is not just a flavor system (rumors are interesting). It's the formalization of the macro→micro perception channel with temporal lag. The lag is the graph distance between the agent and the information source, measured in hops per turn. Well-connected agents (high relationship count, merchant occupation) learn faster. Isolated agents (rural, few bonds) learn slower.

**No structural changes to the dependency graph.** M49 still depends only on M48. M59 still depends on M50 and M55. The depth track validates needs with perfect perception. The scale track adds realistic perception lag. This is the right sequencing — calibrate the response before adding the delay.

**Coupling constant formalization (M59 scope):**

Each information type in M59 should carry a `propagation_weight` that controls how quickly it spreads through the social graph. This is the tunable coupling constant the research describes:

- Trade opportunities: high propagation (merchants actively share price information)
- Threat warnings: high propagation (survival-critical, shared urgently)
- Religious events: medium propagation (spread through co-religionist bonds preferentially)
- Political rumors: low propagation (unreliable, spread slowly through weak ties)

These weights are `[CALIBRATE]` constants tuned in M61.

### Implementation estimate

+0 days (design notes only, no code changes). The reframing of M59's scope may add 0.5-1 day of implementation when M59 is built, but that's within the existing 4-6 day estimate.

---

## Impact on Phase 7 Draft

### Milestone table changes

No new rows. Updated estimates for affected milestones:

| Milestone | Original Est. | Amended Est. | Delta |
|-----------|--------------|-------------|-------|
| M48 | 5-7 days | 6-8 days | +1 (Mule promotions) |
| M52 | 3-4 days | 3.5-4.5 days | +0.5 (Mule artifact trigger) |
| M54 | 7-10 days | 8-11 days | +1 (Morton sort, NUMA experiment) |
| M55 | 5-7 days | 6-8 days | +1 (spatial asabiya) |
| M49 | 5-7 days | 5-7 days | +0 (design note only) |
| M59 | 4-6 days | 4-6 days | +0 (scope clarification only) |

**Revised total estimate:** 83.5-115 days (was 80-110).

### Memory budget changes

No change. Mule flag is 1 bit on GreatPerson (Python-side, negligible). Utility overrides are a small dict on GreatPerson (Python-side, negligible). Morton sort keys are transient (computed, sorted, discarded). Spatial asabiya is per-region, not per-agent.

### New constants summary

| Constant | Thread | Calibrate in |
|----------|--------|-------------|
| `ASABIYA_FRONTIER_GROWTH_RATE` | Spatial asabiya | M61 |
| `ASABIYA_INTERIOR_DECAY_RATE` | Spatial asabiya | M61 |
| `ASABIYA_POWER_DROPOFF` | Spatial asabiya | M61 |
| `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD` | Spatial asabiya | M61 |
| `MULE_PROMOTION_PROBABILITY` | Mule promotions | M53 |
| `MULE_UTILITY_PERTURBATION_SCALE` | Mule promotions | M53 |

6 new constants. All deferred to existing tuning passes (M53 for depth, M61 for scale).

### Dependency graph changes

No new edges. All amendments attach to existing milestones with existing dependencies.

### Risk register additions

| Risk | Severity | Mitigation |
|------|----------|------------|
| Spatial asabiya creates expansion feedback loop | Medium | Logistic ceiling is self-limiting. Interior decay offsets frontier growth at scale. Validate in M61. |
| Mule frequency too high destabilizes simulation | Low | 5-10% of already-rare GreatPerson promotions. ~1 Mule per 100 turns at 50K agents. |
| Morton sort overhead exceeds cache benefit at low agent counts | Low | Only activate sort above agent count threshold (e.g., 100K). Below threshold, arena order is fine. |
| M59 perception lag makes needs system feel unresponsive | Medium | Agents always have perfect knowledge of own region (M49). M59 lag only affects cross-region information. Local conditions are immediate. |

---

## Recommendation

Incorporate all four threads. None requires structural changes to the Phase 7 draft — they're enrichments to existing milestones that increase emergent depth (spatial asabiya, Mule promotions) and performance headroom (Morton sort) at minimal additional cost. The M59 reframing as a perception lag layer is a design clarification that improves the conceptual coherence of the needs→information pipeline without changing the implementation plan.

The spatial asabiya thread has the highest payoff-to-cost ratio. It turns a civ-level scalar into a spatially-grounded system that produces imperial overextension, frontier vigor, and geographic collapse patterns — all from four lines of arithmetic per region per turn.
