# M-AF2: Tooling Trust + Oracle/Workflow Integrity

**Status:** Draft
**Branch:** TBD
**Prerequisite:** M-AF1 merged
**Gate style:** maf.md M-AF2 gate rules

---

## Scope

M-AF2 makes the project's validation, CLI, oracle, viewer workflow, and fixture surfaces **honest and executable**. It does not touch simulation runtime behavior (M-AF1) or structural refactoring (M-AF3).

The guiding principle from maf.md: if a tool, validator, or workflow surface says it did something, it actually did it. If it could not do it, it says so clearly.

---

## Out of Scope

- Live message versioning (Phase 7.5)
- Bundle v1 schema version retrofit (Phase 7.5)
- Arrow IPC sidecar typing in viewer (Phase 7.5)
- Full `LocalClient` token accounting (instrumentation, not trust)
- Bundle v2 large fixture (blocked on M61b)
- War frequency tuning (M-AF1 exclusion still holds)
- Simulation runtime correctness (M-AF1)
- Structural refactoring (M-AF3)

---

## Workstream 1: Hidden Test Tree Triage

### Problem

`test/` (singular) contains 56 tests across 8 files from M30-M38a. Pytest discovers only `tests/` (plural) per `pyproject.toml` `testpaths = ["tests"]`. 10 of 56 tests are currently failing from code drift. This tree has been silently bitrotting — failures are invisible.

### Expected behavior

One canonical Python test root (`tests/`). No secondary undiscovered test tree. Unique coverage preserved, stale duplicates deleted.

### Fix direction

- Overlap-check each `test/` file against `tests/` coverage.
- Migrate unique behavior that still matters:
  - `test/test_m30_bridge.py`: promotion/death/migration sequencing, `notable_migration`, `exile_return`
  - `test/test_m38a_temples.py`: controller-gets-prestige (not builder)
  - `test/test_m30_curator.py` and `test/test_m30_narrative.py`: unique assertions after overlap check
- Delete stale duplicates. `test/test_m36_culture.py` overlaps the modern culture coverage in `tests/test_culture.py` and fails mostly from mock drift.
- Delete `test/` directory entirely after migration.
- Not every legacy file deserves migration — only unique coverage.

### Required regression

- `test/` directory is removed (not just emptied).
- All migrated tests pass under `tests/`.
- `python -m pytest -q` covers retained behaviors.

### Gate

`test/` is removed. Retained behaviors live under `tests/`. `python -m pytest -q` covers them.

---

## Workstream 2: Validation Honesty (Fail-Closed)

### Problem

`validate.py` silently returns `None`/`[]` when pyarrow is missing, when oracles are unknown, or when checks cannot execute. Validation looks clean when it actually skipped.

### Expected behavior

Validation commands fail closed. Missing required dependencies error when a requested oracle requires the data they provide. Unknown oracles error. Skipped checks report as explicit `skipped_with_reason`, not silent empties. Machine-visible structured output, not just console text. CLI exit status matches the report: unknown oracle, missing required dependency for a requested oracle, or any oracle result with status `error` returns non-zero.

### Fix direction

- `_read_arrow_columns()` (`validate.py:103`): error when a requested oracle needs Arrow data and pyarrow is unavailable. Do not turn every missing sidecar into a blanket exception — only fail when the requested oracle actually requires the data.
- `_load_agent_events()` (`validate.py:267`): same principle — error when a requested oracle requires agent event data and pyarrow is unavailable.
- Unknown oracle names in `validate.py`: raise explicitly, do not silently ignore.
- Structured skip/error/pass reporting: each oracle check produces a clear result (pass, fail, skip with reason, error with reason).
- CLI exit semantics: `validate.py` returns non-zero for invalid oracle requests, missing required dependencies for requested checks, and any completed report containing `error` status. Explicit `skip_with_reason` remains machine-visible but does not crash the process.

### Demoted

- `_choose_snapshot_turn()` (`validate.py:71`): silent turn downgrade is a usability issue, not a concrete trust bug. Demoted from core fix list. Can be addressed later if it causes real confusion.

### Required regression

- Test that requesting an Arrow-dependent oracle with missing pyarrow raises.
- Test that an unknown oracle name raises.
- Test that skipped checks appear in output with explicit reason.
- Test that `validate.py` exits non-zero on an unknown oracle or missing required dependency for a requested oracle.

### Expected macro effect

Validation runs that previously looked green may now show explicit skips or errors. This is the point.

---

## Workstream 3: Oracle Crash Paths

### Problem

Oracle/analytics functions have crash paths and silent incorrectness that affect validation trust. These are distinct from the validation-honesty issues in Workstream 2 — these are correctness hazards in the oracle computation itself.

### Expected behavior

Oracle paths produce honest results or clear errors. No NaN pass-throughs, no division by zero, no fragile attribute chains.

### Fix direction

- `_firing_rate()` (`analytics.py:222`): return `0.0` on empty input. This is an internal analytics helper, not a top-level validator — `0.0` is the cleaner contract. Do not leave this as "0.0 or raise."
- NaN correlation (`shadow_oracle.py`): detect identical-value vectors producing `NaN` from `np.corrcoef()`. Produce an explicit fail/skip result, not a silent threshold pass. The oracle result for that metric should clearly indicate the comparison was not meaningful.
- Anderson-Darling fallback: replace fragile `getattr(result, "pvalue", result.significance_level)` chain with explicit attribute check. Raise on unexpected result shape rather than silently producing `None` where `float` is expected.

### Required regression

- Test `_firing_rate()` with empty list returns `0.0`.
- Test oracle with identical-value agent vectors produces explicit skip/fail, not NaN pass.
- Test Anderson-Darling with unexpected result shape raises.

---

## Workstream 4: CLI + Runtime Trust

### Problem

Dead CLI flags erode trust. Mode-specific flags silently ignored outside their mode. LLM runtime fallbacks are completely silent. Token metadata labels in bundle are misleading (say "api" but contain only narrative tokens).

### Expected behavior

Dead flags removed. Mode-specific flags error outside their mode. LLM fallbacks log explicit warnings. Token metadata labels are accurate.

### Fix direction

**CLI flags:**
- Remove `--narrative-voice` entirely. Dead parsed-only flag — pure trust debt.
- `--compare` errors unless `--analyze` is present.
- `--narrate-output` errors unless `--narrate` is present.

**LLM runtime fallbacks:**
- Goal enrichment (`main.py:192`): `except Exception` logs a warning via `logging.warning()` with the exception reason, not bare `pass`. Message: "LLM goal enrichment failed: {reason}; proceeding with empty goals."
- LLM action selection (`main.py:294`): log warning via `logging.warning()` identifying civ name and turn on fallback. Message: "LLM action selection failed for {civ} on turn {turn}; falling back to deterministic selector."

**Token metadata:**
- Make bundle metadata honest about what the token fields measure. Use additive aliases or a compatibility transition rather than a pure rename — the current keys (`api_input_tokens`, `api_output_tokens`) are referenced in `main.py:743`, tests in `test_main.py`, and M44 docs.
- Preferred approach: add `narrative_input_tokens` / `narrative_output_tokens` as the canonical fields, retain old keys for one milestone as deprecated aliases, document the transition.

### Required regression

- Test that `--narrative-voice` is rejected by argparse.
- Test that `--compare` without `--analyze` errors.
- Test that `--narrate-output` without `--narrate` errors.
- Test that LLM goal enrichment failure produces a logged warning (assert on logger, not stdout).
- Test that LLM action selection fallback produces a logged warning with civ and turn.
- Test that bundle metadata contains the new canonical token field names.
- Test that the deprecated `api_input_tokens` / `api_output_tokens` aliases still exist for this milestone and mirror the canonical narrative token fields.

---

## Workstream 5: Viewer Workflow + Live Input Validation

### Problem

Viewer tests unreachable from `npm test`. Viewer lint is red (13 errors, 1 warning). Live server accepts malformed inputs silently — non-object JSON, bad scalar types, and invalid narration ranges all fall into broad `except Exception: pass` handlers and disappear.

### Expected behavior

`npm test` runs viewer tests and passes. `npm run lint` passes. Live server validates inputs at two levels: root-object shape validation, then per-command type validation. Malformed messages get structured error responses, not silent drops.

### Fix direction

**Viewer workflow:**
- Add `"test": "vitest run"` to `viewer/package.json` scripts.
- Fix the 13 lint errors and 1 warning so `npm run lint` is green and usable as a gate.

**Live input validation:**
- Root-object validation: incoming WebSocket messages must be valid JSON objects. Non-object JSON (arrays, scalars, strings) gets a structured error response, not silent drop.
- Per-command type validation: each command handler validates its expected fields exist and have correct types before processing. Invalid field types get error responses.
- Narration range validation (`live.py:294`): check `start_turn <= end_turn`, both within history range. Error response on violation.
- Audit `except Exception: pass` patterns in live message handling (`live.py:216`, `live.py:347`). Replace silent drops with structured error responses to the client. The client should know its message was rejected and why.

### Required regression

- `npm test` exits 0 with all viewer tests passing.
- `npm run lint` exits 0.
- Test that non-JSON WebSocket message returns error response.
- Test that non-object JSON (e.g., `"hello"`, `[1,2,3]`) returns error response.
- Test that out-of-range narration request returns error response.
- Test that malformed command (missing required fields) returns error response, not silent drop.

---

## Workstream 6: Fixture Freshness + Automated Drift Prevention

### Problem

`sample_bundle.json` is manually generated by `scripts/generate_viewer_fixture.py`. No automated check prevents it from silently drifting from the current Python bundle surface. The fixture's `generated_at` timestamp is from March 13; fields may have been added since.

### Expected behavior

Fixture stays in sync with bundle contract. Drift is caught automatically by a test, not discovered by accident.

### Fix direction

- Regenerate `sample_bundle.json` from current `assemble_bundle()` output.
- Add an automated drift test: generate a bundle from `assemble_bundle()` and validate that `sample_bundle.json` contains all **required viewer-consumed fields**. The test validates the fields the viewer loader actually requires (per `viewer/src/lib/bundleLoader.ts`), not every additive bundle field. The goal is to catch contract-breaking drift, not freeze the bundle surface.
- Keep `generate_viewer_fixture.py` as the manual regeneration tool. The test is the gate.
- No v2 large fixture work (blocked on M61b).

### Required regression

- Test that `sample_bundle.json` contains all required viewer-consumed fields from current `assemble_bundle()` output.
- Test fails if bundle surface removes or renames a viewer-required field without fixture update.
- Test does not fail on additive fields (new Python-side fields the viewer doesn't consume yet).

---

## M-AF2 Gate

From maf.md, adapted to this spec:

1. Validation commands fail closed and behave honestly.
2. Hidden/legacy test surfaces have explicit disposition — `test/` is removed, unique coverage migrated to `tests/`.
3. Viewer/tooling workflow executable from documented commands: `npm test`, `npm run lint`, `pytest`.
4. Contract/fixture checks automated — `sample_bundle.json` drift test in CI-equivalent test suite.
5. Oracle paths produce honest results or clear errors — no NaN pass-throughs, no division-by-zero, no fragile fallbacks.
6. CLI flags are either wired or removed — no parsed-but-ignored flags.
7. LLM runtime fallbacks are logged, not silent.
8. Token metadata labels are accurate.

---

## Verification Rule (from maf.md)

M-AF2 is done when:
- The relevant commands fail closed and behave honestly.
- Hidden/legacy surfaces have an explicit disposition.
- Viewer/tooling workflow is executable from documented commands.
- Contract/fixture checks are automated where possible.
