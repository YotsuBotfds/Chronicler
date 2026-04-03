# 2026-04-03 Full Audit Remediation Plan

> For agentic workers: execute this pass in workstreams, not as one giant mixed patch. Verify each cited issue before editing if it is listed as "candidate" rather than "verified live". Keep focused regression coverage with every cluster.

**Goal:** Close the live issues surfaced by the 2026-04-03 consolidated audit, explicitly reject or re-scope stale findings, and leave the repo with stronger correctness and test contracts before new milestone work resumes.

**Primary context:**
- `docs/superpowers/progress/phase-6-progress.md`
- user-provided consolidated audit report from 2026-04-03
- direct code verification performed in the working tree on 2026-04-03

**Important repo rules to preserve while fixing:**
- `--agents=off` must preserve aggregate baseline semantics.
- Phase 10 receives `acc=None` in aggregate mode.
- Bundle consumers must remain agnostic to aggregate vs agent-backed stats.
- New transient Python/Rust signals must be cleared before returning from the builder and must get multi-turn reset tests.
- Rebuild the extension with `.\.venv\Scripts\python.exe -m maturin develop --release` after Rust changes or Python may load stale native code.
- Keep bridge/religion pytest runs in separate processes when needed; `tests/test_religion.py` import stubs can create false bridge failures.

---

## Verification Snapshot

### Verified live

- `C1` shadow logger is effectively unwired from `execute_run()` / `AgentBridge(...)`.
- `C5` settlement transients still lack the required multi-turn reset coverage.
- High-severity correctness issues `H1` through `H18` were directly confirmed in code.
- Medium/low issues directly confirmed in this prep pass:
  - `M1`, `M2`, `M3`, `M4`, `M5`, `M6`, `M8`, `M9`, `M10`, `M11`, `M12`, `M13`, `M14`, `M15`, `M16`, `M17`, `M18`, `M19` (partial but real), `M20`, `M21`, `M22`
  - `L1`, `L2`, `L3`, `L4`, `L5`, `L6`, `L7`, `L8`, `L9`, `L10`, `L11`, `L12`, `L13`, `L23`
- Dead-code or production-unused items directly confirmed:
  - `thread_domains()`
  - `NarrationContext`
  - `clear_expired_capacity_modifier()`
  - `climate_degradation_multiplier()` is test-only
  - `evaluate_region_decisions_v1()` is test-only
  - `extract_stockpiles()` is test-only
  - `sendNarrateRange` / `loadReportFromFile` are exported but unused in runtime

### Rejected or re-scoped

- `C2` reject as filed.
  Shadow mode intentionally compares Rust agent aggregates against the aggregate-world state; there is no shadow-mode write-back contract to "move after". Do not add a shadow write-back.
- `C3` reject as filed.
  The shadow log stores raw aggregate/agent scalar stats, and both sides are already non-negative in the current contract. Rust aggregate batches are themselves emitted as `UInt32`.
- `C4` re-scope.
  The repo does **not** have "zero tests" for the FFI surface:
  - `tests/test_ecology_bridge.py` exercises `EcologySimulator`
  - `tests/test_politics_bridge.py` and `tests/test_agent_bridge.py` exercise `PoliticsSimulator` wiring and bridge paths
  - Rust tests already cover parts of `signals.rs`
  The real issue is narrower: explicit schema-mismatch, round-trip, and contract-hardening coverage around `ffi/batch.rs` and `ffi/schema.rs` is still too thin.

### Candidate items not fully re-verified in this prep pass

- Remaining report items not listed above should still be treated as candidates to verify before patching, especially the lower-severity Rust/world-gen/viewer items (`L14`, `L19`, `L20`, `L21`, `L22`, `L24`, `L25` and any un-sampled mediums).

---

## Workstream 0: Truth Pass and Claim Hygiene

**Goal:** Make the issue list honest before touching behavior.

**This workstream closes or re-labels:** `C2`, `C3`, `C4`, plus any remaining candidate items that fail direct verification.

**Primary files:**
- `docs/superpowers/plans/2026-04-03-full-audit-remediation-plan.md`
- `docs/superpowers/progress/phase-6-progress.md`
- optional follow-up note under `docs/superpowers/audit/` if we want a durable audit-closure memo

### Tasks

- [ ] Preserve the "verified live / rejected / candidate" split from this plan while implementing.
- [ ] Do **not** implement shadow-mode write-back for `C2`.
- [ ] Do **not** convert shadow schema to signed ints unless a new direct reproduction proves a real negative-value path for logged fields.
- [ ] Reframe `C4` from "zero tests" to "insufficient explicit FFI contract tests".
- [ ] For any lower-severity item not directly re-verified here, add a quick verification note before changing code.

---

## Workstream 1: Shadow Mode + Settlement Transient Contracts

**Goal:** Make shadow mode actually produce comparison artifacts, and bring settlement transients up to the documented reset-test standard.

**Closes:** `C1`, `C5`

**Primary files:**
- `src/chronicler/main.py`
- `src/chronicler/agent_bridge.py`
- `src/chronicler/shadow.py`
- `tests/test_main.py`
- `tests/test_agent_bridge.py`
- `tests/test_shadow_oracle.py`
- `tests/test_settlements.py`

### Tasks

- [ ] Thread a real `shadow_output` path from run setup into `AgentBridge(...)`.
- [ ] Decide and document default shadow artifact behavior:
  - recommended: auto-create a deterministic Arrow path inside the run output directory when `--agents=shadow`
  - optional: also expose an explicit CLI override if that fits current CLI conventions
- [ ] Add a regression proving a shadow run writes a non-empty Arrow IPC file.
- [ ] Keep current shadow semantics:
  - aggregate world stays authoritative
  - Rust agent aggregates are comparison-only
  - no shadow-mode write-back
- [ ] Add multi-turn reset tests for:
  - `_settlement_founded_this_turn`
  - `_settlement_dissolved_this_turn`
  - `_settlement_transitions`
- [ ] Verify the transient lists are cleared both on non-detection turns and after a subsequent detection pass with no matching events.

### Validation

- [ ] `.\.venv\Scripts\python.exe -m pytest -q tests/test_main.py tests/test_agent_bridge.py tests/test_shadow_oracle.py tests/test_settlements.py`

---

## Workstream 2: Simulation, Economy, Politics, Actions, and Factions Correctness

**Goal:** Close the largest Python correctness cluster first, because these issues affect live turn outcomes and can poison later oracle comparisons.

**Closes:** `H1`, `H2`, `H3`, `H4`, `H5`, `H6`, `H7`, `H8`, `H9`, `H14`, `H15`, `H16`, `M1`, `M2`, `M3`, `M5`, `M6`, `M7`, `M8`, `M9`, `M10`, `M11`, `M12`, `M20`, `M21`

**Primary files:**
- `src/chronicler/simulation.py`
- `src/chronicler/economy.py`
- `src/chronicler/resources.py`
- `src/chronicler/politics.py`
- `src/chronicler/action_engine.py`
- `src/chronicler/factions.py`
- `src/chronicler/ecology.py`
- `src/chronicler/emergence.py`
- `src/chronicler/climate.py`
- `src/chronicler/infrastructure.py`
- `tests/test_simulation.py`
- `tests/test_economy.py`
- `tests/test_resources.py`
- `tests/test_politics.py`
- `tests/test_action_engine.py`
- `tests/test_factions.py`
- `tests/test_ecology.py`
- `tests/test_emergence.py`
- `tests/test_infrastructure.py`

### Tasks

- [ ] Replace injected-event hardcoded stability drains with tuning keys (`H1`).
- [ ] Fix accumulator-mode war-cost treasury projection to include already-pending keep mutations, not stale scalar treasury (`H2`).
- [ ] Guard `EMPTY_SLOT` and unknown resource keys before category/good lookup (`H3`, `M3`).
- [ ] Change missing-relationship trade default from implicit exclusion to the intended neutral behavior (`H4`).
- [ ] Skip dead civs early in proxy-war and federation-defense flows (`H5`, `H6`).
- [ ] Fix federation creation guard so nonexistent `civ_b` names cannot be admitted (`H7`).
- [ ] Make secession capital selection treat disconnected distances as worst, not best (`H8`).
- [ ] Decide whether the final weight-cap block is:
  - genuinely broken probability logic that should become a real cap
  - or redundant dead code because upstream modifier caps already enforce the intended bound
- [ ] Implement the `H9` fix only after that decision:
  - either remove the dead proportional rescale and update docs/tests
  - or replace it with a cap that actually changes selection probabilities
- [ ] Clear or transfer `pending_build` correctly on conquest / scorched-earth paths (`H14`, `M20`).
- [ ] Move temple build cost/turns fully onto tuning overrides instead of frozen module constants (`H15`).
- [ ] Let temple replacement remain eligible when a foreign-faith temple exists (`H16`).
- [ ] Align asabiya-collapse accumulator math with aggregate-mode integer semantics (`M1`).
- [ ] Exclude dead civs from passive recovery / stress calculations / dead-target diplomacy (`M2`, `M12`, `M21`).
- [ ] Apply the missing severity multiplier on the long-peace economy drain path (`M7`).
- [ ] Normalize faction-shift detection after the pending faction bump and clamp stability with `STAT_FLOOR`, not hardcoded zero (`M8`, `M9`).
- [ ] Make the `INVEST_CULTURE` weight boost conditional on the condition described in the comment/spec, or update the comment/spec if unconditional is truly intended (`M10`).
- [ ] Stop silently recording `TRADE` / `WAR` fallbacks as if the original action happened (`M11`).
- [ ] Fix pandemic/flood ecology paths that still clamp to `1.0` instead of terrain caps (`M5`, `M6`).
- [ ] Preserve the Rust-provided `prev_turn_water` contract or remove the duplicate Python overwrite (`M4`) if it belongs better in Workstream 3.

### Validation

- [ ] `.\.venv\Scripts\python.exe -m pytest -q tests/test_simulation.py tests/test_economy.py tests/test_resources.py tests/test_politics.py tests/test_action_engine.py tests/test_factions.py tests/test_ecology.py tests/test_emergence.py tests/test_infrastructure.py`

---

## Workstream 3: Bridge / FFI Contract Hardening

**Goal:** Harden the Python/Rust seam and add the missing contract tests that would catch silent schema drift.

**Closes:** `C4` (reframed), `H10`, `H11`, `H12`, `H18`, `M4`, `M13`, `L8`, `L9`, `L10`, `L11`, `L12`, `L13`

**Primary files:**
- `src/chronicler/agent_bridge.py`
- `chronicler-agents/src/signals.rs`
- `chronicler-agents/src/ffi/batch.rs`
- `chronicler-agents/src/ffi/schema.rs`
- `chronicler-agents/src/ffi/ecology_sim.rs`
- `chronicler-agents/src/ffi/politics_sim.rs`
- `chronicler-agents/src/relationships.rs`
- `tests/test_agent_bridge.py`
- `tests/test_ecology_bridge.py`
- `tests/test_politics_bridge.py`
- new Rust tests under `chronicler-agents/tests/` as needed

### Tasks

- [ ] Add finite/range validation for demand shifts, faction weights, Gini, tithe share, and any other free-form `f32` civ signals crossing into Rust (`H10`).
- [ ] Replace event-count-as-region-population logic in `_aggregate_events()` with real population or agent-count data (`H11`).
- [ ] Treat `H12` as a design gate, not a blind patch.
- [ ] Before changing code for `H12`, choose and document one stability-ownership rule:
  - merge Python accumulator `keep` deltas into post-tick stability
  - stop Rust write-back from owning final stability
  - or convert the disputed pre-tick effects into agent-consumed signals instead
- [ ] Get a quick architecture review before landing the `H12` implementation.
- [ ] Then implement the chosen `H12` design and lock it down with regression coverage.
- [ ] Replace the blanket `_refresh_snapshot_metrics()` exception swallow with narrower handling and regression coverage (`M13`).
- [ ] Free or compact dead-target relationship slots so long-dead bonds do not permanently consume the 8-slot limit (`H18`).
- [ ] Fold the currently sampled Rust low-severity fixes into this same rebuild/test cycle where verified:
  - settlement assignment clamp (`L8`)
  - `turn as u16` timestamp wrap risk (`L9`)
  - wildcard priest branch (`L10`)
  - RNG-stream formula consistency (`L11`)
  - named-character registry pruning / cap pressure (`L12`)
  - raw occupation integer bypass trigger (`L13`)
- [ ] Add explicit FFI contract tests for:
  - missing column names
  - wrong Arrow types
  - column order / schema name drift where relevant
  - ecology/politics simulator batch round-trip invariants
- [ ] Keep this a hardening pass, not an FFI architecture rewrite.

### Validation

- [ ] `cd chronicler-agents && ..\\.venv\\Scripts\\python.exe -m maturin develop --release`
- [ ] `cargo nextest run --manifest-path chronicler-agents/Cargo.toml`
- [ ] `.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_bridge.py tests/test_ecology_bridge.py tests/test_politics_bridge.py`

---

## Workstream 4: Great Persons, Infrastructure, Analytics, Narrative, Bundle, and Model Hygiene

**Goal:** Close the remaining Python correctness issues that affect persistence, narration, and analytics outputs.

**Closes:** `H13`, `H17`, `M14`, `M15`, `M16`, `M17`, `M18`, `M19`, `L16`, `L18`

> **Note:** Infrastructure issues (`H15`, `H16`) moved to Workstream 2 to consolidate all `infrastructure.py` edits in one lane and avoid merge conflicts during parallel execution.

**Primary files:**
- `src/chronicler/great_persons.py`
- `src/chronicler/analytics.py`
- `src/chronicler/narrative.py`
- `src/chronicler/curator.py`
- `src/chronicler/llm.py`
- `src/chronicler/bundle.py`
- `src/chronicler/relationships.py`
- `src/chronicler/models.py`
- `tests/test_great_persons.py`
- `tests/test_analytics.py`
- `tests/test_narrative.py`
- `tests/test_bundle.py`
- `tests/test_relationships.py`
- `tests/test_models.py`

### Tasks

- [ ] Audit `alive` vs `active` callsites before changing Great Person retirement semantics (`H13`).
- [ ] Prefer the least invasive `H13` fix:
  - update dynasty/extinction checks to use `active` where that matches the intended meaning
  - only change retirement-time `alive` behavior if the callsite audit proves it is the safer contract
- [ ] Add the clergy faction to analytics extractors that currently hardcode a 3-faction world (`H17`).
- [ ] Stop hardcoding `turn: 0` inside narrative recent-history payloads (`M14`).
- [ ] Fix degenerate narrative-role assignment when the climax is first or last (`M15`).
- [ ] Bump or version-gate the bundle schema/version field honestly (`M16`).
- [ ] Add retry/backoff or at least bounded retry-on-transient behavior for narration clients before falling back to mechanical summaries (`M17`).
- [ ] Guard `AnthropicClient.complete()` against empty `content` lists (`M18`).
- [ ] Reset hostage-specific fields cleanly on release, including `hostage_turns`; restore role semantics deliberately instead of forcing an arbitrary replacement (`M19`).
- [ ] Revisit model defaults and serialization hygiene:
  - `civ_majority_faith` / `previous_majority_faith`
  - transient per-turn model fields that should not persist into bundles

### Validation

- [ ] `.\.venv\Scripts\python.exe -m pytest -q tests/test_great_persons.py tests/test_analytics.py tests/test_narrative.py tests/test_bundle.py tests/test_relationships.py tests/test_models.py`

---

## Workstream 5: Viewer and Live Contract Fixes

**Goal:** Bring the viewer/live client back into sync with the current bundle and turn-stream contract.

**Closes:** `M22`, `L1`, `L2`, `L3`, `L4`, `L5`, `L6`, `L7`

**Primary files:**
- `viewer/src/components/phase75/AppShell.tsx`
- `viewer/src/components/InterventionPanel.tsx`
- `viewer/src/components/BatchPanel.tsx`
- `viewer/src/hooks/useLiveConnection.ts`
- viewer tests as needed
- `tests/test_live.py`
- `tests/test_live_integration.py`
- `tests/test_batch_websocket.py`

### Tasks

- [ ] Make trade links use timeline-scrubbed relationship state, not always-final world-state relationships (`M22`).
- [ ] Re-sync `InterventionPanel` local state when `pauseContext` changes (`L1`).
- [ ] Stabilize the `useEffect` dependency pattern around `syncSelectedEntity()` or move the logic so renders do not thrash (`L2`).
- [ ] Guard against `progress.total === 0` in `BatchPanel` (`L3`).
- [ ] Replace repeated append-copy growth patterns in live mode with bounded or batched state updates where possible (`L4`).
- [ ] Preserve `gap_summaries` and the missing optional turn fields in live init / turn snapshots (`L5`, `L6`).
- [ ] Fix the playhead click/display off-by-one contract (`L7`).

### Validation

- [ ] `.\.venv\Scripts\python.exe -m pytest -q tests/test_live.py tests/test_live_integration.py tests/test_batch_websocket.py`
- [ ] `cd viewer && npm test && npm run lint && npm run build`

---

## Workstream 6: Low-Severity Sweep, Dead Code, and Unverified Candidates

**Goal:** Finish the pass without leaving obvious correctness landmines or misleading dead surfaces behind.

**Primary files:** touch only after verification; do not bulk-edit blindly.

### Candidate closures for this sweep

- [ ] Verify and fix remaining lower-severity Rust/world-gen items from the report:
  - `L14`, `L19`, `L20`, `L21`, `L22`, `L23`, `L24`, `L25`
- [ ] Audit test-surface honesty and remove misleading green coverage where tests are dead, stale, or silently skipped.
- [ ] Rehome, delete, or fix known test-hygiene issues only after confirming replacement coverage exists.
- [ ] Decide whether dead-code items should be:
  - deleted
  - converted to documented test helpers
  - left with an explicit "test-only / compatibility shim" comment
- [ ] Clean up confirmed production-unused surfaces after regressions are green:
  - `thread_domains()`
  - `NarrationContext`
  - `clear_expired_capacity_modifier()`
  - `extract_stockpiles()`
  - viewer-unused hook exports

### Validation

- [ ] Run the focused suites that correspond to the files actually changed.

---

## Final Validation Gate

**Do not call this pass complete until all of the following are true:**

- [ ] Python targeted suites for all touched workstreams are green.
- [ ] Rust targeted suites are green, and the extension has been rebuilt before Python bridge tests.
- [ ] Viewer tests/lint/build are green if any viewer files changed.
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` passes, or any intentional skips/failures are documented as pre-existing and reproduced independently.
- [ ] If this pass is being declared milestone-complete, run the 200-seed before/after validation gate per repo guidance.
- [ ] Update `docs/superpowers/progress/phase-6-progress.md` with:
  - what was fixed
  - which audit claims were rejected or re-scoped
  - exact validation commands
  - new gotchas discovered during implementation

---

## Execution Order and Parallelization

W0 (Truth Pass) must complete first - every other workstream depends on its output.

After W0, four lanes can run **in parallel** with zero shared files:

```
W0 (Truth Pass)
 |
 +--- Lane A: W1 -> W3  (Bridge / FFI chain)
 |      Serial within lane: both touch agent_bridge.py
 |
 +--- Lane B: W2  (Simulation / Economy / Politics / Actions / Factions / Ecology / Infrastructure)
 |
 +--- Lane C: W4  (Great Persons / Analytics / Narrative / Bundle / Models)
 |
 +--- Lane D: W5  (Viewer -- fully independent, zero Python overlap)
 |
 v
W6 (Low-severity sweep + test hygiene -- after all lanes land)
 |
 v
Final Validation Gate
```

### Why this is safe

All `infrastructure.py` edits have been consolidated into W2 (Lane B) to avoid cross-lane merge conflicts. The four lanes have **no shared source files**:

| Lane | Exclusive files |
|------|----------------|
| A (W1->W3) | `agent_bridge.py`, `shadow.py`, `main.py`, Rust `ffi/`, `signals.rs`, `relationships.rs` |
| B (W2) | `simulation.py`, `economy.py`, `resources.py`, `politics.py`, `action_engine.py`, `factions.py`, `ecology.py`, `emergence.py`, `climate.py`, `infrastructure.py` |
| C (W4) | `great_persons.py`, `analytics.py`, `narrative.py`, `curator.py`, `llm.py`, `bundle.py`, `relationships.py`, `models.py` |
| D (W5) | `viewer/` TS/JS files |

### Sequential fallback

If parallel execution is not available, the serial order is: W0 -> W1 -> W2 -> W3 -> W4 -> W5 -> W6 -> Final Gate. This keeps the highest-value correctness work first, avoids mixing bridge rebuilds with unrelated viewer changes, and prevents stale audit claims from turning into bad fixes.
