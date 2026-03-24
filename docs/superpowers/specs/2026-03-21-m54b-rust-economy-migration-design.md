# M54b: Rust Economy Migration — Design Spec

> **Status:** Implementation-ready. Runtime semantics, consumer contracts, migration boundaries, FFI shape, helper ownership, and schema surface are locked from the landed M54a pattern.
>
> **Date:** 2026-03-21
> **Updated:** 2026-03-23
>
> **Depends on:** M54a (Rust Ecology Migration, landed) — reuse its explicit Arrow schema helpers, direct `PyRecordBatch` FFI methods, config wiring pattern, and split-bridge discipline.

---

## 1. Scope

### What M54b delivers

- Rust `tick_economy()` method on `AgentSimulator` that owns the full Phase 2 computation: production, demand, pricing, tatonnement, trade allocation, transit decay, stockpile lifecycle (accumulate/consume/decay/cap), and same-turn signal derivation.
- Python orchestration layer: packs input, calls Rust, unpacks result, writes back stockpiles to `Region.stockpile.goods`, feeds EconomyTracker / shock detection / narration consumers.
- Fixed-slot goods normalization for FFI (no variable-length dicts cross the boundary).
- Parity gate: Python `compute_economy()` remains during migration as the parity/reference path. Identical outputs at float tolerance for shared seeds.
- Conservation: inline Rust summary + independent Python validation from sidecar export. Both pass the merge gate.
- Determinism: bit-identical Rust-to-Rust across runs for same seed. Sequential trade kernel with stable route ordering.

### Non-goals

- Migrating `EconomyTracker` to Rust (stays Python, fed by Rust observability).
- Migrating `detect_supply_shocks()` to Rust (stays Python, reads Rust-returned observability).
- Migrating raider modifier to Rust (stays in `action_engine.py`, reads written-back `Region.stockpile.goods`).
- Parallel tatonnement or trade allocation (sequential kernel; future optimization only if profiled).
- Persistent Rust-owned stockpile state (round-trip per turn; Python durably owns).
- Narration/curator economy context migration.
- New economy features or calibration changes.

---

## 2. State Classification

Nothing changes ownership category. Persistent stays persistent, analytics stays analytics, transient stays transient. The only change is which language computes and returns the transient outputs.

### Persistent simulation state (world state)

| State | Current owner | Authoritative during Phase 2 | Notes |
|-------|--------------|------------------------------|-------|
| `Region.stockpile.goods` | Python (Pydantic) | Rust mutates; Python durably owns | Round-trip: Python packs → Rust computes → Python writes back |
| Trade route list | Python (`active_trade_routes`) | Python (read-only input) | Passed to Rust, stable-sorted by (origin, dest) |
| Region terrain / resources / ecology | Python | Python (read-only input) | Context for production, transport costs |

Updated stockpiles serve dual duty: they are durable world state after write-back, and they are also immediately consumed same-turn by Python logic (raider modifier in `action_engine.py`). The write-back step must precede all same-turn Python readers.

### Persistent analytics state (run state, not world state)

| State | Owner | M54b change | Notes |
|-------|-------|-------------|-------|
| `EconomyTracker.trailing_avg` | Python | None — fed by Rust-returned stockpile levels | Cross-turn EMA |
| `EconomyTracker.import_avg` | Python | None — fed by Rust-returned import observability | Cross-turn EMA |

### Transient per-turn outputs (overwritten each turn)

| State | Authoritative during Phase 2 | Notes |
|-------|------------------------------|-------|
| Region signals (`farmer_income_modifier`, `food_sufficiency`, `merchant_margin`, `merchant_trade_income`, `trade_route_count`) | Rust return batch | Feed agent tick via bridge |
| Civ signals (`priest_tithe_share`, `treasury_tax`, `tithe_base`) | Rust return batch | `treasury_tax` routed through `StatAccumulator` (keep category). `tithe_base` consumed by `tick_factions()` in Phase 10 to compute tithe and mutate `civ.treasury`. `priest_tithe_share` feeds agent tick via bridge. |
| Consumer observability (`imports_by_region`, `inbound_sources`, `stockpile_levels`, `import_share`, `trade_dependent`) | Rust return batch | Feed EconomyTracker, shock detection, narration |
| `region_goods` (per-good production/imports/exports/prices) | Validation/debug only unless explicitly retained | No same-turn consumer depends on it today. If kept after migration, it is for parity/debugging, not the production bridge contract. |
| `conservation` | Rust inline + Python validation | See Section 7 |

---

## 3. Consumer Map

After `tick_economy()` returns and Python writes back stockpiles, here is who reads what and when.

### Immediate write-back (before anything else reads)

`Region.stockpile.goods` ← updated stockpile values from Rust return. This must happen first because same-turn Python consumers read stockpiles directly off the model.

### Same-turn Python consumers (Phase 2 post-pass, before agent tick)

| Consumer | Reads | Source | Purpose |
|----------|-------|--------|---------|
| `EconomyTracker.update()` | stockpile_levels, imports_by_region | Rust-returned observability | Update dual EMAs for shock baseline |
| `detect_supply_shocks()` | stockpile_levels, food_sufficiency, imports_by_region, inbound_sources | Rust-returned observability + Python-owned tracker state | Emit shock Events |
| `StatAccumulator` | treasury_tax | Rust-returned civ result | Route fiscal effect (keep category) |
| `world._economy_result` stash | All transient signals + observability | Assembled from Rust return | Stored for later-phase consumers |

`world._economy_result` must remain a one-turn artifact, overwritten each turn. M43b has a 2-turn test verifying this semantic.

### Same-turn Rust consumers (agent tick, via bridge batches)

| Consumer | Reads | Notes |
|----------|-------|-------|
| `build_region_batch()` | farmer_income_modifier, food_sufficiency, merchant_margin, merchant_trade_income, trade_route_count | Must be available before `AgentBridge.tick()` starts building batches |
| `build_signals()` | priest_tithe_share | Must be available before `AgentBridge.tick()` starts building batches |

**Decision:** `_economy_result` remains the canonical Python-side transient handoff object. After `tick_economy()` returns, Python assembles a refreshed `EconomyResult`-like object, writes back stockpiles, stores that object on `world._economy_result`, and `AgentBridge` continues reading same-turn region/civ economy signals from that object when building the later agent batches.

Why lock this now:
- the current bridge already reads economy signals from `_economy_result`
- later Python consumers already key off `_economy_result`
- it avoids inventing a second cached-return path just for the bridge

### Later-phase Python consumers

| Consumer | Reads | Phase |
|----------|-------|-------|
| `action_engine.py` raider modifier | Written-back `Region.stockpile.goods` + `_economy_result` as presence gate | Phase 8 |
| `tick_factions()` | `tithe_base` from civ result (via `_economy_result`) | Phase 10 |
| `narrative.py` context builders | `trade_dependent`, supply shocks (from Events) | Narration |

Phase 8 and Phase 10 consume a mix of durable (stockpiles) and transient (economy result metadata) economy outputs. `tithe_base` is consumed by `tick_factions()` to compute tithe and directly mutate `civ.treasury` — it is not dead data.

---

## 4. FFI Contract (Locked)

This section locks the payload families, method shape, return order, and helper ownership boundaries. M54a already established the conventions this milestone should mirror.

### Entry point

```python
AgentSimulator.tick_economy(
    region_input_batch: PyRecordBatch,
    trade_route_batch: PyRecordBatch,
    season_id: int,
    is_winter: bool,
    trade_friction: float,
) -> tuple[
    PyRecordBatch,  # region_result_batch
    PyRecordBatch,  # civ_result_batch
    PyRecordBatch,  # observability_batch
    PyRecordBatch,  # upstream_sources_batch
    PyRecordBatch,  # conservation_batch
]
```

Lock this to the M54a FFI style:
- batch payloads cross the boundary as explicit `PyRecordBatch` values
- per-turn scalar context crosses as primitive method arguments, not an `economy_context` wrapper object or one-row batch
- config is set separately through a dedicated `set_economy_config(...)` method, matching M54a's `set_ecology_config(...)`
- Python unpacks the return tuple in the fixed order above

### Input family (Python → Rust)

| Batch | Contents | Notes |
|-------|----------|-------|
| Region input | **World-state inputs only:** stockpile goods (fixed slots), terrain, `controller_civ`, storage_population (`Region.population`, for stockpile cap), resource_type_0, resource_effective_yield_0 (ecology-mutated, not static world-gen yield). | One row per region. Rust derives regional agent population / occupation counts and later per-civ merchant wealth / priest counts directly from the live simulator pool; Python should not round-trip those aggregates through FFI. `controller_civ` is required so fiscal civ rows stay aligned with current polity topology even on the turn immediately after a Phase 10 controller change and before the next full `set_region_state()` sync. `M54b` intentionally preserves the current single-slot production rule (`resource_types[0]` / `resource_effective_yields[0]`) rather than broadening economy scope. |
| Trade routes | Per decomposed boundary-pair route: origin_region_id, dest_region_id, is_river | Stable-sorted by `(origin_region_id, dest_region_id)` before crossing FFI. Python still expands civ-level `active_trade_routes` via `decompose_trade_routes()` before the FFI call; Rust does not own that expansion in M54b. Rust derives `is_coastal` from endpoint terrain and computes transport costs internally. |
| Scalar args | `season_id`, `is_winter`, `trade_friction` | Primitive method args, not a wrapper object. Fixed tuning constants belong in `EconomyConfig`, not repeated per row. |

### Output family (Rust → Python)

Authoritative state plus separate observability / diagnostic outputs.

All five return families are dedicated Arrow batches with centralized schema functions in `ffi.rs`. Do not collapse them into a single nested object or ad hoc Python dict.

| Batch | Contents | Notes |
|-------|----------|-------|
| Region result (authoritative) | Per-region: updated stockpile goods (fixed slots), farmer_income_modifier, food_sufficiency, merchant_margin, merchant_trade_income, trade_route_count | One row per region. `trade_route_count` mirrors decomposed boundary-pair count before flow/profitability pruning. |
| Civ result (authoritative) | Per-civ: treasury_tax, tithe_base, priest_tithe_share | One row per civ. In agent modes, Rust computes these directly from the live agent pool / economy pass state; Python does not pre-aggregate merchant wealth or priest counts for the FFI call. |
| Observability | **Fixed per-region:** imports_by_region (per-category), stockpile_levels (per-category), import_share, trade_dependent. **Separate flat batch:** upstream sources (`dest_region_id`, `source_ordinal`, `source_region_id`). | Observability remains a distinct output family from authoritative region/civ results. Python reconstructs `inbound_sources` from the flat source batch; `source_ordinal` preserves the final-pass insertion order expected by `classify_upstream_source()`. |
| Conservation (diagnostic) | 6 floats: production, transit_loss, consumption, storage_loss, cap_overflow, clamp_floor_loss | Single-row diagnostic batch for parity/debugging. Not a same-turn consumer dependency. |

### Fixed good slots

Goods normalized to a fixed ordered set for all FFI crossing. Current goods: grain, fish, salt, timber, ore, botanicals, precious, exotic (8 slots). The migration shape is explicit columns-per-good on both input and region-result batches. Principle: **no variable-length dicts cross FFI**.

### Helper ownership (locked)

M54b should now mirror M54a's helper layout explicitly:

- `chronicler-agents/src/ffi.rs`
  - add centralized schema helpers for each batch family:
    - `economy_region_input_schema()`
    - `economy_trade_route_schema()`
    - `economy_region_result_schema()`
    - `economy_civ_result_schema()`
    - `economy_observability_schema()`
    - `economy_upstream_sources_schema()`
    - `economy_conservation_schema()`
  - add result-batch builders adjacent to those schema helpers
  - add `set_economy_config(...)` and `tick_economy(...)` on `AgentSimulator`
- `src/chronicler/economy.py`
  - add dedicated economy FFI pack/unpack helpers
  - own reconstruction of the Python `EconomyResult` / `_economy_result`
  - own write-back of returned stockpile goods onto `Region.stockpile.goods`
- `src/chronicler/simulation.py`
  - continue to orchestrate call order, tracker/shock consumers, and accumulator routing
  - do not absorb schema packing logic

Do **not** extend `build_region_batch()` / `set_region_state()` for M54b. Those are the generic agent/ecology sync surfaces, not the dedicated economy FFI contract.

---

## 5. Parallelism & Determinism

### Execution phases within `tick_economy()`

```
Phase A — parallel per-region (production + demand extraction):
  - Production from resource_type + resource_effective_yield_0 + farmer_count
  - Demand from agent_population + soldier_count + wealthy_count
  - Merchant count carried forward for trade capacity in Phase B

Phase B — sequential, stable order (trade kernel):
  - Sort routes by (origin_region_id, dest_region_id)
  - Compute pre-trade prices from production / demand
  - Tatonnement loop (3 passes max, damping 0.2, convergence 0.01):
      - Compute margins from current prices
      - Allocate trade flow (log-dampened, margin-weighted, pro-rata)
      - Update prices with damping, clamp [0.5, 2.0]
      - Check convergence (max price delta < threshold)
  - Preserve final-pass category import/export summaries for prices, shock observability, and merchant formulas
  - Track ordered inbound sources from final-pass positive flows
  - Decompose final-pass category flows to per-good shipments
  - Apply per-route per-good transit decay BEFORE destination per-good aggregation
  - Materialize delivered per-good imports for the later stockpile lifecycle

Phase C — parallel per-region (stockpile lifecycle + signal derivation):
  - Accumulate stockpile (production − exports + decayed imports)
  - Derive food_sufficiency from pre-consumption stockpile, clamp [0.0, 2.0]
  - Consume from stockpile (proportional demand drawdown)
  - Apply storage decay (with salt preservation)
  - Apply stockpile cap
  - Derive signals: farmer_income_modifier, merchant_margin, merchant_trade_income
  - Derive observability: trade_dependent, import_share
  (merchant_margin / merchant_trade_income / import_share use Phase B's final-pass pre-transit category summaries; stockpile lifecycle uses delivered per-good imports)

Phase D — sequential, per-civ (fiscal + diagnostics):
  - Compute treasury_tax, tithe_base, priest_tithe_share
  - Assemble conservation summary
```

### Determinism guarantees

- Phase B route order is the determinism anchor. Same sorted route list → same float accumulation order → bit-identical prices and flows.
- Phases A and C are embarrassingly parallel per-region — no cross-region data dependencies.
- Phase D is small and sequential.
- No RNG consumed. Economy is fully deterministic from inputs.

### Implementation rollout

1. Ship with plain iterators everywhere (Phases A through D sequential).
2. Parity-test against Python `compute_economy()`.
3. After parity is green, add rayon on Phases A and C only.
4. Re-verify determinism after rayon introduction.
5. Phase B stays sequential permanently.

---

## 6. Invariants & Gates

### Hard invariants (must hold for merge)

1. **Conservation law.** `old_stockpile + production = new_stockpile + consumption + transit_loss + storage_loss + cap_overflow + clamp_floor_loss`. The `clamp_floor_loss` term accounts for the non-negative clamp in stockpile accumulation (`max(0.0)` when `production - exports + imports` produces a negative delta exceeding existing stockpile). This is negligible at equilibrium but can occur in edge cases. Both Rust inline summary and Python independent validation must pass.

2. **Determinism (Rust-to-Rust).** Same seed + same inputs → bit-identical outputs across runs. No tolerance. Route sort order is the anchor.

3. **Parity (Rust-to-Python).** Rust output matches Python `compute_economy()` output within float tolerance for shared seeds. Tolerance applies here (cross-language float differences), not to determinism.

4. **`--agents=off` compatibility / scope freeze.** M54b does **not** change the current runtime behavior: the Rust economy path runs only when an agent-backed snapshot exists, and aggregate-mode simulation remains correct with economy absent. Unit-level `agent_mode=False` economy behavior remains part of the Python oracle/test surface, but enabling same-turn economy in aggregate runs is out of scope for this migration.

5. **`food_sufficiency` from pre-consumption stockpile.** Not single-turn production. Clamped [0.0, 2.0]. M43a Decision 9.

6. **`trade_dependent` definition.** `food_imports / max(food_demand, 0.1)`, threshold 0.6. Not stockpile-based.

7. **Raider modifier semantics.** Max adjacent enemy food stockpile (not sum). Reads written-back `Region.stockpile.goods`. `_economy_result` is presence gate only.

8. **`world._economy_result` is transient.** Overwritten each turn. 2-turn test from M43b must pass.

9. **Same-turn signal availability.** All region/civ signals available before `AgentBridge.tick()` builds batches.

10. **Fixed good slot ordering.** FFI uses a fixed ordered set. No variable-length dicts cross the boundary.

11. **Transit decay ordering.** Per-route, per-good, before destination aggregation. Phase B responsibility, not Phase C.

12. **Supply shock actor ordering.** Affected civ first, upstream civ second. Stays Python-side but depends on correct Rust-returned observability.

13. **Single-slot production semantics.** Production remains keyed to `resource_types[0]` / `resource_effective_yields[0]`, matching the live Python economy path. Multi-slot production is a separate future milestone, not an M54b side effect.

14. **Agent-derived counts stay Rust-side.** `tick_economy()` derives per-region agent population / occupation counts and per-civ merchant wealth / priest counts from the live Rust pool. Python does not round-trip those aggregates through FFI.

15. **Trade-route decomposition stays Python-side.** M54b passes stable-sorted region-pair routes into Rust; it does not migrate civ-pair expansion or `decompose_trade_routes()` ownership into the simulator.

16. **`trade_route_count` semantics.** The value equals decomposed boundary-pair count per origin region before zero-flow or profitability filtering, matching the live `boundary_pair_counts` path.

17. **Import observability timing.** `imports_by_region` and `import_share` are derived from final-pass category route allocations before per-good transit decay, matching current M43b trade-dependency and shock semantics.

18. **Stockpile observability timing.** `stockpile_levels` aggregate written-back per-good stockpiles by category after the full stockpile lifecycle: accumulate -> consume -> storage decay -> cap.

19. **Merchant signal formulas.** `merchant_margin` is the normalized average positive post-trade price delta across outgoing routes, while `merchant_trade_income` is pre-decay route flow × post-trade margin arbitrage per merchant. Preserve the live intentional mismatch.

20. **Dedicated economy builders.** M54b adds dedicated economy batch pack/unpack helpers; it does not reuse `build_region_batch()` / `set_region_state()` or overload the ecology/agent full-sync contract.

### Merge gates (200-seed validation)

- **Migration gate (parity):** Rust economy output matches Python `compute_economy()` within float tolerance for 200 seeds.
- **Runtime gate (determinism):** Same seed produces bit-identical Rust output across 3 runs.
- **Conservation gate:** Passes on all 200 seeds (both Rust inline and Python independent).
- **Regression gate:** Satisfaction, extinction, economy health metrics within acceptable range of pre-M54b baseline.

### Soft invariants (should hold; investigate if violated)

- Tatonnement converges within 3 passes for >95% of turns across 200 seeds. If not converged, behavior matches Python's capped 3-pass result.
- Storage decay with salt preservation produces same relative ordering as Python path.
- `inbound_sources` upstream attribution matches Python path exactly.

---

## 7. Conservation Strategy

**Production path:** Rust computes inline conservation totals and returns a small summary (6 floats: production, transit_loss, consumption, storage_loss, cap_overflow, clamp_floor_loss). Cheap — the data is already in hand during the economy pass.

**Validation path:** Python independently verifies conservation from a richer debug/sidecar export or shadow recompute. This is the genuinely independent check that catches translation bugs.

**Merge gate:** Both the Rust inline balance and the Python validation check must pass during parity/200-seed validation.

**Design principle:** Conservation is validation infrastructure first, gameplay state second. The inline Rust summary is runtime accounting. The independent Python verifier is a gate, not a same-turn production dependency.

---

## 8. What Is Locked After M54a

### Locked by this spec

- Scope boundary and non-goals (Section 1)
- State classification: persistent / analytics / transient (Section 2)
- Migration boundary: Rust economic state machine / Python analytics + consumers
- Consumer map and call-sequence constraints (Section 3)
- FFI contract shape: authoritative batches plus separate observability/diagnostic outputs, fixed good slots, Rust-side agent-count derivation, Python-side route decomposition (Section 4)
- Parallelism strategy: sequential kernel, parallel region shell (Section 5)
- Stockpile ownership: Python durable, Rust per-turn (Section 2)
- All hard invariants and merge gates (Section 6)
- Conservation split: inline Rust + independent Python validation (Section 7)
- `_economy_result` remains the canonical Python transient handoff object for the bridge and later Python consumers
- Rust derives transport costs; Python does not pre-compute them for FFI
- Rust derives regional occupation counts / demand population directly from the live pool
- Rust computes agent-mode fiscal outputs directly from simulator state
- Python still owns civ-route -> region-route decomposition before FFI
- `trade_route_count`, `imports_by_region`, `stockpile_levels`, and merchant-signal timing semantics are locked to the current Python path
- `--agents=off` runtime behavior does not expand in M54b
- Production remains single-slot (`resource_types[0]` / `resource_effective_yields[0]`)
- Required batch split and assembly order in Section 9

### Principles locked for the full spec

- Economy tuning constants pass through an `EconomyConfig` struct (matching M54a's `EcologyConfig` pattern), not compiled as Rust module constants.

### Locked by the landed M54a pattern

- `tick_economy()` uses direct `PyRecordBatch` inputs/outputs plus primitive scalar args, not a wrapper payload object
- `ffi.rs` owns centralized schema functions and batch builders for each economy batch family
- simulator config follows the M54a pattern: dedicated `set_economy_config(...)` setter, not per-turn config batches
- Python owns dedicated economy pack/unpack helpers rather than extending `build_region_batch()`
- `simulation.py` keeps orchestration and consumer ordering but not Arrow schema details

### Remaining implementation choices (not semantic open questions)

- Optional debug payload shape for `region_goods`, if retained beyond parity/validation
- Rayon introduction timing and which phases get parallel iterators first
- Exact integer widths may still be tuned during implementation if tests or scale data show a clear need, but any deviation from Section 9 should be intentional and reflected in the spec/plan rather than improvised in code review.

---

## 9. Schema Appendix (Implementation Contract)

This appendix is now the implementation contract for execution planning. If implementation deviates from it, the plan or PR should explain why and update the spec rather than inventing a parallel contract in code.

### 9.1 Required batch set

- `region_input_batch`: world-state inputs only, keyed by `region_id`
- `trade_route_batch`: decomposed boundary-pair routes, stable row order
- `region_result_batch`: authoritative per-region write-back plus same-turn bridge signals
- `civ_result_batch`: authoritative per-civ fiscal outputs
- `observability_batch`: fixed per-region analytics / shock fields
- `upstream_sources_batch`: ordered flat source mapping for `inbound_sources`
- `conservation_batch`: single-row diagnostics

### 9.2 Region input columns

| Column | Meaning | Notes |
|-------|---------|-------|
| `region_id` | Index into `world.regions` | Python maps results back to names / models after return |
| `terrain` | Terrain enum / id | Used with route endpoints to derive transport cost |
| `storage_population` | `Region.population` | Used only for stockpile cap; do not reuse as demand population |
| `resource_type_0` | Primary resource slot | Single-slot production remains authoritative |
| `resource_effective_yield_0` | Current ecology-mutated yield | Use effective, not base, yield |
| `stockpile_grain` ... `stockpile_exotic` | Durable per-good stockpiles | Explicit columns are the migration shape |

Rust should derive the following internally from the live agent pool instead of receiving them from Python: `agent_population`, `farmer_count`, `soldier_count`, `merchant_count`, `wealthy_count`, per-civ merchant wealth, and per-civ priest count.

### 9.3 Trade route batch

| Column | Meaning | Notes |
|-------|---------|-------|
| `origin_region_id` | Source region | |
| `dest_region_id` | Destination region | |
| `is_river` | River discount applies | `is_coastal` is derived from endpoint terrain inside Rust |

Python should continue to expand civ-level `active_trade_routes` into stable-sorted boundary-pair routes before the FFI call. Batch row order should already be `(origin_region_id, dest_region_id)` sorted when Rust receives it.

### 9.4 Region result batch

| Column | Meaning | Notes |
|-------|---------|-------|
| `region_id` | Result key | |
| `stockpile_grain` ... `stockpile_exotic` | Post-lifecycle per-good stockpiles | Python writes these back to `Region.stockpile.goods` immediately |
| `farmer_income_modifier` | Farmer income signal | Derived from post-trade category supply vs demand |
| `food_sufficiency` | Food sufficiency signal | Computed from pre-consumption stockpile after accumulation |
| `merchant_margin` | Merchant satisfaction signal | Normalized average positive post-trade price delta |
| `merchant_trade_income` | Merchant wealth signal | Pre-decay route flow × post-trade margin arbitrage per merchant |
| `trade_route_count` | Boundary-pair route count | Count before flow / profitability pruning |

### 9.5 Civ result batch

| Column | Meaning | Notes |
|-------|---------|-------|
| `civ_id` | Civilization index | |
| `treasury_tax` | Tax amount routed through `StatAccumulator` | Derived from merchant wealth in Rust |
| `tithe_base` | Merchant-wealth tithe base | Consumed later by `tick_factions()` |
| `priest_tithe_share` | Per-priest income share | Feeds same-turn bridge signals |

### 9.6 Observability batch

| Column | Meaning | Notes |
|-------|---------|-------|
| `region_id` | Result key | |
| `imports_food` / `imports_raw_material` / `imports_luxury` | Final-pass category imports | Pre-transit-decay, matching current M43b semantics |
| `stockpile_food` / `stockpile_raw_material` / `stockpile_luxury` | Category stockpile totals | Post-consumption / post-decay / post-cap aggregates |
| `import_share` | `food_imports / max(food_demand, 0.1)` | Uses `imports_food` above |
| `trade_dependent` | `import_share > 0.6` | Boolean mirror of live threshold |

### 9.7 Upstream sources batch

| Column | Meaning | Notes |
|-------|---------|-------|
| `dest_region_id` | Importing region | |
| `source_ordinal` | Stable source order for this dest | Preserves final-pass insertion order |
| `source_region_id` | Unique upstream source region | Emit once per positive-flow source |

Python reconstructs `EconomyResult.inbound_sources[dest_name]` by grouping on `dest_region_id`, sorting by `source_ordinal`, then mapping region ids back to names. This keeps `classify_upstream_source()` behavior stable without forcing nested variable-length payloads across FFI.

### 9.8 Conservation batch

Single row, 6 fields:

- `production`
- `transit_loss`
- `consumption`
- `storage_loss`
- `cap_overflow`
- `clamp_floor_loss`

This is diagnostic output, not same-turn gameplay state.

### 9.9 Python assembly order

1. Build decomposed, stable-sorted region-pair trade routes from `active_trade_routes`, including `is_river`.
2. Pack `region_input_batch` from world-state only using dedicated economy helpers in `economy.py`. Do not precompute agent counts, regional demand population, merchant wealth, or priest counts in Python.
3. Pack `trade_route_batch` with the dedicated economy helper; do not route this through `build_region_batch()`.
4. Call `AgentSimulator.tick_economy(...)` with the two batches plus primitive scalar args (`season_id`, `is_winter`, `trade_friction`).
5. Unpack the fixed return tuple in order: region result, civ result, observability, upstream sources, conservation.
6. Immediately write returned stockpile goods back onto `Region.stockpile.goods`.
7. Reconstruct a fresh Python `EconomyResult` / `_economy_result` from `region_result_batch`, `civ_result_batch`, `observability_batch`, and `upstream_sources_batch`.
8. Feed `EconomyTracker`, `detect_supply_shocks()`, and later consumers from that reconstructed transient object.
9. Route `treasury_tax` through the accumulator, stash `_economy_result`, and let `AgentBridge` continue reading same-turn signals from it.
10. Keep `region_goods` and richer per-route debug payloads out of the production FFI surface unless parity tooling explicitly needs them.

---

## 10. Oracle Sources

Existing test suites and specs that encode the economy decisions M54b must preserve:

- `tests/test_economy.py` — core economy tests (42 tests)
- `tests/test_economy_m43a.py` — transport, perishability, stockpile tests (48 tests)
- `tests/test_economy_m43b.py` — shock detection, trade dependency, raider tests (36 tests)
- `docs/superpowers/specs/2026-03-17-m43a-transport-perishability-stockpiles-design.md` — M43a design decisions
- `docs/superpowers/specs/2026-03-17-m43b-shock-detection-trade-dependency-design.md` — M43b design decisions
- `src/chronicler/economy.py` — reference implementation (1,068 lines)
