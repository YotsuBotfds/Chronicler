# M-AF2: Tooling Trust + Oracle/Workflow Integrity - Implementation Plan

> For agentic workers: execute this plan workstream-by-workstream, keep changes scoped, and prefer focused regression runs after each task.

**Goal:** Make the repo's validation, CLI, oracle, viewer workflow, and fixture surfaces honest and executable before moving on to new milestone work.

**Architecture:** `M-AF2` is a tooling-trust pass, not a simulation-behavior pass. Most changes stay in Python (`validate.py`, `main.py`, `live.py`, tests) plus the viewer TypeScript workflow. No Rust changes are expected. Hidden legacy tests are migrated by behavior, not by file preservation.

**Tech Stack:** Python 3.13+, pytest, React 19, Vitest, ESLint, WebSocket live server

**Spec:** `docs/superpowers/specs/2026-04-01-m-af2-tooling-trust-design.md`

---

## Shared execution notes

1. Use `.\.venv\Scripts\python.exe` for Python commands so the repo venv stays consistent.
2. Keep `validate.py` changes local to the existing module. This is not an `M-AF3` split/refactor pass.
3. Workstream 5 touches already-active viewer files:
   - `viewer/src/App.tsx`
   - `viewer/src/components/TerritoryMap.tsx`
   - `viewer/src/components/phase75/AppShell.tsx`
   - `viewer/src/hooks/useLiveConnection.ts`
   - `viewer/src/hooks/useTimeline.ts`
   Implement incrementally and do not revert unrelated shell work already in the tree.
4. Remove `test/` only after retained coverage has been migrated into `tests/` and the replacement tests are green.
5. Preserve compatibility where the spec requires it:
   - validation status shape should remain machine-readable
   - legacy `api_*` token metadata stays for one milestone as deprecated aliases

---

## Workstream 1: Hidden Test Tree Triage

**Goal:** End with one canonical Python test root: `tests/`.

**Primary files:**
- Delete after migration: `test/`
- Modify target suites:
  - `tests/test_agent_bridge.py`
  - `tests/test_curator.py`
  - `tests/test_narrative.py`
  - `tests/test_infrastructure.py`
  - any additional modern target file only if the overlap audit proves it is the better home

### Task 1.1: Baseline the hidden tree

- [ ] Run the legacy tree directly:
  - `.\.venv\Scripts\python.exe -m pytest -q test`
- [ ] Record which failures are stale-fixture drift versus still-valuable behavior coverage.
- [ ] Confirm the baseline discovery problem:
  - `pyproject.toml` limits discovery to `tests/`, so `python -m pytest -q` cannot see `test/`.

### Task 1.2: Migrate unique behavior, not legacy file structure

- [ ] Audit `test/test_m30_bridge.py` against `tests/test_agent_bridge.py`.
- [ ] Preserve still-unique agent bridge behavior:
  - promotion naming / registration
  - death transitions on named great persons
  - same-tick promotion then migration sequencing
  - `notable_migration`
  - `exile_return`
  - any still-unique aggregate-event actor assertions
- [ ] Audit `test/test_m38a_temples.py` against `tests/test_infrastructure.py`.
- [ ] Preserve the controller-gets-prestige temple regression in the modern infrastructure suite.
- [ ] Audit `test/test_m30_curator.py` against `tests/test_curator.py`.
- [ ] Audit `test/test_m30_narrative.py` against `tests/test_narrative.py`.
- [ ] Migrate only assertions that are not already covered by the modern tests.

### Task 1.3: Delete stale duplicates and remove the hidden root

- [ ] Delete files whose coverage is fully superseded, including the known overlap in `test/test_m36_culture.py`.
- [ ] Delete the `test/` directory entirely once retained behaviors are rehomed.

### Task 1.4: Verify the canonical end state

- [ ] Run focused migrated suites:
  - `.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_bridge.py tests/test_curator.py tests/test_narrative.py tests/test_infrastructure.py`
- [ ] Run the default repo discovery command:
  - `.\.venv\Scripts\python.exe -m pytest -q`
- [ ] Confirm `test/` no longer exists in the tree.

---

## Workstream 2: Validation Honesty (Fail-Closed)

**Goal:** `validate.py` must stop looking green when it silently skipped work.

**Primary files:**
- `src/chronicler/validate.py`
- `tests/test_validate.py`

### Task 2.1: Make oracle selection explicit and reject unknown names

- [ ] Add a single source of truth for supported oracle names near `run_oracles()`.
- [ ] Reject unknown oracle names before any batch loading starts.
- [ ] Keep `all` as the expansion alias, but ensure the final selected set contains only known oracle names.
- [ ] Add a CLI-level non-zero exit path for invalid oracle requests.

### Task 2.2: Distinguish missing dependency from missing data

- [ ] Audit the data requirements for each oracle using the current call paths:
  - `community` uses graph snapshots and can fall back to `validation_community_summary.json`
  - `needs` uses needs snapshots plus `agent_events.arrow`
  - `cohort` uses graph snapshots, needs snapshots, and `agent_events.arrow`
  - `determinism`, `era`, `artifacts`, `arcs`, and `regression` are bundle-first
- [ ] Keep existing JSON sidecar fallbacks where they already exist.
- [ ] Change `_read_arrow_columns()` and `_load_agent_events()` so a missing `pyarrow` dependency is surfaced when the requested oracle has no usable non-Arrow fallback for the required input.
- [ ] Treat absent optional data as an explicit `SKIP` with a reason, not a silent `None` / `[]` that later looks like a clean pass.

### Task 2.3: Make result structure and exit codes honest

- [ ] Preserve compatibility with the current uppercase report style:
  - `PASS`
  - `FAIL`
  - `SKIP`
  - add `ERROR` for aborted checks
- [ ] Require every non-pass result to carry a machine-visible reason:
  - `SKIP` -> `reason`
  - `ERROR` -> `reason`
- [ ] In `main()`, return non-zero when:
  - the oracle request is invalid
  - a required dependency for a requested check is unavailable
  - any oracle result has `status == "ERROR"`
- [ ] Leave intentional `SKIP` results machine-visible but non-crashing.

### Task 2.4: Regression coverage

- [ ] Add tests in `tests/test_validate.py` for:
  - unknown oracle names
  - missing `pyarrow` on an Arrow-dependent requested oracle with no fallback
  - explicit `SKIP` output containing a reason
  - CLI exit code behavior for invalid-oracle and missing-dependency cases

### Task 2.5: Verification

- [ ] Run:
  - `.\.venv\Scripts\python.exe -m pytest -q tests/test_validate.py`

---

## Workstream 3: Oracle Crash Paths

**Goal:** Oracle code must yield honest results or explicit failures, not divide-by-zero or non-finite math.

**Primary files:**
- `src/chronicler/analytics.py`
- `src/chronicler/shadow_oracle.py`
- `tests/test_analytics.py`
- `tests/test_shadow_oracle.py`

### Task 3.1: Fix empty-input analytics helper behavior

- [ ] Change `_firing_rate()` in `analytics.py` to return `0.0` on empty input.
- [ ] Add a focused regression in `tests/test_analytics.py`.

### Task 3.2: Harden Anderson-Darling fallback handling

- [ ] Replace the current fragile fallback:
  - `getattr(result, "pvalue", result.significance_level)`
- [ ] Use explicit attribute checks instead.
- [ ] Raise a clear error on unexpected SciPy result shapes instead of returning `None` through float conversion.
- [ ] Add a regression in `tests/test_shadow_oracle.py` for the unexpected-result-shape path.

### Task 3.3: Make correlation failures explicit

- [ ] Audit `compare_distributions()` in `shadow_oracle.py`.
- [ ] When the correlation inputs are degenerate or the computed delta is non-finite:
  - do not leave `NaN` in a normal result path
  - emit an explicit failed or skipped correlation result with a machine-readable reason
- [ ] Keep `OracleReport.correlation_passed` honest when one of those invalid comparisons occurs.
- [ ] If needed, extend `CorrelationResult` with minimal metadata such as `reason: str | None = None`; do not turn this into a broad contract redesign.
- [ ] Add a regression for identical-value vectors in `tests/test_shadow_oracle.py`.

### Task 3.4: Verification

- [ ] Run:
  - `.\.venv\Scripts\python.exe -m pytest -q tests/test_analytics.py tests/test_shadow_oracle.py`

---

## Workstream 4: CLI + Runtime Trust

**Goal:** No parsed-but-ignored flags, no silent LLM degradation, and token metadata that says what it actually measures.

**Primary files:**
- `src/chronicler/main.py`
- `tests/test_main.py`

### Task 4.1: Remove dead and inert CLI behavior

- [ ] Remove `--narrative-voice` from `_build_parser()`.
- [ ] Add argument validation in `main()` so:
  - `--compare` errors unless `--analyze` is present
  - `--narrate-output` errors unless `--narrate` is present
- [ ] Use `parser.error(...)` or an equivalent argparse-driven exit path so callers get a proper CLI failure instead of a silent no-op.

### Task 4.2: Log runtime LLM fallbacks

- [ ] Replace the bare goal-enrichment swallow in `main.py`:
  - current path: `enrich_with_llm(...)` inside `except Exception: pass`
- [ ] Log `logging.warning(...)` with the exception reason and the "proceeding with empty goals" behavior.
- [ ] Replace the silent action-selection fallback in the `action_selector` closure.
- [ ] Log civ name and turn when the LLM action path falls back to the deterministic selector.

### Task 4.3: Make token metadata honest without breaking current consumers

- [ ] In bundle assembly output, add canonical fields:
  - `narrative_input_tokens`
  - `narrative_output_tokens`
- [ ] For one milestone, keep:
  - `api_input_tokens`
  - `api_output_tokens`
  as deprecated aliases mirroring the canonical narrative fields.
- [ ] Update both emission sites:
  - normal run bundle metadata
  - `_run_narrate()` output metadata
- [ ] Keep current tests and M44-era consumers working during the transition.

### Task 4.4: Regression coverage

- [ ] Add or update tests in `tests/test_main.py` for:
  - parser rejection of `--narrative-voice`
  - `--compare` without `--analyze`
  - `--narrate-output` without `--narrate`
  - logged warning on goal-enrichment failure
  - logged warning on action-selection fallback with civ + turn context
  - canonical token fields present
  - legacy `api_*` token aliases still present and equal to the canonical values

### Task 4.5: Verification

- [ ] Run:
  - `.\.venv\Scripts\python.exe -m pytest -q tests/test_main.py`

---

## Workstream 5: Viewer Workflow + Live Input Validation

**Goal:** The viewer workflow should be runnable from documented commands, and malformed live inputs should get clear error responses instead of disappearing.

**Primary files:**
- `viewer/package.json`
- `viewer/src/App.tsx`
- `viewer/src/components/TerritoryMap.tsx`
- `viewer/src/components/phase75/AppShell.tsx`
- `viewer/src/hooks/useLiveConnection.ts`
- `viewer/src/hooks/useTimeline.ts`
- `src/chronicler/live.py`
- `tests/test_live.py`
- `tests/test_live_integration.py`

### Task 5.1: Wire `npm test` and make the viewer gates runnable

- [ ] Add `"test": "vitest run"` to `viewer/package.json`.
- [ ] Keep the existing `build` and `lint` scripts intact.

### Task 5.2: Fix the current lint failures in the live viewer shell

- [ ] Address the current `react-hooks/set-state-in-effect` failures in:
  - `viewer/src/App.tsx`
  - `viewer/src/components/TerritoryMap.tsx`
  - `viewer/src/components/phase75/AppShell.tsx`
  - `viewer/src/hooks/useTimeline.ts`
- [ ] Address the current `react-hooks/refs` failure in:
  - `viewer/src/hooks/useLiveConnection.ts`
- [ ] Prefer modern React patterns already allowed by repo guidance where they actually fit:
  - `useEffectEvent` for effect-driven callback freshness
  - `startTransition` when surface changes should be deprioritized
  - derive state instead of synchronously mirroring it inside effects where possible
- [ ] Do not expand this into a broad Phase 7.5 redesign. The objective is a clean, runnable workflow gate.

### Task 5.3: Add live root-object and per-command validation

- [ ] In `live.py`, validate that parsed messages are JSON objects before any `.get(...)` access.
- [ ] Add lightweight per-command validation helpers for the currently accepted commands:
  - `speed`
  - `start`
  - `batch_start`
  - `batch_cancel`
  - `batch_load_report`
  - `batch_load_bundle`
  - `narrate_range`
  - paused-mode commands already handled through `command_queue`
- [ ] Ensure malformed field types return structured error payloads instead of falling into the outer broad `except`.
- [ ] Replace the outer `except Exception: pass` in the WebSocket handler with an explicit error response and safe connection continuation or shutdown behavior.

### Task 5.4: Validate narration ranges and current live prerequisites

- [ ] In the `narrate_range` handler, validate:
  - `start_turn` and `end_turn` are integers
  - `start_turn <= end_turn`
  - both bounds fall within the currently loaded history range
  - the server actually has initialization data needed to narrate
- [ ] Return structured error messages on invalid ranges instead of sending `narration_started` and then failing later.

### Task 5.5: Regression coverage

- [ ] Add or update WebSocket integration tests in `tests/test_live_integration.py` for:
  - invalid JSON payload
  - non-object JSON payloads such as `"hello"` or `[1, 2, 3]`
  - malformed command payloads with missing or wrong-typed fields
  - out-of-range narration requests
- [ ] Add helper-level unit tests in `tests/test_live.py` if the validation logic is split into local functions.
- [ ] Keep existing live queue protocol tests passing.

### Task 5.6: Verification

- [ ] Run viewer commands:
  - `npm test`
  - `npm run lint`
  - `npm run build`
  from `viewer/`
- [ ] Run Python live tests:
  - `.\.venv\Scripts\python.exe -m pytest -q tests/test_live.py tests/test_live_integration.py`

---

## Workstream 6: Fixture Freshness + Automated Drift Prevention

**Goal:** `sample_bundle.json` stays aligned with the current viewer-consumed bundle contract.

**Primary files:**
- `scripts/generate_viewer_fixture.py`
- `viewer/src/__fixtures__/sample_bundle.json`
- `tests/test_bundle.py`
- `viewer/src/lib/__tests__/bundleLoader.test.ts` if a viewer-side assertion needs to be tightened

### Task 6.1: Regenerate the committed fixture from the current bundle writer

- [ ] Run `scripts/generate_viewer_fixture.py` after the bundle contract work in Workstream 4 is complete.
- [ ] If the script's args namespace has drifted from `execute_run()` expectations, update the script minimally so it remains the canonical regeneration tool.
- [ ] Commit the refreshed `viewer/src/__fixtures__/sample_bundle.json`.

### Task 6.2: Add a Python-side drift check for viewer-required fields

- [ ] Add a regression in `tests/test_bundle.py` that:
  - generates a bundle through `assemble_bundle()` or `execute_run()`
  - loads `viewer/src/__fixtures__/sample_bundle.json`
  - asserts the fixture still contains the legacy required viewer keys currently enforced by `viewer/src/lib/bundleLoader.ts`
  - verifies the required metadata shape for viewer-consumed fields
- [ ] Do not freeze every additive bundle field. The check should protect viewer-required fields only.

### Task 6.3: Keep the viewer-side fixture contract runnable

- [ ] Keep `viewer/src/lib/__tests__/bundleLoader.test.ts` green with the regenerated fixture.
- [ ] If needed, add one explicit assertion that the fixture still classifies as a valid legacy bundle after regeneration.

### Task 6.4: Verification

- [ ] Run:
  - `.\.venv\Scripts\python.exe -m pytest -q tests/test_bundle.py`
  - `npm test`
  from `viewer/`

---

## Final validation

### Targeted validation

- [ ] Python trust/oracle suites:
  - `.\.venv\Scripts\python.exe -m pytest -q tests/test_validate.py tests/test_analytics.py tests/test_shadow_oracle.py tests/test_main.py tests/test_live.py tests/test_live_integration.py tests/test_bundle.py`
- [ ] Modern suites that received hidden-test migration coverage:
  - `.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_bridge.py tests/test_curator.py tests/test_narrative.py tests/test_infrastructure.py`
- [ ] Viewer workflow:
  - `npm test`
  - `npm run lint`
  - `npm run build`
  from `viewer/`

### End-state verification

- [ ] Run the repo-default Python command:
  - `.\.venv\Scripts\python.exe -m pytest -q`
- [ ] Confirm:
  - `test/` is gone
  - `npm test` exists and passes
  - `npm run lint` passes
  - validation CLI now fails closed on invalid requests
  - live malformed inputs return explicit error responses
  - bundle metadata contains both canonical narrative token fields and deprecated `api_*` aliases

---

## Documentation closeout

- [ ] Update `docs/superpowers/progress/phase-6-progress.md` when implementation is complete with:
  - M-AF2 scope landed
  - commands used for final verification
  - any deferred follow-up that was consciously left for Phase 7.5 or M-AF3
