# M56 Deferred Implementation Handoff (Post-M56a)

> Date: 2026-03-26  
> Audience: implementation agent taking M56b + deferred closeout tasks  
> Baseline branch: `feat/m56a-settlement-detection` at `5b1f4aa`

## Current Baseline (Already Landed)

- M56a is implemented and tested:
  - `src/chronicler/settlements.py` (detection, matching, lifecycle, diagnostics)
  - `src/chronicler/models.py` settlement models and snapshot fields
  - `src/chronicler/simulation.py` settlement tick wiring
  - `src/chronicler/main.py` terminal-force + snapshot summary fields
  - `src/chronicler/analytics.py` settlement diagnostics extractor
  - `tests/test_settlements.py` (54 tests)
- Off-mode (`--agents=off`) is verified as a no-op for settlement detection.
- Hybrid smoke remains blocked by a pre-existing FFI issue (`set_economy_config` AttributeError).

## Guardrails (Do Not Break)

- Preserve M56a scope split: M56a remains detection-only; M56b owns mechanical effects.
- Preserve off-mode no-op semantics (`--agents=off` should not synthesize settlements).
- Keep determinism guarantees (stable sorts, explicit tie-breakers, no hash-order dependence).
- Respect existing caps/rules:
  - non-ecological satisfaction penalties capped at `-0.40`
  - action modifier cap remains `2.5x`
- Any new Python/Rust transient signal must be cleared before builder return and must have a multi-turn reset test.

## Workstream 0: Unblock Hybrid Smoke (Blocker)

### Objective
Fix the pre-existing FFI mismatch so hybrid-mode validation can run.

### Suspected Touch Points
- `src/chronicler/agent_bridge.py`
- `chronicler-agents/src/ffi.rs`
- `chronicler-agents/src/lib.rs`
- Any adapter/wrapper invoking `set_economy_config`

### Acceptance
- Command passes without AttributeError:
  - `$env:PYTHONPATH = "src"`
  - `python -m chronicler.main --seed 42 --turns 30 --agents hybrid --simulate-only`
- Existing bridge test suites still pass.

## Workstream 1: M56b Mechanical Consumers

### Objective
Consume M56a settlement outputs to produce per-agent urban/rural mechanics.

### Recommended Signal Choice
- Prefer `settlement_id` on agents (future-proof), with derived `is_urban = settlement_id != 0`.

### Minimum Implementation Slices
1. Classification plumbing:
- Use `Region.settlements[*].footprint_cells` + agent `(x, y)` cell mapping to assign `settlement_id`.
- Run assignment on each hybrid tick after movement/migration state is current.

2. Rust-facing signal integration:
- Add lightweight signal path in bridge/FFI (do not ship full settlement objects every tick).
- Ensure deterministic assignment tie-breaks if multiple settlements overlap.

3. Mechanical effects (bounded constants, [CALIBRATE M61b]):
- Needs restoration bias (urban social/material up, safety down).
- Satisfaction input deltas via `SatisfactionInputs` extension (struct fields, not positional args).
- Culture/conversion pace modulation (urban faster than rural).
- Keep effects small and legible; avoid global retune.

### Candidate Files
- Python: `src/chronicler/agent_bridge.py`, `src/chronicler/simulation.py`
- Rust: `chronicler-agents/src/ffi.rs`, `chronicler-agents/src/tick.rs`, `chronicler-agents/src/needs.rs`, `chronicler-agents/src/satisfaction.rs`, `chronicler-agents/src/culture_tick.rs`, `chronicler-agents/src/conversion_tick.rs`

### Acceptance
- Deterministic same-seed urban assignment in hybrid mode.
- No cap/routing regressions.
- Off-mode behavior unchanged.

## Workstream 2: Narrator Integration (Deferred from M56a)

### Objective
Make settlement lifecycle and urbanization legible in narration outputs.

### Scope
- Add settlement-aware context to narration pipeline (founding/dissolution summaries, urbanization trend snippets).
- Keep event schema stable; enrich rendering/templates, not simulation causality.

### Candidate Files
- `src/chronicler/curator.py`
- `src/chronicler/narrative.py`
- `tests/test_narrative.py`

### Acceptance
- Settlement events appear coherently in generated text.
- No regression in existing narration tests.

## Workstream 3: Calibration + Regression Gate (M61b Follow-up)

### Objective
Calibrate new urban/settlement constants and run canonical before/after sweeps once hybrid smoke is fixed.

### Constants To Tune
- M56a detection/lifecycle constants in `src/chronicler/settlements.py`
- M56b urban effect multipliers/constants (new)

### Validation Sequence
1. Focused tests (Python + Rust)
2. Hybrid smoke runs
3. 200-seed before/after regression sweep
4. Document outcomes in `docs/superpowers/progress/phase-6-progress.md`

### Acceptance
- Regression envelope acceptable for target metrics.
- Determinism and off-mode invariants preserved.
- Deferred items list updated with what remains.

## Suggested Execution Order

1. Fix Workstream 0 (hybrid blocker) first.  
2. Implement Workstream 1 (M56b mechanics) with tight tests.  
3. Add Workstream 2 (narrator integration).  
4. Run Workstream 3 calibration/regression and document results.

## Minimum Test Commands

- `python -m pytest tests/test_settlements.py -q`
- `python -m pytest tests/test_agent_bridge.py tests/test_simulation.py tests/test_main.py -q`
- `cargo nextest run`
- `$env:PYTHONPATH = "src"; python -m chronicler.main --seed 42 --turns 30 --agents off --simulate-only`
- `$env:PYTHONPATH = "src"; python -m chronicler.main --seed 42 --turns 30 --agents hybrid --simulate-only`

