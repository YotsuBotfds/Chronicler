# M59b Pre-Spec Handoff

> Date: 2026-03-30  
> Audience: spec-writing / question-gathering agent  
> Purpose: lock an implementation-ready spec for `M59b: Perception-Coupled Behavior`, using the now-merged `M59a` packet substrate on `main` as the live baseline.

## Status Snapshot

- `M59a` is now merged on `main` at `f4df802` (`fix(m59a): harden admission and diagnostics`).
- The live repo already has:
  - Rust-owned per-agent packet slots on `AgentPool`
  - packet decay, direct observation, propagation, and commit at tick phase `0.95`
  - additive `knowledge_stats` bundle metadata and extractors
  - deterministic test coverage for packet-state replay, slot-order independence, and producer-only behavior
- `M59b` is the next step in the roadmap:
  - merchants act on learned trade opportunities
  - migrants react to distant threats
  - agents may act on stale or partially wrong information
- The roadmap gate is behavioral, not substrate-only:
  - cross-region awareness must measurably change behavior
  - own-region perception must remain immediate
  - the sim must not become omniscient again through hidden fallbacks

## Canonical Requirement (Roadmap)

Source: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

- Goal: let agents actually act on propagated information, including stale or partially wrong information.
- Intended effects:
  - merchants react to learned trade opportunities
  - migrants and loyalists react to distant threats
  - stale packets can still drive decisions even after conditions change
- Scope meaning:
  - `M59a` was the information layer
  - `M59b` is where that layer becomes a decision-system modifier
- Gate: cross-region awareness changes behavior in measurable ways without making needs or loyalty feel instantly omniscient

## Current Code Reality (Live Baseline)

### The packet substrate is real and merged

- `chronicler-agents/src/knowledge.rs` now owns:
  - `InfoType::{ThreatWarning, TradeOpportunity, ReligiousSignal}`
  - 4 packet slots per agent
  - direct observation from region truth plus merchant arrival
  - buffered one-hop-per-turn propagation
  - per-turn `KnowledgeStats`
- `chronicler-agents/src/pool.rs` now stores:
  - `pkt_type_and_hops`
  - `pkt_source_region`
  - `pkt_source_turn`
  - `pkt_intensity`
  - `arrived_this_turn`
- `chronicler-agents/src/tick.rs` runs `knowledge_phase(...)` after merchant mobility and before satisfaction.
- `src/chronicler/agent_bridge.py`, `src/chronicler/main.py`, and `src/chronicler/analytics.py` now expose `knowledge_stats` as bundle metadata.

### Packet shape is intentionally minimal

- A packet stores only:
  - `info_type`
  - `source_region`
  - `source_turn`
  - `intensity`
  - `hop_count`
- There is no stored:
  - `source_civ`
  - `source_belief`
  - propagation channel
  - sender identity
- That minimal shape is a live constraint on `M59b`.
- If a proposed consumer truly needs `source_civ` or another extra field, the spec should treat that as a deliberate packet-layout expansion, not an accidental convenience.

### Merchant planning is still fully perfect-info

- `chronicler-agents/src/merchant.rs::evaluate_route(...)` still scans all reachable destinations using live `merchant_route_margin` from `RegionState`.
- The current route score is still:
  - local origin planning margin
  - plus destination planning margin
  - over the full reachable route graph
- `M59a` merchants are packet producers only.
- `M59b` is where this must change if the milestone is going to mean anything.

### Migration and loyalty still read live regional truth, not packets

- `chronicler-agents/src/behavior.rs` still computes migration opportunity from adjacent regions' live `RegionState` and region aggregates.
- Loyalty drift / flip logic still depends on current same-region civ satisfaction comparisons.
- Nothing in `behavior.rs` reads packet slots today.
- Own-region perception is still immediate, which is correct and should remain so.

### Legacy civ-level information systems still coexist unchanged

- `src/chronicler/simulation.py` still runs `tick_trade_knowledge_sharing(...)`.
- `src/chronicler/exploration.py` still owns `known_regions`.
- `src/chronicler/intelligence.py` and `chronicler-agents/src/politics.rs` still own the older civ-level perception layer from `M24`.
- `M59b` should not try to unify or replace those systems.

### Diagnostics already exist, but only for diffusion

- `knowledge_stats` currently tells us:
  - packet creation / refresh / transmit / expire / evict / drop counts
  - per-type created / transmitted counts
  - live count, agents-with-packets, mean/max age, mean/max hops
- There are no counters yet for:
  - merchant plans driven by packets
  - packet-aware migration avoidance
  - no-packet fallbacks
  - stale-packet decision overrides
- `M59b` should add consumer-facing observability, not just behavioral changes.

## Non-Negotiables To Preserve

- Own-region perception remains immediate.
  - packets are for cross-region awareness, not local-region fog
- `M59a` packet slots remain the single authoritative knowledge state unless the spec explicitly widens them
- `--agents=off` remains unchanged
- deterministic same-seed replay still applies
- no randomized container iteration or order-sensitive packet consumption
- no hidden return to global omniscience
  - if a fallback is kept for bootstrap, it should be explicit, narrow, and counted
- no new Python->Rust transient signals unless the spec can show packet-derived behavior truly cannot be expressed from existing Rust-local state
- legacy `known_regions` / `M24` civ-level perception remains parallel unless the user explicitly asks to collapse systems

## Critical Live Constraint: Merchant Bootstrap

This is the biggest architectural issue the `M59b` spec needs to solve cleanly.

- Current `M59a` trade packets are produced on merchant arrival.
- Current merchant routing needs destination knowledge to create trips.
- If `M59b` simply says "merchants may only plan from held trade packets" with no bootstrap rule, trade can deadlock:
  - no trip
  - no arrival
  - no new trade packets
  - no learned destinations

The spec must explicitly choose one of these strategies:

1. Broaden trade direct observation in `M59b`
   - merchants refresh a local `trade_opportunity` packet from their current region, not only on arrival
2. Keep a narrow oracle bootstrap fallback
   - if a merchant has no usable external trade packet, use the current perfect-info route planner
3. Hybrid
   - local merchant observation seeds the network
   - explicit counted fallback prevents total trade collapse when packet coverage is empty

Recommended default: use the hybrid.

- Let merchants refresh a local trade packet from their current region using Rust-local truth.
- When a merchant has at least one usable nonlocal trade packet, route planning should be packet-driven.
- When a merchant has none, keep a counted bootstrap fallback to the old oracle planner rather than risking a dead economy on turn 1.

That keeps `M59b` behaviorally meaningful without making the first cut brittle.

## Recommended Architecture Lean

### 1. Keep behavior coupling Rust-local

- `M59b` should consume packet slots directly inside Rust decision code.
- The natural modules are:
  - `chronicler-agents/src/merchant.rs`
  - `chronicler-agents/src/behavior.rs`
  - `chronicler-agents/src/knowledge.rs` for packet query helpers
- Python should stay at the metadata / analytics boundary unless the spec chooses to add new aggregate diagnostics.

### 2. Merchants should be the first-class consumer

- The merchant seam is already crisp and high-value.
- Recommended planning contract:
  - route topology remains perfect-known through the route graph
  - economic attractiveness becomes packet-coupled
  - destination candidates come from held `trade_opportunity` packets, not a global scan of every reachable region
- Suggested score shape:
  - current-region live origin margin
  - plus stale destination attractiveness derived from packet `intensity`
  - minus confidence loss from packet age / hops
  - plus existing deterministic tie-breaks

This gives `M59b` a strong behavioral identity without rewriting route topology or shadow-ledger logic.

### 3. Threat coupling should be conservative and localizable

- `threat_warning` is the clearest non-merchant consumer, but it should not become a generic panic multiplier.
- Recommended first-cut use:
  - threat packets reduce attractiveness of threatened adjacent migration targets if the agent heard about them before moving
  - optionally, fresh threat packets can raise migration urgency modestly when the threatened source region is immediately relevant to the agent's reachable neighborhood
- Avoid any design that makes agents react equally to every threat packet everywhere on the map.

### 4. Loyalty coupling should only ship if it fits the existing packet shape

- The current packet shape does not store `source_civ`.
- That makes "react to threats against my civ" harder to define cleanly than merchant routing or destination avoidance.
- Recommended default:
  - do **not** widen the packet layout in `M59b`
  - if a clean loyalty contract cannot be defined from `(info_type, source_region, source_turn, intensity, hop_count)` plus current region truth, defer loyalty coupling to a later milestone

This is the main place where deferral may be wiser than forcing semantics.

### 5. Religious packets do not need a consumer yet

- `religious_signal` now proves the substrate can handle selective propagation.
- It does not need to drive behavior in `M59b` unless a very clear, bounded consumer emerges.
- Recommended default: keep `religious_signal` producer-only in `M59b`.

### 6. Diagnostics should show consumer behavior explicitly

- Add counters that tell us whether packet-driven behavior is actually happening.
- Recommended minimum diagnostics:
  - merchant route plans using packet-known destinations
  - merchant oracle bootstrap fallbacks
  - merchants idle due to no usable packet knowledge
  - migration targets rejected because of threat packets
  - if loyalty coupling ships, loyalty drifts / flips influenced by packets

Recommended surface: extend the existing `knowledge_stats` metadata history rather than adding a brand-new metadata family unless the user explicitly wants a separate behavior-facing series.

## Scope Recommendation

In scope for `M59b`:

- merchant route planning consuming `trade_opportunity` packets
- explicit bootstrap policy for merchant packet consumption
- conservative threat-aware migration targeting or migration urgency
- additive consumer diagnostics
- determinism and compatibility coverage for the new behavior path

Recommended out of scope for `M59b`:

- widening the packet slot layout unless absolutely necessary
- `political_rumor`
- replacing `known_regions` or the older `M24` civ-perception layer
- viewer overlays / Bundle v2 knowledge visualization
- campaign logistics / battle awareness
- rich religious migration, pilgrimage routing, or diplomacy-as-information-economy features

Conditional / user-call scope:

- loyalty coupling
  - include only if the spec can define it cleanly without packet-layout churn

## Likely File Touch Map

Rust:

- `chronicler-agents/src/knowledge.rs`
  - packet query helpers for consumer code
  - possibly extra diagnostics fields
- `chronicler-agents/src/merchant.rs`
  - replace destination oracle scan with packet-aware candidate selection
  - bootstrap fallback policy if retained
- `chronicler-agents/src/behavior.rs`
  - threat-aware migration or loyalty modifiers
- `chronicler-agents/src/ffi.rs`
  - only if new aggregate diagnostics cross the bridge
- `chronicler-agents/tests/test_knowledge.rs`
  - consumer-facing packet determinism and bootstrap tests
- `chronicler-agents/tests/test_merchant.rs`
  - route-planning regressions

Python:

- `src/chronicler/agent_bridge.py`
  - diagnostics normalization if `knowledge_stats` grows
- `src/chronicler/main.py`
  - metadata inclusion if shape changes
- `src/chronicler/analytics.py`
  - extractor updates if new fields are added
- `tests/test_m59a_knowledge.py`
  - likely renamed or extended for M59b behavior assertions
- `tests/test_merchant_mobility.py`
  - packet-aware merchant behavior integration
- `tests/test_agent_bridge.py`
  - reset/metadata coverage if diagnostics grow

## Design Decisions Agent Should Lock In The Spec

1. Scope of first consumer set:
   - merchants only
   - merchants + migration
   - merchants + migration + loyalty
2. Merchant bootstrap strategy:
   - strict packet-only
   - explicit fallback
   - hybrid
3. Merchant candidate set semantics:
   - packet-gated destinations
   - packet-weighted bias over full oracle scan
4. Mapping from packet state to merchant planning score:
   - how intensity, age, and hop count degrade destination attractiveness
5. Threat coupling contract:
   - destination avoidance only
   - migration urgency boost
   - both
6. Loyalty coupling:
   - ship now from existing packet shape
   - or defer rather than widening packet storage
7. Whether `religious_signal` gets a consumer in `M59b`
8. Diagnostics contract for packet consumption and bootstrap fallbacks

## High-Value Questions To Bring Back

Recommended defaults are included so the spec can keep moving if answers are sparse.

1. Should `M59b` scope to merchants only, or also include migration / loyalty coupling?
   Recommended: merchants plus threat-aware migration; defer loyalty unless a clean contract emerges without widening packet layout.

2. How should merchant bootstrap work so packet-aware planning does not deadlock trade?
   Recommended: hybrid. Add local merchant trade observation plus an explicit counted oracle fallback when no usable external packet exists.

3. When a merchant has usable `trade_opportunity` packets, should those packets gate destination candidates, or merely bias a full perfect-info scan?
   Recommended: gate cross-region destination candidates. Otherwise behavior is still effectively omniscient.

4. How should trade packet staleness affect route scoring?
   Recommended: derive destination attractiveness from packet intensity, then discount by age and hop count. Keep current-region origin truth immediate.

5. How should `threat_warning` affect migration?
   Recommended: use it conservatively to reduce attractiveness of threatened adjacent destinations, with only a modest urgency boost if a fresh threat is directly relevant.

6. Should `M59b` force a loyalty consumer even though packets do not store `source_civ`?
   Recommended: no. If loyalty semantics are not clean from the current packet shape, defer rather than expanding storage casually.

7. Should `religious_signal` drive any behavior in `M59b`?
   Recommended: no. Keep it as a live propagated packet type with no consumer yet.

8. Where should packet-consumption diagnostics live?
   Recommended: extend `knowledge_stats` with consumer counters and bootstrap/fallback counters before inventing a second metadata family.

## Validation Expectations

- Rust unit tests:
  - merchants with usable trade packets choose packet-known destinations deterministically
  - merchants with no usable packet knowledge hit the chosen bootstrap path deterministically
  - threat-aware migration destination filtering is deterministic and slot-order independent
- Rust integration tests:
  - no merchant deadlock on a multi-turn smoke scenario
  - packet-aware merchants measurably diverge from the old oracle route choices when packets exist
  - if loyalty coupling ships, packet-influenced drift / flip behavior is stable and explainable
- Python integration tests:
  - bundle metadata still includes stable `knowledge_stats`
  - any new consumer counters are present and type-stable
  - `--agents=off` still emits no knowledge metadata
- Compatibility tests:
  - own-region perception remains immediate
  - no change to legacy `known_regions` / `M24` surfaces
  - merchant mobility / delivery accounting still conserves correctly
- Determinism tests:
  - same-seed same-process replay
  - same-seed cross-process replay where practical
  - no order sensitivity from packet-candidate iteration

## Expected Output From The Next Agent

- A single `M59b` implementation spec that:
  - uses the merged `M59a` packet substrate as the baseline
  - defines the merchant bootstrap contract explicitly
  - draws a crisp line between packet-gated behavior and retained local immediate truth
  - states whether loyalty coupling ships now or is deferred
  - preserves determinism, compatibility, and memory-budget discipline
- A short user-facing question set based on the 8 questions above, with recommended defaults and rationale.
