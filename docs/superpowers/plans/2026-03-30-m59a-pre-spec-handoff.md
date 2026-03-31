# M59a Pre-Spec Handoff

> Date: 2026-03-30  
> Audience: spec-writing / question-gathering agent  
> Purpose: lock an implementation-ready spec for `M59a: Information Packets & Diffusion`, and surface the small set of user decisions that materially affect architecture before spec freeze.

## Status Snapshot

- There is no dedicated `M59a` spec or implementation plan in the repo yet.
- Canonical roadmap: `M59a` is a Phase 7 scale-track milestone, estimate `2-3` days, depending on `M50` and `M55a`.
- The live baseline is already well past the older draft assumptions:
  - `M50a`, `M50b`
  - `M54a`, `M54b`, `M54c`
  - `M55a`, `M55b`
  - `M56a`, `M56b`
  - `M57a`, `M57b`
  - `M58a`, `M58b`
- `M59a` is explicitly the substrate half only:
  - packet data model
  - direct observation plus social propagation
  - lag / decay / staleness accounting
  - inspectable diagnostics for later consumers
- `M59b` still owns:
  - behavior coupling for merchants / migrants / loyalists
  - acting on stale or partially wrong information
  - replacing current perfect-info decision inputs where appropriate
- `M60a` is an important downstream consumer, but campaign awareness / logistics is not part of `M59a`.

## Canonical Requirements (Roadmap)

Source: `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

- Goal: build the packet substrate that lets agents carry cross-region knowledge through the social graph with lag and decay.
- Mechanism:
  - information packets of the form `(info_type, source_region, turn, intensity)`
  - `2-4` active packets per agent
  - propagation probability weighted by relationship sentiment and channel type
  - decay and staleness on each hop
  - diagnostics for source channel, freshness, and lag
- Propagation priorities:
  - trade opportunity and threat warning should spread fastest
  - religious and political signals can move more slowly or along more selective bond types
- Gate: diffusion is deterministic, inspectable, and already emitting the lag / staleness statistics that `M59b` and `M61b` will need.

Additional roadmap context that matters:

- `M49` deliberately assumes perfect knowledge of the agent's own region. `M59` adds lag only for cross-region perception.
- `M58b` explicitly kept merchant planning on current-turn perfect-info signals. `M59` is the intended home for stale trade information, not `M58`.
- The roadmap reserves RNG stream offset `1800` for information propagation noise.
- The Phase 7 memory budget assumes `M59a` fits in roughly `24 bytes/agent` for `4` packet slots.

## Current Code Reality (Live Baseline)

### Relationship substrate is already Rust-owned and packet-ready

- Live agent-backed runs already treat Rust as the authoritative relationship layer:
  - `src/chronicler/agent_bridge.py`: `rust_owns_formation = True`
  - Python-side M40 formation is gated off in hybrid mode
- `chronicler-agents/src/relationships.rs` already gives `M59a` the core social graph substrate:
  - fixed `REL_SLOTS = 8`
  - per-bond `sentiment: i8`
  - stable bond ordinals:
    - `Mentor = 0`
    - `Rival = 1`
    - `Marriage = 2`
    - `ExileBond = 3`
    - `CoReligionist = 4`
    - `Kin = 5`
    - `Friend = 6`
    - `Grudge = 7`
- Bridge / FFI seams already exist for reading and mutating this graph:
  - `apply_relationship_ops`
  - `get_agent_relationships`
  - `get_social_edges`
  - relationship diagnostics metadata

### Spatial and travel seams already exist

- `M55a` landed per-agent `region`, `x`, `y`, and region-local spatial infrastructure.
- `M56a` / `M56b` added `settlement_id` and urban classification infrastructure.
- `M58a` / `M58b` added merchant trip state and multi-turn movement:
  - `trip_phase`
  - `trip_origin_region`
  - `trip_dest_region`
  - path / cargo / elapsed-turn tracking
- This means `M59a` already has natural direct-observation sources from:
  - where an agent currently is
  - where a merchant has just traveled
  - who the agent is socially connected to

### Region-local truth already exists in Rust for direct observation

- `chronicler-agents/src/region.rs::RegionState` already exposes many signals that can seed packets without inventing new Python-side plumbing:
  - `food_sufficiency`
  - `merchant_margin`
  - `merchant_route_margin`
  - `trade_route_count`
  - `controller_changed_this_turn`
  - `war_won_this_turn`
  - `seceded_this_turn`
  - `conversion_rate`
  - `persecution_intensity`
  - `majority_belief`
  - `schism_convert_from` / `schism_convert_to`
  - `has_temple`
- Strong implication: the first cut of `M59a` can stay mostly Rust-local if direct observation is based on current region truth plus travel / relationship state.

### There is no packet store or knowledge cache in the live agent model yet

- `chronicler-agents/src/pool.rs` has no packet / knowledge-slot fields.
- `chronicler-agents/src/ffi.rs` exports no packet or knowledge columns.
- `src/chronicler/models.py` / `GreatPerson` have memories, needs, and bonds, but no packet summary surface.
- There is no `knowledge_stats` metadata family yet.

### Legacy knowledge / perception systems exist, but they are not the M59a substrate

- `src/chronicler/exploration.py` still owns civ-level fog / `known_regions` and a legacy `tick_trade_knowledge_sharing()` routine that shares discovered regions across trade contact.
- `src/chronicler/intelligence.py` plus the Rust politics mirror in `chronicler-agents/src/politics.rs` implement the older `M24` civ-vs-civ perception layer for:
  - WAR target evaluation
  - trade gain estimation
  - tribute / rebellion checks
  - congress ranking
- These are real live systems and cannot be ignored for compatibility, but they should not dictate the architecture of `M59a`, which is the Phase 7 agent-scale perception-lag layer.

### Observability pattern already exists and is the easiest M59a diagnostics seam

- Recent scale milestones already push per-turn subsystem stats into bundle metadata:
  - `relationship_stats`
  - `household_stats`
  - `merchant_trip_stats`
- `src/chronicler/main.py` appends these histories into bundle metadata.
- `src/chronicler/analytics.py` already has extractor patterns for these metadata families.
- `M59a` should strongly prefer the same first surface unless replay/debug needs justify heavier schema work.

## Non-Negotiables To Preserve

- Own-region perception remains immediate.
  - `M59` is the lag layer for cross-region knowledge, not a rewrite of local-region awareness.
- Determinism rules still apply:
  - no randomized container iteration
  - explicit tie-breaks
  - canonical ordering before propagation, FFI, or serialization
  - identical results across thread counts if propagation is parallelized
- RNG stream discipline:
  - roadmap reserves `1800` for information propagation noise
  - `agent.rs` does not yet register an `M59a` offset, so the spec should lock this explicitly
- Memory budget discipline:
  - roadmap budget assumes `4` packet slots and about `24 bytes/agent`
  - exceeding that should require explicit justification
- `--agents=off` must remain behaviorally stable.
  - Recommended `M59a` behavior in off mode: no packet state, no packet metadata.
- Any new transient Python->Rust signal must:
  - clear before return in the emitting builder
  - include a multi-turn reset integration test
- Scope guard:
  - `M59a` should not absorb `M59b` behavior coupling
  - `M59a` should not require rewriting fog-of-war or the older `M24` civ-level perception system
  - `M59a` should not drag viewer / Bundle v2 knowledge overlays into required scope
- Merchant planning should remain perfect-info during `M59a` unless the user explicitly wants to collapse the `M59a` / `M59b` boundary.

## Recommended Architecture Lean

### 1. Rust-owned fixed-width packet slots on `AgentPool`

- Keep packet state near the existing agent tick, relationship store, and merchant travel state.
- Prefer a fixed-width per-agent slot design over dynamic vectors or Python-owned packet state.
- Keep the packet core close to roadmap intent:
  - `info_type`
  - `source_region`
  - `source_turn` or equivalent age basis
  - `intensity`
- Only widen the packet shape beyond that if a downstream milestone clearly needs it.

### 2. Separate direct observation from social propagation

- Direct observation should come from what an agent actually sees:
  - current region state
  - merchant arrival / travel context
  - local shocks or transitions
- Social propagation should then move packets over the existing relationship graph.
- Use staged writes or double-buffer semantics so a packet moves at most one hop per turn.
  - This matches the roadmap framing of graph distance as temporal lag.

### 3. Keep `M59a` as the perception substrate, not a decision rewrite

- `M59a` should produce inspectable packet state and lag/staleness metrics.
- `M59b` should decide how merchants, migrants, loyalists, and others actually consume that information.
- The clean seam for merchants is:
  - `M58a` / `M58b`: route planner reads current-turn regional truth
  - `M59a`: build packet substrate and direct-observation model
  - `M59b`: switch merchant planning from perfect-info to packet-derived knowledge where desired

### 4. Diagnostics should ship in the same milestone

- Emit per-turn packet metrics in `M59a`, not later:
  - packets created
  - packets transmitted
  - packets expired / evicted
  - per-type counts
  - per-channel counts
  - age / lag / hop summaries
- Bundle metadata is the easiest first surface.
- Add snapshot or FFI packet surfaces only if replay/debug needs truly require them.

### 5. Any derived cache should stay secondary to packet truth

- If the spec wants a civ-region knowledge summary for analytics or later viewer overlays, derive it from packet state.
- Do not make a second authoritative knowledge model in the first cut unless the user explicitly asks for that larger semantic move.

## Scope Recommendation

In-scope for `M59a`:

- Packet slot data model and lifecycle.
- Minimum viable direct-observation sources for a first launch packet set.
- Relationship-driven propagation with sentiment / channel weighting.
- Lag, decay, staleness, refresh, and eviction semantics.
- Deterministic diagnostics surfaces for packet freshness and spread.
- Any minimum bridge / metadata hooks needed to validate the subsystem.

Out-of-scope for `M59a`:

- Merchants actually acting on stale trade packets.
- Migration / loyalty behavior changing because of packets.
- Campaign awareness / battle intelligence semantics.
- Replacing or unifying civ-level fog-of-war and the older `M24` perception code.
- Bundle v2 knowledge overlays / viewer activation.
- Full per-civ knowledge economy, map trading, or diplomacy-as-information-currency features.

## Likely File Touch Map

Python:

- `src/chronicler/agent_bridge.py`
- `src/chronicler/main.py`
- `src/chronicler/analytics.py`
- `src/chronicler/models.py` if packet summaries or metadata types need a Python surface
- `src/chronicler/simulation.py` and `src/chronicler/exploration.py` only if the legacy trade-knowledge path needs gating or explicit coexistence rules

Rust:

- `chronicler-agents/src/agent.rs`
- `chronicler-agents/src/pool.rs`
- `chronicler-agents/src/tick.rs`
- `chronicler-agents/src/relationships.rs`
- `chronicler-agents/src/ffi.rs`
- likely a new module such as `chronicler-agents/src/knowledge.rs` or `packets.rs`
- `chronicler-agents/src/merchant.rs` if merchant arrival / travel emits direct-observation packets
- `chronicler-agents/src/region.rs` only if the direct-observation contract truly needs more local truth fields

Tests:

- `tests/test_agent_bridge.py`
- a new focused Python `M59` integration test file
- Rust unit / integration tests for packet lifecycle and propagation
- determinism replay coverage if propagation uses parallel scans
- explicit transient reset tests for any new Python->Rust packet-source signals

## Design Decisions Agent Should Lock In The Spec

1. Tick placement and staging:
   - when decay runs
   - when direct observation runs
   - when propagation runs
   - when expiry / eviction / diagnostics run
2. Packet slot count and replacement policy:
   - `2`, `4`, or configurable
   - refresh in place vs overwrite vs evict weakest / stalest
3. Minimum packet schema:
   - whether roadmap tuple is enough
   - whether `source_civ`, channel, or hop count need to be stored explicitly
4. Minimum launch packet types.
5. Direct observation sources for each packet type.
6. Propagation rule form:
   - probabilistic keyed roll
   - deterministic threshold
   - hybrid
7. Bond-type channel filters and weighting:
   - which bonds carry which information types
   - how sentiment changes propagation probability or intensity
8. One-hop-per-turn enforcement model.
9. Whether `M59a` introduces any derived civ-region knowledge cache now or remains packet-only.
10. Exact `M59a` / `M59b` seam for merchant planning and stale trade knowledge.
11. Diagnostics contract shape:
   - metadata only
   - metadata plus FFI getter
   - metadata plus snapshot fields
12. Coexistence policy with legacy systems:
   - leave `known_regions` / `tick_trade_knowledge_sharing()` untouched
   - gate them
   - or bridge them explicitly

## High-Value Questions To Bring Back

These are the user decisions most worth asking explicitly. Recommended defaults are included so the spec can keep moving if answers are sparse.

1. Should `M59a` stay packet-only, or should it also introduce a derived civ-region knowledge cache right away?
   Recommended: packet-only authoritative state in `M59a`; derive summaries later if needed.

2. Should merchants keep using perfect-info route signals in `M59a`, with stale trade knowledge deferred to `M59b`?
   Recommended: yes. Preserve the `M59a` / `M59b` boundary.

3. Which packet types should the first cut include?
   Recommended: `trade_opportunity`, `threat_warning`, `religious_signal`, and `political_rumor`.

4. Should direct observation stay mostly Rust-local from region truth plus travel state, or should `M59a` already introduce new Python->Rust packet-source signals?
   Recommended: stay Rust-local where possible; only add Python signals for sources that existing `RegionState` cannot express cleanly.

5. Should propagation be probabilistic with deterministic keyed rolls on stream `1800`, or fully deterministic thresholding with no randomness?
   Recommended: probabilistic-but-deterministic keyed rolls on stream `1800`, since the roadmap already frames propagation in probability terms.

6. Should `M59a` touch the legacy fog-of-war / `known_regions` / `M24` civ-level perception systems now?
   Recommended: no. Keep them compatible but separate in `M59a`.

7. Where should packet diagnostics live first?
   Recommended: bundle metadata time series first, plus an optional focused Rust getter if debugging needs it.

8. When a fresh packet of the same type and source arrives, should it occupy a new slot or refresh the existing slot?
   Recommended: refresh / merge in place to preserve the fixed-slot budget.

## Validation Expectations

- Unit tests:
  - packet refresh / merge / eviction semantics
  - age and staleness decay
  - channel filtering by bond type
  - deterministic propagation rolls / tie-breaks
- Integration tests:
  - multi-turn chain diffusion across several bonded agents
  - direct observation from travel or regional shock source
  - one-hop-per-turn enforcement
  - diagnostics counters emitted and stable
- Determinism tests:
  - cross-process same-seed replay
  - cross-thread replay if propagation is parallelized
- Compatibility tests:
  - `--agents=off` unchanged
  - merchant planning remains unchanged in `M59a` if behavior coupling stays deferred
  - no unwanted leakage into bundle metadata outside agent-backed runs
- Transient tests:
  - any new Python->Rust packet-source signal must prove reset on subsequent turns

## Expected Output From The Next Agent

- A single `M59a` implementation spec that:
  - uses the live Rust-owned relationship / spatial / merchant seams
  - defines packet storage, propagation, and lag semantics cleanly
  - codifies determinism, RNG, memory-budget, and test requirements
  - draws a crisp line between `M59a`, `M59b`, and the legacy fog / `M24` perception surfaces
- A short user-facing question set based on the 8 questions above, with recommended defaults and rationale.
