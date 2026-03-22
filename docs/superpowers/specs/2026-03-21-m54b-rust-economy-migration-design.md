# M54b: Rust Economy Migration — Pre-Spec

> **Status:** Design-ahead (pre-spec). Locks scope, invariants, and open questions. Full implementation spec follows after M54a proves the migration contract.
>
> **Date:** 2026-03-21
>
> **Depends on:** M54a (Rust Ecology Migration) — establishes Arrow-batch-in / Arrow-batch-out pattern, shared FFI helpers, and bridge conventions.

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
| Civ signals (`priest_tithe_share`, `treasury_tax`, `tithe_base`) | Rust return batch | Feed bridge + accumulator. Note: only `treasury_tax` is currently routed through `StatAccumulator`; `tithe_base` is returned and stored but not an accumulator effect. |
| Consumer observability (`imports_by_region`, `inbound_sources`, `stockpile_levels`, `import_share`, `trade_dependent`) | Rust return batch | Feed EconomyTracker, shock detection, narration |
| `region_goods` (per-good production/imports/exports/prices) | Unresolved | May become sidecar-only, validation-mode-only, or compact observability. Pre-spec does not promise it survives as a production return payload. |
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

Whether these read from a cached Rust return batch or from `_economy_result` is a full-spec decision.

### Later-phase Python consumers

| Consumer | Reads | Phase |
|----------|-------|-------|
| `action_engine.py` raider modifier | Written-back `Region.stockpile.goods` + `_economy_result` as presence gate | Phase 8 |
| `narrative.py` context builders | `trade_dependent`, supply shocks (from Events) | Narration |

Phase 8 consumes a mix of durable (stockpiles) and transient (economy result metadata) economy outputs.

---

## 4. FFI Contract (Conceptual)

This section locks the shape, not exact schemas — those wait for M54a.

### Entry point

```
AgentSimulator.tick_economy(region_input_batch, trade_route_batch, economy_context)
    -> (region_result_batch, civ_result_batch, observability_batch)
```

### Input family (Python → Rust)

| Batch | Contents | Notes |
|-------|----------|-------|
| Region input | **World-state inputs:** stockpile goods (fixed slots), terrain, resource_type, resource_yield, controller_civ. **Agent-derived counts:** population, farmer_count, soldier_count, merchant_count, wealthy_count, scholar_count, priest_count, ecology state. | One row per region. Agent-derived vs world-state distinction matters for how the batch is built. |
| Trade routes | Per-route: origin_region_id, dest_region_id, is_river, is_coastal | Stable-sorted by (origin, dest) before crossing FFI |
| Economy context | Current season (winter bool), friction_multiplier, tuning multipliers | Small scalar payload. Not "climate" in the Phase 1 sense. |

### Output family (Rust → Python)

Three-way split: authoritative state / consumer observability / diagnostics.

| Batch | Contents | Notes |
|-------|----------|-------|
| Region result (authoritative) | Per-region: updated stockpile goods (fixed slots), farmer_income_modifier, food_sufficiency, merchant_margin, merchant_trade_income, trade_route_count | One row per region |
| Civ result (authoritative) | Per-civ: treasury_tax, tithe_base, priest_tithe_share | One row per civ |
| Observability | **Fixed per-region:** imports_by_region (per-category), stockpile_levels (per-category), import_share, trade_dependent. **Variable-length:** inbound_sources (route/source mapping for upstream attribution). | Fixed observability may merge into region result; inbound_sources may need a sub-batch. Full spec decides. |
| Conservation (diagnostic) | 5 floats: production, transit_loss, consumption, storage_loss, cap_overflow | Returned as metadata or small batch. Not a same-turn consumer dependency. |

### Fixed good slots

Goods normalized to a fixed ordered set for all FFI crossing. Current goods: grain, fish, salt, timber, ore, botanicals, precious, exotic (8 slots). Exact representation (columns-per-good vs nested array) is a full-spec decision. Principle: **no variable-length dicts cross FFI**.

---

## 5. Parallelism & Determinism

### Execution phases within `tick_economy()`

```
Phase A — parallel per-region (production + demand extraction):
  - Production from resource_type + resource_yield + farmer_count
  - Demand from population + soldier_count + wealthy_count
  - Merchant count carried forward for trade capacity in Phase B

Phase B — sequential, stable order (trade kernel):
  - Sort routes by (origin_region_id, dest_region_id)
  - Compute pre-trade prices from production / demand
  - Tatonnement loop (3 passes max, damping 0.2, convergence 0.01):
      - Compute margins from current prices
      - Allocate trade flow (log-dampened, margin-weighted, pro-rata)
      - Apply per-route per-good transit decay BEFORE destination aggregation
      - Update prices with damping, clamp [0.5, 2.0]
      - Check convergence (max price delta < threshold)
  - Materialize decayed per-region import aggregates and trade summaries

Phase C — parallel per-region (stockpile lifecycle + signal derivation):
  - Accumulate stockpile (production − exports + decayed imports)
  - Derive food_sufficiency from pre-consumption stockpile, clamp [0.0, 2.0]
  - Consume from stockpile (proportional demand drawdown)
  - Apply storage decay (with salt preservation)
  - Apply stockpile cap
  - Derive signals: farmer_income_modifier, merchant_margin, merchant_trade_income
  - Derive observability: trade_dependent, import_share
  (merchant_margin / merchant_trade_income assume Phase B route summaries are stable)

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

1. **Conservation law.** `old_stockpile + production = new_stockpile + consumption + transit_loss + storage_loss + cap_overflow`. Both Rust inline summary and Python independent validation must pass.

2. **Determinism (Rust-to-Rust).** Same seed + same inputs → bit-identical outputs across runs. No tolerance. Route sort order is the anchor.

3. **Parity (Rust-to-Python).** Rust output matches Python `compute_economy()` output within float tolerance for shared seeds. Tolerance applies here (cross-language float differences), not to determinism.

4. **`--agents=off` behavioral compatibility.** Aggregate mode produces correct economy results. Implementation path is a full-spec decision; output correctness is the gate.

5. **`food_sufficiency` from pre-consumption stockpile.** Not single-turn production. Clamped [0.0, 2.0]. M43a Decision 9.

6. **`trade_dependent` definition.** `food_imports / max(food_demand, 0.1)`, threshold 0.6. Not stockpile-based.

7. **Raider modifier semantics.** Max adjacent enemy food stockpile (not sum). Reads written-back `Region.stockpile.goods`. `_economy_result` is presence gate only.

8. **`world._economy_result` is transient.** Overwritten each turn. 2-turn test from M43b must pass.

9. **Same-turn signal availability.** All region/civ signals available before `AgentBridge.tick()` builds batches.

10. **Fixed good slot ordering.** FFI uses a fixed ordered set. No variable-length dicts cross the boundary.

11. **Transit decay ordering.** Per-route, per-good, before destination aggregation. Phase B responsibility, not Phase C.

12. **Supply shock actor ordering.** Affected civ first, upstream civ second. Stays Python-side but depends on correct Rust-returned observability.

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

**Production path:** Rust computes inline conservation totals and returns a small summary (5 floats). Cheap — the data is already in hand during the economy pass.

**Validation path:** Python independently verifies conservation from a richer debug/sidecar export or shadow recompute. This is the genuinely independent check that catches translation bugs.

**Merge gate:** Both the Rust inline balance and the Python validation check must pass during parity/200-seed validation.

**Design principle:** Conservation is validation infrastructure first, gameplay state second. The inline Rust summary is runtime accounting. The independent Python verifier is a gate, not a same-turn production dependency.

---

## 8. What Is Locked vs What Waits for M54a

### Locked by this pre-spec

- Scope boundary and non-goals (Section 1)
- State classification: persistent / analytics / transient (Section 2)
- Migration boundary: Rust economic state machine / Python analytics + consumers
- Consumer map and call-sequence constraints (Section 3)
- FFI contract shape: three-way output, fixed good slots (Section 4)
- Parallelism strategy: sequential kernel, parallel region shell (Section 5)
- Stockpile ownership: Python durable, Rust per-turn (Section 2)
- All hard invariants and merge gates (Section 6)
- Conservation split: inline Rust + independent Python validation (Section 7)

### Deferred to full spec (after M54a lands)

- Exact Arrow schemas (column names, types, nesting)
- `tick_economy()` method signature details (how `economy_context` is passed)
- Whether observability merges into region result batch or stays separate
- Whether conservation rides on the result tuple or a diagnostic sidecar
- `inbound_sources` representation (flat batch, sub-batch, or variable-length payload)
- `build_region_batch()` wiring: reads from Rust return cache or from `_economy_result`
- Shared FFI helper patterns (`ffi.rs` batch builders, `agent_bridge.py` pack/unpack)
- `--agents=off` execution path: Python, Rust, or switchable
- `region_goods` fate: production payload, sidecar-only, or dropped
- Rayon introduction timing and which phases get parallel iterators first

### What unlocks the full spec

M54a must demonstrate:
1. A working Arrow-batch-in / Arrow-batch-out phase migration with parity
2. A concrete bridge pack/unpack pattern in `agent_bridge.py`
3. Shared FFI helpers in `ffi.rs` (batch builders, schema definitions)
4. A determinism harness shape that M54b can inherit

Once these are proven in M54a, the full M54b spec inherits the conventions and resolves all deferred items.

---

## 9. Oracle Sources

Existing test suites and specs that encode the economy decisions M54b must preserve:

- `tests/test_economy.py` — core economy tests (42 tests)
- `tests/test_economy_m43a.py` — transport, perishability, stockpile tests (48 tests)
- `tests/test_economy_m43b.py` — shock detection, trade dependency, raider tests (36 tests)
- `docs/superpowers/specs/2026-03-17-m43a-transport-perishability-stockpiles-design.md` — M43a design decisions
- `docs/superpowers/specs/2026-03-17-m43b-shock-detection-trade-dependency-design.md` — M43b design decisions
- `src/chronicler/economy.py` — reference implementation (1,068 lines)
