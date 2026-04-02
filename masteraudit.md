# Chronicler Master Audit — April 1, 2026

Two independent audits cross-referenced and verified against live code. Every finding below was confirmed by reading the actual source at the cited locations. False findings from either audit are listed at the bottom.

**Sources:**
- **Opus audit** (`opusaudit4-1-26.md`) — 22 agents, ~1,100 tool calls
- **Codex audit** — 12 high-severity findings, simulation-focused

**Verification:** 7 parallel agents checked every Opus finding; 3 parallel agents checked every Codex finding. All line references validated against current code.

---

## Severity Counts (verified)

| Tier | Count | Meaning |
|------|-------|---------|
| **BLOCKING** | 3 | Actively broken in hybrid mode right now |
| **CRITICAL** | 15 | Will crash, silently corrupt data, or violate documented invariants |
| **HIGH** | 35 | Logic errors, missing safety nets, significant test/doc gaps |
| **MEDIUM** | ~40 | Design inconsistencies, fragile patterns, performance |
| **STRATEGIC** | 3 | Architecture decisions affecting project trajectory |

---

## BLOCKING — Fix Immediately

### B-1. Stability recovery is dead code in hybrid mode
**Source:** Opus (FFI-1) | **Verified:** YES
**Files:** `simulation.py:526`, `agent_bridge.py:2120`, `pool.rs:760`

Stability recovery routes as `"keep"`, gets applied to `civ.stability` before the Rust tick, then `_write_back` unconditionally overwrites it with Rust's formula (`mean_sat * mean_loy * 100`). The recovery never takes effect.

---

### B-2. Persecution intensity formula is inverted
**Source:** Opus (Religion-3) | **Verified:** YES
**File:** `religion.py:525`

```python
intensity = 1.0 * (1.0 - minority_ratio) * (_gm(world, _KRI) if world else 1.0)
```

Tiny minorities (1%) get intensity 0.99; large minorities (40%) get 0.60. Backwards.

---

### B-3. Persecution satisfaction penalty constant defined but never used
**Source:** Opus (Religion-1) | **Verified:** YES
**File:** `religion.py:41`

`PERSECUTION_SAT_PENALTY = 0.15` is defined but never referenced. Rust uses `PERSECUTION_SAT_WEIGHT = 0.09` independently. The Python constant is orphaned dead code.

---

## CRITICAL — Fix Before Next Milestone

### C-1. Hybrid Phase 10 acc.add() work is effectively dropped
**Source:** Codex (Finding 2) | **Verified:** YES
**Files:** `simulation.py:1592`, `simulation.py:1636-1643`

The accumulator is flushed via `acc.apply_keep()` before Phase 10 (line 1592). Phase 10 then calls `acc.add()` for stability drains, cultural milestones, faction effects — but there is NO second flush after Phase 10. All Phase 10 accumulator mutations are silently lost in hybrid mode.

---

### C-2. Phase 10 misses same-turn events
**Source:** Codex (Finding 1) | **Verified:** YES
**Files:** `simulation.py:1147`, `simulation.py:1735`

Events from Phases 1-9 exist only in the local `turn_events` list. They aren't committed to `world.events_timeline` until line 1735, AFTER Phase 10 completes. Phase 10's `update_event_counts()`, `check_great_person_generation()`, and `tick_factions()` all read from the stale timeline, missing same-turn war/trade/expand/famine/build events.

---

### C-3. Famine creates population on the accumulator path
**Source:** Codex (Finding 3) | **Verified:** YES
**Files:** `ecology.py:125-152`

Source-side famine population loss routes through `acc.add(..., "guard")` — skipped in hybrid mode. Refugee additions to neighboring regions are direct mutations (`add_region_pop`). Net effect: hybrid mode gains population during famine without the matching loss. Conservation violation.

---

### C-4. "guard" accumulator category silently dropped
**Source:** Opus (C-2) | **Verified:** YES — 17 call sites found
**File:** `accumulator.py:111-124`

`apply_keep()` only handles `"keep"`. `to_shock_signals()` handles `"signal"` and `"guard-shock"`. `to_demand_signals()` handles `"guard-action"`. Pure `"guard"` mutations (17 call sites across ecology, emergence, politics, simulation) are recorded but never applied or routed. Silent data loss for population, military, economy mutations.

---

### C-5. KeyError crashes in dynasty checks
**Source:** Opus (C-3) | **Verified:** YES
**Files:** `dynasties.py:107, 125, 127`

Direct `gp_map[mid]` access without key guards. Contrasts with safe `.get()` pattern used elsewhere in the same file (lines 39-40, 146-148). Will KeyError if a dead agent is pruned before `check_extinctions` runs.

---

### C-6. Pandemic skips severity multiplier (M18 violation)
**Source:** Opus (C-4) | **Verified:** YES
**File:** `emergence.py:322, 326`

`tick_pandemic` applies `pop_loss = min(severity * 3, 12)` and `eco_loss = min(severity * 2, 8)` without `get_severity_multiplier()`. Every other negative stat change uses it per M18.

---

### C-7. Persecution penalty fires for BELIEF_NONE agents in Rust
**Source:** Opus (C-5) | **Verified:** YES
**File:** `satisfaction.rs:192-195`

The religious mismatch penalty (line 183) correctly guards both beliefs against `BELIEF_NONE`. The persecution penalty block has no such guard. Agents with `BELIEF_NONE` incorrectly receive persecution penalties.

---

### C-8. upsert_symmetric EvictSlot leaves rel_count stale
**Source:** Opus (C-6) | **Verified:** YES
**File:** `relationships.rs:250-252`

`commit_resolved` for `EvictSlot` writes the new bond via `write_rel()` but does NOT call `swap_remove_rel()`. The old relationship is lost without decrementing `rel_count`. Corrupts slot tracking over time.

---

### C-9. unwrap() in production PyO3 method — UB risk
**Source:** Opus (C-7) | **Verified:** YES
**File:** `ffi.rs:2278`

```rust
let world_seed = u64::from_le_bytes(self.master_seed[0..8].try_into().unwrap());
```

Panic across FFI boundary is undefined behavior. Should propagate via `PyResult`.

---

### C-10. Shadow mode uses wrong accumulator path
**Source:** Opus (C-8) | **Verified:** YES
**File:** `simulation.py:1592, 1605`

Hybrid uses `acc.apply_keep()` (only "keep" changes). Shadow/demographics-only uses `acc.apply()` (ALL changes). Shadow comparison is fundamentally unfair — different stat categories get applied.

---

### C-11. Bare `civ.regions[0]` without empty-guard
**Source:** Opus (C-9) | **Verified:** YES
**File:** `simulation.py:1281`

`_art_region = civ.capital_region or civ.regions[0]` — IndexError if regions is empty and capital_region is None.

---

### C-12. No accumulator routing for religion events
**Source:** Opus (C-10) | **Verified:** YES
**Files:** `religion.py:437-555`, `religion.py:558-619`

`compute_persecution()` and `compute_martyrdom_boosts()` mutate region state directly (`region.persecution_intensity = intensity`) without any `acc.add()` calls. Bypasses the accumulator system entirely.

---

### C-13. Arc summary mutates world state (LLM feedback loop)
**Source:** Opus (C-11) | **Verified:** YES
**File:** `narrative.py:1280`

`_update_arc_summary()` mutates `GreatPerson.arc_summary` in-place. Those objects are later serialized into the bundle via `world.model_dump_json()`. LLM narration content feeds back into persistent state, violating "LLM never decides."

---

### C-14. Satisfaction formula test comments reference old divisor
**Source:** Opus (C-12) | **Verified:** YES
**Files:** `satisfaction.rs:110`, `satisfaction.rs:484`

Formula divides by `200.0`. Test comment says `80/300 = 0.267`. Tests pass only because assertions use wide tolerances.

---

### C-15. TypeScript types drastically incomplete vs Python models
**Source:** Opus (C-13) | **Verified:** YES
**File:** `viewer/src/types.ts`

- Region: 7 fields in TS vs ~54 in Python (~46 missing)
- CivSnapshot: 12 fields in TS vs ~33 in Python (~21 missing)
- TurnSnapshot: 4 fields in TS vs ~28 in Python (~24 missing)

---

## HIGH — Prioritized Fixes

### Accumulator & Hybrid Mode

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-1 | Restoration stat mutations bypass accumulator — hybrid mode desync | Opus | politics.py | 1072-1077 |

### Economy & Trade

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-2 | Tithe extracted without food sufficiency check | Opus | economy.py | 1477-1481 |
| H-3 | Wealth conservation only tracks goods, not treasury flows | Opus | economy.py | 519-524 |
| H-4 | Zero-farmer regions produce amplified farmer income signals (capped at 3.0) | Opus | economy.py | 688-698 |
| H-5 | Non-adjacent NAVIGATION/RAILWAYS/federation routes pay treasury but bypass goods economy — decompose_trade_routes filters to adjacent only | Codex | resources.py:161, economy.py:595 | |
| H-6 | get_active_trade_routes() has side effects — appends capability events on query, re-fires during snapshot reads | Codex | resources.py:192, intelligence.py:29 | |

### Politics & Extinction

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-7 | Absorbed civ capital_region not cleared (3 code paths) — dangling reference | Opus | politics.py | 1322, 1396, 2413 |
| H-8 | Dead civs still participate in tribute, federation, movement, and cultural victory logic | Codex | politics.py:475, movements.py:84, culture.py:388 | |
| H-9 | Great persons not cleaned up on civ extinction — modifiers still apply | Opus | action_engine.py | 573-575 |
| H-10 | Dead-civ population floor of 1 in Python diverges from Rust zero-count | Opus | agent_bridge.py | 2115 |

### Relationships & Dynasties

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-11 | Hostage trapped forever if origin civ extinct — no cleanup | Opus | relationships.py | 379-382 |
| H-12 | Mentorship formation: no seniority tiebreaker for same-turn births | Opus | relationships.py | 119-157 |

### Religion

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-13 | Schisms can create zero-follower faiths (snapshot staleness risk) | Opus | religion.py | 678-747 |
| H-14 | `_persecuted_regions` accumulates forever without reset | Opus | simulation.py | 991-992 |

### Ecology

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-15 | Terrain transitions don't clamp ecology to TERRAIN_ECOLOGY_CAPS (e.g. sets forest=0.7 on plains with cap=0.40) | Opus | emergence.py | 704-717 |
| H-16 | No Python validation of Rust ecology write-back values | Opus | ecology.py | 211-254 |

### Tech & Focus

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-17 | Tech focus bonus removal undershoots baseline — applied with cap, removed without cap awareness | Codex | tech_focus.py:390-406, tech.py:126-140 | |

### Agent Bridge

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-18 | Gini lag resets to empty dict on exception instead of preserving prior values | Opus | agent_bridge.py | 969-973 |
| H-19 | Unprotected ROLE_MAP[role_id] KeyError in promotions | Opus | agent_bridge.py | 1397 |
| H-20 | `_conquered_this_turn` not cleared in AgentBridge.reset() (cleared in simulation.py only) | Opus | agent_bridge.py, simulation.py | |

### Simulation Logic

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-21 | Holy war weight bonus is additive (+=) while all others are multiplicative (*=) | Opus | action_engine.py | 920-933 |
| H-22 | Weight cap caps absolute weight value, not multiplier product — effective cap diverges from documented 2.5x | Opus | action_engine.py | 993-997 |

### Scenario

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-23 | Scenario overrides leave world state inconsistent — no population resync, capital_region repair, or ecology clamping | Codex | scenario.py | 321, 337, 376, 394 |

### CLI / Batch / Live

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-24 | --batch --parallel narrated runs silently fall back to _DummyClient, emitting bogus "DEVELOP" chronicles | Codex | batch.py | 64, 110 |
| H-25 | Live batch_load_bundle doesn't populate _init_data — narrate_range fails on loaded bundles | Codex | live.py:353-385, useLiveConnection.ts:247 | |
| H-26 | Live narration dropped on client disconnect (exception swallowed) | Opus | live.py:457, useLiveConnection.ts:227 | |

### Faction / Succession

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-27 | Clergy alignment unreachable from leader traits — TRAIT_FACTION_MAP has no clergy mapping | Codex | factions.py | 40-49 |
| H-28 | Exile restoration overwrites incumbent leader in place | Codex | succession.py | 314-321 |

### Rust Performance

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-29 | O(n*m) CivSignals lookup in 3 hot loops (wealth, satisfaction, demographics) | Opus | tick.rs | 968, 1057, 1259 |
| H-30 | partition_by_region called 8x per tick (audit said 6, actual 8) | Opus | tick.rs | multiple |

### Rust Determinism

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-31 | HashMap iteration in wealth_tick — non-deterministic, should be BTreeMap | Opus | tick.rs | 1015 |
| H-32 | civ_data HashMap safe only because of post-sort — fragile pattern | Opus | behavior.rs | 273 |

### Documentation

| # | Finding | Source | File | Line(s) |
|---|---------|--------|------|---------|
| H-33 | `--agent-narrative` flag documented but doesn't exist in CLI | Opus | CLAUDE.md | line 111 |
| H-34 | Line counts 52-277% stale (Python: ~21K documented, ~32K actual; Rust: ~7K documented, ~26K actual) | Opus | CLAUDE.md | lines 4-7 |
| H-35 | `bundle_version` documented but never written to bundle metadata | Opus | CLAUDE.md, bundle.py | |

### Test Coverage

| # | Finding | Source | Verified |
|---|---------|--------|----------|
| H-36 | 2.5x combined weight cap — zero tests anywhere | Opus | YES |
| H-37 | Phases 4, 6, 7, 8 — no dedicated phase-function tests | Opus | YES |
| H-38 | culture_tick.rs / conversion_tick.rs — no external integration tests | Opus | YES |
| H-39 | demographics.rs — no external integration test | Opus | YES |
| H-40 | `--agents=off` bit-identical guarantee — no test verifies | Opus | YES |

---

## MEDIUM (selected — not exhaustive)

### Rust

| ID | Finding | File |
|----|---------|------|
| M-1 | shock_pen naming inversion — added not subtracted | satisfaction.rs:127 |
| M-2 | Magic numbers 0.08, 0.05, 0.10 not named constants | satisfaction.rs:118-123 |
| M-3 | SWITCH_OVERSUPPLY_THRESH comment says "2.0" but value is 1.0 | agent.rs:76 |
| M-4 | kill() doesn't zero fields — dead slots hold stale data | pool.rs:340 |
| M-5 | civ_id is UInt8 in some schemas, UInt16 in others | ffi.rs:95, 141 |
| M-6 | Good memories can zero out persecution/cultural penalties — no cap | satisfaction.rs:222 |
| M-7 | region_state_schema suppressed with #[allow(dead_code)] | ffi.rs:154 |
| M-8 | SPATIAL_DRIFT_STREAM_OFFSET registered but never consumed | agent.rs:112 |
| M-9 | alive_slots rebuilt 2x per tick (not 3 as audit claimed) | tick.rs:64, 752 |

### Viewer

| ID | Finding | File |
|----|---------|------|
| M-10 | Logic bug — missing closing brace in surface transitions | App.tsx:76-84 |
| M-11 | No error boundary — any component throw = white screen | App.tsx |
| M-12 | key={i} in event lists — React reconciliation bugs | EventLog.tsx:87, ChroniclePanel.tsx:44 |
| M-13 | TerritoryMap d3-force recalculates on every turn change | TerritoryMap.tsx:150-244 |
| M-14 | AppShell monolithic at 2,481 lines | AppShell.tsx |
| M-15 | No runtime validation for WebSocket JSON messages | useLiveConnection.ts:121 |

### Documentation

| ID | Finding | File |
|----|---------|------|
| M-16 | --narrator supports `gemini` mode, undocumented | CLAUDE.md |
| M-17 | M44 API narration described in future tense but is implemented | CLAUDE.md |
| M-18 | "Current Focus" section says M43b is next — stale | CLAUDE.md |

---

## STRATEGIC — Architecture Findings

### S-1. ffi.rs at ~5,000 lines is the highest-risk module
**Source:** Opus (Phoebe) | **Verified:** 4,983 lines confirmed.

Two simulator implementations, 60+ column parsers, all PyO3 bindings. Every new system adds code in 3+ locations. Split into schema definitions, batch conversion, AgentSimulator impl, EcologySimulator impl.

### S-2. Python critical path limits 9950X utilization ceiling
**Source:** Opus (Phoebe)

Phase 10 + settlement detection + economy post-processing all run single-threaded after the Rust tick. Continue M54-series migration.

### S-3. politics.py at 3,157 lines doing two jobs
**Source:** Opus (Phoebe) | **Verified:** 3,157 lines confirmed.

Game logic (1,600 lines) + FFI integration (1,400 lines). Split into `politics.py` + `politics_bridge.py`.

---

## Dead Code (verified)

| What | File | Status |
|------|------|--------|
| `household_effective_wealth_py()` | agent_bridge.py:2217 | Safe to delete |
| `social.rs` (entire file) | chronicler-agents/src/ | Deprecated M50a, still compiled |
| `social_graph` field | ffi.rs:1650 | Unused holdover in AgentSimulator |
| `PERSECUTION_SAT_PENALTY = 0.15` | religion.py:41 | Never referenced |
| `region_state_schema()` | ffi.rs:154 | Suppressed with #[allow(dead_code)] |
| 11 reserved RNG stream offsets | agent.rs | Registered but never consumed |

---

## Clean Bills of Health (from Opus, not contradicted by Codex)

| Area | Result |
|------|--------|
| Data model gotcha adherence | 9.8/10 — zero violations across codebase |
| RNG determinism | 17 unique stream offsets, airtight seed chain, same seed = same output |
| Faction weight pipeline | 2.5x cap correctly enforced through action engine |
| Design principles | "LLM narrates, never decides" — clean except C-13 |
| Bundle format | Simple, forward-compatible |
| Module cohesion | No circular dependencies |

---

## FALSE Findings (audit was wrong — rejected after verification)

| ID | Audit | Claim | Why False |
|----|-------|-------|-----------|
| Opus C-1 | Opus | att_idx/def_idx crash risk in resolve_war() | Variables assigned in first `if acc is not None` block (line 527-528), all later uses also inside `if acc is not None`. Always defined when used. |
| Opus H-12 | Opus | Arrow IPC file handle not in context manager | Code uses `with pa.OSFile(str(out_path), "wb") as f:` — properly wrapped. |
| Opus H-13 | Opus | LiveServer race condition on client disconnect | Protected by `async with client_lock:`. Proper cleanup. |
| Opus H-24 | Opus | "Phase 4 bit-identical" claim false when economy active | Economy only runs when agent_bridge is not None; agents=off doesn't create agent_bridge. Claim is valid. |
| Opus H-27 | Opus | Faith init before turn 0 | Faith properly initialized in world_gen before any turn runs. |
| Codex 11a | Codex | Faction influence can sum above 1.0 | `normalize_influence()` enforces floors and renormalizes to sum=1.0. Working correctly. |

---

## Partially Confirmed (nuanced)

| ID | Audit | Claim | Reality |
|----|-------|-------|---------|
| Opus C-14a | Opus | 0.40 penalty cap has zero tests | FALSE — Rust tests exist (`test_penalty_cap_clamps` in satisfaction.rs:339) |
| Opus C-14b | Opus | 2.5x weight cap has zero tests | CONFIRMED — no test found anywhere |
| Opus H-14 | Opus | Live narration silently dropped | Only on client disconnect (exception swallowed), not general operation |
| Opus H-16 (Rust) | Opus | partition_by_region called 6x | Actually 8 calls found — undercount |
| Opus H-17 | Opus | Schisms create zero-follower faiths | Risk exists but mitigated by minority-present guard in detect_schisms() |
| Opus H-2 (Rust) | Opus | alive_slots rebuilt 3x per tick | Only 2 rebuilds confirmed |

---

## Recommended Fix Ordering

### Phase 1: Blocking (hybrid mode broken)
1. B-1 — Stability write-back override
2. B-2 — Inverted persecution intensity
3. B-3 + C-7 — Wire persecution satisfaction correctly (dead Python constant + Rust BELIEF_NONE guard)

### Phase 2: Critical accumulator/ordering bugs
4. C-1 — Phase 10 acc.add() dropped (add second flush)
5. C-2 — Phase 10 stale events (commit events before Phase 10)
6. C-3 — Famine population conservation violation
7. C-4 — Guard category behavior definition (17 call sites affected)
8. C-10 — Shadow accumulator path mismatch
9. C-12 — Religion events accumulator routing

### Phase 3: Critical correctness
10. C-5 — Dynasty KeyError guards
11. C-6 — Pandemic severity multiplier (M18)
12. C-8 — EvictSlot rel_count corruption
13. C-9 — FFI unwrap safety
14. C-11 — Bare regions[0] guard
15. C-13 — Arc summary world state mutation

### Phase 4: High-priority logic fixes
16. H-5 — Non-adjacent routes goods economy gap
17. H-6 — Trade route query side effects
18. H-7 — Absorbed civ capital_region cleanup
19. H-8 — Dead civ participation cleanup
20. H-17 — Tech focus bonus undershoot
21. H-23 — Scenario state consistency
22. H-24 — Batch parallel narration guard
23. H-1 — Restoration accumulator routing

### Phase 5: Test coverage
24. H-36 — 2.5x weight cap test
25. H-37-40 — Phase function tests, Rust integration tests, bit-identical test

### Phase 6: Documentation
26. H-33-35 — CLAUDE.md fixes (stale flags, line counts, bundle_version)
27. M-16-18 — CLAUDE.md updates (gemini mode, M44 status, current focus)

### Phase 7: Architecture (next milestone window)
28. S-1 — Split ffi.rs
29. S-3 — Split politics.py
30. Dead code cleanup (social.rs, orphaned constants)

---

## Comprehensive Execution Plan

This section turns the verified audit into an execution-ready remediation plan. It covers every explicit finding ID listed in this document and is designed so one agent can drive the work end to end while still making safe use of parallel lanes when file ownership and dependency boundaries allow it.

### Success Criteria

- Every `BLOCKING`, `CRITICAL`, and `HIGH` finding is fixed or explicitly reclassified with proof.
- Every listed `MEDIUM` finding is either fixed in the same pass or moved into a dated follow-up artifact with an owner and a gate.
- `--agents=off` behavior remains preserved unless a documented invariant bug requires a deliberate change.
- Hybrid, shadow, and off-mode semantics are test-covered where the audit found drift.
- Full Python, Rust, and viewer validation gates pass, plus the milestone-scale before/after regression comparison.

### Guardrails

- Read `docs/superpowers/progress/phase-6-progress.md` before each substantial coding pass and update it after each substantial batch.
- Use `.venv\Scripts\python.exe` for Python commands, and rebuild the Rust extension with `maturin develop --release` after any Rust/FFI change before hybrid validation.
- Preserve the exact `ActionType` set, the M18 negative-stat rule, and the documented `2.5x` combined weight-cap semantics.
- Keep `phase_consequences(..., acc=None)` in aggregate mode unless a larger contract change is deliberately justified and parity-tested.
- Any new transient signal across the Python/Rust boundary must be cleared before the builder returns and must receive a multi-turn reset test.
- Bundle consumers must stay agnostic to whether stats came from aggregate or hybrid execution.
- Do not mix strategic refactors with critical correctness fixes in the same patch series.

### Execution Method

1. Reproduce the finding with a focused test or deterministic harness.
2. Fix the smallest coherent seam that resolves the whole issue cluster.
3. Add or tighten regression coverage before moving to the next cluster.
4. Run the local batch gate, then rerun the shared smoke gate.
5. Update `phase-6-progress.md` and this document's checklist/status notes.

### Shared Smoke Gate

Run this after every batch that touches simulation, bridge, Rust, live mode, bundle contracts, or viewer runtime behavior:

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_simulation.py tests/test_agent_bridge.py tests/test_religion.py tests/test_live.py tests/test_live_integration.py tests/test_bundle.py`
- `cd chronicler-agents && cargo test --quiet`
- `cd viewer && npm test`
- `cd viewer && npm run lint`
- `cd viewer && npm run build`

Final closeout additionally requires:

- `.\.venv\Scripts\python.exe -m pytest -q`
- `cd chronicler-agents && cargo nextest run`
- the current hybrid/off/shadow comparison harness
- the canonical 200-seed before/after comparison artifact

### Dependency and Parallelization Map

**Critical path**
- Batch A must land first because it defines the hybrid/accumulator/event contract that many later fixes depend on.
- Batch H is the closeout gate after the correctness batches are green.
- Batch I stays last; it is intentionally separated from correctness work.

**Parallel opportunities once Batch A is stable**
- Batch B and Batch C can run in parallel.
  Batch B owns religion/satisfaction/factions.
  Batch C owns dynasty, emergence, narrative, FFI safety, and bridge safety.
- Batch D and Batch E can run in parallel.
  Batch D owns economy/trade/scenario/live/batch/ecology contracts.
  Batch E owns politics/extinction/relationships/succession/action weights.
- Batch F and Batch G can run in parallel after the core correctness batches are green.
  Batch F is Rust hot-path/determinism work.
  Batch G is viewer/type/doc contract work.
- Parallel execution assumes disjoint write ownership for both code and tests.
  If two batches need the same test file or contract fixture, assign one owner and let the other batch land afterward or via an integration follow-up.

**Partial parallel work that can start early but should merge later**
- Batch G documentation updates can be drafted early, but the `viewer/src/types.ts` and bundle-contract portion should wait until Batch D settles runtime payload changes.
- Batch H test scaffolding can start during earlier batches, but the final gate run belongs at the end.
- Dead-code deletion from Batch I can be prepared in parallel, but should not merge until the full regression suite is green.

**Do not parallelize these pairs without tight coordination**
- Batch A with Batch B, because persecution routing/reset semantics are part of the accumulator contract.
- Batch A with Batch E, because weight-pipeline and extinction behavior both read the same Phase 10 / hybrid state.
- Batch D with Batch G on live-mode payload handling unless ownership is split cleanly between backend message shape and frontend consumption.

### Batch Overview

| Batch | Focus | Finding IDs | Can run in parallel with |
|------|-------|-------------|--------------------------|
| A | Hybrid pipeline + accumulator contract | B-1, C-1, C-2, C-3, C-4, C-10, C-12, H-1, H-14, H-20 | none |
| B | Religion + satisfaction correctness | B-2, B-3, C-7, H-13, H-27 | C |
| C | Core safety + data integrity | C-5, C-6, C-8, C-9, C-11, C-13, C-14, H-18, H-19 | B |
| D | Economy, trade, ecology, scenario, live/batch runtime | H-2, H-3, H-4, H-5, H-6, H-15, H-16, H-17, H-23, H-24, H-25, H-26 | E |
| E | Politics, extinction, relationships, succession, action weights | H-7, H-8, H-9, H-10, H-11, H-12, H-21, H-22, H-28 | D |
| F | Rust hot path, determinism, and medium Rust cleanup | H-29, H-30, H-31, H-32, M-1, M-2, M-3, M-4, M-5, M-6, M-7, M-8, M-9 | G |
| G | Viewer/type contract + documentation cleanup | C-15, H-33, H-34, H-35, M-10, M-11, M-12, M-13, M-14, M-15, M-16, M-17, M-18 | F |
| H | Test coverage and audit closeout gates | H-36, H-37, H-38, H-39, H-40 | prep can overlap earlier work; final run is last |
| I | Strategic refactors + dead-code removal | S-1, S-2, S-3, dead-code list | planning can overlap; merge last |

### Batch A: Hybrid Pipeline + Accumulator Contract

**Primary files**
- `src/chronicler/simulation.py`
- `src/chronicler/accumulator.py`
- `src/chronicler/ecology.py`
- `src/chronicler/religion.py`
- `src/chronicler/politics.py`
- `src/chronicler/agent_bridge.py`

**Plan**
- Define the intended meaning of `keep`, `guard`, `guard-action`, `guard-shock`, and `signal` in code comments and tests before changing routing.
- Fix B-1 and C-1 together by deciding which side owns same-turn stability recovery/drain in hybrid mode, then making that ownership explicit.
- Fix C-2 before any further Phase 10 work so same-turn events are visible to all Phase 10 readers.
- Fix C-3, C-4, and C-10 in one routing pass so hybrid and shadow no longer apply different change categories accidentally.
- Fix C-12, H-1, H-14, and H-20 in the same pass so religion/restoration/conquest transients obey the same lifecycle rules as other signals.

**Required tests**
- New regression proving Phase 10 accumulator changes take effect in hybrid mode.
- New regression proving Phase 10 sees same-turn war/trade/expand/famine/build events.
- New famine conservation regression in hybrid mode.
- New routing regression proving every accumulator category is either applied, converted, or rejected deliberately.
- New reset regression for `_persecuted_regions` and `_conquered_this_turn`.
- Shadow-mode parity regression covering the finalized routing semantics.

### Batch B: Religion + Satisfaction Correctness

**Primary files**
- `src/chronicler/religion.py`
- `chronicler-agents/src/satisfaction.rs`
- `src/chronicler/factions.py`

**Plan**
- Fix the persecution intensity formula so it scales in the intended direction.
- Decide whether `PERSECUTION_SAT_PENALTY` is real and wired or dead and removed; do not keep split-brain constants.
- Add the missing `BELIEF_NONE` guard to the Rust persecution penalty.
- Prevent schisms from producing zero-follower faiths under stale-order conditions.
- Make clergy alignment reachable from actual leader trait pathways, or replace the current mapping with an explicit clergy-input mechanism.

**Required tests**
- Monotonic persecution intensity regression across multiple minority ratios.
- Rust regression showing `BELIEF_NONE` agents do not receive persecution penalties.
- Schism regression proving no zero-follower faith can be created.
- Faction regression proving clergy alignment can be produced intentionally.

### Batch C: Core Safety + Data Integrity

**Primary files**
- `src/chronicler/dynasties.py`
- `src/chronicler/emergence.py`
- `src/chronicler/narrative.py`
- `src/chronicler/agent_bridge.py`
- `chronicler-agents/src/relationships.rs`
- `chronicler-agents/src/ffi.rs`

**Plan**
- Replace unsafe dynasty indexing with guarded lookups and define behavior when referenced agents are gone.
- Route pandemic losses through `get_severity_multiplier()` and add an M18 regression.
- Fix `EvictSlot` bookkeeping so relationship slot counts stay correct after replacement.
- Replace the production `unwrap()` across the FFI boundary with a `PyResult` error path.
- Guard empty-civ region access consistently, not just at the cited line.
- Stop arc summaries from mutating authoritative world state.
- Fix the stale satisfaction divisor comments while the relevant tests are open.
- Preserve prior Gini state and promotion safety when exceptions or unknown role IDs occur.

**Required tests**
- Dynasty regression with missing expected GPs.
- Pandemic severity regression.
- Rust relationship-slot replacement regression.
- FFI error-path regression for invalid seed bytes.
- Narrative regression proving LLM arc summaries do not persist into authoritative state.
- Agent-bridge regressions for Gini preservation and unknown role IDs.

### Batch D: Economy, Trade, Ecology, Scenario, Live/Batch Runtime

**Primary files**
- `src/chronicler/economy.py`
- `src/chronicler/resources.py`
- `src/chronicler/tech_focus.py`
- `src/chronicler/tech.py`
- `src/chronicler/scenario.py`
- `src/chronicler/live.py`
- `src/chronicler/batch.py`
- `src/chronicler/ecology.py`
- `viewer/src/hooks/useLiveConnection.ts`

**Plan**
- Fix tithe gating and wealth accounting where treasury flows should be part of conservation.
- Fix zero-farmer signal amplification and the non-adjacent route goods-economy gap together so planner and goods flow stay aligned.
- Make `get_active_trade_routes()` pure and move side effects into explicit mutation paths.
- Fix the tech-focus removal undershoot with exact baseline-restoration coverage.
- Repair scenario overrides so population, capital, and ecology invariants are restored after mutation.
- Make narrated parallel batch mode fail closed instead of silently using `_DummyClient`.
- Fix live `batch_load_bundle` initialization and disconnect handling so narration still works after bundle load and client-drop cases are explicit.
- Add Python-side validation or clamping for Rust ecology write-back values.

**Required tests**
- Economy regressions for tithe gating, conservation, zero-farmer bounds, and non-adjacent route decomposition.
- Regression proving route queries no longer emit capability events during reads.
- Tech-focus regression proving exact baseline restoration.
- Scenario consistency regression after overrides.
- Live/batch regressions for narrated parallel mode, `batch_load_bundle`, and disconnect handling.
- Ecology write-back validation regression.

### Batch E: Politics, Extinction, Relationships, Succession, Action Weights

**Primary files**
- `src/chronicler/politics.py`
- `src/chronicler/movements.py`
- `src/chronicler/culture.py`
- `src/chronicler/action_engine.py`
- `src/chronicler/succession.py`
- `src/chronicler/relationships.py`
- `src/chronicler/agent_bridge.py`

**Plan**
- Clear `capital_region` and any other dangling civ references on all absorption/extinction paths.
- Exclude dead civs from tribute, federation, movement, cultural victory, and similar loops via centralized alive checks where possible.
- Remove extinct-civ great-person effects and reconcile the Python dead-civ population floor with Rust zero-count behavior.
- Fix hostage cleanup when the origin civ no longer exists.
- Add deterministic mentorship tiebreaking for same-turn births.
- Normalize holy-war weighting to the same multiplicative pipeline as other modifiers, then enforce the real `2.5x` combined-cap rule on multiplier products.
- Fix exile restoration so it does not overwrite an incumbent leader in place.

**Required tests**
- Extinction/absorption regressions covering capital cleanup, dead-civ exclusion, GP cleanup, and zero-pop parity.
- Relationship regressions for hostage cleanup and mentorship determinism.
- Action-engine regressions for holy-war weighting and the documented `2.5x` cap.
- Succession regression for exile restoration behavior.

### Batch F: Rust Hot Path, Determinism, and Medium Rust Cleanup

**Primary files**
- `chronicler-agents/src/tick.rs`
- `chronicler-agents/src/behavior.rs`
- `chronicler-agents/src/satisfaction.rs`
- `chronicler-agents/src/agent.rs`
- `chronicler-agents/src/pool.rs`
- `chronicler-agents/src/ffi.rs`

**Plan**
- Replace repeated O(n*m) civ-signal scans with indexed lookup structures.
- Reduce repeated `partition_by_region` work by caching or threading grouped state through tick phases.
- Remove nondeterministic `HashMap` iteration from wealth paths or sort before use.
- Harden the fragile `civ_data` pattern in `behavior.rs`.
- Close the listed medium Rust issues while these files are already open: naming cleanup, constant extraction, stale comments, dead schema helpers, field-width consistency, dead-slot semantics, unused RNG offset follow-up, and redundant rebuild points.

**Required tests**
- Rust determinism regression running the same seed multiple times.
- Result-parity tests for the new indexed lookup paths.
- Targeted regressions for any medium cleanup that changes semantics.

### Batch G: Viewer/Type Contract + Documentation Cleanup

**Primary files**
- `viewer/src/types.ts`
- `viewer/src/App.tsx`
- `viewer/src/hooks/useLiveConnection.ts`
- `viewer/src/components/*`
- `CLAUDE.md`
- `src/chronicler/bundle.py`

**Plan**
- Close C-15 first by either fully syncing `viewer/src/types.ts` to the Python bundle contract or introducing a generated/shared schema path.
- Fix the listed viewer runtime issues: missing brace, no error boundary, unstable `key={i}` usage, repeated force-layout work, monolithic `AppShell`, and missing runtime validation for WebSocket payloads.
- Update `CLAUDE.md` so flags, line counts, current focus, and M44/API narration status match reality.
- Decide whether `bundle_version` is real and written or remove the doc claim.

**Required tests**
- Viewer unit tests for the runtime fixes and message validation.
- Fixture-drift test proving TypeScript expectations match the Python bundle shape.
- `npm test`, `npm run lint`, `npm run build`.
- Python regression for any bundle metadata contract change.

### Batch H: Test Coverage and Final Audit Gate

**Plan**
- Add explicit coverage for the `2.5x` combined weight cap.
- Add dedicated phase-function tests for Phases 4, 6, 7, and 8.
- Add external integration tests for `culture_tick.rs`, `conversion_tick.rs`, and `demographics.rs`.
- Add an explicit `--agents=off` bit-identical or contract-equivalent regression, depending on the exact supported guarantee.
- Run the full Python suite, full Rust suite, viewer gate, hybrid/off/shadow comparison, and 200-seed before/after comparison.

**Parallel note**
- Test file scaffolding can be prepared during earlier batches, but the final green gate belongs here after all correctness work merges.

### Batch I: Strategic Refactors + Dead Code

**Plan**
- Split `ffi.rs` into schema/batch/binding modules without changing behavior.
- Split `politics.py` into game logic and bridge/runtime plumbing.
- Treat S-2 as a roadmap/perf follow-on: document the remaining Python critical path and tie it to the next migration milestone.
- Remove dead code only after the full suite is green and there are no remaining references in tests, scripts, or docs.

**Parallel note**
- Planning and file-boundary design can happen during earlier batches, but merge this work only after Batch H is green.

### Final Closeout Checklist

- [ ] Batch A complete
- [ ] Batch B complete
- [ ] Batch C complete
- [ ] Batch D complete
- [ ] Batch E complete
- [ ] Batch F complete
- [ ] Batch G complete
- [ ] Batch H complete
- [ ] Batch I complete
- [ ] Full Python suite passes
- [ ] Full Rust suite passes
- [ ] Viewer test/lint/build passes
- [ ] Hybrid/off/shadow comparison passes
- [ ] 200-seed before/after artifact archived
- [ ] `docs/superpowers/progress/phase-6-progress.md` updated with the final audit closeout state
