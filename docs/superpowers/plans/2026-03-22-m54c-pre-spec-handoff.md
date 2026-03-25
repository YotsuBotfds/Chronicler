# M54c Pre-Spec Handoff

> Date: 2026-03-22
> Purpose: fast context pack for brainstorming/spec-ahead work on `M54c` while `M54a` establishes the Rust phase-migration pattern and `M54b` settles the shared conventions.

## Status Snapshot

- There is no dedicated `M54c` spec or implementation plan in the repo yet.
- The canonical roadmap currently defines `M54c` as **Rust Politics Migration + Spatial Sort** with a 7-11 day estimate.
- The roadmap says `M54c` depends on `M54a`, not on `M54b`, and can partially overlap with `M54b` after `M54a` lands.
- `M54a` is now unblocked from the passing M53 baseline.
- The main docs tension is unresolved: the roadmap bundles spatial sort into `M54c`, while the viability-adjustments memo moves shared sort infrastructure into `M54a` and leaves `M54c` as politics-only.

## Recommendation Context

My recommendation is:
- do a **politics-focused pre-spec now**
- wait to do the **full implementation spec** until `M54a` lands
- do **not** let the unresolved spatial-sort placement block the politics pre-spec

Reason:
- `M54a` is supposed to establish the Arrow-batch-in / Arrow-batch-out pattern, helper layout, write-back conventions, and determinism harness shape
- `M54c` mutates object-rich Python topology state more heavily than `M54a` or `M54b`
- part of the milestone may still move if the roadmap adopts the viability memo's dependency rewrite

What is stable enough to lock now:
- likely scope boundary
- likely hot-path subphase
- current ownership seams
- phase-ordering invariants
- off-mode risk points
- the real open design questions

What should wait for `M54a`:
- exact Arrow schemas
- exact PyO3 method signatures
- whether topology changes come back as op batches, write-back batches, or a mixed patch/result contract
- shared helper structure in `ffi.rs` and `agent_bridge.py`
- whether spatial sort stays inside `M54c`

## What The Docs Currently Say

### Canonical roadmap meaning

Primary reference:
- `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`

Current roadmap wording:
- `M54c` = politics migration plus spatial sort
- secession and federation checks are the highlighted core
- the roadmap motivation is that Rust can read agent distributions directly from the pool instead of round-tripping through Python snapshots
- the milestone gate is **determinism + bit-identical `--agents=off` output**
- `M54b` and `M54c` can overlap after `M54a` establishes the migration pattern

### Dependency-shape tension

Reference:
- `docs/superpowers/plans/2026-03-20-phase7-viability-adjustments.md`

Important point:
- the memo explicitly argues that spatial infrastructure should stop blocking the spatial branch
- its proposed split is:
  - `M54a` = ecology migration + shared sort infrastructure
  - `M54b` = economy migration
  - `M54c` = politics migration
- this is not yet reconciled with the canonical roadmap

Inference:
- any full `M54c` spec should call out which dependency graph it is following
- a politics pre-spec can still proceed now, because the politics core is meaningful either way

### Existing M54 docs to spec against

Useful references already in the repo:
- `docs/superpowers/specs/2026-03-21-m54a-rust-ecology-migration-design.md`
- `docs/superpowers/specs/2026-03-21-m54b-rust-economy-migration-design.md`
- `docs/superpowers/plans/2026-03-21-m54a-brainstorm-handoff.md`
- `docs/superpowers/plans/2026-03-21-m54b-pre-spec-handoff.md`

Why these matter:
- `M54a` already locks a good structure for **what stays in Python**, **state ownership**, **call sequence**, and **`--agents=off` handling**
- `M54b` already demonstrates a good **"lock now vs wait for M54a"** pre-spec structure

## Current Code Reality

### "Politics" is split across multiple turn sites

Primary files:
- `src/chronicler/politics.py`
- `src/chronicler/simulation.py`
- `src/chronicler/action_engine.py`
- `src/chronicler/agent_bridge.py`

In `simulation.py`, politics-related logic currently spans:

**Phase 2 automatic effects**
- `apply_governing_costs()`
- `collect_tribute()`
- `apply_proxy_wars()`
- `apply_exile_effects()`
- `apply_balance_of_power()`
- `apply_fallen_empire()`
- `apply_twilight()`
- `apply_long_peace()`
- `update_peak_regions()`

**Action / war-resolution hooks**
- `resolve_move_capital()` via `action_engine.py`
- `resolve_fund_instability()` via `action_engine.py`
- `trigger_federation_defense()` during war resolution

**Phase 10 consequence chain**
- `check_capital_loss()`
- `check_secession()`
- `update_allied_turns()`
- `check_vassal_rebellion()`
- `check_federation_formation()`
- `check_federation_dissolution()`
- `check_proxy_detection()`
- `check_restoration()`
- `check_twilight_absorption()`

Important consequence:
- `M54c` probably should not be read as "port all 1326 lines of `politics.py` in one cut"

### The likely hot migration target is the Phase 10 consequence chain

That chain is the most natural first migration boundary because:
- it is the most stateful political logic
- it creates, splits, restores, and absorbs polities
- it contains the roadmap-highlighted secession/federation work
- it already has hybrid-vs-aggregate/off branching that a Rust migration would need to preserve

By contrast, the Phase 2 helpers are mostly smaller scalar loops and bookkeeping rules. They may still belong in a later politics migration, but they do not look like the best first spec target unless profiling says otherwise.

### Current topology state is still Python-owned

Current Python-owned political world state includes:
- `civ.regions`, `civ.capital_region`, `civ.founded_turn`, `civ.decline_turns`
- `region.controller`
- `world.relationships`
- `world.vassal_relations`
- `world.federations`
- `world.proxy_wars`
- `world.exile_modifiers`
- `world.active_wars`
- `world.war_start_turns`
- `world.pending_shocks`
- GreatPerson ownership lists and related named-character metadata

There is no dedicated Rust politics entry point in `chronicler-agents/src/ffi.rs` today. The exposed surface is still the generic agent simulation interface: `set_region_state()`, `tick()`, `get_snapshot()`, `get_aggregates()`, `set_agent_civ()`, relationship helpers, and diagnostics.

### Rust already has live agent state that `M54c` could exploit

Primary files:
- `chronicler-agents/src/pool.rs`
- `chronicler-agents/src/signals.rs`
- `chronicler-agents/src/ffi.rs`

Relevant existing Rust-side state:
- `civ_affinity`
- `region`
- `loyalty`
- `occupation`
- `satisfaction`
- per-civ aggregate derivation from the live pool via `get_aggregates()`
- direct agent reassignment via `set_agent_civ()`

Inference:
- the roadmap's "read agent distributions directly from the pool" is plausible
- but the surrounding topology objects are still Python-owned today, so a first-cut migration does not need to force full Rust ownership of federations/vassals/relationships

### There is no spatial sort implementation yet

There is no live Morton/radix/spatial-sort implementation in:
- `src/chronicler/`
- `chronicler-agents/src/`

If spatial sort stays inside `M54c`, that part of the milestone is still pure design work at this point.

## Current Consumer Map

### Bridge transition helpers are already the seam

Primary file:
- `src/chronicler/agent_bridge.py`

Current helpers:
- `apply_secession_transitions()`
- `apply_restoration_transitions()`
- `apply_absorption_transitions()`
- `_transfer_region_agents_to_civ()`

These run **after** Python politics decisions and handle:
- ordinary-agent civ reassignment through `set_agent_civ()`
- named-character ownership moves
- political transition events like `secession_defection`

Important consequence:
- any `M54c` design has to either keep these helpers as the apply/materialization layer, or replace them with an explicit returned op contract

### There is already a transient region signal seam

`check_secession()` currently sets `region._seceded_this_turn = True` for breakaway regions.

`build_region_batch()` currently:
- reads `_controller_changed_this_turn`
- reads `_war_won_this_turn`
- reads `_seceded_this_turn`
- clears all three before returning

`tests/test_agent_bridge.py` already has 2-turn cleanup coverage for these transients.

Important consequence:
- if `M54c` changes how secession is surfaced to the next turn, it still needs to preserve the repo's transient-signal rule and the multi-turn reset test pattern

### Off-mode and hybrid branching is pervasive

Many politics functions currently have three behaviors:
- **hybrid:** append `pending_shocks` and/or call bridge transition helpers
- **acc path:** route through `StatAccumulator`
- **direct mutation path:** mutate Python models immediately

This is one reason `M54c` should not be spec'd as "hybrid only." The roadmap explicitly makes `--agents=off` part of the gate.

### Phase 10 politics outputs are next-turn inputs

Important timing fact:
- Phase 10 politics runs **after** the agent tick in `run_turn()`
- hybrid-mode `pending_shocks` appended in Phase 10 are consumed on the **next** turn
- topology transients like `_seceded_this_turn` are likewise visible on the **next** turn's `build_region_batch()`

This latency is already part of the design and should be treated as an invariant unless the spec explicitly changes it.

## State Categories Worth Locking Now

### Persistent Python world state

These remain Python-owned today:
- relationships
- vassal relations
- federations
- proxy wars
- exile modifiers
- active wars and war-start metadata
- civ region membership / capitals / founded-turn metadata
- region controllers
- GreatPerson ownership and labels

### Persistent Rust simulator state

These already exist on the simulator side:
- live agent pool affiliation and region placement
- loyalty/satisfaction/occupation data
- aggregate views derivable from the pool

### Per-turn political outputs

The first `M54c` cut will likely need an explicit contract for at least some of these:
- shock ops to enqueue into `pending_shocks`
- civ topology ops: create civ, split civ, absorb civ, restore civ, reassign capital
- region ops: controller changes, secession flags, restoration/absorption swaps
- relationship/federation/vassal/war ops
- named-character / ordinary-agent reassignment ops
- typed political event triggers for Python materialization

## Likely Migration Boundary

My current lean for the first `M54c` cut:

### Likely Rust-owned decision core

- `check_capital_loss()` candidate selection
- secession trigger and breakaway-region selection
- vassal rebellion trigger
- federation formation / dissolution trigger logic
- proxy-detection trigger
- restoration eligibility and target-region selection
- twilight-absorption absorber selection
- possibly `update_allied_turns()` if the relationship state is already packed for the pass

### Likely Python-side materialization / orchestration

- constructing or patching `Civilization`, `Federation`, `VassalRelation`, `ProxyWar`, `ExileModifier`, and `Relationship` objects
- regnal naming and other string-heavy naming logic
- `Event` object materialization
- artifact lifecycle intents on twilight absorption
- `sync_civ_population()` calls
- bridge transition helper calls, unless M54c explicitly absorbs them into returned ops
- accumulator / `pending_shocks` routing for aggregate/hybrid parity

Reason:
- this follows the same basic "Rust computes, Python materializes" pattern that `M54a` is formalizing
- it avoids forcing the first `M54c` cut to move every object-rich topology structure into Rust
- it leaves room for a later deeper ownership shift if profiling proves it worthwhile

### Probably out of scope for the first `M54c` cut

- every low-cost Phase 2 politics helper
- `MOVE_CAPITAL` / `FUND_INSTABILITY` action handlers
- `trigger_federation_defense()` during war resolution
- any redesign of the diplomacy/intelligence perception systems
- any semantic change to dead-civ handling, exiles, or artifact lifecycle

## Biggest Design Questions

### 1. Does `M54c` still include spatial sort?

Options:
- follow the roadmap and bundle sort here
- follow the viability memo and move shared sort infra to `M54a`

My lean:
- do not block the politics pre-spec on this
- call out both dependency shapes explicitly

### 2. What is the actual unit of migration?

Options:
- all of `politics.py`
- the Phase 10 politics chain only
- a narrower core around secession / federation / restoration / twilight

My lean:
- the ordered Phase 10 chain is the best first-cut boundary

### 3. Who owns topology mutations after Rust returns?

Options:
- Rust authoritative, Python mirrors
- Python authoritative, Rust returns ops/patches
- hybrid model: Rust decides, Python applies

My lean:
- Rust decides, Python applies for the first cut

### 4. What is the return contract?

The natural data buckets look like:
- civ ops
- region ops
- relationship/federation/vassal/war ops
- shock ops
- event trigger rows

Inference:
- `M54c` probably wants more structure than a single flat result object
- the exact contract should follow the `M54a` pattern instead of inventing a competing one now

### 5. How is new-civ creation handled deterministically?

Secession and restoration currently rely on Python-side:
- `Civilization` construction/update
- regnal naming helpers
- trait/value mutation
- `founded_turn` bookkeeping

`M54c` has to either:
- keep those in Python materialization, or
- return enough structured data from Rust to reproduce them exactly

### 6. What is the `--agents=off` story?

Options:
- a lightweight Rust politics engine usable without the full hybrid path
- keeping Python as the off-mode fallback

My lean:
- the spec should mirror `M54a` and decide this explicitly early
- otherwise cleanup/deletion work never becomes clean

### 7. How are bridge transition helpers integrated?

Current futures to choose from:
- keep the helpers and call them after Rust returns political ops
- replace them with returned agent-reassignment ops
- let a new Rust politics entry point mutate pool affiliations directly

This needs an explicit decision because secession, restoration, and absorption all depend on it.

### 8. Where do transients live?

At minimum:
- secession currently emits `_seceded_this_turn`
- that transient follows the clear-before-return rule
- it already has multi-turn tests

Any returned-op contract should preserve that explicitly.

## Invariants The Agent Should Not Lose

- Phase 10 ordering is part of the behavior:
  - capital loss
  - secession
  - allied-turn update
  - vassal rebellion
  - federation formation
  - federation dissolution
  - proxy detection
  - restoration
  - twilight absorption
- `world.pending_shocks` produced in Phase 10 are next-turn inputs, not same-turn inputs.
- Dead civs stay in `world.civilizations`; extinction is represented by `len(civ.regions) == 0`, not list removal.
- Secession sets `_seceded_this_turn` on breakaway regions; the transient must clear on the next `build_region_batch()` read and keep its 2-turn test.
- Hybrid mode currently calls bridge transition helpers for secession, restoration, and twilight absorption. Those transitions cannot silently disappear.
- Many politics RNG sites use `stable_hash_int(...)`; a Rust port must preserve deterministic seed construction rather than switch to thread-order-sensitive RNG.
- `check_twilight_absorption()` also emits artifact lifecycle intents; that side effect is easy to miss.
- `trigger_federation_defense()` is part of war resolution, not the Phase 10 chain.
- `update_allied_turns()` runs between secession and the federation checks; moving it changes federation timing.
- `--agents=off` must remain bit-identical to the established baseline per roadmap.
- Any new transient crossing the Python/Rust boundary needs the usual multi-turn reset test.

## Good Oracle Sources

- `tests/test_politics.py`
- `tests/test_agent_bridge.py`
- `src/chronicler/politics.py`
- `src/chronicler/simulation.py`
- `src/chronicler/agent_bridge.py`
- `src/chronicler/action_engine.py`
- `src/chronicler/models.py`

Especially useful existing coverage:
- secession fire/non-fire behavior
- secession stat-split conservation
- federation formation and defense
- restoration hybrid bridge handoff
- twilight absorption dead-civ behavior
- twilight absorption hybrid bridge handoff
- transient cleanup for `seceded_this_turn`

## Suggested Next Output

If the next agent wants a focused deliverable before `M54a` lands, I would aim for:
- a 1-2 page `M54c` pre-spec
- explicit scope / non-goals, with a separate line item for the spatial-sort placement decision
- a state-classification table: Python topology state vs Rust live pool state vs per-turn political ops
- an ordered Phase 10 contract section
- a section on hybrid/off-mode handling
- a short "what waits for M54a" section

I would explicitly avoid, for now:
- freezing exact Arrow schemas
- freezing the final PyO3 method signature
- committing to a full-Rust ownership model for federations/vassals/relationships before the return contract is clear
- letting the unresolved spatial-sort dependency graph stall the politics spec itself
