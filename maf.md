# M-AF Decision Guide

Compact operating guide for deciding what belongs in `M-AF1`, `M-AF2`, and `M-AF3`.

Use this to keep planning sessions short, consistent, and high-signal.

## Purpose

`M-AF` exists to harden the repo before building more milestone logic on top of it.

The goal is not "fix everything." The goal is:
- fix behavior that is wrong right now
- make validation/tooling trustworthy
- isolate structural debt so it does not contaminate milestone work

## Milestone Split

### `M-AF1`: Runtime Truth + Runtime Safety

This is the real pre-`M60a` gate.

Include items that:
- make supported runs simulate the wrong thing
- leave supported modes in stale/corrupt state
- can crash or abort a supported runtime path

Supported modes count:
- `--agents=off`
- `--agents=demographics-only`
- `--agents=shadow`
- `--agents=hybrid`

Default examples:
- accumulator routing bugs
- action resolution / bookkeeping mismatches
- dead-wired runtime political/religious/ecology systems
- FFI crash paths on live runtime surfaces
- writeback/state sync bugs
- off-mode bugs if `off` is a supported baseline

### `M-AF2`: Tooling Trust + Oracle/Workflow Integrity

Include items that:
- affect validation honesty
- affect CLI/workflow correctness
- affect hidden/legacy test surfaces
- affect viewer contract/tooling trust
- affect oracle/test/parity surfaces without corrupting the main runtime

Default examples:
- fail-open validator behavior
- inert CLI flags
- hidden failing test trees
- stale generated fixtures
- missing `npm test`
- oracle-only crashes
- token accounting/reporting bugs

### `M-AF3`: Structural Debt + Refactor Seams

Include items that:
- improve maintainability or extensibility
- reduce duplicated source-of-truth logic
- split oversized files/modules
- formalize phase/runtime contracts

Default examples:
- `ffi.rs` split
- `AgentBridge` split
- politics source-of-truth reduction
- `validate.py` split
- typed turn/phase contexts

Pull `M-AF3` items forward only if they are true blockers for the next milestone.

## Fast Decision Rule

When classifying a finding, ask these in order:

1. Does this make a supported run produce wrong behavior today?
2. Can this crash, panic, or abort a supported run?
3. Is this mostly about validation, tooling, workflow, viewer contract, or oracle trust?
4. Is this mostly about maintainability, duplication, or future-proofing?

Routing:
- `yes` to 1 or 2 -> `M-AF1`
- `yes` to 3 -> `M-AF2`
- `yes` to 4 -> `M-AF3`

## Tie-Break Rules

Use these defaults when an item is ambiguous:

- If it affects `--agents=off`, treat it as runtime, not edge-case.
- If it only affects Python oracle/test/parity surfaces, default to `M-AF2`.
- If it is a panic/abort path on a live Python/Rust boundary, default to `M-AF1`.
- If it is tuning/calibration rather than broken wiring, keep it out of `M-AF1` unless the bug makes tuning meaningless.

## Decisions Already Made

These are the session defaults unless new evidence changes them.

### In `M-AF1`
- positive `guard-shock` routing bug
- `TRADE` without real route
- executed action vs recorded action mismatch
- missing `war_start_turns`
- federation defense wiring
- governing-cost stability truncation bug
- zero-agent aggregate writeback gap
- promotion civ/origin identity loss over FFI
- missing severity-multiplier consumers
- dead-wired schism conversion
- martyrdom decay/filtering bugs
- impossible rewilding
- `replace_social_edges()` positional unwrap panic path
- `conquest_conversion_active` stale state in `--agents=off`, unless proven harmless

### In `M-AF2`
- validation fail-open behavior
- inert `--compare`
- hidden `test/` tree decision
- stale viewer fixture / missing Python->viewer contract check
- viewer lint/test workflow cleanup
- batch/token-accounting trust issues
- barren-region economy oracle crash, unless a supported production path can hit it

### Not In `M-AF1` By Default
- war frequency tuning
- large refactor waves
- broad cleanup/dead-code sweeps

War frequency is intentionally excluded from `M-AF1` because tuning a brokenly wired system produces misleading results.

## Spec Depth Rule

Use spec style `B` for `M-AF` items:

- `Problem`
- `Expected behavior`
- `Fix direction`
- `Required regression coverage`
- `Expected macro effect` when relevant

Do **not** use:
- pure `A` style for `M-AF1` bugfixes, because that causes rediscovery tax
- rigid `C` style with exact line edits, because it becomes brittle immediately

## Verification Rule

### Every Fix

Every item must ship with:
- at least one targeted regression test
- the smallest integration test needed to prove the bug is actually fixed

### `M-AF1` Gate

`M-AF1` is not done until all of these are true:

1. targeted regressions for each fix are green
2. affected suites are green
3. full Python and Rust suites are green
4. final signoff includes an adjudicated `200-seed` comparison against the pre-`M-AF1` baseline

Interpret the 200-seed comparison correctly:
- do **not** require numeric similarity to buggy behavior
- do require no new crashes, no new invariant failures, and no pathological outcomes
- do document expected directional shifts caused by the fixes

### `M-AF2` Gate

`M-AF2` is done when:
- the relevant commands fail closed and behave honestly
- hidden/legacy surfaces have an explicit disposition
- viewer/tooling workflow is executable from documented commands
- contract/fixture checks are automated where possible

### `M-AF3` Gate

`M-AF3` is done when:
- refactor parity is demonstrated
- suites stay green
- interfaces/contracts are simpler than before

## Adjudication Rule For `M-AF1`

Use this framing when reviewing the final gate:

- We are fixing bugs, not preserving them.
- Behavior is allowed to move in the direction implied by the fixes.
- Unexpected movement is what needs investigation.

Examples of acceptable directional shifts:
- federation defense can increase war entanglement
- fixing positive-event shock routing can improve satisfaction
- governing-cost stability becoming nonzero can reduce large-empire stability
- real schism conversion can change religious distributions

## Compact Planning Template

For each candidate item, write:

```md
- Finding:
- Bucket: M-AF1 / M-AF2 / M-AF3
- Problem:
- Expected behavior:
- Fix direction:
- Required regression:
- Gate impact:
- Expected macro effect:
```

## Compact Session Prompt

Use this when starting a new planning session:

```md
Use `maf.md` as the operating rulebook.

Classify each finding into M-AF1, M-AF2, or M-AF3 using:
- M-AF1 = runtime truth + runtime safety for supported modes
- M-AF2 = tooling trust, validation honesty, oracle/workflow integrity
- M-AF3 = structural debt and refactor seams

For each item, answer in spec style B:
- Problem
- Expected behavior
- Fix direction
- Required regression coverage
- Expected macro effect if relevant

Do not re-litigate default decisions in `maf.md` unless new repo evidence contradicts them.
```

## Practical Goal

If a future session follows this doc, it should:
- spend less time on scope debate
- avoid mixing runtime bugfixes with refactor waves
- preserve the distinction between "simulation is wrong" and "workflow is untrustworthy"
- produce tighter milestone specs and better implementation plans

## Current Handoff (2026-04-01)

### M-AF1 status

- `M-AF1` has been implemented on `m-af1-runtime-correctness`.
- The 200-seed gate passed and the behavior shift was adjudicated:
  `docs/superpowers/audits/m-af1-behavior-shift-note.md`
- The runtime follow-up found after the main gate is also now patched in the working tree:
  agent-event `belief` survives Rust `tick()` events -> Python `AgentEventRecord` -> `agent_events.arrow`,
  restoring martyrdom filtering on real death events.
- Use `docs/superpowers/progress/phase-6-progress.md` as the current status source of truth.

### M-AF2 intake confirmed in the current tree

- **Validation fail-open behavior is still live.**
  `src/chronicler/validate.py` still accepts an arbitrary oracle list without fail-closed validation,
  and the validation workflow should be reviewed as an honesty surface rather than a simulation bug.
- **`--compare` is still inert unless paired with `--analyze`.**
  `src/chronicler/main.py` only consumes `args.compare` inside the `if args.analyze:` branch.
- **The hidden `test/` tree is still excluded by default and still red.**
  `pyproject.toml` limits `pytest` discovery to `tests`, and `python -m pytest -q test`
  still fails on the current tree.
- **Viewer workflow trust is still incomplete.**
  `viewer/package.json` still has no `npm test`, and `npm run lint` is currently red.
- **Viewer fixture / Python->viewer contract trust still needs an explicit decision.**
  The fixture generator exists, but there is still no canonical automated contract check
  proving the committed fixture matches the current Python bundle surface.
- **Batch/oracle workflow integrity still needs review.**
  `src/chronicler/batch.py` still reuses one narrative client in sequential batch mode and
  still routes `--batch --parallel` through `_run_single_no_llm()`.
- **The pure-Python economy oracle barren-region crash remains an `M-AF2` candidate.**
  `src/chronicler/economy.py` still guards bootstrap on `resource_types[0] == 255`,
  but `compute_economy()` still unconditionally resolves production from slot `0`.

### Good opening questions for M-AF2 planning

- Should `--compare` become a true top-level mode, or should the CLI reject it unless `--analyze` is present?
- Should the hidden `test/` tree be fixed in place, migrated into `tests/`, or explicitly retired?
- What is the intended viewer gate: `lint + vitest + build`, or do we first want a real `npm test` wrapper?
- Should narrated parallel batch runs be supported, or should the CLI fail closed when the requested mode cannot honor real LLM behavior?
- Should the viewer fixture become generated-on-demand with an automated Python->viewer contract assertion?

### Resume prompt

Use `maf.md` as the operating rulebook.

Plan `M-AF2` in spec style `B`, starting from:
- validation/CLI honesty
- hidden test-surface disposition
- viewer workflow + contract trust
- batch/oracle integrity

Prefer the smallest tranche that makes the tooling and validation surfaces trustworthy before new milestone work.

## Active Execution State (2026-04-01)

### Current objective

- Finish `M-AF2` end-to-end from the committed 2026-04-01 spec/plan.
- Then execute the smallest defensible `M-AF3` tranche instead of opening a broad refactor wave.

### M-AF2 source docs

- Spec: `docs/superpowers/specs/2026-04-01-m-af2-tooling-trust-design.md`
- Plan: `docs/superpowers/plans/2026-04-01-m-af2-tooling-trust-implementation-plan.md`

### M-AF2 execution order

1. Hidden `test/` tree migration and removal
2. `validate.py` fail-closed honesty
3. oracle crash-path hardening
4. CLI/runtime trust fixes in `main.py`
5. viewer workflow + live input validation
6. fixture freshness automation

### Current completed work

- Workstream 1 complete:
  - unique legacy coverage migrated into `tests/`
  - hidden `test/` root deleted
- Workstreams 2-4 complete locally:
  - `validate.py` now rejects unknown oracle names, fails closed on missing required Arrow dependencies, reports explicit `SKIP` reasons, and returns non-zero on request/dependency/runtime-error cases
  - oracle crash paths are hardened in `analytics.py` and `shadow_oracle.py`
  - `main.py` now rejects inert flag combinations, logs LLM fallback warnings, and emits canonical `narrative_*_tokens` fields while preserving deprecated `api_*` aliases
- Workstream 6 complete locally:
  - `viewer/src/__fixtures__/sample_bundle.json` regenerated
  - Python-side fixture drift checks added against the current legacy viewer contract
- Focused Python verification is green for:
  - migrated legacy suites
  - `tests/test_validate.py`
  - `tests/test_analytics.py`
  - `tests/test_shadow_oracle.py`
  - `tests/test_main.py`
  - `tests/test_bundle.py`

### Remaining M-AF2 work

- None. Workstreams 1-6 are complete in the current working tree.

### Chosen M-AF3 tranche

- Scope: `validate.py` structural split after M-AF2 lands.
- Why this seam:
  - it is already being touched heavily by M-AF2
  - it is explicitly listed in `maf.md` as an M-AF3 example
  - it is materially smaller and safer than an `AgentBridge` or `ffi.rs` split
- Non-goals for this tranche:
  - no `AgentBridge` split
  - no `ffi.rs` split
  - no broad politics boundary rewrite

### Shared-file caution

- Viewer files under active shell work are already dirty in the tree. Do not revert unrelated changes while making M-AF2 lint/test fixes.
- The current live M-AF1 follow-up files (`agent_bridge.py`, `bundle.py`, Rust event schema, related tests) are also dirty; work around them rather than resetting anything.

### Next checkpoint

- If new trust/runtime findings appear, classify them against the completed `M-AF2` / scoped `M-AF3` baseline rather than reopening the finished workstreams by default.

### Completion checkpoint (2026-04-01)

- `M-AF2` is complete on the current working tree.
  - Workstream 1: hidden `test/` tree migrated by retained behavior and removed.
  - Workstream 2: validation now fails closed for unknown oracle requests and missing required Arrow dependencies, reports explicit `SKIP` reasons, and exits non-zero on invalid/dependency/runtime-error cases.
  - Workstream 3: `_firing_rate()` empty-input crash removed and `shadow_oracle.py` now handles degenerate distribution/correlation cases honestly.
  - Workstream 4: dead/inert CLI behavior removed or rejected, runtime LLM fallback warnings added, and canonical `narrative_*_tokens` metadata landed while preserving deprecated `api_*` aliases.
  - Workstream 5: viewer workflow now has `npm test`, lint is green, and `live.py` rejects malformed root messages, bad payload types, and invalid `narrate_range` windows with structured errors.
  - Workstream 6: `sample_bundle.json` regenerated and Python-side fixture drift checks added against the legacy viewer contract.

- `M-AF3` is complete for the chosen small tranche.
  - `src/chronicler/validate.py` is now a facade/CLI layer.
  - `src/chronicler/validation_io.py` owns bundle/sidecar loading plus dependency preflight.
  - `src/chronicler/validation_oracles.py` owns oracle algorithms and per-oracle runners.
  - Public imports from `chronicler.validate` remain stable.
  - Plan record: `docs/superpowers/plans/2026-04-01-m-af3-validate-structural-split.md`

- Verified commands:
  - `.\.venv\Scripts\python.exe -m pytest -q tests/test_live.py tests/test_live_integration.py tests/test_validate.py tests/test_analytics.py tests/test_shadow_oracle.py tests/test_main.py tests/test_bundle.py tests/test_agent_bridge_legacy_migration.py tests/test_curator_legacy_migration.py tests/test_narrative_legacy_migration.py tests/test_infrastructure_legacy_migration.py`
  - `npm test`
  - `npm run lint`
  - `Test-Path test` -> `False`
  - Full discovered Python suite: `2308 passed, 4 skipped`

- Follow-up closeout:
  - `tests/test_m36_regression.py` was the last red test in the discovered Python suite.
  - Root cause: the hybrid economy assertion had gone stale after the post-M54b off-mode economy split, and the harness itself was order-dependent about whether the real Rust extension was loaded.
  - Fix: prefer the real extension when available, mirror production off-mode runtime wiring, bind the hybrid bridge to the same world instance being advanced, and compare cross-mode stability instead of treasury.
  - Post-audit trust fixes also landed:
    - nonexistent validation batch paths now error instead of `SKIP/no_bundles`
    - `needs`/`cohort` only demand `pyarrow` when Arrow data is the actual blocker, otherwise they keep structured skip reasons
    - malformed `batch_start` nested config now returns `batch_error` instead of killing the live batch thread
  - Result: full discovered `pytest -q` now passes cleanly on the current working tree.
