# M54c: Rust Politics Migration — Design Spec (Pre-Spec)

> **Status:** Pre-spec. Scope, ownership model, and contract structure are locked. Exact Arrow schemas, PyO3 method signatures, and off-mode wiring mechanism are deferred until M54a lands and establishes the migration pattern.
>
> **Date:** 2026-03-22
>
> **Depends on:** M54a (Rust Ecology Migration) — establishes Arrow-batch-in / Arrow-batch-out pattern, shared FFI helpers, bridge conventions, and off-mode wiring.
>
> **Estimated days:** 7-11
>
> **Roadmap ref:** `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md` — Scale Track

---

## 1. Scope

### What M54c delivers

- Rust `tick_politics()` method on `AgentSimulator` that executes the **11-step ordered Phase 10 political consequence sub-pass** as a single pass. This sub-pass currently begins after `apply_asabiya_dynamics(world)` in `phase_consequences()` and ends with forced-collapse evaluation.
- Python orchestration layer: packs political world state, calls Rust, unpacks returned ops, applies them through existing materialization machinery.
- Structured op return contract with typed families (civ ops, region ops, relationship ops, federation ops, vassal ops, exile ops, proxy-war ops, effect ops, bookkeeping deltas, artifact-intent ops, event triggers).
- Determinism gate: identical results across runs for same seed, including across thread counts if rayon is used.
- `--agents=off` parity gate: bit-identical post-political-sub-pass world state.

### What stays in Python

- **Topology materialization:** `Civilization` construction/update, `Federation`/`VassalRelation`/`ProxyWar`/`ExileModifier` CRUD, region controller patches.
- **Bridge transition helpers:** `apply_secession_transitions()`, `apply_restoration_transitions()`, `apply_absorption_transitions()` — handle agent civ reassignment, named-character ownership moves, transition events.
- **Event object construction:** Rust returns typed event metadata; Python builds `Event` objects with final description strings.
- **Shock routing:** `pending_shocks` append in hybrid mode.
- **Regnal naming** and all string-heavy naming logic.
- **`sync_civ_population()`** calls after topology mutations.
- **Accumulator routing** for aggregate/off-mode stat deltas.

### Non-goals

- Phase 2 political helpers (governing costs, tribute, proxy wars, exile effects, balance of power, twilight, long peace, peak tracking).
- Action-resolution hooks (`MOVE_CAPITAL`, `FUND_INSTABILITY`, `trigger_federation_defense()`).
- Spatial sort (deferred to M55 / spatial branch).
- New political features or calibration changes.
- Full Rust ownership of federations/vassals/relationships (future optimization only).
- Redesign of diplomacy/intelligence perception systems.
- Any semantic change to dead-civ handling, exiles, or artifact lifecycle.

---

## 2. Ordered Phase 10 Political Consequence Contract

Rust executes these 11 steps in strict order. The ordering is a hard invariant — each step can see mutations from prior steps.

| Step | Function | Op Families | Notes |
|------|----------|-------------|-------|
| 1 | `check_capital_loss` | civ ops (reassign capital) + shock/effect ops + event triggers | hybrid/acc branching |
| 2 | `check_secession` | civ ops (create breakaway) + region ops (controller swaps, `_seceded_this_turn`) + relationship ops (HOSTILE parent-breakaway, NEUTRAL breakaway-others) + shock/effect ops + event triggers | Bridge helper call site. Most complex step. Updates `civ.event_counts`. |
| 3 | `update_allied_turns` | relationship state deltas (increment for ALLIED, reset to 0 for HOSTILE/SUSPICIOUS/NEUTRAL) | Pure bookkeeping, no events |
| 4 | `check_vassal_rebellion` | relationship ops (remove vassal relation, set vassal-overlord HOSTILE) + civ stat deltas + shock/effect ops + event triggers | hybrid/acc branching |
| 5 | `check_federation_formation` | federation ops (create new or append member) + event triggers | No acc param |
| 6 | `check_federation_dissolution` | federation ops (remove member or dissolve entirely) + shock/effect ops + event triggers | Event only on full dissolution. hybrid/acc branching |
| 7 | `check_proxy_detection` | proxy-war state delta (`detected=True`) + relationship state delta (disposition-HOSTILE) + shock/stat ops + event triggers | hybrid/acc branching |
| 8 | `check_restoration` | civ ops (restore exiled civ, transfer regions) + exile ops (remove modifier) + relationship ops (init full block for restored civ) + event triggers | Bridge helper call site |
| 9 | `check_twilight_absorption` | civ ops (absorb dying civ, transfer regions, `regions=[]`) + exile ops (append new modifier) + artifact-intent ops + event triggers | Bridge helper call site. Two trigger paths: unviable (<10 capacity) and terminal twilight (40+ decline turns). Absorbed civ stays in `world.civilizations` with `regions=[]`. |
| 10 | `update_decline_tracking` | bookkeeping deltas (`stats_sum_history` append, `decline_turns` increment/reset) | Pure bookkeeping, no events |
| 11 | Forced collapse | civ ops (strip to first remaining region via `regions[:1]`) + region ops (nullify dropped controllers) + shock/effect ops + event triggers | Currently inline in `simulation.py:1020-1041`. No acc path: hybrid emits `pending_shocks`, non-hybrid directly halves military/economy. |

**Contract notes:**

- Steps 1 and 2 also update `civ.event_counts` — covered by bookkeeping delta ops.
- Step 9 does NOT update vassals or federations. It transfers regions, appends a new `ExileModifier`, emits artifact lifecycle intents, and calls the absorption bridge helper in hybrid mode.
- Step 11 keeps `civ.regions[:1]` (first listed region), which is NOT necessarily `capital_region`. This is existing behavior, not a bug.

---

## 3. Ownership Model

**Rule:** Rust decides, Python applies. Rust evaluates the consequence chain and returns structured political ops. Python materializes those ops onto the world state through the existing machinery. Rust does not directly mutate any Python-owned state. The return contract is the only channel for political decisions flowing back to Python.

### 3.1 Python-owned persistent state (read by Rust, mutated by Python apply layer)

| State | Model Location | Notes |
|-------|---------------|-------|
| `civ.regions` | `Civilization` | List topology |
| `civ.capital_region` | `Civilization` | String or None |
| `civ.founded_turn`, `civ.decline_turns` | `Civilization` | Scalar bookkeeping |
| `civ.stats_sum_history` | `Civilization` | Bounded 20-element window |
| `civ.event_counts` | `Civilization` | Dict bookkeeping |
| `civ.traditions` | `Civilization` | List of strings (inherited on secession) |
| `civ.population`, `civ.military`, `civ.economy`, `civ.culture`, `civ.stability`, `civ.treasury`, `civ.asabiya` | `Civilization` | Core scalar stats. Rust may return deltas; Python is authoritative owner. |
| `civ.leader`, `civ.leader_name_pool`, `civ.values`, `civ.domains`, `civ.tech_era` | `Civilization` | Materialization-relevant metadata for secession/restoration |
| `region.controller` | `Region` | `str \| None` |
| `world.relationships` | `WorldState` | Nested dict of Pydantic `Relationship` objects |
| `world.vassal_relations` | `WorldState` | List of `VassalRelation` |
| `world.federations` | `WorldState` | List of `Federation` |
| `world.proxy_wars` | `WorldState` | List of `ProxyWar` |
| `world.exile_modifiers` | `WorldState` | List of `ExileModifier` |
| `world.civilizations` | `WorldState` | List (dead civs stay with `regions=[]`) |

### 3.2 Python-owned transient/turn-bridging state

| State | Semantics |
|-------|-----------|
| `world.pending_shocks` | Append-only per turn. Consumed next turn. |
| `region._seceded_this_turn` | Set in step 2. Cleared before next `build_region_batch()` read. 2-turn test coverage required. |

### 3.3 Rust-readable live pool state and derived inputs (agent-backed modes only)

| State | Pool Location | Potential Use |
|-------|--------------|---------------|
| `civ_affinity` per agent | `AgentPool` SoA | Secession region selection, federation checks |
| `loyalty` per agent | `AgentPool` SoA | Secession/rebellion thresholds |
| `satisfaction` per agent | `AgentPool` SoA | Secession propensity |
| `occupation` per agent | `AgentPool` SoA | Stat-split calculations |
| `region` per agent | `AgentPool` SoA | Region-level agent distribution |
| Per-civ aggregates | Derived from pool | Population counts, loyalty means, satisfaction distributions |

Agent-backed live inputs are available directly from Rust pool state. The current Python politics code does not consume pool-native summaries — it uses civ stats, region topology, and world structures. M54c's value proposition is that Rust *can* enrich consequence evaluation with live pool distributions where advantageous. Off-mode uses packed world-state inputs only.

### 3.4 Per-turn political ops (returned by Rust, applied by Python)

| Op Family | Examples | Consumers |
|-----------|----------|-----------|
| Civ ops | Create breakaway, restore exiled, absorb dying, reassign capital, strip to first region | Python apply layer |
| Region ops | Controller swaps, `_seceded_this_turn` transient, nullify controllers | Python apply layer |
| Relationship ops | Init HOSTILE/NEUTRAL blocks, set disposition, increment/reset `allied_turns` | Python apply layer |
| Federation ops | Create/append member, remove member/dissolve | Python apply layer |
| Vassal ops | Remove vassal relation | Python apply layer |
| Exile ops | Append new modifier, remove expired modifier | Python apply layer |
| Proxy-war ops | Set `detected=True` | Python apply layer |
| Civ effect ops | Stat deltas with explicit routing metadata | Mode-dispatched by Python |
| Bookkeeping deltas | `event_counts`, `stats_sum_history`, `decline_turns` (typed, field-specific) | Python apply layer |
| Artifact-intent ops | Twilight absorption lifecycle intents (per-region) | Python apply layer |
| Bridge transition ops | Secession/restoration/absorption transition triggers | Python apply layer |
| Event triggers | Typed event metadata (event_type, actor refs, importance, step, typed context) | Python event construction |

---

## 4. Input Families

What Python packs and sends to Rust. Exact Arrow schemas deferred to M54a conventions.

### Family 1: Civ State (per-civilization row)

Scalars Rust needs to evaluate thresholds and compute deltas:

- **Identity:** stable civ index
- **Core stats:** `stability`, `military`, `economy`, `culture`, `treasury`, `asabiya`
- **Decline:** `decline_turns`, `stats_sum_history` (bounded 20-element window)
- **Focus:** `active_focus` (for surveillance secession threshold)
- **Topology:** `regions` (list of region indices), `capital_region` (index or sentinel for None)
- **Factions:** `total_effective_capacity` (precomputed by Python from `factions.py`)
- **Population:** `population` (for population-relative checks)
- **Founding:** `founded_turn` (for secession grace period, twilight age gate)

### Family 2: Region State (per-region row)

- **Identity:** region index
- **Controller:** civ index or sentinel for uncontrolled (`str | None` mapped to index)
- **Adjacencies:** list of adjacent region indices
- **Carrying capacity**
- **Population**

### Family 3: Political Topology State

Conceptually distinct registries, not pairwise relationship edges:

- **Relationship graph:** `(civ_a, civ_b, disposition, allied_turns)` — pairwise
- **Vassal relations:** `(vassal_civ, overlord_civ)`
- **Federations:** `(federation_id, member_list)`
- **Proxy wars:** `(sponsor, target_civ, target_region, detected)`
- **Exile modifiers:** `(original_civ, absorber_civ, conquered_regions, turns_remaining)`

### Family 4: Agent-Backed Live Inputs (available when present)

Rust may read live pool distributions directly in agent-backed modes for consequence evaluation where that is advantageous. Not a required input — the consequence engine must produce correct results from Families 1-3 and 5 alone.

In `--agents=off`, no live pool exists. Consequence evaluation uses packed world-state inputs only.

### Family 5: Run-Level Context and Configuration

- **Seed:** `world.seed`
- **Turn:** `world.turn`
- **Runtime mode:** `hybrid`, `shadow`, `demographics-only`, `off`
- **Tuning overrides:** resolved config values (`K_SECESSION_THRESHOLD`, `K_CAPITAL_LOSS_STABILITY`, `K_TWILIGHT_ABSORPTION_DECLINE`, etc.)
- **Severity multiplier inputs** per civ (or precomputed multipliers)

---

## 5. Output Op Families

### 5.1 Op Structure

Every op is a typed, self-contained instruction. Python's apply layer dispatches on op type without interpreting intent. No prose, no ambiguity.

**Conceptual op shapes (exact encoding deferred to M54a conventions):**

```
CivOp:
  type: CREATE_BREAKAWAY | RESTORE | ABSORB | REASSIGN_CAPITAL | STRIP_TO_FIRST_REGION
  source_civ: CivRef
  target_civ: CivRef
  regions: list[region_index]
  stat_deltas: optional
  traditions: optional list
  metadata: optional (founded_turn, etc.)

RegionOp:
  type: SET_CONTROLLER | NULLIFY_CONTROLLER | SET_SECEDED_TRANSIENT
  region: region_index
  controller: CivRef | None

RelationshipOp:
  type: INIT_PAIR | SET_DISPOSITION | RESET_ALLIED_TURNS | INCREMENT_ALLIED_TURNS
  civ_a: CivRef
  civ_b: CivRef
  disposition: optional

FederationOp:
  type: CREATE | APPEND_MEMBER | REMOVE_MEMBER | DISSOLVE
  federation_ref: FederationRef
  civ: CivRef

VassalOp:
  type: REMOVE
  vassal: CivRef
  overlord: CivRef

ExileOp:
  type: APPEND | REMOVE
  original_civ: CivRef
  absorber_civ: CivRef
  conquered_regions: list[region_index]
  turns_remaining: int (for APPEND)

ProxyWarOp:
  type: SET_DETECTED
  sponsor: CivRef
  target_civ: CivRef

CivEffectOp:
  civ: CivRef
  field: enum (military, economy, stability, treasury, ...)
  delta: f32
  routing: KEEP | SIGNAL | GUARD_SHOCK | DIRECT_ONLY | HYBRID_SHOCK

BookkeepingDelta:
  civ: CivRef
  type: APPEND_STATS_HISTORY | INCREMENT_DECLINE | RESET_DECLINE | INCREMENT_EVENT_COUNT
  field and value: typed, field-specific

ArtifactIntentOp:
  losing_civ: CivRef
  gaining_civ: CivRef
  region: region_index
  is_capital: bool
  is_destructive: bool
  action: "twilight_absorption"

BridgeTransitionOp:
  type: SECESSION | RESTORATION | ABSORPTION
  source_civ: CivRef
  target_civ: CivRef
  regions: list[region_index]

EventTrigger:
  event_type: str
  actors: list[CivRef]
  importance: u8
  step: u8
  context: typed metadata per event_type
```

### 5.2 CivRef and FederationRef

Newly created entities need temporary references that later ops can use within the same pass:

- `CivRef = Existing(civ_index) | New(local_id)` — Rust assigns `local_id` during the pass. Python resolves `New(local_id)` to a real civ index when applying `CREATE_BREAKAWAY` or `RESTORE`.
- `FederationRef = Existing(federation_index) | New(local_id)` — same pattern for federation creation followed by member append in the same pass.

Exact encoding deferred to M54a conventions. If M54a establishes a ref pattern, M54c adopts it.

### 5.3 Ordering

Ops are emitted with `step + seq` ordering. Python applies them in that order. The ordering preserves cross-family dependencies within a step (e.g., `CREATE_BREAKAWAY` before the `RegionOp`s and `RelationshipOp`s that reference the new civ).

### 5.4 Mode Branching

Rust returns `CivEffectOp` with explicit `routing` metadata. Python checks `agent_mode` x `routing`:

- **Hybrid runtime:** route `HYBRID_SHOCK` effects to `pending_shocks`.
- **Non-hybrid runtime:** apply `DIRECT_ONLY` / `KEEP` / `SIGNAL` / `GUARD_SHOCK` as direct stat deltas.
- Accumulator compatibility is optional for preserving direct function-level test surfaces, not part of the primary dispatch path.

---

## 6. Python Apply Flow

After Rust returns the op set, Python applies it as a deterministic ordered-op dispatcher.

### 6.1 Dispatch Model

Python iterates the op stream in `step + seq` order and dispatches on op type. The apply layer never needs to know which step it is in — only what op type it is processing.

Bridge transition helper calls, `sync_civ_population()` barriers, and event merges are driven by explicit ops or metadata in the stream, not by Python hardcoding step-specific behavior.

### 6.2 Apply Actions by Op Type

- **CivOp CREATE_BREAKAWAY:** Construct `Civilization` object, assign name (regnal naming), copy traditions, set `founded_turn`, append to `world.civilizations`, resolve `New(local_id)` to real civ index.
- **CivOp RESTORE:** Reactivate exiled civ, transfer regions, init relationship block for restored civ.
- **CivOp ABSORB:** Transfer regions to absorber, set absorbed civ `regions=[]`, call `reset_war_frequency_on_extinction()`.
- **CivOp REASSIGN_CAPITAL:** Set `civ.capital_region` to best remaining region.
- **CivOp STRIP_TO_FIRST_REGION:** Set `civ.regions` to `[:1]`.
- **RegionOp:** Set/nullify `region.controller`, set `_seceded_this_turn` transient.
- **RelationshipOp:** Init/update entries in `world.relationships`.
- **FederationOp / VassalOp / ExileOp / ProxyWarOp:** CRUD on respective `world` state lists.
- **CivEffectOp:** Mode-dispatched (hybrid to `pending_shocks`, non-hybrid to direct mutation).
- **BookkeepingDelta:** Typed field-specific updates (`stats_sum_history`, `decline_turns`, `event_counts`).
- **ArtifactIntentOp:** Call `emit_conquest_lifecycle_intent()` per op.
- **BridgeTransitionOp:** Call the appropriate bridge helper (`apply_secession_transitions()`, `apply_restoration_transitions()`, `apply_absorption_transitions()`). Merge any helper-returned events (e.g., `secession_defection`) into the event list.
- **sync barrier:** `sync_civ_population()` — called after topology mutations that change region membership. Step-local, not deferred.
- **EventTrigger:** Build `Event` objects from typed metadata. Python assembles final description strings. Merge with bridge-helper-returned events in deterministic order. Append to `collapse_events`.

### 6.3 What This Preserves

- Strict 11-step ordering.
- Bridge transition helpers called at their current timing relative to topology mutations.
- Dead civs stay in `world.civilizations` with `regions=[]`.
- `pending_shocks` appended in hybrid mode are next-turn inputs.
- `_seceded_this_turn` transient follows clear-before-return rule with existing 2-turn test.
- `sync_civ_population()` called step-locally after topology mutations.

### 6.4 What Changes

- Decision logic moves to Rust (the "why" of each mutation).
- Python apply layer is mechanical dispatch (the "how" of each mutation).
- No more hybrid/acc/direct branching scattered across `politics.py` functions — that branching is handled by `CivEffectOp.routing` in the apply layer.

---

## 7. `--agents=off` Strategy

### Target Architecture

M54c targets a single Rust politics consequence implementation across all runtime modes, including `--agents=off`, mirroring the intended M54a off-mode pattern. The exact off-mode wiring is deferred until M54a lands. If M54a's lightweight simulator approach proves clean, M54c adopts it; if not, Python fallback may remain temporarily, but that is not the desired steady state.

### What That Means

- `--agents=off` parity is a **hard milestone gate**, not a nice-to-have.
- The consequence engine must work from packed world-state inputs alone (Families 1-3, 5) when no live pool exists.
- Secession/federation checks that could benefit from pool distributions fall back to aggregate civ stats in off-mode — which is exactly what the current Python code does today.
- One consequence engine semantics. Agent-backed modes may enrich evaluation with live pool data when available. Off-mode uses packed world-state inputs only.
- Python deletion of old Phase 10 politics functions is gated on **both** hybrid-mode and off-mode being wired through Rust and passing parity tests.

### Parity Test Definition

For any seed, the post-political-sub-pass world state in `--agents=off` must be bit-identical before and after M54c:

- `world.civilizations` topology and civ fields (`regions`, `capital_region`, `decline_turns`, `stats_sum_history`, `event_counts`, core stats)
- Political registries (`relationships`, `federations`, `vassal_relations`, `proxy_wars`, `exile_modifiers`)
- All `region.controller` values
- Emitted political events (type, actors, importance)
- `pending_shocks == []` in off-mode

---

## 8. Invariants and Merge Gates

### Hard Invariants

1. **Phase 10 political sub-pass ordering.** The 11-step sequence is fixed. Steps must execute in order. Each step sees mutations from prior steps.

2. **Dead-civ persistence.** Absorbed/collapsed civs remain in `world.civilizations` with `regions=[]`. Never removed from the list.

3. **Next-turn shock semantics.** `pending_shocks` appended during the political sub-pass are consumed on the next turn, not the current turn.

4. **Transient signal rule.** `_seceded_this_turn` (and any new transients) must clear before the next `build_region_batch()` read. Existing 2-turn test coverage must be preserved or extended.

5. **Deterministic RNG.** All RNG sites use `stable_hash_int()` seed construction (or Rust equivalent with identical derivation). No thread-order-sensitive RNG. Identical seed + world state = identical ops.

6. **Bridge transition helper semantics.** `apply_secession_transitions()`, `apply_restoration_transitions()`, `apply_absorption_transitions()` continue to handle agent civ reassignment and named-character ownership moves. Their call timing relative to topology mutations must match current behavior.

7. **Artifact lifecycle intents.** Twilight absorption emits `emit_conquest_lifecycle_intent()` per absorbed region. These must not silently disappear.

8. **`--agents=off` parity.** Bit-identical post-political-sub-pass world state per Section 7 parity test definition.

9. **Severity multiplier.** All negative stat changes (except treasury, ecology) go through M18 severity multiplier. Rust must replicate this.

10. **`sync_civ_population()` timing.** Called after topology mutations that change region membership — must remain step-local, not deferred.

11. **Deterministic event merge ordering.** Bridge-helper-returned events (e.g., `secession_defection`) must merge with Rust event triggers in deterministic order. No reordering across runs.

### Merge Gates

| Gate | Criteria |
|------|----------|
| Determinism | Identical op output across 5 runs for same seed |
| Cross-thread determinism | Identical results at 1/4/8/16 thread counts (if rayon is used) |
| Off-mode parity | Bit-identical post-sub-pass state for 20+ seeds vs. pre-M54c baseline |
| Hybrid-mode parity | Same political events and topology outcomes for 20+ seeds vs. pre-M54c baseline |
| Existing test suite | All `test_politics.py` and `test_agent_bridge.py` tests pass (adapted for new call path) |
| Transient coverage | 2+ turn integration tests for every transient crossing the Rust/Python boundary |
| Phase consequences integration test | Full 11-step sub-pass ordering test verifying cross-step interaction correctness |
| 200-seed regression | Distribution comparison against M53 baseline (event counts, secession rate, federation formation rate, extinction rate) |

---

## 9. What Waits for M54a

| Item | Why |
|------|-----|
| Exact Arrow schemas | M54a establishes batch conventions |
| PyO3 method signatures | M54a establishes the `tick_*()` pattern |
| Shared helper structure in `ffi.rs` / `agent_bridge.py` | Reuse, don't reinvent |
| Op encoding choice (unified stream vs per-step batches) | Should follow M54a's return pattern |
| Off-mode wiring mechanism | M54a proves lightweight-simulator approach first |
| CivRef / FederationRef encoding | Match M54a's ref pattern if one emerges |

---

## 10. Spatial Sort

Spatial sort is **not part of M54c**. The canonical roadmap bundles spatial sort with M54c, but this spec follows the viability-adjustments recommendation: M54c is politics-only. Spatial sort is deferred to the spatial branch (M55), where it extends naturally into the full Morton Z-curve key with (x,y) interleaving once spatial coordinates exist.

---

## Reference: Current Code Locations

| File | Relevant Content |
|------|-----------------|
| `src/chronicler/politics.py` | All 9 named Phase 10 functions + `update_decline_tracking` |
| `src/chronicler/simulation.py:1001-1041` | Phase 10 call chain + inline forced collapse |
| `src/chronicler/agent_bridge.py:1218-1350` | Bridge transition helpers (secession, restoration, absorption) |
| `src/chronicler/models.py:480-510` | `VassalRelation`, `Federation`, `ProxyWar`, `ExileModifier` |
| `src/chronicler/factions.py` | `total_effective_capacity()` (used by twilight absorption) |
| `src/chronicler/artifacts.py` | `emit_conquest_lifecycle_intent()` |
| `tests/test_politics.py` | Existing politics test coverage |
| `tests/test_agent_bridge.py` | Bridge transition and transient cleanup tests |
