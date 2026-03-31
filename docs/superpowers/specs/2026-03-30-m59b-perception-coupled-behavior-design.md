# M59b: Perception-Coupled Behavior — Design Spec

> Date: 2026-03-30
> Status: Approved
> Depends on: M59a (merged at `f4df802`)
> Baseline: `main` at M59a merge head

---

## Goal

Let agents act on propagated information. Merchants plan routes from learned trade opportunities instead of scanning all destinations. Migrants avoid destinations they've heard are threatened. Stale or partially wrong packets still influence decisions — that's the point.

**Gate:** Cross-region awareness measurably changes behavior without making the sim omniscient again.

---

## Scope

### Ships in M59b

1. **Merchant route planning** — `trade_opportunity` packets gate cross-region destination candidates. Packet gating applies when usable nonlocal trade packets exist, with counted oracle fallback only for the empty usable set.
2. **Threat-aware migration** — `threat_warning` packets penalize adjacent migration targets. No migrate-urgency effect in M59b.

### Deferred

- **Loyalty coupling** — requires `source_civ` on packets; deliberate layout expansion belongs in a future milestone.
- **Religious signal consumers** — `religious_signal` remains producer-only; a real consumer belongs in a religion-focused milestone with proper semantics (pilgrimage pull, distant revival pressure, sect-based destination preference).
- **Packet layout expansion** — no new fields (`source_civ`, propagation channel, sender identity) added in M59b.
- **Political rumor packets** — not yet defined.
- **Viewer/bundle knowledge visualization** — out of scope.

### Unchanged

- `--agents=off` path produces identical output.
- Legacy `known_regions` / M24 civ-level perception remains parallel.
- Own-region perception remains immediate — packets are for cross-region awareness only.

---

## Merchant Route Planning

### Current state

`merchant.rs::evaluate_route()` scans all reachable destinations using live `merchant_route_margin` from `RegionState`. Merchants are packet producers only (M59a).

### M59b contract

**1. Local trade observation**

Broaden merchant direct observation: merchants in a region refresh a `trade_opportunity` packet from their current region's live truth (Rust-local `RegionState`), using the existing trade threshold from `knowledge.rs`. This supplements (does not replace) the existing arrival-based refresh from M59a. Merchant-only — no other occupation produces local trade packets.

**2. Packet-gated destination selection**

When a merchant has ≥1 usable nonlocal `trade_opportunity` packet, only packet-known destinations are candidates. The merchant does **not** read live `merchant_route_margin` for unseen regions.

**3. "Usable" definition**

A nonlocal `trade_opportunity` packet is usable if all three conditions hold:

- `pkt_intensity > 0` (not fully decayed)
- `source_region ≠ current_region` (nonlocal)
- `source_region` is currently reachable in the route graph from the merchant's origin

Packets pointing at unreachable destinations (blocked by war, embargo, suspension) do not count toward the usable set and do not suppress bootstrap.

**4. Destination scoring**

- **Origin attractiveness:** live current-region truth (immediate, as always).
- **Destination attractiveness:** `pkt_intensity as f32 / 255.0` directly.
- **No second decay layer.** Consumer scoring uses current `pkt_intensity` directly. The M59a substrate already decays intensity per turn and attenuates per hop — M59b does not re-apply age or hop penalties.
- **Route topology:** remains perfect-known. The merchant knows *how* to get there; the packet tells them *whether it's worth going*.
- **Tie-breaks:** existing deterministic merchant planning logic.

**5. Bootstrap fallback**

Bootstrap triggers only when the usable packet-gated set is empty after nonlocal + reachability filtering. The merchant falls back to the current oracle planner (full destination scan with live margins). The fallback is counted via diagnostics. This ensures no trade deadlock on early turns or in packet-sparse regions.

---

## Threat-Aware Migration

### Current state

`behavior.rs` scores adjacent migration destinations from live `RegionState` and region aggregates. Nothing reads packet slots.

### M59b contract

**1. Scope**

Threat packets affect migration target selection only. No migrate-urgency effect in M59b.

**2. Penalty application**

When an agent evaluates adjacent regions for migration, any held `threat_warning` packet whose `source_region` matches that adjacent candidate applies a penalty:

```
penalty = MAX_THREAT_PENALTY × (pkt_intensity as f32 / 255.0)
```

Subtracted from the candidate's attractiveness score. Applied inside adjacent-target scoring, before the final comparison against `own_score`. Works naturally with the existing `migration_opportunity = (best_adj_score - own_score).max(0.0)` logic.

**3. Multiple packet rule**

If multiple threat packets point at the same candidate region, take the strongest penalty only. No stacking.

**4. Adjacency constraint**

Only adjacent candidate regions are affected. Non-adjacent threat packets are ignored for migration purposes.

**5. Own-region exclusion**

Threat packets sourced from the agent's own region are not applied here. Own-region perception remains immediate through live `RegionState`.

**6. Constant**

`MAX_THREAT_PENALTY`: tunable constant. Initial value: **0.20**.

---

## Diagnostics

### Surface

All new counters extend the existing `KnowledgeStats` struct in `knowledge.rs`. They flow through the same inline normalization block in `agent_bridge.py` into bundle metadata. No new metadata family.

### New counters (4)

| Counter | Incremented when | Semantics |
|---------|-----------------|-----------|
| `merchant_plans_packet_driven` | A merchant produces a successful route plan from the packet-gated destination set | Behavioral proof: packet-driven planning is happening |
| `merchant_plans_bootstrap` | A merchant produces a successful route plan via the oracle fallback | Bootstrap usage rate |
| `merchant_no_usable_packets` | A merchant enters the planning phase and finds zero usable nonlocal trade packets (after reachability filtering) | Coverage metric: how often bootstrap triggers |
| `migration_choices_changed_by_threat` | The final selected migration target (including "no move" / own region) differs from the baseline target before threat penalties | Behavioral proof: threat packets change decisions |

### Counter relationships

- `merchant_plans_packet_driven` and `merchant_plans_bootstrap` are **mutually exclusive** for a given planning attempt.
- `merchant_no_usable_packets` increments before the fallback attempt, so it can co-occur with `merchant_plans_bootstrap` but never with `merchant_plans_packet_driven`.

### Existing counters unchanged

All M59a counters (created, refresh, transmit, expire, evict, drop, per-type counts, live stats) remain as-is.

---

## Non-Negotiables

- Own-region perception remains immediate.
- M59a packet slots remain the single authoritative knowledge state.
- `--agents=off` remains unchanged.
- Deterministic same-seed replay.
- No randomized container iteration or order-sensitive packet consumption.
- No hidden return to global omniscience — if the bootstrap fallback fires, it is counted.
- No new Python→Rust transient signals.
- Legacy `known_regions` / M24 civ-level perception remains parallel.

---

## File Touch Map

### Rust

| File | Changes |
|------|---------|
| `chronicler-agents/src/knowledge.rs` | Packet query helpers for consumer code; local trade observation broadening; 4 new diagnostic counter fields on `KnowledgeStats` |
| `chronicler-agents/src/merchant.rs` | Replace destination oracle scan with packet-gated candidate selection; bootstrap fallback policy; diagnostic counter increments |
| `chronicler-agents/src/behavior.rs` | Threat penalty on adjacent migration targets; diagnostic counter increment |
| `chronicler-agents/src/ffi.rs` | Only if new diagnostic counters cross the bridge (likely: extend existing Arrow column set) |
| `chronicler-agents/tests/test_knowledge.rs` | Consumer-facing packet determinism and bootstrap tests |
| `chronicler-agents/tests/test_merchant.rs` | Route-planning regressions, packet-gated behavior |

### Python

| File | Changes |
|------|---------|
| `src/chronicler/agent_bridge.py` | Diagnostics normalization for new `knowledge_stats` fields |
| `src/chronicler/main.py` | Metadata inclusion if shape changes |
| `src/chronicler/analytics.py` | Extractor updates for new fields |
| `tests/test_m59a_knowledge.py` | Extended or renamed for M59b behavior assertions |
| `tests/test_merchant_mobility.py` | Packet-aware merchant behavior integration |
| `tests/test_agent_bridge.py` | Reset/metadata coverage for new diagnostics |

---

## Validation

### Rust unit tests

- Merchant with usable trade packets chooses only packet-known destinations (deterministic)
- Merchant with no usable packets hits bootstrap fallback (deterministic, counter increments)
- Merchant with packets pointing at unreachable destinations falls through to bootstrap
- `merchant_no_usable_packets` increments even when bootstrap still fails to produce a plan
- `merchant_plans_packet_driven` and `merchant_plans_bootstrap` are mutually exclusive for a given planning attempt
- Threat penalty changes best adjacent migration target (deterministic, counter increments)
- Threat penalty with multiple packets on same target uses strongest only
- Threat packet from agent's own region does not affect migration choice
- Non-adjacent threat packet does not affect migration choice
- Slot-order independence: same result regardless of which packet slot holds the data

### Rust integration tests

- Multi-turn smoke: no merchant deadlock (trade activity remains nonzero across 20+ turns)
- Packet-aware merchants measurably diverge from oracle-only route choices when packets exist
- Local trade observation seeds packet network (merchants in active trade regions produce packets without needing arrival)

### Python integration tests

- Bundle metadata includes all 4 new `knowledge_stats` counters, type-stable
- `--agents=off` emits no knowledge metadata (unchanged)
- Existing M59a counters remain present and stable

### Compatibility tests

- Own-region perception remains immediate
- Legacy `known_regions` / M24 surfaces unchanged
- Existing merchant mobility / economy accounting regressions remain green

### Determinism tests

- Same-seed same-process replay produces identical counter values
- No order sensitivity from packet-candidate iteration
