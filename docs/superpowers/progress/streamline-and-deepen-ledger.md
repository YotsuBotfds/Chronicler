# Streamline and deepen — integration ledger

The lead session's dated record of what was integrated on `claude/exciting-mayer-nolksw`, how each piece was reviewed, and which gates ran. Nothing here is merged to `main`. Opening PRs is the owner's call. Decisions are in [streamline-and-deepen-decisions.md](streamline-and-deepen-decisions.md) and statuses in [streamline-and-deepen.json](streamline-and-deepen.json).

**Process for every task**
- An implementer works on its own branch `sd/<task>` from the roadmap plan block, in an isolated worktree.
- An independent reviewer then re-runs the checks. Corrections and the pin transition get two reviewers, one for scope and behaviour and one for repository contracts.
- Up to two fix and re-review rounds follow.
- The lead merges only approved branches, with `--no-ff`, so each reviewed head stays in history. The lead then runs the gates below on the merged head.

**Shared identity baseline.** All nine `scripts/turn_speed_identity.py` cases were run from `4e8e76b7`, with the native extension built from that tree (SHA-256 `2125dfd7b5f9e2091ac70fad5f08709c14d2e553ab65691f7638d219e9c22641`). The run used Linux and the cloud container's Python 3.13.18.

## 2026-11-09 — integration 1 (R1/R2, first batch)

Merged, each approved by an independent reviewer with no blocker or major findings:

| Task | Reviewed head | Class | Notes |
|---|---|---|---|
| HYG-2 | `a00ada41` | config | `.gitignore` additions; `git ls-files -ci --exclude-standard` is empty |
| DEAD-3 | `48108143` | removal | Dead Rust helpers removed; five test-only functions put under `cfg(test)`; `cargo check` gives 0 warnings |
| FIX-6, FIX-13 | `a4e37a63` | fix | `settle_food_purchases` returns `Err` before any pool write; `+0.0`-normalised `total_cmp` comparators at the six sort and argmax sites |
| DEAD-2a | `a457aab5` | removal | Dead Python leaf helpers removed from 10 modules, with their tests |
| FIX-4, FIX-5, FIX-12, FIX-2 | `e54095ca` | fix + test | M53 record YAMLs moved to `docs/validation/m53/`, with a clean-load test; historiography and languages sidecars made atomic; FIX-2's audit claim was not reproduced (`CAPTURED` moves ownership, not stock), and a test pins the residual |
| FIX-9 | `686c1224` | fix | LLM client timeout (120 s), truncation counts, token and call budgets, batch poll deadline; narration only |

Gates on the merged head `e4557096`:
- `scripts/refactor_preflight.py --git-diff 4e8e76b`: no content pin and no recorded digest touched. The only `enforced` items are native-shard and oracle-chunk ownership of eight test modules that were edited in place, which is allowed.
- `scripts/run_python_oracle_checks.py --jobs 2`: PASS in 237.4 s. 76 chunks; 8,139 passed, 69 skipped, 0 failed. The 110 s limit is unchanged.
- `cargo test --locked`: every test binary passed (library 779 passed).
- The native extension was built fresh from `e4557096`. Its SHA-256, `97049985efadbee551631cb3166267f8c8cc403eb1c418b80db8ecafd2e7c6f8`, matches the FIX-6 implementer's independent build. `check_python_env.py --expect native` passes.
- `turn_speed_identity.py`, all 9 cases against the baseline: **399 files compared, 0 differences**. This covers the cases the FIX-6 review noted as unrun (off_s7, proc48_off_s7, scaled22k_s42 and scaled52k_s7).

Not run: viewer lanes (no viewer change in this batch), the 200-seed gate (no outcome change intended), and GitHub CI (no PR).

Integration notes:
- A disk-full error during workflow A stopped worktree creation for HYG-1/HYG-3, HYG-5/HYG-6, DEAD-2b, DEP-7 and the FIX-7 review. They were relaunched, and those agents now remove their venvs when they finish.
- FIX-7 is held back for the scope ruling recorded in the decision record.

## 2026-11-09 — integration 2 (tooling chain)

Merged `sd/HYG-8`, which carries the sequential tooling chain. Each step was approved by an independent reviewer with no blocker or major findings:

| Task | Reviewed head | Class | Notes |
|---|---|---|---|
| CON-8 | `35307b63` | tooling/test | Pins the frozen screen scripts by SHA-256; tests the runner's state files; the single-runner docs list the unspent cohorts |
| DEP-9 | `3bec6e62` | tooling | Seed-registry gate check (a `full` run off its gate range is refused), with the 14 existing reuses on an explicit allowlist; Holm-adjusted needs p-values, reported only; `best_of` documented as never a gate; `--hash-seed`, default `0`, so the default env is unchanged; `hashseed-sweep.yml`, kept off with `if: false` until COR-1; nightly `regression-smoke.yml` with a locally generated fixture; a real two-process batch test under hash seeds 0 and 1 |
| ENV-4 | `2dcc5227` | fix | Parallel batch workers start with `spawn` and `PYTHONHASHSEED=0` |
| HYG-8 | `05bf9a31` | ci | Five later-added native modules moved from shard 0 to shard 1. The timings are real per-module JUnit times from main Tests runs 42431233265, 42428257952 and 42417310582. Projected shard times are 628.5 s and 620.6 s, a 1.2 percent gap |

Gates on the merged head `78caa287`:
- Preflight against `4e8e76b` (70 paths): no content pin or digest touched outside in-place shard and chunk ownership.
- Oracle lane `--jobs 2`: PASS in 280.2 s. 76 chunks; 8,177 passed, 69 skipped, 0 failed.
- `pytest -m real_process tests/test_batch_parallel_real.py`: 1 passed.
- Focused new and shard tests (`test_native_ci_shards`, `test_seed_registry_check`, `test_validation_multiplicity`, `test_screen_frozen_evidence`): 243 passed.
- Identity for off_s42, off_s7, hybrid_s42 and proc48_off_s7, using the integration-1 native (no Rust change since): 144 files compared, 0 differences.

Not run here:
- `actionlint` (not installed) on the new workflows.
- The first dispatch of `regression-smoke.yml`, so runner minutes are unmeasured.
- The shard balance on CI (needs a PR).
- The 200-seed gate (no outcome change).

## 2026-11-09 — integration 3 (relaunched R1/R2 tasks)

Merged, each approved by an independent reviewer with no blocker or major findings:

| Task | Reviewed head | Class | Notes |
|---|---|---|---|
| HYG-1, HYG-3 | `e943525e` | docs | `docs/CONTINUATION.md` opens with `## Current status` and is under 100 lines; history moved byte-for-byte to `progress/continuation-history.md`; README, AGENTS and RECOVERY drop PR chains; new `tests/test_docs_status.py`; audits index; feature-options corrected (42 switches, 861 pairs, 0 refused, dated 2026-11-08) |
| HYG-5, HYG-6 | `aa9e6a2b` | tooling | `cloud_setup.sh` prints a failure summary and exits non-zero only under `CHRONICLER_SETUP_STRICT=1`; 15 doc-only scripts moved to `scripts/archive/` with smoke-manifest entries; `docs/workflows/README.md` index |
| DEAD-2b | `8b9973a6` | removal | Test-only narrative wrappers and five analytics extractors removed |
| FIX-7 | `e01bda87` | fix (CLI acceptance) | Saved-world prerequisite refusals with "pass --no-<x> to end it". Changed-mode and orphan-mode refusals dropped under the lead scope ruling (decision record) |
| DEP-7 | `751aae7c` | measurement (partial) | `household_access` metrics module, state, analytics section (absent unless present) and viewer reader. **Switch registration deferred:** it needs `batch_manifest.py` (enforced) and waits for PIN-1, so the module is not reachable from the CLI yet |

The lead added commit `abb97f5`. It keeps the four summarised CONTINUATION entries verbatim at the end of the history file, repoints two RECOVERY.md links (minor HYG-1 review findings), and points the status block at the decision record and this ledger. Merge conflicts were only the module-count assertion in `tests/test_native_ci_shards.py` (now 468), resolved by addition.

Gates on the merged head `8ba44078`:
- Preflight against `4e8e76b` (134 paths): no content pin or digest touched.
- Oracle lane `--jobs 2`: PASS in 176.8 s. 77 chunks; 8,192 passed, 69 skipped, 0 failed.
- Focused suite: 414 passed. It covers docs status, household access, livelihoods wiring, epidemic care, recovery-skills wiring, household retail, recovery crews, narrative, batch narration, analytics, check_python_env and the screen runner.
- `cloud_setup.sh` with `PATH=/nonexistent` and a scratch native venv: exit 1 with `CHRONICLER_SETUP_STRICT=1`, exit 0 without it.
- Identity, 7 cases (all but the two scaled ones), integration-1 native: 357 files compared, 0 differences.

Open owner questions from DEP-7 (no answer needed until registration):
- the weights of a joint food-and-care welfare primary;
- whether P2's denominator is all observed person-turns (as implemented) or retail person-turns only;
- whether "child shortfall share" means the children's share of total shortfall (as implemented).
