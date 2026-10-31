# Kimi remediation tracker — 2026-10-31

This is the live handoff ledger for the remediation branch. Update it with every commit and before any interruption. Do not describe source-only edits or unrun checks as qualified.

## Branch and baseline

- Repository: `yotsubotfds/Chronicler`
- Branch: `dev/kimi-remediation-20261031`
- Base branch: `dev/claude-handoff-20261030`
- Base commit: `2e7425f4f863274c2a973ceba5f9cfb89b857ffb`
- Current head: this batch-4 commit; preceding remediation commits are recorded in branch history.
- Current owner: Kimi K3.1
- Overall state: IN PROGRESS
- Next exact action: resolve B5 malformed-exile semantics explicitly, add native and Python regressions, and leave native execution marked UNRUN.

## Working rules

1. Land small, independently reviewable commits; keep unrelated cleanup out of correctness fixes.
2. Add a behavioral regression for every fixed defect. Preserve deterministic RNG streams, civilization/region index identity, serialization compatibility, and native/Python oracle contracts.
3. Run focused tests before each commit. Run broader affected suites before handoff. Record commands and counts below.
4. Native/Rust checks are unavailable in the current environment. Native edits must remain explicitly UNRUN until a Rust gate executes them.
5. The dev branch is intentionally inert for push CI. Local checks do not substitute for a fresh dedicated CI runref.
6. Do not merge, open a PR, alter unrelated branches, or delete evidence without a separate user decision.
7. If work stops mid-batch, set the interrupted item to `[~]`, list modified files and the exact next command, and push this tracker before stopping whenever possible.

## Model and effort routing

Labels are recommendations for the next implementer; they are not claims that this interface switched models.

- **K2.8 / Standard:** mechanical documentation edits, dead-parameter removal, simple test renames, already-specified one-line guards.
- **K3.1 Pro / Standard:** localized Python/TypeScript fixes with straightforward behavioral regressions.
- **K3.1 Pro / High:** cross-runtime parity, checkpoint/resume lifecycle, batch failure semantics, analytics correctness.
- **K3.1 Pro / Max:** native restoration semantics, architectural refactors, full determinism or scientific qualification.

## Task board

Status: `[ ]` pending, `[~]` active/interrupted, `[x]` landed and focused-checked, `[!]` blocked/needs a decision.

| Status | ID | Priority | Recommended model / effort | Task | Evidence / handoff |
|---|---|---|---|---|---|
| [x] | B1a | P0 | K3.1 Pro / Standard | Fix negative drains in `utils.distribute_pop_loss`; regression covers rounded overdraw and no regional growth. | Batch 1: clamp every drain to population and remaining non-negative budget; focused and surrounding tests passed. |
| [x] | B1b | P0 | K3.1 Pro / Standard | Make checkpoint replay source identity include nested Python packages; share `batch_manifest.package_digest` if compatible. | Batch 1: replay now uses the canonical recursive package digest; top-level and nested-module checkpoint invalidation passed. |
| [x] | B2a | P0 | K3.1 Pro / High | Match restoration trait RNG to the Python oracle, including per-civilization stream identity. | Batch 2: bridge uses the oracle's stable per-civilization restoration-trait stream. |
| [x] | B2b | P0 | K3.1 Pro / High | Set restored region asabiya in both existing- and new-record bridge paths. | Batch 2: common post-materialization initialization covers both paths; new-record regression passed. |
| [x] | B2c | P0 | K3.1 Pro / High | Filter unreachable (`-1`) distances in bridge breakaway-capital selection. | Batch 2: mirrors the oracle's reachable-distance filter and fallback; disconnected-capital regression passed. |
| [x] | B3 | P1 | K3.1 Pro / Standard | Update `num_turns` in the initial resumed-live `save_loaded` checkpoint. | Batch 3: initial resumed-pause checkpoint now stores the extended length; focused and surrounding checkpoint tests passed. |
| [x] | B4 | P1 | K3.1 Pro / Standard | Preserve own `__proto__` data keys through all viewer object-patch output paths; add Python/TS parity coverage. | Batch 4: safe own-property definitions cover fast/reference/ordered paths; Python and TS parity regressions, lint, and build passed. |
| [ ] | B5 | P1 | K3.1 Pro / Max | Guard unresolved native exile `original_civ` before every index; decide whether malformed exiles reject in both runtimes or retain name-based restoration. | Rust UNRUN. Files: `chronicler-agents/src/politics.rs`, native regression tests. Do not silently invent parity semantics. |
| [ ] | C1 | P1 | K3.1 Pro / High | Make batch failures finalize manifests and preserve completed-run evidence; specify fail-fast versus per-seed continuation. | Needs explicit lifecycle design and failure-injection tests. Files: `batch.py`, `batch_manifest.py`, live batch caller. |
| [ ] | C2 | P1 | K3.1 Pro / High | Repair action entropy/persistence across leader resets, era boundaries, and late-founded civs; remove or implement dead checkpoints argument. | Prefer per-turn resolved actions over cumulative-count diffs. Base repro returned entropy 0 instead of 1.5 and persistence 100% instead of 50%. |
| [ ] | C3 | P1 | K3.1 Pro / Standard | Route primary artifact writes through existing atomic I/O helpers with fault-injection coverage. | Bundle JSON/Arrow, world state, chronicle, live batch report. |
| [ ] | C4 | P2 | K3.1 Pro / High | Resolve recorded-but-uncompared `PYTHONHASHSEED` checkpoint identity semantics. | Compare it or document/test hash invariance; do not just delete without checking native resume. |
| [ ] | C5 | P2 | K3.1 Pro / High | Fix Node 20 viewer hash-test portability or narrow documented support; add CI coverage for supported floor. | Base: 738 passed / 5 failed on Node 20.20.2; Node Web Crypto rejected jsdom File ArrayBuffer. Production fallback is deliberate. |
| [ ] | D1 | P2 | K2.8 / Standard | Correct misleading economy-parity test naming/docs without weakening genuine native coupling parity tests. | `test_economy_parity.py` never invokes Rust; real parity exists in `test_economy_coupling.py`. |
| [ ] | D2 | P2 | K2.8 / Standard | Correct campaign-default docs, README continuation pointer, and Python-floor metadata after checking packaging intent. | Mechanical only after code behavior is confirmed unchanged. |
| [ ] | D3 | P3 | K3.1 Pro / High | Split orchestration/validation hotspots and reduce source-text witness dependence. | Separate follow-up; do not mix with correctness batches. |
| [ ] | D4 | P3 | K2.8 / Standard | Triage dormant duplicate workflows, stale audit docs, and viewer lockfile advisories. | Preserve retained evidence functions; reviewed dependency refresh required. |

## Commit ledger

| Commit | Scope | Checks | Follow-up |
|---|---|---|---|
| `852525cdfcdfdb78ef919d25b2a1fd1bc5092640` | Repository tracker only | No product code changed; no tests required for tracker commit. | Start B1a/B1b. |
| `0f29cd14a7f109d6e8affcfa23df107826ca43be` | Batch 1: population-loss clamp and recursive checkpoint source identity | New regressions failed before the fix (2 failed, 1 passed), then passed (3 passed). Surrounding suites: 169 passed. | Start B2a/B2b/B2c. |
| Batch-2 commits | Batch 2: restoration trait/asabiya and breakaway-capital bridge parity | New regressions failed before the fix (2 failed), then passed (2 passed). Politics suites: 204 passed, 53 skipped. Native cases remain unrun. | Start B3. |
| `71127b5a` | Batch 3: extended resumed-live initial checkpoint length | Regression failed before the fix with saved `num_turns == 12` instead of 16, then passed. Surrounding checkpoint suites: 33 passed. | Start B4. |
| this commit | Batch 4: viewer codec own `__proto__` safety and Python parity | TS regression failed before the fix, then 8 focused TS tests passed. Python codec module: 23 passed. Viewer lint and production build passed. | Start B5; native checks remain UNRUN. |

## Verification log

Baseline review at `2e7425f4f863274c2a973ceba5f9cfb89b857ffb`:

- Python full no-Rust run: 8,729 passed, 355 skipped, 623 subtests passed; 28 parent-archive failures were mount-specific (`st_nlink == 0`). The complete affected module passed on a normal filesystem: 66 passed.
- Viewer on Node 20.20.2: 738 passed, 5 failed; lint and production build passed.
- Two seed-42, 30-turn aggregate smoke runs matched except `metadata.generated_at`.
- Rust/Cargo and `chronicler_agents` were unavailable; native execution and fresh CI remain unqualified.

Remediation checks:

- Batch 1 pre-fix regression control: `.venv/bin/python -m pytest -q tests/test_population_conservation.py::test_population_loss_never_grows_a_region_after_rounding_overdraw tests/test_turn_artifact_runner.py::test_new_source_module_changes_identity_and_rejects_checkpoint` — 2 failed, 1 passed; failures were the negative drain and unchanged nested-source digest.
- Batch 1 focused: same command — 3 passed.
- Batch 1 surrounding: `.venv/bin/python -m pytest -q tests/test_population_conservation.py tests/test_utils_civ_helpers.py tests/test_checkpoint_replay.py tests/test_turn_artifact_runner.py tests/test_batch_manifest.py` — 169 passed in 17.45s.
- Batch 2 pre-fix regression control: `.venv/bin/python -m pytest -q tests/test_politics_bridge.py::TestApplyPoliticsOps::test_breakaway_capital_ignores_unreachable_parent_regions tests/test_politics_bridge.py::TestApplyPoliticsOps::test_new_restoration_matches_oracle_trait_and_initializes_region_asabiya` — 2 failed with the expected wrong capital and trait.
- Batch 2 focused: same command — 2 passed.
- Batch 2 surrounding: `.venv/bin/python -m pytest -q tests/test_politics_bridge.py tests/test_politics.py tests/test_politics_parity.py` — 204 passed, 53 skipped in 2.40s.
- Batch 3 pre-fix regression control: `.venv/bin/python -m pytest -q tests/test_live_checkpoints.py::test_an_extended_resume_shows_and_saves_the_new_length` — 1 failed; the saved turn-12 checkpoint retained `num_turns == 12` instead of 16.
- Batch 3 focused: same command — 1 passed in 1.91s.
- Batch 3 surrounding: `.venv/bin/python -m pytest -q tests/test_live_checkpoints.py tests/test_run_checkpoint.py` — 33 passed in 21.10s.
- Batch 4 pre-fix regression control: viewer `bundleCodec.test.ts` own-`__proto__` case failed because the key disappeared and ordered output no longer matched.
- Batch 4 focused TS: `npx vitest run src/lib/__tests__/bundleCodec.test.ts src/lib/__tests__/bundleCodecFast.test.ts` from `viewer/` — 8 passed, including randomized fast/reference histories.
- Batch 4 Python parity and surrounding codec module: `.venv/bin/python -m pytest -q tests/test_bundle_codec.py` — 23 passed in 2.64s.
- Batch 4 viewer gates on Node 20.20.2: `npm run lint` passed; `npm run build` passed.
- Environment: locked `uv sync` on CPython 3.13.18. No Rust/native execution or fresh CI.

## Handoff checklist for Codex or Claude

1. Read `AGENTS.md`, `docs/DEVELOPMENT.md`, and this tracker before editing.
2. Confirm the branch head and read the latest commit ledger entry; do not reuse baseline qualification for changed source.
3. Continue with the first `[~]` item, otherwise the highest-priority `[ ]` item. Keep its recommended model/effort label when delegating.
4. Inspect existing neighboring tests before creating a new test file.
5. After each fix: run focused tests, inspect the complete diff, update task status/head/checks/next action here, and commit source plus tracker together when practical.
6. At handoff, leave no ambiguity about unrun native, viewer, full-suite, CI, determinism, or scientific gates.
