# M54c: Rust Politics Migration — Design Spec

> **Status:** Ready for implementation after M54a and M54b landed cleanly. Scope, ownership model, batch families, helper ownership, off-mode strategy, and ordered-op contract are locked. This spec intentionally treats M54c as politics-only; spatial sort remains deferred to M55 until the roadmap text is reconciled.
>
> **Date:** 2026-03-22
> **Updated:** 2026-03-23
>
> **Depends on:** M54a (Rust Ecology Migration, landed) and M54b (Rust Economy Migration, landed) — reuse their dedicated `PyRecordBatch` entry points, centralized schema helpers, config-setter pattern, split-orchestration discipline, and off-mode wrapper shape.
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

- **Phase 10 prelude before politics:** condition ticking, movement/culture/religion work, belief/persecution updates, and `apply_asabiya_dynamics(world)` all remain in Python. M54c only replaces the politics block that currently begins immediately after `apply_asabiya_dynamics(world)`.
- **Topology materialization:** `Civilization` construction/update, `Federation`/`VassalRelation`/`ProxyWar`/`ExileModifier` CRUD, region controller patches.
- **Bridge transition helpers:** `apply_secession_transitions()`, `apply_restoration_transitions()`, `apply_absorption_transitions()` — handle agent civ reassignment, named-character ownership moves, transition events.
- **Event object construction:** Rust returns typed event metadata; Python builds `Event` objects with final description strings.
- **Shock routing:** `pending_shocks` append in hybrid mode.
- **Regnal naming** and all string-heavy naming logic.
- **`sync_civ_population()`** calls after topology mutations.
- **Direct stat application in non-hybrid mode.** Accumulator compatibility may survive as an oracle/test helper surface, but it is not part of the production runtime contract.

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
| 1 | `check_capital_loss` | civ ops (reassign capital) + shock/effect ops + event triggers | hybrid runtime vs non-hybrid direct. Optional acc compatibility only for legacy/oracle tests. |
| 2 | `check_secession` | civ ops (create breakaway) + region ops (controller swaps, `_seceded_this_turn`) + relationship ops (HOSTILE parent-breakaway, NEUTRAL breakaway-others) + shock/effect ops + event triggers | Bridge helper call site. Most complex step. Updates `civ.event_counts`. Uses `graph_distance()` for secession scoring and breakaway capital selection. Reads `civ_majority_faith` and `region.majority_belief` for M38b schism secession modifier. |
| 3 | `update_allied_turns` | relationship state deltas (increment for ALLIED, reset to 0 for HOSTILE/SUSPICIOUS/NEUTRAL) | Pure bookkeeping, no events |
| 4 | `check_vassal_rebellion` | relationship ops (remove vassal relation, set vassal-overlord HOSTILE) + civ stat deltas + shock/effect ops + event triggers | hybrid runtime vs non-hybrid direct. Step-4 perception must recompute against current in-pass state rather than precomputed Python perceived values. Has `rebelled_overlords` intra-step accumulator: first rebellion uses base prob, subsequent against same overlord use reduced prob + require HOSTILE/SUSPICIOUS disposition. Iteration order over `world.vassal_relations` must be deterministic. Optional acc compatibility only for legacy/oracle tests. |
| 5 | `check_federation_formation` | federation ops (create new or append member) + event triggers (CREATE only, not APPEND_MEMBER) | No acc param |
| 6 | `check_federation_dissolution` | federation ops (remove member or dissolve entirely) + shock/effect ops + event triggers | Event only on full dissolution. hybrid runtime vs non-hybrid direct. Optional acc compatibility only for legacy/oracle tests. |
| 7 | `check_proxy_detection` | proxy-war state delta (`detected=True`) + relationship state delta (disposition-HOSTILE) + shock/stat ops + event triggers | hybrid runtime vs non-hybrid direct. Optional acc compatibility only for legacy/oracle tests. |
| 8 | `check_restoration` | civ ops (restore exiled civ, transfer regions) + exile ops (remove modifier) + relationship ops (init full block for restored civ) + event triggers | Bridge helper call site |
| 9 | `check_twilight_absorption` | civ ops (absorb dying civ, transfer regions, `regions=[]`) + exile ops (append new modifier) + artifact-intent ops + event triggers | Bridge helper call site. Two trigger paths: unviable (<10 capacity) and terminal twilight (40+ decline turns). Absorbed civ stays in `world.civilizations` with `regions=[]`. |
| 10 | `update_decline_tracking` | bookkeeping deltas (`stats_sum_history` append, `decline_turns` increment/reset) | Pure bookkeeping, no events |
| 11 | Forced collapse | civ ops (strip to first remaining region via `regions[:1]`) + region ops (nullify dropped controllers) + shock/effect ops + event triggers | Currently inline in `simulation.py:1020-1041`. No acc path: hybrid emits `pending_shocks`, non-hybrid directly halves military/economy via integer division (`//`), not severity multiplier. Does NOT call `sync_civ_population()`. |

**Contract notes:**

- Steps 1 and 2 also update `civ.event_counts` — covered by bookkeeping delta ops.
- Step 9 does NOT update vassals or federations. It transfers regions, appends a new `ExileModifier`, emits artifact lifecycle intents, and calls the absorption bridge helper in hybrid mode.
- Step 11 keeps `civ.regions[:1]` (first listed region), which is NOT necessarily `capital_region`. This is existing behavior, not a bug.
- Step 11 uses integer division (`military // 2`, `economy // 2`), not the M18 severity multiplier. This is intentional existing behavior — see invariant 9 exception note.
- Step 11 does NOT call `sync_civ_population()` after stripping regions. This is existing behavior — see invariant 10 exception note.

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

What Python packs and sends to Rust. Concrete Arrow schemas should follow the landed M54a/M54b pattern: dedicated `PyRecordBatch` families with centralized schema helpers in `ffi.rs`, plus primitive scalar args for run-level context.

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
- **Religion:** `civ_majority_faith` (for M38b schism secession modifier in step 2)
- **Stress:** `civ_stress` (for `get_severity_multiplier()` — used at 8+ call sites across steps 1-9)
- **Observer accuracy metadata:** per-civ inputs needed by step-4 perception recompute that do not change during steps 1-3 (for example dominant-faction class and observer-side bonus summaries)

### Family 2: Region State (per-region row)

- **Identity:** region index
- **Controller:** civ index or sentinel for uncontrolled (`str | None` mapped to index)
- **Adjacencies:** list of adjacent region indices
- **Carrying capacity**
- **Population**
- **Majority belief:** `majority_belief` (for M38b schism secession modifier in step 2)

### Family 3: Political Topology State

Conceptually distinct registries, not pairwise relationship edges:

- **Relationship graph:** `(civ_a, civ_b, disposition, allied_turns)` — pairwise
- **Vassal relations:** `(vassal_civ, overlord_civ)` — step-4 perceived values are recomputed inside Rust from current in-pass state, not precomputed by Python
- **Federations:** `(federation_id, member_list)`
- **Active wars:** `(civ_a, civ_b)` — needed for step-4 perception recompute
- **Embargoes:** `(civ_a, civ_b)` — needed for trade-contact perception recompute
- **Proxy wars:** `(sponsor, target_civ, target_region, detected)`
- **Exile modifiers:** `(original_civ, absorber_civ, conquered_regions, turns_remaining, recognized_by)` — `recognized_by` is needed for restoration probability bonus and restored civ relationship initialization
- **Perception pair metadata:** observer→target bonuses that are stable within steps 1-3 (for example hostage/grudge markers used by the narrow step-4 intelligence subset)

### Family 4: Agent-Backed Live Inputs (available when present)

Rust may read live pool distributions directly in agent-backed modes for consequence evaluation where that is advantageous. Not a required input — the consequence engine must produce correct results from Families 1-3 and 5 alone.

In `--agents=off`, no live pool exists. Consequence evaluation uses packed world-state inputs only.

### Family 5: Run-Level Context and Configuration

- **Seed:** `world.seed`
- **Turn:** `world.turn`
- **Runtime mode:** `hybrid`, `shadow`, `demographics-only`, `off`
- **Tuning overrides:** resolved config values (`K_SECESSION_THRESHOLD`, `K_CAPITAL_LOSS_STABILITY`, `K_TWILIGHT_ABSORPTION_DECLINE`, etc.)
- **Severity multiplier inputs** per civ (or precomputed multipliers)

### Rust Helper Functions

Functions that Rust must reimplement to execute the consequence pass. Analogous to M54a's `effective_capacity` and `pressure_multiplier` callouts.

- **`graph_distance(adjacency_graph, from_region, to_region) -> i32`** — BFS over region adjacencies. Used by `check_secession()` for secession scoring (distance from capital) and breakaway capital selection (min distance to remaining parent regions). Source: `src/chronicler/adjacency.py`.
- **`effective_capacity(region) -> int`** — reads `region.ecology.soil`, `region.ecology.water`, `region.carrying_capacity`, `region.capacity_modifier`. Used by secession scoring (step 2), capital reassignment (step 1), and restoration target selection (step 8). M54a already implements this in Rust for ecology — M54c should reuse that implementation. Requires post-ecology region state to be available in Rust at Phase 10 time (guaranteed since ecology runs in Phase 9).
- **`get_severity_multiplier(civ, world) -> float`** — reads `civ.civ_stress` and severity tuning constants (`K_SEVERITY_STRESS_DIVISOR`, `K_SEVERITY_STRESS_SCALE`, `K_SEVERITY_CAP`, `K_SEVERITY_MULTIPLIER`). Pure function, no side effects. Used at 8+ call sites across steps 1, 2, 4, 6, 7, 8, 9 (not step 11). Source: `src/chronicler/emergence.py`. Reimplementing in Rust is clean. `civ_stress` must be included in Family 1 inputs; severity constants in Family 5 / `PoliticsConfig`.
- **`stable_hash_int(...)` equivalent** — deterministic seed construction for all RNG sites. Must produce identical values to the Python implementation for off-mode parity.

### Intelligence System Boundary (B1 Resolution)

`check_vassal_rebellion()` (step 4) calls `get_perceived_stat()` which depends on `compute_accuracy()` in `intelligence.py`. That function reads adjacency, trade-contact, federation membership, vassal relations, active wars/proxy wars, faction dominance, GreatPerson bonuses (merchant role, hostage status), and leader grudges.

M54c must **not** precompute final perceived values in Python before the Rust pass. Step 4 runs after steps 1-3, so topology-dependent inputs (region control, relationships, trade contact, federation/vassal state, wars) must be recomputed against the current in-pass state.

Boundary choice: Rust reimplements the **narrow** `compute_accuracy()` / `get_perceived_stat()` subset needed by step 4 only. Python may still prepack observer bonuses or pair metadata that do not change within steps 1-3, but the final perceived overlord stability/treasury values are computed inside Rust at step 4.

---

## 5. Output Op Families

### 5.1 Op Structure

Every op is a typed, self-contained instruction. Python's apply layer dispatches on op type without interpreting intent. No prose, no ambiguity.

**Conceptual op shapes (exact Arrow column names belong in the implementation plan, but encoding should follow the landed M54a/M54b batch pattern):**

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

Arrow encoding follows the landed M54a/M54b batch pattern: refs are primitive columns, not nested wrapper objects.

- `CivRef` is encoded as `<field>_ref_kind: u8` (`0 = Existing`, `1 = New`) plus `<field>_ref_id: u16` (existing civ index or local id).
- `FederationRef` uses the same two-column pattern.

### 5.3 Ordering

Ops are emitted with `step + seq` ordering. Python applies them in that order. The ordering preserves cross-family dependencies within a step (e.g., `CREATE_BREAKAWAY` before the `RegionOp`s and `RelationshipOp`s that reference the new civ).

### 5.4 Mode Branching

Production runtime is two-way, matching `simulation.py`:

- **Hybrid runtime:** shock-style political effects (`HYBRID_SHOCK`) append to `pending_shocks`; direct bookkeeping/treasury/asabiya deltas still mutate immediately where encoded.
- **Non-hybrid runtime (`off`, aggregate/direct runs):** apply returned deltas directly to Python-owned civ state. There is no production accumulator path for the Phase 10 political sub-pass.
- **Optional compatibility:** `SIGNAL` / `GUARD_SHOCK` tags may be retained only to preserve direct function-level oracle/test surfaces. They are not part of the production runtime contract.

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
- **CivEffectOp:** Runtime-dispatched (hybrid shock routing to `pending_shocks` where encoded; otherwise direct mutation).
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
- No more hybrid-vs-direct branching scattered across `politics.py` functions — that branching is handled by `CivEffectOp.routing` in the apply layer. Optional accumulator compatibility, if retained, lives only in oracle/test helpers, not the runtime path.

### 6.5 Python Helper Ownership

To match the landed M54a/M54b pattern:

- `src/chronicler/politics.py` owns the dedicated politics pack/unpack/apply helpers.
- `src/chronicler/simulation.py` owns turn-order orchestration and runtime dispatch only.
- `src/chronicler/agent_bridge.py` keeps the bridge transition helpers (`apply_secession_transitions()`, `apply_restoration_transitions()`, `apply_absorption_transitions()`), but does **not** become the schema-assembly layer for M54c.

Expected helper families:

- `build_politics_civ_input_batch(...)`
- `build_politics_region_input_batch(...)`
- dedicated topology builders for relationships, vassals, federations, wars, embargoes, proxy wars, and exile modifiers
- `reconstruct_politics_ops(...)`
- `apply_politics_ops(...)`

M54c must **not** extend `build_region_batch()` or overload `set_region_state()` for politics. Phase 10 politics is a dedicated call path, not an extension of the generic region-sync surface.

---

## 7. `--agents=off` Strategy

### Target Architecture

M54c targets a single Rust politics consequence implementation across all runtime modes, including `--agents=off`. Following the landed M54a pattern, off-mode should use a dedicated politics-only wrapper analogous to `EcologySimulator` (for example `PoliticsSimulator`) rather than keeping Python politics as the steady-state fallback.

### What That Means

- `--agents=off` parity is a **hard milestone gate**, not a nice-to-have.
- The consequence engine must work from packed world-state inputs alone (Families 1-3, 5) when no live pool exists.
- Secession/federation checks that could benefit from pool distributions fall back to aggregate civ stats in off-mode — which is exactly what the current Python code does today.
- One consequence engine semantics. Agent-backed modes may enrich evaluation with live pool data when available. Off-mode uses packed world-state inputs only.
- Off-mode should instantiate the dedicated politics wrapper, set config, send the politics batches, call `tick_politics()`, and apply the returned op batches through the same Python materialization path.
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

9. **Severity multiplier.** All negative stat changes (except treasury, ecology) go through M18 severity multiplier. Rust must replicate this. **Exception:** Step 11 (forced collapse) uses integer division (`military // 2`, `economy // 2`), not the severity multiplier. This is intentional existing behavior — do not "fix" it to match the general rule.

10. **`sync_civ_population()` timing.** Called after topology mutations that change region membership — must remain step-local, not deferred. **Exception:** Step 11 (forced collapse) does NOT call `sync_civ_population()` after stripping regions. This is existing behavior — do not add a sync call.

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
| 200-seed regression | Canonical `200 seeds x 500 turns` regression recorded against the accepted M54b baseline (`output/m54b/.../validate_report.json`) |

---

## 9. What Is Locked After M54a/M54b

### Locked by the landed migration pattern

- `tick_politics()` should use dedicated `PyRecordBatch` inputs/outputs plus primitive scalar args, not a wrapper payload object and not overloads on `set_region_state()`.
- `ffi.rs` should own centralized schema helpers and batch builders for each politics batch family, matching the landed ecology/economy pattern.
- Politics tuning should flow through a dedicated `set_politics_config(...)` setter on the simulator, analogous to `set_ecology_config(...)` and `set_economy_config(...)`.
- Python should own dedicated politics pack/unpack helpers in `politics.py`; `simulation.py` keeps orchestration and call order, not Arrow schema assembly.
- `--agents=off` should use a dedicated politics wrapper analogous to `EcologySimulator`, not Python politics as the steady-state fallback.
- Ordered politics output should use dedicated per-family batches with `step` and `seq` columns, not a heterogeneous wrapper object.
- `CivRef` and `FederationRef` should use primitive `(ref_kind, ref_id)` columns inside those batches, per Section 5.2.

### Concrete PyO3 surface

The implementation should follow this shape:

```text
set_politics_config(...)

tick_politics(
  civ_input_batch,
  region_input_batch,
  relationship_input_batch,
  vassal_input_batch,
  federation_input_batch,
  war_input_batch,
  embargo_input_batch,
  proxy_war_input_batch,
  exile_input_batch,
  turn,
  hybrid_mode,
) -> (
  civ_ops_batch,
  region_ops_batch,
  relationship_ops_batch,
  federation_ops_batch,
  vassal_ops_batch,
  exile_ops_batch,
  proxy_war_ops_batch,
  civ_effect_batch,
  bookkeeping_batch,
  artifact_intent_batch,
  bridge_transition_batch,
  event_trigger_batch,
)
```

Each batch should always be returned, even when empty. Python dispatch depends on a fixed tuple order, not optional returns.

The dedicated off-mode wrapper (`PoliticsSimulator`, or the chosen equivalent name) should expose the same `tick_politics(...)` signature and return order so `simulation.py` can share one orchestration path across agent-backed and off-mode execution.

### Remaining implementation choices

- Exact batch family split, if a few adjacent families are merged for ergonomics without changing the `step + seq` ordered-dispatch contract.
- Final naming of the off-mode wrapper (`PoliticsSimulator` vs similar).
- Exact `PoliticsConfig` field list and widths. The implementation plan should enumerate all consumed constants, distinguish compiled constants from override-path values, and mirror the M54a/M54b config-setter pattern.

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
